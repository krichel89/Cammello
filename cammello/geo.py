"""Location data (0.15.0): camera position and depicted position.

Design decisions (agreed with Harald, 2026-07-26/28):
  * TWO coordinates per file, kept apart on purpose:
      - camera   -> {{Location dec}}        / P1259 (point of view)
      - object   -> {{Object location dec}} / P9149 (depicted place)
    For a portrait the difference is academic; for a building it is the
    whole point - the camera stands across the street from the subject.
  * Reading order: the SIDECAR WINS over EXIF. Harald's reasoning: a value
    in the sidecar got there through a deliberate act (Lightroom,
    darktable), while EXIF GPS is whatever the camera happened to record.
  * The sidecar is read in PURE PYTHON, never through exiv2 - iptc.py
    already does it that way because exiv2 crashes on Windows merely
    OPENING a sidecar file. Same road here, no exceptions.
  * Storage mirrors channels.py and edits.py: one JSON object in QSettings
    keyed by the normalized path. No Qt import in here, so the logic is
    testable on its own.
  * What the user types or matches ALWAYS beats what was read from a file.
    That is what makes "clear it and enter it again" work.

Coordinates are decimal degrees, latitude first, as float pairs.
"""
import json
import os
import re

from .edits import norm
from .exif import read_gps

_SETTINGS_KEY = 'locations'

# Where a value came from, so the UI can say it and so a file read never
# overwrites something the user set by hand.
SRC_SIDECAR = 'sidecar'
SRC_EXIF = 'exif'
SRC_USER = 'user'
SRC_GPX = 'gpx'


def sidecar_path(path):
    """The .xmp sidecar Lightroom and darktable write next to an image.

    Both spellings occur in the wild: image.xmp (extension replaced) and
    image.CR3.xmp (extension appended). Returns the one that exists, or
    None.
    """
    if not path:
        return None
    stem, _ext = os.path.splitext(path)
    for cand in (path + '.xmp', stem + '.xmp', path + '.XMP', stem + '.XMP'):
        if os.path.exists(cand):
            return cand
    return None


def _num(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def parse_xmp_coordinate(text):
    """One XMP GPS value -> decimal degrees, or None.

    XMP stores these as "DDD,MM.mmK" or "DDD,MM,SSK" with a trailing
    hemisphere letter (Adobe's XMP specification for exif:GPSLatitude), but
    plain decimal degrees also turn up in files written by other tools. All
    three are accepted; anything else yields None, which the caller treats
    as "no coordinate" rather than as an error.
    """
    if text is None:
        return None
    text = str(text).strip()
    if not text:
        return None
    ref = ''
    if text[-1] in 'NSEWnsew':
        ref = text[-1].upper()
        text = text[:-1].strip()
    parts = [p for p in text.split(',') if p != '']
    if len(parts) == 1:
        value = _num(parts[0])
    elif len(parts) == 2:
        deg, minutes = _num(parts[0]), _num(parts[1])
        value = None if deg is None or minutes is None else deg + minutes / 60.0
    elif len(parts) == 3:
        deg, minutes, sec = _num(parts[0]), _num(parts[1]), _num(parts[2])
        value = (None if deg is None or minutes is None or sec is None
                 else deg + minutes / 60.0 + sec / 3600.0)
    else:
        return None
    if value is None:
        return None
    if ref in ('S', 'W'):
        value = -abs(value)
    return value


_LAT_PATTERNS = (
    r'exif:GPSLatitude>([^<]*)<',
    r'exif:GPSLatitude=["\']([^"\']*)["\']',
)
_LON_PATTERNS = (
    r'exif:GPSLongitude>([^<]*)<',
    r'exif:GPSLongitude=["\']([^"\']*)["\']',
)


def read_sidecar_gps(path, log=None):
    """(lat, lon) from the .xmp sidecar next to `path`, or None.

    Pure text parsing, deliberately: see the module docstring. A sidecar
    that cannot be read is not an error - the caller simply has no
    coordinates from it.
    """
    sc = sidecar_path(path)
    if not sc:
        return None
    try:
        # Bounded read (0.15.0 review): a sidecar is a small XML file; real
        # ones are a few hundred KB at most. Reading whatever happens to
        # carry the .xmp name WITHOUT a limit would hand a corrupt or
        # mis-named multi-gigabyte file straight to memory. 8 MB covers
        # every legitimate sidecar with room to spare.
        with open(sc, 'r', encoding='utf-8', errors='replace') as fh:
            text = fh.read(8 * 1024 * 1024)
    except OSError as e:
        if log:
            log.info('Sidecar for "%s" could not be read: %s',
                     os.path.basename(path), e)
        return None
    lat = lon = None
    for pat in _LAT_PATTERNS:
        m = re.search(pat, text)
        if m:
            lat = parse_xmp_coordinate(m.group(1))
            break
    for pat in _LON_PATTERNS:
        m = re.search(pat, text)
        if m:
            lon = parse_xmp_coordinate(m.group(1))
            break
    if lat is None or lon is None:
        return None
    return (lat, lon)


def read_camera_position(path, log=None):
    """The camera position for one file as ((lat, lon), source), or None.

    Sidecar first, EXIF second - see the module docstring for why round
    that way. Note that read_gps() goes through Pillow, which generally
    cannot open camera RAW: for a RAW-only shot the sidecar is usually the
    only source that answers at all.
    """
    coords = read_sidecar_gps(path, log=log)
    if coords is not None:
        return (coords, SRC_SIDECAR)
    coords = read_gps(path, log=log)
    if coords is not None:
        return (coords, SRC_EXIF)
    return None


# ── storage ──────────────────────────────────────────────────────────────────

def _valid_pair(value):
    """A [lat, lon] pair inside the valid range, or None."""
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    lat, lon = _num(value[0]), _num(value[1])
    if lat is None or lon is None:
        return None
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        return None
    return [lat, lon]


def _normalize_record(rec):
    """One stored record, cleaned; None when nothing usable is left."""
    if not isinstance(rec, dict):
        return None
    out = {}
    for key in ('camera', 'object'):
        pair = _valid_pair(rec.get(key))
        if pair is not None:
            out[key] = pair
            src = rec.get(key + '_src')
            if src in (SRC_SIDECAR, SRC_EXIF, SRC_USER, SRC_GPX):
                out[key + '_src'] = src
    return out or None


def load_locations(settings):
    """-> {normalized_path: record} from QSettings; unusable entries dropped
    rather than raising."""
    raw = settings.value(_SETTINGS_KEY, '') or ''
    try:
        data = json.loads(raw) if raw else {}
    except ValueError:
        return {}
    if not isinstance(data, dict):
        return {}
    out = {}
    for k, v in data.items():
        rec = _normalize_record(v)
        if rec is not None:
            out[str(k)] = rec
    return out


def save_locations(settings, locations):
    settings.setValue(_SETTINGS_KEY, json.dumps(locations, ensure_ascii=False))
    settings.sync()


def get_location(locations, path):
    """The record for one path, or None."""
    return locations.get(norm(path))


def set_position(locations, path, which, coords, source=SRC_USER):
    """Set 'camera' or 'object' for one path. coords=None removes it.

    Returns True when something changed, so callers can skip a save.
    """
    if which not in ('camera', 'object'):
        raise ValueError('which must be "camera" or "object"')
    key = norm(path)
    rec = dict(locations.get(key) or {})
    before = dict(rec)
    if coords is None:
        rec.pop(which, None)
        rec.pop(which + '_src', None)
    else:
        pair = _valid_pair(coords)
        if pair is None:
            return False
        rec[which] = pair
        rec[which + '_src'] = source
    if rec == before:
        return False
    if rec:
        locations[key] = rec
    else:
        locations.pop(key, None)
    return True


def has_any(locations, paths):
    """Whether ANY of these paths carries a coordinate. Drives the Location
    column, which is shown only while there is something to show."""
    for p in paths:
        rec = locations.get(norm(p))
        if rec and ('camera' in rec or 'object' in rec):
            return True
    return False


# ── formatting ───────────────────────────────────────────────────────────────

def format_pair(coords, decimals=6):
    """(lat, lon) -> "48.775846, 9.182932"; None -> ''.

    A POINT as the decimal separator, always: the value goes into wikitext
    and into structured data, where a German comma would be a defect. Same
    reason the exposure display forces a point.
    """
    pair = _valid_pair(coords)
    if pair is None:
        return ''
    return f'{pair[0]:.{decimals}f}, {pair[1]:.{decimals}f}'


def parse_pair(text):
    """"48.775846, 9.182932" -> (lat, lon), or None.

    Accepts a semicolon or plain whitespace as the separator too, and a
    German decimal comma when the two numbers are separated by something
    else ("48,775846 9,182932"). Ambiguous input yields None rather than a
    guess - a silently mis-parsed coordinate is worse than an empty field.
    """
    if not text:
        return None
    raw = str(text).strip()
    if not raw:
        return None
    tokens = [t.strip().strip(',;') for t in re.split(r'[;\s]+', raw)]
    tokens = [t for t in tokens if t]
    if len(tokens) == 2:
        # Whitespace-separated: a comma inside a token is a decimal comma.
        parts = [t.replace(',', '.') for t in tokens]
    elif len(tokens) == 1 and tokens[0].count(',') == 1:
        # "48.775846,9.182932" - the single comma is the separator.
        parts = tokens[0].split(',')
    else:
        return None
    if len(parts) != 2:
        return None
    pair = _valid_pair(parts)
    if pair is None:
        return None
    return (pair[0], pair[1])


def column_text(rec):
    """Both coordinates for the file table: camera on top, object below.

    ONE column with the two lines under each other (Harald's choice), so
    the table does not grow a second column that is empty most of the time.
    """
    if not rec:
        return ''
    lines = []
    if 'camera' in rec:
        lines.append(format_pair(rec['camera']))
    if 'object' in rec:
        lines.append(format_pair(rec['object']))
    return '\n'.join(lines)


# ── writing into the file (0.15.0) ───────────────────────────────────────────
# Only JPEG and TIFF. Writing into RAW was struck by Harald ("lass … schreiben
# in raw weg"), and for good reason: a RAW is the negative, and every
# converter keeps its own idea of what belongs in it. A RAW file therefore
# keeps its Cammello record but is never modified on disk.
WRITABLE_EXTENSIONS = ('.jpg', '.jpeg', '.tif', '.tiff')


def is_writable_image(path):
    """Whether the position may be written INTO this file."""
    return bool(path) and os.path.splitext(path)[1].lower() \
        in WRITABLE_EXTENSIONS


def clear_gps_in_file(path, log=None):
    """Remove every coordinate field from the file. -> (ok, detail).

    ok is False only on a real error; a file that simply carries no
    position returns (True, 0). The IPTC place names are untouched by
    design - those are entered deliberately and stay (Harald).
    """
    from . import native_exec, native_ops
    if not is_writable_image(path):
        return True, 'skipped'
    try:
        n = native_exec.run(native_ops.clear_gps_raw, path)
        return True, n
    except Exception as e:
        if log:
            log.error('Could not clear GPS in "%s": %s',
                      os.path.basename(path), e)
        return False, str(e)


def write_gps_in_file(path, coords, log=None):
    """Write one camera position into the file. -> (ok, detail)."""
    from . import native_exec, native_ops
    if not is_writable_image(path):
        return True, 'skipped'
    pair = _valid_pair(coords)
    if pair is None:
        return False, 'invalid coordinates'
    try:
        native_exec.run(native_ops.write_gps_raw, path, pair[0], pair[1])
        return True, 'written'
    except Exception as e:
        if log:
            log.error('Could not write GPS to "%s": %s',
                      os.path.basename(path), e)
        return False, str(e)
