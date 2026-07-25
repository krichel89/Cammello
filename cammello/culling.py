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
import logging
import os
import queue
import re
import threading

from .constants import *

# NOTE (0.12.6): this module no longer imports pyexiv2 at all. Ratings and
# labels are read as text and written as text (sidecar XML / JPEG APP1
# segment), so exiv2 cannot take the culling workflow down.

# ── XMP rating/label reading WITHOUT pyexiv2 ────────────────────────────────
#
# The folder scan must never call pyexiv2. exiv2 crashes hard (uncatchable
# Windows access violation) somewhere in the scan - not reproducible in
# isolation (pyexiv2 alone, Qt alone, and pyexiv2+Qt interleaved single-thread
# all pass), so the trigger is some combination we could not pin down. Rather
# than keep chasing it, the read path avoids the native library entirely:
# rating (xmp:Rating) and colour label (xmp:Label) are plain XMP, which is XML
# text. In a sidecar the whole file is that XML; in a JPEG it sits in an APP1
# XMP packet as UTF-8 text. Both are found by locating the <x:xmpmeta> block in
# the raw bytes and matching the two tags (attribute form, as Photo Mechanic /
# Lightroom write, and element form). Writing is pure Python too (write_item_
# metadata), but that is user-triggered and one file at a time, not the scan.

_XMP_META_START = b'<x:xmpmeta'
_XMP_META_END = b'</x:xmpmeta>'
_RE_RATING_ATTR = re.compile(r'xmp:Rating\s*=\s*"(-?\d+(?:\.\d+)?)"')
_RE_RATING_ELEM = re.compile(r'<xmp:Rating>\s*(-?\d+(?:\.\d+)?)\s*</xmp:Rating>')
_RE_LABEL_ATTR = re.compile(r'xmp:Label\s*=\s*"([^"]*)"')
_RE_LABEL_ELEM = re.compile(r'<xmp:Label>\s*([^<]*?)\s*</xmp:Label>')


# The XMP APP1 packet of a JPEG sits in the header segments, i.e. before the
# compressed image data; a bounded read of the file head finds it without
# pulling a 20+ MB camera JPEG fully into memory (the metadata scan of a
# 3000-image card was dominated by exactly that I/O).
#
# 0.12.9: the head read is a LADDER, not one 4 MB gulp. A JPEG APP1 segment
# is at most 64 KiB, and cameras write EXIF + XMP within the first ~100 KiB,
# so the first rung (192 KiB) settles virtually every file; measured on
# 20 MB JPEGs the scan read dropped ~20x. Across a 3000-image card that is
# the difference between ~0.6 GB and ~12 GB pulled off the card reader.
# The 4 MiB rung and the final full read keep correctness unchanged for
# exotic layouts (XMP behind an oversized MPF/preview block, sidecars are
# settled by rung one anyway).
_XMP_HEAD_LADDER = (192 * 1024, 4 * 1024 * 1024)
# Backwards-compatible alias (tests referenced the old name).
_XMP_HEAD_BYTES = _XMP_HEAD_LADDER[-1]


def _xmp_block_complete(data):
    return _XMP_META_START in data and _XMP_META_END in data


def _read_rating_label_text(path):
    """Return (rating_str_or_None, label_str_or_None) by reading the XMP as
    text. No native library. Works for .xmp sidecars and for JPEGs with an
    embedded XMP packet. Returns (None, None) if the file has no XMP or cannot
    be read."""
    try:
        with open(path, 'rb') as f:
            requested = _XMP_HEAD_LADDER[0]
            data = f.read(requested)
            for rung in _XMP_HEAD_LADDER[1:]:
                # Stop climbing when the file is exhausted (the previous read
                # came back short) or the block is already in hand.
                if len(data) < requested or _xmp_block_complete(data):
                    break
                data += f.read(rung - len(data))
                requested = rung
            if (len(data) == _XMP_HEAD_LADDER[-1]
                    and not _xmp_block_complete(data)):
                data += f.read()   # rare: XMP starts or ends beyond the head
    except OSError:
        return None, None
    i = data.find(_XMP_META_START)
    if i < 0:
        return None, None
    j = data.find(_XMP_META_END, i)
    block = data[i:j + len(_XMP_META_END)] if j >= 0 else data[i:]
    text = block.decode('utf-8', 'replace')
    rating = None
    m = _RE_RATING_ATTR.search(text) or _RE_RATING_ELEM.search(text)
    if m:
        rating = m.group(1)
    label = None
    m = _RE_LABEL_ATTR.search(text) or _RE_LABEL_ELEM.search(text)
    if m:
        label = m.group(1)
    return rating, label

# ── Pure-Python XMP sidecar writer (0.12.6 fix) ──────────────────────────────
#
# pyexiv2 crashes on Windows/Python 3.14 even when opening a harmless .xmp
# file (confirmed 2026-07-18: three consecutive NativeCrash on sidecar
# writes). Since a sidecar is plain XML text — not a binary image container —
# we can write it without any native library. Rating and Label are the only
# two fields Cammello's culling module writes; both live in the xmp: namespace
# and are stored as attributes on the rdf:Description element (the compact
# form that Lightroom, Photo Mechanic and darktable all read).

_NS_XMP = 'xmlns:xmp="http://ns.adobe.com/xap/1.0/"'

_RE_XMP_NS = re.compile(r'xmlns:xmp\s*=\s*"[^"]*"')
_RE_DESC_OPEN = re.compile(r'(<rdf:Description\b.*?)(/>|>)', re.S)


def _patch_xmp_text(text, rating, label):
    """Return the XMP packet with xmp:Rating / xmp:Label set (or removed).

    Shared by the sidecar and the embedded-JPEG writer. Everything else in
    the packet - whatever Lightroom, Photo Mechanic or the camera wrote -
    is preserved untouched.
    """
    # Ensure the xmp namespace is declared on rdf:Description.
    if 'xmlns:xmp=' not in text:
        text = _RE_DESC_OPEN.sub(lambda m: m.group(1) + ' ' + _NS_XMP + m.group(2), text, count=1)

    # Update or insert the xmp:Rating attribute.
    if rating is not None and rating != 0:
        val = str(int(rating))
        if 'xmp:Rating=' in text:
            text = _RE_RATING_ATTR.sub(f'xmp:Rating="{val}"', text)
        else:
            text = _RE_DESC_OPEN.sub(lambda m: m.group(1) + f' xmp:Rating="{val}"' + m.group(2), text, count=1)
    else:
        # Remove Rating entirely (0 = unrated in Lightroom).
        text = re.sub(r'\s*xmp:Rating\s*=\s*"[^"]*"', '', text)

    # Update or insert the xmp:Label attribute.
    if label:
        if 'xmp:Label=' in text:
            text = _RE_LABEL_ATTR.sub(f'xmp:Label="{label}"', text)
        else:
            text = _RE_DESC_OPEN.sub(lambda m: m.group(1) + f' xmp:Label="{label}"' + m.group(2), text, count=1)
    else:
        text = re.sub(r'\s*xmp:Label\s*=\s*"[^"]*"', '', text)

    return text


# Names Windows reserves regardless of extension. The app also targets
# Windows, so a Mac-side rename to one of these would produce a file the
# other platform cannot even open (0.14.1).
_WINDOWS_RESERVED = {'con', 'prn', 'aux', 'nul',
                     *(f'com{i}' for i in range(1, 10)),
                     *(f'lpt{i}' for i in range(1, 10))}


def rename_stem_problem(stem):
    """None if `stem` is a safe cross-platform file stem, else a short
    English reason code: 'reserved' (Windows device name) or 'trailing'
    (ends with a dot or space - Windows strips those silently). The GUI
    maps the code to a translated message."""
    if stem.lower() in _WINDOWS_RESERVED:
        return 'reserved'
    if stem != stem.rstrip('. '):
        return 'trailing'
    return None


def _write_xmp_sidecar(path, rating, label):
    """Write Rating and Label into a .xmp sidecar in pure Python.

    Creates the file from the skeleton when missing, amends an existing one.
    """
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            text = f.read()
    else:
        text = _XMP_SKELETON
    with open(path, 'w', encoding='utf-8') as f:
        f.write(_patch_xmp_text(text, rating, label))


# ── Embedded XMP in JPEG, in pure Python (0.12.6) ────────────────────────────
#
# A JPEG is a chain of marker segments; XMP lives in an APP1 segment whose
# payload starts with the Adobe namespace header. Rewriting that segment is
# plain byte surgery - no image data is touched and no native library is
# needed, which matters because exiv2 crashes the helper process on Harald's
# Windows for every single JPEG write.

_XMP_APP1_HEADER = b'http://ns.adobe.com/xap/1.0/\x00'
_APP1 = b'\xff\xe1'
_SOI = b'\xff\xd8'
_SOS = b'\xff\xda'
_MAX_SEGMENT = 65533          # 2 length bytes are part of the 65535 limit


def _jpeg_segments(data):
    """Yield (start, end, marker) for each marker segment up to SOS."""
    pos = 2                                   # skip SOI
    while pos + 4 <= len(data):
        if data[pos] != 0xFF:
            return
        marker = data[pos:pos + 2]
        if marker == _SOS or marker == b'\xff\xd9':
            return
        length = int.from_bytes(data[pos + 2:pos + 4], 'big')
        yield pos, pos + 2 + length, marker
        pos += 2 + length


def _write_xmp_jpeg(path, rating, label):
    """Set xmp:Rating / xmp:Label in a JPEG's embedded XMP packet.

    Replaces an existing XMP APP1 segment, or inserts one after the leading
    APPn block when the file has none. Raises OSError/ValueError on a file
    that is not a readable JPEG.
    """
    with open(path, 'rb') as f:
        data = f.read()
    if not data.startswith(_SOI):
        raise ValueError('not a JPEG')

    xmp_start = xmp_end = None
    insert_at = 2
    for start, end, marker in _jpeg_segments(data):
        if marker == _APP1 and data[start + 4:start + 4 + len(_XMP_APP1_HEADER)] == _XMP_APP1_HEADER:
            xmp_start, xmp_end = start, end
            break
        if marker in (b'\xff\xe0', _APP1):   # APP0/APP1 (JFIF, Exif)
            insert_at = end

    if xmp_start is not None:
        packet = data[xmp_start + 4 + len(_XMP_APP1_HEADER):xmp_end]
        text = packet.decode('utf-8', 'replace')
    else:
        text = _XMP_SKELETON

    text = _patch_xmp_text(text, rating, label)
    payload = _XMP_APP1_HEADER + text.encode('utf-8')
    if len(payload) + 2 > _MAX_SEGMENT:
        raise ValueError('XMP packet too large for one APP1 segment')
    segment = _APP1 + (len(payload) + 2).to_bytes(2, 'big') + payload

    if xmp_start is not None:
        out = data[:xmp_start] + segment + data[xmp_end:]
    else:
        out = data[:insert_at] + segment + data[insert_at:]

    tmp = path + '.cammello-tmp'
    with open(tmp, 'wb') as f:
        f.write(out)
    os.replace(tmp, path)


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


def scan_folder(folder, report=None):
    """Scan one folder (not recursive - SD card folders are flat) and pair
    RAW+JPEG by identical stem (case-insensitive). Returns CullItems sorted by
    stem. Filenames only; no file is opened.

    `report`: an optional dict that is FILLED IN with what the scan saw -
    see scan_report_text(). Added because "the folder has 200 pictures but
    only 40 show up" cannot be answered from the outside: the scan can only
    ever drop a file for an unknown extension, or fold several files into one
    entry because they share a stem, and nothing in the UI distinguished the
    two. Counting is cheap (names only, no file is opened), so the numbers
    are always collected and simply ignored when no dict is passed.
    """
    items = {}
    by_ext = {}
    listed = 0
    accepted = 0
    try:
        names = sorted(os.listdir(folder))
    except OSError as exc:
        if report is not None:
            report.update({'error': str(exc), 'listed': 0, 'accepted': 0,
                           'items': 0, 'by_ext': {}})
        return []
    for name in names:
        listed += 1
        stem, ext = os.path.splitext(name)
        ext = ext.lower()
        by_ext[ext] = by_ext.get(ext, 0) + 1
        if ext not in RAW_EXTENSIONS and ext not in JPEG_EXTENSIONS:
            continue
        accepted += 1
        path = os.path.join(folder, name)
        key = stem.casefold()
        item = items.get(key)
        if item is None:
            item = items[key] = CullItem(stem)
        if ext in RAW_EXTENSIONS:
            item.raw_path = path
        else:
            item.jpg_path = path
    out = [items[k] for k in sorted(items)]
    if report is not None:
        report.update({'error': None, 'listed': listed, 'accepted': accepted,
                       'items': len(out), 'by_ext': by_ext})
    return out


def scan_report_text(report):
    """One log line explaining a scan result: how many names the folder
    listed, how many were picture files, how many entries came out, and the
    extension histogram. The histogram is the part that answers the question
    in practice - an unexpected extension (or a pile of hidden placeholder
    files from a cloud drive) shows up immediately."""
    if not report:
        return ''
    if report.get('error'):
        return f"scan failed: {report['error']}"
    hist = ', '.join(f'{e or "(no ext)"}={n}'
                     for e, n in sorted(report.get('by_ext', {}).items(),
                                        key=lambda kv: (-kv[1], kv[0])))
    dropped = report['listed'] - report['accepted']
    folded = report['accepted'] - report['items']
    return (f"{report['listed']} name(s) listed, {report['accepted']} picture "
            f"file(s), {dropped} skipped (unknown extension), {folded} folded "
            f"into pairs -> {report['items']} entries; extensions: {hist}")


# ── XMP I/O ──────────────────────────────────────────────────────────────────

_XMP_SKELETON = ('<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
                 '<x:xmpmeta xmlns:x="adobe:ns:meta/">'
                 '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
                 '<rdf:Description rdf:about=""/></rdf:RDF></x:xmpmeta>\n'
                 '<?xpacket end="w"?>')


def read_item_metadata(item):
    """Fill item.rating / item.label from disk WITHOUT pyexiv2.

    Precedence: sidecar (the Photo Mechanic / Lightroom source of truth) >
    embedded XMP in the JPEG. The RAW file is never read - exiv2 crashes on
    some RAW formats and the scan avoids the native library entirely (see
    _read_rating_label_text). A RAW rated only in-camera, with no sidecar and
    no JPEG partner, reads as unrated.
    """
    sources = []
    sc = item.sidecar_path
    if sc and os.path.exists(sc):
        sources.append(sc)
    if item.jpg_path:
        sources.append(item.jpg_path)
    for src in sources:
        rating, label = _read_rating_label_text(src)
        if rating is None and label is None:
            continue
        # 0.12.7: CLAMP to the valid range. Harald hit a file that showed an
        # endless row of stars while its XMP said 1 - the exact cause could
        # not be reconstructed (the sidecar was overwritten before it could
        # be inspected), so this does two things: it makes any out-of-range
        # value harmless, and it writes the RAW string to the log so a
        # recurrence is diagnosable instead of merely visible.
        # -1 is "rejected", 0..5 are the stars; everything else is bogus.
        try:
            value = int(float(rating)) if rating is not None else 0
        except (TypeError, ValueError):
            logging.getLogger('Cammello').warning(
                'XMP rating of "%s" is not a number (raw value: %r) - '
                'treated as unrated.', src, rating)
            value = 0
        if value < -1 or value > 5:
            logging.getLogger('Cammello').warning(
                'XMP rating of "%s" out of range (raw value: %r) - '
                'clamped to %d.', src, rating,
                max(-1, min(5, value)))
            value = max(-1, min(5, value))
        item.rating = value
        item.label = label or ''
        return item
    item.rating = 0
    item.label = ''
    return item


def write_item_metadata(item):
    """Write rating/label: sidecar for the RAW (created if missing, existing
    ones amended), embedded for the JPEG. The RAW file itself is not touched.
    Returns the list of paths written.

    Sidecars (.xmp) are written in PURE PYTHON (no native library): they are
    plain text, and pyexiv2 crashes on Windows even on harmless .xmp files.
    The JPEG's embedded XMP is written the same way (APP1 segment surgery),
    so a JPEG-only picture - which has no sidecar - keeps its rating too.
    """
    written = []
    sc = item.sidecar_path
    if sc:
        _write_xmp_sidecar(sc, item.rating, item.label)
        written.append(sc)
    if item.jpg_path:
        # Embedded XMP in the JPEG - also pure Python (0.12.6). exiv2 is no
        # longer involved anywhere in the culling write path, so a
        # JPEG-only picture (which has NO sidecar) keeps its rating too.
        try:
            _write_xmp_jpeg(item.jpg_path, item.rating, item.label)
            written.append(item.jpg_path)
        except Exception as e:
            logging.getLogger('Cammello').warning(
                'XMP write to JPEG failed for "%s": %s', item.stem, e)
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
            # A reject has no meaningful star count. Until 0.12.6 the rejects
            # switch alone decided; since 0.12.7 rejects are shown BY DEFAULT
            # (Harald), and that made an active star filter show every reject
            # alongside the selects - "3 stars and up" would have listed the
            # discarded frames. So an active minimum rating now hides them as
            # well: with no star filter they stay visible (greyed, red X),
            # with one they drop out.
            if exclude_rejects or min_rating > 0:
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
