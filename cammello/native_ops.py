"""Leaf functions executed in the metadata HELPER PROCESS (0.12.6).

This module is imported by the spawned helper process (see native_exec), so
it must stay LIGHT: pyexiv2 and the standard library only - no Qt, no other
Cammello modules. Every function here is top-level (picklable by reference)
and returns plain picklable data.

Why a separate process at all: exiv2 error paths have crashed the whole
application on Windows with access violations that no try/except can catch
(observed 2026-07-18 on a Canon DNG with a corrupt maker note, and once on a
sidecar write). pyexiv2 also documents itself as not thread safe due to C++
globals. Running every exiv2 call in a dedicated helper process turns any
such crash into a catchable error: the helper dies, Cammello survives.

0.12.9: pyexiv2 is imported LAZILY, inside _require(). The GUI process also
imports this module - iptc.py needs the function objects to hand to the
executor (pickled by reference) - and a top-level import therefore loaded
the crash-prone native library into exactly the process the whole
architecture keeps it out of. The functions only ever RUN in the helper, so
the import now happens there, on first use.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:                       # never true at runtime
    # Bundlers (py2app, PyInstaller) build their module graph from bytecode
    # imports. The real import below lives inside _require() and stays lazy;
    # this dead-but-compiled import guarantees pyexiv2 is still PACKAGED.
    # (`if False:` would not work - CPython folds it away entirely.)
    import pyexiv2                      # noqa: F401

_PYEXIV2 = None
_PYEXIV2_ERROR = None


def _require():
    """Import pyexiv2 on first use (in the helper process) and return it."""
    global _PYEXIV2, _PYEXIV2_ERROR
    if _PYEXIV2 is None and _PYEXIV2_ERROR is None:
        try:
            import pyexiv2
            _PYEXIV2 = pyexiv2
        except Exception as e:          # pragma: no cover - optional dep
            _PYEXIV2_ERROR = str(e)
    if _PYEXIV2 is None:
        raise RuntimeError('pyexiv2 is not available in the helper process: '
                           + (_PYEXIV2_ERROR or 'unknown import error'))
    return _PYEXIV2


def read_iptc_raw(path):
    px = _require()
    img = px.Image(path)
    try:
        return img.read_iptc() or {}
    finally:
        img.close()


def read_xmp_raw(path):
    px = _require()
    img = px.Image(path)
    try:
        return img.read_xmp() or {}
    finally:
        img.close()


def write_xmp_raw(path, payload):
    px = _require()
    img = px.Image(path)
    try:
        img.modify_xmp(payload)
    finally:
        img.close()


def modify_all_raw(path, iim_payload, xmp_payload):
    """One open for both families - IIM and XMP - like iptc.write_iptc
    always did."""
    px = _require()
    img = px.Image(path)
    try:
        if iim_payload:
            img.modify_iptc(iim_payload)
        if xmp_payload:
            img.modify_xmp(xmp_payload)
    finally:
        img.close()


# ── GPS in the file (0.15.0) ─────────────────────────────────────────────────
# The EXIF GPS keys pyexiv2 exposes. Removal covers ALL of them, not just
# latitude and longitude: leaving the reference letters, the altitude or the
# timestamp behind means the file still says where it was (Harald: "alle
# Koordinatenfelder"). The IPTC place names are deliberately NOT here - those
# are entered deliberately and stay.
GPS_EXIF_KEYS = (
    'Exif.GPSInfo.GPSVersionID',
    'Exif.GPSInfo.GPSLatitude',
    'Exif.GPSInfo.GPSLatitudeRef',
    'Exif.GPSInfo.GPSLongitude',
    'Exif.GPSInfo.GPSLongitudeRef',
    'Exif.GPSInfo.GPSAltitude',
    'Exif.GPSInfo.GPSAltitudeRef',
    'Exif.GPSInfo.GPSTimeStamp',
    'Exif.GPSInfo.GPSDateStamp',
    'Exif.GPSInfo.GPSSatellites',
    'Exif.GPSInfo.GPSStatus',
    'Exif.GPSInfo.GPSMeasureMode',
    'Exif.GPSInfo.GPSDOP',
    'Exif.GPSInfo.GPSSpeed',
    'Exif.GPSInfo.GPSSpeedRef',
    'Exif.GPSInfo.GPSTrack',
    'Exif.GPSInfo.GPSTrackRef',
    'Exif.GPSInfo.GPSImgDirection',
    'Exif.GPSInfo.GPSImgDirectionRef',
    'Exif.GPSInfo.GPSMapDatum',
    'Exif.GPSInfo.GPSDestLatitude',
    'Exif.GPSInfo.GPSDestLatitudeRef',
    'Exif.GPSInfo.GPSDestLongitude',
    'Exif.GPSInfo.GPSDestLongitudeRef',
    'Exif.GPSInfo.GPSProcessingMethod',
    'Exif.GPSInfo.GPSAreaInformation',
    'Exif.GPSInfo.GPSDifferential',
    'Exif.GPSInfo.GPSHPositioningError',
)

# The XMP twins. A file can carry the position twice; clearing only the EXIF
# side would leave the XMP copy to be read back by the next tool.
GPS_XMP_KEYS = (
    'Xmp.exif.GPSLatitude',
    'Xmp.exif.GPSLongitude',
    'Xmp.exif.GPSAltitude',
    'Xmp.exif.GPSAltitudeRef',
    'Xmp.exif.GPSTimeStamp',
    'Xmp.exif.GPSVersionID',
    'Xmp.exif.GPSMapDatum',
    'Xmp.exif.GPSProcessingMethod',
    'Xmp.exif.GPSImgDirection',
    'Xmp.exif.GPSImgDirectionRef',
)


def _dms_strings(value):
    """Decimal degrees -> exiv2's rational DMS triple plus the hemisphere.

    exiv2 wants "deg/1 min/1 sec/100" as a string; the sign lives in the
    reference letter, never in the numbers.
    """
    ref_neg = value < 0
    value = abs(float(value))
    deg = int(value)
    rest = (value - deg) * 60.0
    minutes = int(rest)
    seconds = (rest - minutes) * 60.0
    return f'{deg}/1 {minutes}/1 {int(round(seconds * 100))}/100', ref_neg


def clear_gps_raw(path):
    """Remove every GPS key from EXIF and XMP. -> number of keys cleared.

    Uses modify_exif/modify_xmp with an empty string, which is how pyexiv2
    deletes a key; keys that are not present are skipped, so this never
    fails on a file that simply has no position.
    """
    px = _require()
    img = px.Image(path)
    try:
        present_exif = img.read_exif() or {}
        present_xmp = img.read_xmp() or {}
        exif_payload = {k: '' for k in GPS_EXIF_KEYS if k in present_exif}
        xmp_payload = {k: '' for k in GPS_XMP_KEYS if k in present_xmp}
        if exif_payload:
            img.modify_exif(exif_payload)
        if xmp_payload:
            img.modify_xmp(xmp_payload)
        return len(exif_payload) + len(xmp_payload)
    finally:
        img.close()


def write_gps_raw(path, lat, lon):
    """Write one camera position into the file's EXIF GPS block.

    Replaces whatever was there: the reference letters are written together
    with the numbers, so a position moving from north to south cannot leave
    a stale "N" behind.
    """
    px = _require()
    lat_str, lat_neg = _dms_strings(lat)
    lon_str, lon_neg = _dms_strings(lon)
    img = px.Image(path)
    try:
        img.modify_exif({
            'Exif.GPSInfo.GPSVersionID': '2 0 0 0',
            'Exif.GPSInfo.GPSLatitude': lat_str,
            'Exif.GPSInfo.GPSLatitudeRef': 'S' if lat_neg else 'N',
            'Exif.GPSInfo.GPSLongitude': lon_str,
            'Exif.GPSInfo.GPSLongitudeRef': 'W' if lon_neg else 'E',
        })
        return True
    finally:
        img.close()
