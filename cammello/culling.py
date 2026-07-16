"""Culling data model: folder scan, RAW+JPEG pairing, ratings, color labels,
XMP/sidecar I/O and filtering. NO GUI in here - everything is headless
testable. The viewer (Phase 1b) sits on top of this.

Storage follows the concept document:
  * ratings and labels are standard XMP (Xmp.xmp.Rating / Xmp.xmp.Label),
  * RAW files are NEVER touched - a .xmp sidecar next to the RAW carries the
    metadata (existing Lightroom sidecars are amended, not replaced),
  * JPEGs get the XMP embedded,
  * RAW+JPEG pairs are one item; writes go to sidecar AND JPEG so both stay
    consistent,
  * reject is Rating = -1 (Lightroom/Bridge convention),
  * color labels are localized TEXT; reading matches against all configured
    label sets, writing uses the active set.
"""
import os
import queue
import re
import threading

from .constants import *
from . import iptc as iptc_mod        # for available(); pyexiv2 access below
from . import native_exec

try:
    import pyexiv2
except Exception:
    pyexiv2 = None

# ── File types ───────────────────────────────────────────────────────────────

RAW_EXTENSIONS = {'.cr3', '.cr2', '.crw', '.nef', '.nrw', '.arw', '.raf',
                  '.orf', '.rw2', '.dng', '.pef', '.srw', '.x3f'}
JPEG_EXTENSIONS = {'.jpg', '.jpeg'}

# ── Color label sets ─────────────────────────────────────────────────────────
#
# Lightroom stores the label as text and the text depends on the UI language /
# the active "color label set". A string outside the active set shows up as a
# white marker in LR, so writing must use the set the user's LR expects.
LABEL_SETS = {
    'en': ['Red', 'Yellow', 'Green', 'Blue', 'Purple'],
    'de': ['Rot', 'Gelb', 'Grün', 'Blau', 'Lila'],
}
LABEL_COLORS = ['#d33', '#dc3', '#3a3', '#36c', '#93c']   # UI swatches, index-aligned


def label_text(index, set_name):
    """Label text for color index 0-4 in the given set ('' for None/out of range)."""
    labels = LABEL_SETS.get(set_name) or []
    if index is None or not (0 <= index < len(labels)):
        return ''
    return labels[index]


def label_index(text, extra_sets=None):
    """Color index 0-4 for a label text, matched case-insensitively against
    ALL configured sets (so a German 'Rot' is recognized while the active set
    is English). Returns None for unknown/custom labels - the caller keeps the
    original text so nothing is destroyed on write."""
    if not text:
        return None
    t = text.strip().casefold()
    sets = dict(LABEL_SETS)
    if extra_sets:
        sets.update(extra_sets)
    for labels in sets.values():
        for i, name in enumerate(labels):
            if name.casefold() == t:
                return i
    return None


# ── Items and folder scan ────────────────────────────────────────────────────

class CullItem:
    """One picture = a RAW file, a JPEG, or a RAW+JPEG pair (same stem)."""

    __slots__ = ('stem', 'raw_path', 'jpg_path', 'rating', 'label',
                 'in_table')

    def __init__(self, stem, raw_path=None, jpg_path=None):
        self.stem = stem
        self.raw_path = raw_path
        self.jpg_path = jpg_path
        self.rating = 0          # 0-5, -1 = reject
        self.label = ''          # raw label text as stored in XMP
        self.in_table = False    # badge: already in the upload table

    @property
    def display_path(self):
        """The file whose pixels are shown: the JPEG of a pair (it is already
        a full-size JPEG - cheaper than extracting the RAW preview)."""
        return self.jpg_path or self.raw_path

    @property
    def is_pair(self):
        return bool(self.raw_path and self.jpg_path)

    @property
    def sidecar_path(self):
        if not self.raw_path:
            return None
        return os.path.splitext(self.raw_path)[0] + '.xmp'

    @property
    def label_color_index(self):
        return label_index(self.label)

    def __repr__(self):
        return (f'CullItem({self.stem!r}, raw={bool(self.raw_path)}, '
                f'jpg={bool(self.jpg_path)}, rating={self.rating}, '
                f'label={self.label!r})')


def scan_folder(folder):
    """Scan one folder (not recursive - SD card folders are flat) and pair
    RAW+JPEG by identical stem (case-insensitive). Returns CullItems sorted by
    stem. Filenames only; no file is opened."""
    items = {}
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return []
    for name in names:
        stem, ext = os.path.splitext(name)
        ext = ext.lower()
        if ext not in RAW_EXTENSIONS and ext not in JPEG_EXTENSIONS:
            continue
        path = os.path.join(folder, name)
        key = stem.casefold()
        item = items.get(key)
        if item is None:
            item = items[key] = CullItem(stem)
        if ext in RAW_EXTENSIONS:
            item.raw_path = path
        else:
            item.jpg_path = path
    return [items[k] for k in sorted(items)]


# ── XMP I/O ──────────────────────────────────────────────────────────────────

_XMP_SKELETON = ('<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
                 '<x:xmpmeta xmlns:x="adobe:ns:meta/">'
                 '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
                 '<rdf:Description rdf:about=""/></rdf:RDF></x:xmpmeta>\n'
                 '<?xpacket end="w"?>')


def _read_xmp_raw(path):
    img = pyexiv2.Image(path)
    try:
        return img.read_xmp() or {}
    finally:
        img.close()


def _read_xmp_from(path):
    # All pyexiv2 access is confined to the single native-imaging thread
    # (see native_exec): exiv2/XMP is not thread-safe, and a lock alone did
    # not prevent the Windows access-violation crash.
    return native_exec.run(_read_xmp_raw, path)


def _write_xmp_raw(path, payload):
    img = pyexiv2.Image(path)
    try:
        img.modify_xmp(payload)
    finally:
        img.close()


def _write_xmp_to(path, payload):
    native_exec.run(_write_xmp_raw, path, payload)


def read_item_metadata(item):
    """Fill item.rating / item.label from disk.

    Precedence: sidecar (LR's truth for RAWs) > embedded XMP in the RAW
    (e.g. the in-camera rating of an EOS R6) > embedded XMP in the JPEG.
    """
    if pyexiv2 is None:
        raise RuntimeError('pyexiv2 is not installed')
    sources = []
    sc = item.sidecar_path
    if sc and os.path.exists(sc):
        sources.append(sc)
    if item.raw_path:
        sources.append(item.raw_path)
    if item.jpg_path:
        sources.append(item.jpg_path)
    for src in sources:
        try:
            xmp = _read_xmp_from(src)
        except Exception:
            continue
        rating = xmp.get('Xmp.xmp.Rating')
        label = xmp.get('Xmp.xmp.Label')
        if rating is None and label is None:
            continue
        try:
            item.rating = int(float(rating)) if rating is not None else 0
        except (TypeError, ValueError):
            item.rating = 0
        item.label = label or ''
        return item
    item.rating = 0
    item.label = ''
    return item


def write_item_metadata(item):
    """Write rating/label: sidecar for the RAW (created if missing, existing
    ones amended), embedded for the JPEG. The RAW file itself is not touched.
    Returns the list of paths written."""
    if pyexiv2 is None:
        raise RuntimeError('pyexiv2 is not installed')
    payload = {
        'Xmp.xmp.Rating': str(item.rating) if item.rating else None,
        'Xmp.xmp.Label': item.label if item.label else None,
    }
    # Rating 0 with no label: write explicit deletions so a previous value
    # (from LR or the camera) is cleared rather than silently kept.
    written = []
    sc = item.sidecar_path
    if sc:
        if not os.path.exists(sc):
            with open(sc, 'w', encoding='utf-8') as f:
                f.write(_XMP_SKELETON)
        _write_xmp_to(sc, payload)
        written.append(sc)
    if item.jpg_path:
        _write_xmp_to(item.jpg_path, payload)
        written.append(item.jpg_path)
    return written


# ── Write-behind queue ───────────────────────────────────────────────────────

class WriteBehind:
    """Coalescing background writer: the keyboard never waits for disk I/O.

    enqueue(item) marks the item dirty; a worker thread writes the LATEST
    state per item (rapid re-rating of the same picture collapses into one
    write). flush() blocks until everything queued so far is on disk - used
    on folder change, app exit and in tests. Errors land in .errors and the
    logger; they must never crash the worker."""

    def __init__(self, logger=None):
        self._pending = {}                 # id(item) -> item (latest state)
        self._lock = threading.Lock()
        self._kick = queue.Queue()
        self._idle = threading.Event()
        self._idle.set()
        self._stop = False
        self.errors = []
        self.log = logger
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def enqueue(self, item):
        with self._lock:
            self._pending[id(item)] = item
            self._idle.clear()
        self._kick.put(None)

    def flush(self, timeout=30):
        return self._idle.wait(timeout)

    def stop(self):
        self.flush()
        self._stop = True
        self._kick.put(None)
        self._thread.join(timeout=5)

    def _run(self):
        while True:
            self._kick.get()
            if self._stop:
                return
            while True:
                with self._lock:
                    if not self._pending:
                        self._idle.set()
                        break
                    _key, item = self._pending.popitem()
                try:
                    write_item_metadata(item)
                except Exception as e:
                    self.errors.append((item.stem, str(e)))
                    if self.log:
                        self.log.error('XMP write failed for "%s": %s',
                                       item.stem, e, exc_info=True)


# ── Filtering ────────────────────────────────────────────────────────────────

def filter_items(items, min_rating=0, exclude_rejects=True, label_indices=None):
    """label_indices: None = all labels, else a set of color indices 0-4;
    include -1 in the set to also match items without any label."""
    out = []
    for it in items:
        if it.rating == -1:
            # A reject has no meaningful star count: the rejects switch alone
            # decides, the min_rating filter does not apply to it.
            if exclude_rejects:
                continue
        elif it.rating < min_rating:
            continue
        if label_indices is not None:
            idx = it.label_color_index
            key = -1 if idx is None else idx
            if key not in label_indices:
                continue
        out.append(it)
    return out
