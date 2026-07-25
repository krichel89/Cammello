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
import os
import sys
import threading
import ctypes
from collections import OrderedDict

# Silence libtiff's console chatter. RAW files are TIFF containers, and
# libtiff prints "Unknown field with tag …", "Photometric tag is missing"
# and "Old-style JPEG compression support is not configured" for practically
# every CR2/DNG that Qt or Pillow touches. Harmless, but it floods the
# console. Both the warning AND the error handler are silenced; the DLL is
# looked up under the names used by Pillow, Qt and MSYS builds.
_TIFF_LIB_NAMES = ('libtiff.so.6', 'libtiff.so.5', 'libtiff-6.dll',
                   'libtiff-5.dll', 'tiff.dll', 'libtiff.dylib')
_tiff = None
for _name in _TIFF_LIB_NAMES:
    try:
        _tiff = ctypes.CDLL(_name)
        break
    except OSError:
        continue
if _tiff is not None:
    try:
        _TIFF_HANDLER = ctypes.CFUNCTYPE(None, ctypes.c_char_p,
                                         ctypes.c_char_p, ctypes.c_void_p)
        # Module-level references keep the callbacks alive for the process.
        _tiff_silence = _TIFF_HANDLER(lambda *_: None)
        _tiff.TIFFSetWarningHandler(_tiff_silence)
        _tiff.TIFFSetErrorHandler(_tiff_silence)
    except Exception:
        pass

from PyQt5.QtCore import (QObject, QRunnable, QThreadPool, pyqtSignal, Qt,
                          QSize, QBuffer, QIODevice, QByteArray)
from PyQt5.QtGui import QImage, QImageReader, QTransform

from . import edits

# numpy is not a declared dependency; it arrives with rawpy. Used only to
# speed up the live tone preview, with a pure-Python fallback below.
try:
    import numpy as _np
except ImportError:     # pragma: no cover - depends on the installation
    _np = None


try:
    import rawpy
    _RAWPY_ERROR = None
except Exception as e:
    rawpy = None
    _RAWPY_ERROR = str(e)

# 0.12.9: the pyexiv2 import that used to sit here is GONE. Nothing in this
# module used it (every function below advertises being pyexiv2-free), yet
# the import loaded the crash-prone native library into the GUI process at
# startup - against the 0.12.6 architecture and ~0.2 s of launch time.

# RAW extensions that must never be opened with pyexiv2 (exiv2 crashes on some,
# e.g. .RW2). Kept in sync with culling.RAW_EXTENSIONS; duplicated here to
# avoid an import cycle (culling imports heavy siblings).
_RAW_EXTS = {'.cr3', '.cr2', '.crw', '.nef', '.nrw', '.arw', '.raf',
             '.orf', '.rw2', '.dng', '.pef', '.srw', '.x3f'}

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


# Orientation cache (0.12.3): decode_preview runs once per cache level
# (thumb/screen/full) and used to re-read the orientation each time - for a
# RAW that meant a fresh rawpy.imread per level ON TOP of the one for the
# embedded JPEG, up to six opens per image. Orientation never changes during
# a session, so one read per path is enough. Filled by read_orientation AND
# by the combined RAW extraction below (which gets the flip for free from
# the same open that yields the embedded JPEG).
_ORIENT_CACHE = {}
_ORIENT_LOCK = threading.Lock()


def clear_orientation_cache():
    """Folder change / reload: forget cached orientations (paths may be
    reused by different files after a card re-import)."""
    with _ORIENT_LOCK:
        _ORIENT_CACHE.clear()


def _read_orientation_pillow(path):
    """EXIF orientation via Pillow - no pyexiv2. Pillow coexists with Qt
    without the crashes exiv2 causes, and is already a dependency."""
    from PIL import Image
    with Image.open(path) as im:
        exif = im.getexif()
    return exif.get(0x0112)          # 0x0112 = Orientation


# libraw flip code -> EXIF orientation (1/3/6/8). libraw: 0=none, 3=180,
# 5=90 CCW, 6=90 CW.
_FLIP_TO_ORIENTATION = {0: 1, 3: 3, 5: 8, 6: 6}


def _raw_orientation_via_rawpy(path):
    if rawpy is None:
        return 1
    with rawpy.imread(path) as raw:
        flip = getattr(raw.sizes, 'flip', 0)
    return _FLIP_TO_ORIENTATION.get(flip, 1)


def read_orientation(path):
    """EXIF orientation (1-8) of a file; 1 when unknown. Cached per path.

    pyexiv2 is never used here - exiv2 crashes in the scan process. JPEG
    orientation comes from Pillow, RAW orientation from libraw via rawpy.
    Both libraries coexist with Qt without the exiv2 crash.
    """
    with _ORIENT_LOCK:
        cached = _ORIENT_CACHE.get(path)
    if cached is not None:
        return cached
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext in _RAW_EXTS:
            orient = _raw_orientation_via_rawpy(path)
        else:
            val = _read_orientation_pillow(path)
            orient = int(val) if val else 1
    except Exception:
        orient = 1
    with _ORIENT_LOCK:
        _ORIENT_CACHE[path] = orient
    return orient


def _raw_exif_summary(path):
    """EXIF summary for a RAW file, without pyexiv2. Exposure data comes from
    libraw via rawpy (raw.other: aperture/focal/shutter/ISO/timestamp,
    raw.lens: lens make+model) - available for every format libraw decodes,
    CR3 and RW2 included. The camera name is not exposed by rawpy; if the
    pure-Python exifread package is installed it is filled in from there
    (works for TIFF-based RAWs; CR3 support in exifread is unverified), and
    simply omitted otherwise."""
    out = {}
    try:
        with rawpy.imread(path) as raw:
            o = raw.other
            lens = raw.lens
            if getattr(o, 'focal_length', 0):
                out['focal'] = f'{float(o.focal_length):g} mm'
            if getattr(o, 'aperture', 0):
                out['aperture'] = f'f/{float(o.aperture):g}'
            sp = float(getattr(o, 'shutter_speed', 0) or 0)
            if sp > 0:
                out['shutter'] = (f'1/{round(1 / sp)} s' if sp < 1
                                  else f'{sp:g} s')
            if getattr(o, 'iso_speed', 0):
                out['iso'] = f'ISO {int(o.iso_speed)}'
            ts = int(getattr(o, 'timestamp', 0) or 0)
            if ts > 0:
                import datetime
                out['captured'] = datetime.datetime.fromtimestamp(
                    ts).strftime('%Y:%m:%d %H:%M:%S')
            lmodel = (getattr(lens, 'model', '') or '').strip()
            lmake = (getattr(lens, 'make', '') or '').strip()
            if lmodel:
                out['lens'] = (lmodel if lmodel.lower().startswith(
                    lmake.lower()) or not lmake else f'{lmake} {lmodel}')
    except Exception:
        return {}
    # Camera make/model via exifread, when available (optional, pure Python).
    try:
        import exifread
        with open(path, 'rb') as f:
            tags = exifread.process_file(f, details=False)
        make = str(tags.get('Image Make', '') or '').strip()
        model = str(tags.get('Image Model', '') or '').strip()
        if model:
            out['camera'] = model if model.lower().startswith(make.lower()) \
                else f'{make} {model}'.strip()
    except Exception:
        pass
    return out


def read_exif_summary(path):
    """Small EXIF summary for the culling info overlay, without pyexiv2.
    JPEGs are read via Pillow; RAW files via libraw/rawpy (plus exifread for
    the camera name when installed) - see _raw_exif_summary. Returns a dict
    with any of the keys camera, lens, focal, aperture, shutter, iso,
    captured; empty dict when nothing is readable."""
    if os.path.splitext(path)[1].lower() in _RAW_EXTS:
        return _raw_exif_summary(path)
    try:
        from PIL import Image
        with Image.open(path) as im:
            exif = im.getexif()
            ifd = exif.get_ifd(0x8769)   # Exif sub-IFD
    except Exception:
        return {}
    out = {}
    make = str(exif.get(0x010F, '')).strip()
    model = str(exif.get(0x0110, '')).strip()
    if model:
        # Canon writes the make into the model already; avoid "Canon Canon".
        out['camera'] = model if model.lower().startswith(make.lower()) \
            else f'{make} {model}'.strip()
    lens = str(ifd.get(0xA434, '')).strip()
    if lens:
        out['lens'] = lens
    fl = ifd.get(0x920A)
    if fl:
        try:
            out['focal'] = f'{float(fl):g} mm'
        except (TypeError, ValueError):
            pass
    fn = ifd.get(0x829D)
    if fn:
        try:
            out['aperture'] = f'f/{float(fn):g}'
        except (TypeError, ValueError):
            pass
    et = ifd.get(0x829A)
    if et:
        try:
            et = float(et)
            out['shutter'] = (f'1/{round(1 / et)} s' if 0 < et < 1
                              else f'{et:g} s')
        except (TypeError, ValueError, ZeroDivisionError):
            pass
    iso = ifd.get(0x8827)
    if iso:
        if isinstance(iso, (tuple, list)):
            iso = iso[0] if iso else None
        if iso:
            out['iso'] = f'ISO {iso}'
    dt = str(ifd.get(0x9003, '')).strip()      # DateTimeOriginal
    if dt:
        out['captured'] = dt
    return out


def _apply_orientation(qimage, orientation):
    rot, mirror = _ORIENTATION.get(orientation, (0, False))
    if mirror:
        qimage = qimage.mirrored(True, False)
    if rot:
        qimage = qimage.transformed(QTransform().rotate(rot),
                                    Qt.SmoothTransformation)
    return qimage


def apply_tone(qimage, wb=None, ev=0.0):
    """Return `qimage` with white balance and exposure applied (0.14.2).

    This is the ON-SCREEN half of what edits.render_edited() does on
    export: the same LUTs from edits.py, so what the culling view shows is
    what the uploaded copy will look like.

    Two paths, both writing INTO a private copy of the image buffer so no
    intermediate copies of several megabytes are made:
      * numpy, when available (it ships with rawpy) - table lookup per
        channel, the fast path;
      * bytes.translate() on channel slices otherwise - all in C too, but
        it copies each slice; noticeably slower on large previews, which
        is why the caller debounces.

    Returns the input unchanged when there is nothing to do or the buffer
    has an unexpected layout; a preview is never worth a crash.
    """
    if qimage is None or qimage.isNull() or (not wb and not ev):
        return qimage
    try:
        img = qimage.convertToFormat(QImage.Format_RGB32)
        if img is qimage or img.constBits() == qimage.constBits():
            img = img.copy()             # never write into the caller's image
        w = img.width()
        if img.bytesPerLine() != w * 4:  # padded rows: not our layout
            return qimage
        r_gain, g_gain, b_gain = wb if wb else (1.0, 1.0, 1.0)
        r_lut = edits._combined_lut(r_gain, ev)
        g_lut = edits._combined_lut(g_gain, ev)
        b_lut = edits._combined_lut(b_gain, ev)
        # Format_RGB32 is 0xffRRGGBB as a 32-bit int, so the byte order in
        # memory follows the machine: BGRA on little-endian.
        if sys.byteorder == 'little':
            per_offset = {0: b_lut, 1: g_lut, 2: r_lut}
        else:
            per_offset = {1: r_lut, 2: g_lut, 3: b_lut}
        ptr = img.bits()
        ptr.setsize(img.byteCount())
        if _np is not None:
            arr = _np.frombuffer(ptr, dtype=_np.uint8)
            for off, lut in per_offset.items():
                table = _np.frombuffer(bytes(lut), dtype=_np.uint8)
                arr[off::4] = table[arr[off::4]]
        else:
            buf = bytearray(ptr)
            for off, lut in per_offset.items():
                buf[off::4] = bytes(buf[off::4]).translate(bytes(lut))
            ptr[:] = bytes(buf)
        return img
    except Exception:
        return qimage


def _extract_thumb_raw(path):
    """One rawpy open yields BOTH the embedded thumb and the orientation
    (libraw flip) - the flip is free once the file is open, and caching it
    saves the extra rawpy.imread that read_orientation would need per cache
    level. Returns the rawpy Thumbnail namedtuple (its .data/.format are
    plain bytes/enum, safe to hand back across threads)."""
    with rawpy.imread(path) as raw:
        flip = getattr(raw.sizes, 'flip', 0)
        thumb = raw.extract_thumb()
    with _ORIENT_LOCK:
        _ORIENT_CACHE[path] = _FLIP_TO_ORIENTATION.get(flip, 1)
    return thumb


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
    # rawpy runs directly on the calling pool thread, in parallel. It was
    # temporarily serialized through native_exec while rawpy was a crash
    # suspect; the actual culprit turned out to be pyexiv2 on the scan path
    # (now removed entirely), and rawpy's docs state separate RawPy instances
    # are safe to use concurrently - which is exactly what the pool does.
    # Parallel RAW thumb extraction restores the pre-0.11.1 scan speed.
    thumb = _extract_thumb_raw(path)
    if thumb.format == rawpy.ThumbFormat.JPEG:
        return thumb.data
    # Bitmap fallback: encode to JPEG once so the rest of the pipeline is
    # uniform. (Untested against a real bitmap-thumb RAW - none available.)
    h, w = thumb.data.shape[:2]
    qimg = QImage(thumb.data.tobytes(), w, h, 3 * w, QImage.Format_RGB888)
    from PyQt5.QtCore import QBuffer, QIODevice
    qbuf = QBuffer()
    qbuf.open(QIODevice.WriteOnly)
    qimg.save(qbuf, 'JPG', 92)
    return bytes(qbuf.data())


def decode_preview(path, orientation=None, max_edge=None):
    """QImage of the preview, orientation applied, optionally scaled so the
    long edge is max_edge. Runs on the calling (pool) thread.

    Everything here runs in parallel across the pool: the Qt image decode
    (QImageReader.read), Pillow orientation reads, and rawpy thumb extraction
    (separate RawPy instances are concurrency-safe per its docs). pyexiv2 is
    not used anywhere on this read path - see the crash post-mortem in
    culling._read_rating_label_text.
    """
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
        clear_orientation_cache()       # paths may point at new files now
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
