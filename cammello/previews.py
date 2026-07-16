"""Preview pipeline: extraction, two-level cache, prioritized prefetch.

The speed strategy (verified on real EOS R6 CR3s, 2026-07-13: ~75 ms warm for
the whole chain, embedded preview is a FULL-RESOLUTION JPEG):
  * never decode the RAW - extract the camera-rendered embedded JPEG (rawpy),
  * for RAW+JPEG pairs display the JPEG file directly (even cheaper),
  * decode in a QThreadPool, prefetch in the browsing direction,
  * two cache levels: THUMB (256 px, all ~3000 images of an SD card fit in
    ~250 MB RAM) and SCREEN (display resolution, small LRU window).
100%-zoom uses the SCREEN/full image - the embedded preview is full-size, so
no RAW decode is needed even then.

QImage (not QPixmap) is used throughout: QImage is safe to create in worker
threads; the viewer converts to QPixmap on the GUI thread.

rawpy is OPTIONAL: without it, RAW-only items cannot be previewed (JPEGs and
pairs still work); previews.raw_available() tells the UI.
"""
import io
import os
import threading
import time
from collections import OrderedDict

from PyQt5.QtCore import (QObject, QRunnable, QThreadPool, pyqtSignal, Qt,
                          QSize, QBuffer, QIODevice, QByteArray)
from PyQt5.QtGui import QImage, QImageReader, QTransform

from . import native_exec

try:
    import rawpy
    _RAWPY_ERROR = None
except Exception as e:
    rawpy = None
    _RAWPY_ERROR = str(e)

try:
    import pyexiv2
except Exception:
    pyexiv2 = None

THUMB_EDGE = 256          # long edge of the thumbnail level

# EXIF orientation -> (rotation degrees clockwise, mirror horizontally).
# The embedded preview JPEG usually carries no EXIF of its own, so the
# orientation of the CONTAINER file must be applied to it.
_ORIENTATION = {
    1: (0, False), 2: (0, True), 3: (180, False), 4: (180, True),
    5: (90, True), 6: (90, False), 7: (270, True), 8: (270, False),
}


def raw_available():
    return rawpy is not None


def raw_unavailable_reason():
    return _RAWPY_ERROR or 'rawpy is not installed'


def _read_orientation_raw(path):
    img = pyexiv2.Image(path)
    try:
        return (img.read_exif() or {}).get('Exif.Image.Orientation')
    finally:
        img.close()


def read_orientation(path):
    """EXIF orientation (1-8) of a file; 1 when unknown."""
    if pyexiv2 is None:
        return 1
    try:
        val = native_exec.run(_read_orientation_raw, path)
        return int(val) if val else 1
    except Exception:
        return 1


def _apply_orientation(qimage, orientation):
    rot, mirror = _ORIENTATION.get(orientation, (0, False))
    if mirror:
        qimage = qimage.mirrored(True, False)
    if rot:
        qimage = qimage.transformed(QTransform().rotate(rot),
                                    Qt.SmoothTransformation)
    return qimage


def _extract_thumb_raw(path):
    """Runs on the native-imaging thread; returns a rawpy Thumbnail namedtuple
    (its .data/.format are plain bytes/enum, safe to hand back across threads)."""
    with rawpy.imread(path) as raw:
        return raw.extract_thumb()


def extract_preview_bytes(path):
    """JPEG bytes of the best available preview.

    JPEG file -> the file itself. RAW -> embedded preview via rawpy. A bitmap
    thumb (rare) is converted to JPEG via QImage. Raises on failure."""
    ext = os.path.splitext(path)[1].lower()
    if ext in ('.jpg', '.jpeg'):
        with open(path, 'rb') as f:
            return f.read()
    if rawpy is None:
        raise RuntimeError(raw_unavailable_reason())
    # rawpy (libraw) runs on the SAME single native-imaging thread as
    # pyexiv2 (see native_exec): earlier Windows crash logs showed access
    # violations with several rawpy.imread threads active at once. The Qt
    # decode below stays parallel across the pool; only this short native
    # thumb extraction serializes onto the dedicated thread.
    thumb = native_exec.run(_extract_thumb_raw, path)
    if thumb.format == rawpy.ThumbFormat.JPEG:
        return thumb.data
    # Bitmap fallback: encode to JPEG once so the rest of the pipeline is
    # uniform. (Untested against a real bitmap-thumb RAW - none available.)
    h, w = thumb.data.shape[:2]
    qimg = QImage(thumb.data.tobytes(), w, h, 3 * w, QImage.Format_RGB888)
    buf = io.BytesIO()
    from PyQt5.QtCore import QBuffer, QIODevice
    qbuf = QBuffer()
    qbuf.open(QIODevice.WriteOnly)
    qimg.save(qbuf, 'JPG', 92)
    return bytes(qbuf.data())


def decode_preview(path, orientation=None, max_edge=None):
    """QImage of the preview, orientation applied, optionally scaled so the
    long edge is max_edge. Runs fine in a worker thread.

    Scaling happens INSIDE the decoder (QImageReader.setScaledSize): for JPEG
    libjpeg then decodes at a reduced DCT scale instead of producing 20
    megapixels that are thrown away right after. This was the 'reading JPEGs
    makes the program extremely slow' bug: a 256-px thumb of an EOS R6 JPEG
    cost a full-resolution decode, times 3000 files, times 8 threads - the GUI
    starved. Scaled decode is roughly an order of magnitude cheaper."""
    ext = os.path.splitext(path)[1].lower()
    if ext in ('.jpg', '.jpeg'):
        reader = QImageReader(path)
        buf = None
    else:
        data = extract_preview_bytes(path)
        buf = QBuffer()
        buf.setData(QByteArray(data))
        buf.open(QIODevice.ReadOnly)
        reader = QImageReader(buf)
    reader.setAutoTransform(False)      # orientation is applied below, once
    if max_edge:
        size = reader.size()            # header only, no decode
        if size.isValid() and max(size.width(), size.height()) > max_edge:
            reader.setScaledSize(size.scaled(max_edge, max_edge,
                                             Qt.KeepAspectRatio))
    qimg = reader.read()
    if buf is not None:
        buf.close()
    if qimg.isNull():
        raise RuntimeError(f'preview of "{os.path.basename(path)}" did not '
                           f'decode: {reader.errorString()}')
    if orientation is None:
        orientation = read_orientation(path)
    return _apply_orientation(qimg, orientation)


# ── Cache ────────────────────────────────────────────────────────────────────

class PreviewCache:
    """Byte-budgeted LRU per level ('thumb' / 'screen'). Thread-safe."""

    def __init__(self, thumb_budget=320 * 1024 * 1024,
                 screen_budget=1024 * 1024 * 1024,
                 full_budget=512 * 1024 * 1024):
        # 'full' holds the unscaled preview (EOS R6: ~80 MB as QImage) for the
        # 100% zoom of the CURRENT image only - the small budget keeps just a
        # couple of them around.
        self._levels = {
            'thumb': (OrderedDict(), [0], thumb_budget),
            'screen': (OrderedDict(), [0], screen_budget),
            'full': (OrderedDict(), [0], full_budget),
        }
        self._lock = threading.Lock()

    def get(self, level, key):
        store, _size, _budget = self._levels[level]
        with self._lock:
            img = store.get(key)
            if img is not None:
                store.move_to_end(key)
            return img

    def put(self, level, key, qimage):
        store, size, budget = self._levels[level]
        nbytes = qimage.sizeInBytes()
        with self._lock:
            old = store.pop(key, None)
            if old is not None:
                size[0] -= old.sizeInBytes()
            store[key] = qimage
            size[0] += nbytes
            while size[0] > budget and len(store) > 1:
                _k, evicted = store.popitem(last=False)
                size[0] -= evicted.sizeInBytes()

    def stats(self):
        with self._lock:
            return {lvl: (len(st), sz[0])
                    for lvl, (st, sz, _b) in self._levels.items()}


# ── Prioritized loader ───────────────────────────────────────────────────────

class _LoaderSignals(QObject):
    loaded = pyqtSignal(str, str)          # key (path), level
    failed = pyqtSignal(str, str)          # key, error text


class _LoadJob(QRunnable):
    def __init__(self, loader, key, path, level, max_edge, generation):
        super().__init__()
        self.loader = loader
        self.key = key
        self.path = path
        self.level = level
        self.max_edge = max_edge
        self.generation = generation

    def run(self):
        ld = self.loader
        if self.generation != ld.generation:
            ld._done(self.key, self.level)
            return                          # stale prefetch: folder changed
        if ld.cache.get(self.level, self.key) is not None:
            ld._done(self.key, self.level)
            ld.signals.loaded.emit(self.key, self.level)
            return
        try:
            img = decode_preview(self.path, max_edge=self.max_edge)
        except Exception as e:
            ld._done(self.key, self.level)
            ld.signals.failed.emit(self.key, str(e))
            return
        ld.cache.put(self.level, self.key, img)
        ld._done(self.key, self.level)
        ld.signals.loaded.emit(self.key, self.level)


class PreviewLoader:
    """QThreadPool front-end with priorities and a generation counter.

    request(..., priority): higher runs earlier (current image > prefetch >
    filmstrip thumbs). new_generation() invalidates queued jobs on folder
    change. prefetch_around() implements the browsing-direction strategy."""

    P_CURRENT, P_PREFETCH, P_THUMBS = 100, 50, 10

    def __init__(self, cache=None, screen_edge=2560, threads=None):
        self.cache = cache or PreviewCache()
        self.signals = _LoaderSignals()
        self.screen_edge = screen_edge
        self.generation = 0
        self._pool = QThreadPool()
        if threads:
            self._pool.setMaxThreadCount(threads)
        self._inflight = set()
        self._lock = threading.Lock()

    def new_generation(self):
        self.generation += 1
        with self._lock:
            self._inflight.clear()

    def _done(self, key, level):
        with self._lock:
            self._inflight.discard((key, level))

    def request(self, path, level='screen', priority=P_CURRENT):
        key = path
        if self.cache.get(level, key) is not None:
            self.signals.loaded.emit(key, level)
            return
        with self._lock:
            if (key, level) in self._inflight:
                return
            self._inflight.add((key, level))
        max_edge = {'thumb': THUMB_EDGE, 'screen': self.screen_edge,
                    'full': None}[level]
        self._pool.start(_LoadJob(self, key, path, level, max_edge,
                                  self.generation), priority)

    def prefetch_around(self, paths, index, direction=1,
                        ahead=8, behind=2):
        """Queue the neighbourhood of `index`: `ahead` images in the browsing
        direction, `behind` against it."""
        n = len(paths)
        order = ([index + direction * i for i in range(1, ahead + 1)] +
                 [index - direction * i for i in range(1, behind + 1)])
        for j in order:
            if 0 <= j < n:
                self.request(paths[j], 'screen', self.P_PREFETCH)

    def wait_idle(self, msecs=30000):
        return self._pool.waitForDone(msecs)
