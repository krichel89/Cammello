"""GPX track matching (0.15.0): give photos the position of a logger track.

Design decisions (agreed with Harald, 2026-07-26/28):
  * A DIALOG in the MediaWiki module, also usable by hand: pick the .gpx,
    see every file with its matched point, adjust, then apply.
  * The camera clock offset is GUESSED FROM THE SYSTEM TIME ZONE as the
    preset, in an editable field: cameras write local time without a zone,
    GPX runs in UTC. The guess is right exactly when the camera clock stood
    in the zone this machine is in now - a trip abroad or a drifting camera
    clock needs the field.
  * The maximum time gap for a match is ADJUSTABLE; beyond it a photo gets
    no point rather than a wrong one.

No Qt in here - the parsing and matching are plain logic, testable on
their own (the dialog lives in gpx_dialog.py). XML goes through the
stdlib ElementTree: it does not resolve external entities, and the read
is size-capped, so a hostile file gets no further than a parse error.
"""
import bisect
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

# A day-long track at one point per second is ~7 MB of XML; 64 MB covers
# every real logger file with a wide margin and stops a mis-named
# multi-gigabyte file from being handed to the parser whole.
MAX_GPX_BYTES = 64 * 1024 * 1024

# Default maximum distance in time between a photo and its nearest track
# point. Beyond it the photo gets NO position: a logger that was off for an
# hour must not pin the photo to wherever the track happened to stop.
DEFAULT_MAX_GAP_S = 300


def system_utc_offset_s(when=None):
    """The LOCAL zone's offset from UTC in seconds, DST included.

    This is the preset for the offset field - the camera offset it guesses
    is only right when the camera clock stood in this machine's zone.
    """
    if when is None:
        when = time.time()
    local = datetime.fromtimestamp(when).astimezone()
    off = local.utcoffset()
    return int(off.total_seconds()) if off is not None else 0


_TIME_RE = re.compile(
    r'(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})(\.\d+)?'
    r'(Z|[+-]\d{2}:?\d{2})?')


def parse_gpx_time(text):
    """A GPX <time> value -> UTC epoch seconds, or None.

    GPX times are UTC by specification ("Z"), but files with an explicit
    numeric offset exist and are honoured; a bare time is read as UTC.
    """
    if not text:
        return None
    m = _TIME_RE.match(str(text).strip())
    if not m:
        return None
    y, mo, d, h, mi, s = (int(m.group(i)) for i in range(1, 7))
    frac = float(m.group(7) or 0)
    zone = m.group(8)
    try:
        dt = datetime(y, mo, d, h, mi, s, tzinfo=timezone.utc)
    except ValueError:
        return None
    epoch = dt.timestamp() + frac
    if zone and zone != 'Z':
        sign = 1 if zone[0] == '+' else -1
        zh = int(zone[1:3])
        zm = int(zone[-2:])
        epoch -= sign * (zh * 3600 + zm * 60)
    return epoch


def parse_exif_datetime(text, utc_offset_s):
    """An EXIF-style local timestamp -> UTC epoch seconds, or None.

    Accepts both "2025:01:15 14:30:00" (raw EXIF) and the
    "2025-01-15 14:30:00" shape read_exif_date() returns. EXIF carries no
    zone, so the caller says how far the camera clock stood from UTC.
    """
    if not text:
        return None
    t = str(text).strip().replace(':', '-', 2) if ':' in str(text)[:8] \
        else str(text).strip()
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})', t)
    if not m:
        return None
    y, mo, d, h, mi, s = (int(m.group(i)) for i in range(1, 7))
    try:
        dt = datetime(y, mo, d, h, mi, s, tzinfo=timezone.utc)
    except ValueError:
        return None
    # The timestamp was LOCAL camera time; subtracting the offset turns it
    # into UTC (a camera at UTC+2 writes 14:30 when UTC says 12:30).
    return dt.timestamp() - utc_offset_s


def parse_gpx(path, log=None):
    """A .gpx file -> [(utc_epoch, lat, lon)], sorted by time.

    Track points without a usable time are skipped - they cannot be
    matched. Route points (<rtept>) and waypoints are ignored on purpose:
    only the recorded track says where the photographer WAS.
    """
    try:
        if os.path.getsize(path) > MAX_GPX_BYTES:
            if log:
                log.error('GPX file is larger than %d MB, refusing: %s',
                          MAX_GPX_BYTES // (1024 * 1024), path)
            return []
    except OSError:
        return []
    try:
        tree = ET.parse(path)
    except (ET.ParseError, OSError) as e:
        if log:
            log.error('GPX could not be parsed: %s (%s)', path, e)
        return []
    points = []
    for el in tree.iter():
        if not el.tag.endswith('}trkpt') and el.tag != 'trkpt':
            continue
        try:
            lat = float(el.get('lat'))
            lon = float(el.get('lon'))
        except (TypeError, ValueError):
            continue
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            continue
        when = None
        for child in el:
            if child.tag.endswith('}time') or child.tag == 'time':
                when = parse_gpx_time(child.text)
                break
        if when is None:
            continue
        points.append((when, lat, lon))
    points.sort(key=lambda p: p[0])
    return points


def nearest_point(points, epoch, max_gap_s):
    """The track point nearest in time, or None when the gap is too wide.

    `points` must be sorted by time (parse_gpx guarantees it); the lookup
    is a bisect, so matching thousands of photos against a day-long track
    stays instant. No interpolation between points on purpose: a logger
    writes every few seconds, and inventing positions between two points
    minutes apart would place the photo on a straight line the
    photographer never walked.
    """
    if not points or epoch is None:
        return None
    times = [p[0] for p in points] if not isinstance(points, _Indexed) \
        else points.times
    i = bisect.bisect_left(times, epoch)
    best = None
    for j in (i - 1, i):
        if 0 <= j < len(points):
            gap = abs(points[j][0] - epoch)
            if best is None or gap < best[0]:
                best = (gap, points[j])
    if best is None or best[0] > max_gap_s:
        return None
    return best[1]


class _Indexed(list):
    """parse-once time index for repeated nearest_point calls."""

    def __init__(self, points):
        super().__init__(points)
        self.times = [p[0] for p in points]


def index_points(points):
    """Wrap the point list so repeated lookups reuse one time index."""
    return _Indexed(points)


def match_files(points, dated_files, utc_offset_s, max_gap_s):
    """[(path, exif_date_text)] -> {path: (lat, lon) | None}.

    None means: the file has a date but no track point inside the gap, or
    no usable date at all. The caller distinguishes the two through
    parse_exif_datetime if it needs to.
    """
    idx = index_points(points) if not isinstance(points, _Indexed) else points
    out = {}
    for path, date_text in dated_files:
        epoch = parse_exif_datetime(date_text, utc_offset_s)
        hit = nearest_point(idx, epoch, max_gap_s)
        out[path] = (hit[1], hit[2]) if hit else None
    return out
