"""EXIF reading: capture date, GPS position, camera details."""
import re
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def read_exif_date(filepath, log=None):
    """Read the capture date from EXIF data.

    DateTimeOriginal (36867) and DateTimeDigitized (36868) live in the EXIF
    sub-IFD (0x8769); DateTime (306) is in the base IFD. img.getexif() only
    exposes the base IFD directly, so the sub-IFD must be read explicitly.
    """
    if not HAS_PIL:
        return ''
    try:
        img = Image.open(filepath)
        exif = img.getexif()
        if not exif:
            return ''

        candidates = []
        try:
            sub = exif.get_ifd(0x8769)  # EXIF sub-IFD
            candidates.append(sub.get(36867))  # DateTimeOriginal
            candidates.append(sub.get(36868))  # DateTimeDigitized
        except Exception:
            pass
        candidates.append(exif.get(306))       # DateTime (base IFD)

        for value in candidates:
            if value:
                # "2025:01:15 14:30:00" -> "2025-01-15 14:30:00"
                return str(value).replace(':', '-', 2).strip()
        return ''
    except Exception as e:
        if log:
            log.debug('Could not read EXIF date for %s: %s', filepath, e)
        return ''


def _dms_to_decimal(dms, ref):
    """(deg, min, sec) + 'N'/'S'/'E'/'W' -> signed decimal degrees.

    EXIF stores the three parts as rationals; float() handles Pillow's
    IFDRational as well as plain ints and Fractions.
    """
    deg, minutes, seconds = (float(x) for x in dms)
    value = deg + minutes / 60.0 + seconds / 3600.0
    if str(ref).strip().upper() in ('S', 'W'):
        value = -value
    return value


def read_gps(filepath, log=None):
    """Camera position from EXIF as (lat, lon) in decimal degrees, or None.

    The GPS block is its own IFD (0x8825) with numeric tags:
      1 GPSLatitudeRef   2 GPSLatitude   3 GPSLongitudeRef   4 GPSLongitude
    Returns None when the file has no GPS block, when a part is missing, or
    when the values are unusable - the caller then simply has no coordinates,
    which is a normal case, not an error.

    Note: this reads what Pillow can open. JPEGs are covered; for camera RAW
    files Pillow generally cannot read the EXIF, so a RAW-only shot yields
    None here even though the camera wrote GPS.
    """
    if not HAS_PIL:
        return None
    try:
        img = Image.open(filepath)
        exif = img.getexif()
        if not exif:
            return None
        gps = exif.get_ifd(0x8825)
        if not gps:
            return None
        lat, lat_ref = gps.get(2), gps.get(1)
        lon, lon_ref = gps.get(4), gps.get(3)
        if not lat or not lon or not lat_ref or not lon_ref:
            return None
        latitude = _dms_to_decimal(lat, lat_ref)
        longitude = _dms_to_decimal(lon, lon_ref)
    except Exception as e:
        if log:
            log.debug('Could not read EXIF GPS for %s: %s', filepath, e)
        return None
    # A camera that never got a fix writes zeros; and out-of-range values are
    # corrupt rather than "somewhere at sea".
    if not (-90.0 <= latitude <= 90.0) or not (-180.0 <= longitude <= 180.0):
        if log:
            log.debug('EXIF GPS out of range for %s: %s, %s',
                      filepath, latitude, longitude)
        return None
    if latitude == 0.0 and longitude == 0.0:
        return None
    return latitude, longitude


def format_coordinates(lat, lon):
    """The text form Cammello stores in the description: 'lat, lon'.

    Six decimals is about 0.1 m - far beyond what a camera GPS resolves, but
    it costs nothing and avoids rounding away a good fix.
    """
    return f'{lat:.6f}, {lon:.6f}'


def parse_coordinates(text):
    """'48.137154, 11.576124' -> (48.137154, 11.576124), or None.

    Accepts a comma or a semicolon as separator and tolerates surrounding
    whitespace, because this value can be typed or pasted by hand.
    """
    if not text:
        return None
    parts = [p.strip() for p in re.split(r'[;,]', str(text)) if p.strip()]
    if len(parts) != 2:
        return None
    try:
        lat, lon = float(parts[0]), float(parts[1])
    except ValueError:
        return None
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        return None
    return lat, lon


def _fmt_exposure(value):
    """'1/250 s' for values < 1, '2 s' otherwise. Pillow returns a Fraction-
    like IFDRational; float() works on all of them."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if v <= 0:
        return str(value)
    if v < 1:
        return f'1/{round(1 / v)} s'
    return f'{v:g} s'


def read_exif_summary(filepath, log=None):
    """[(english_label, value_str)] of the capture EXIF of a JPEG, for the
    culling info overlay. Pillow only - the culling READ path must never touch
    pyexiv2 (exiv2 crashed the scan; see culling.py). Returns [] when the file
    has no EXIF or Pillow cannot open it (e.g. a RAW container); the caller
    shows plain file info instead. Labels are English tr() keys.
    """
    if not HAS_PIL:
        return []
    out = []
    try:
        with Image.open(filepath) as img:
            width, height = img.size
            exif = img.getexif()
        out.append(('Dimensions', f'{width} × {height}'))
        if not exif:
            return out
        make = str(exif.get(0x010F) or '').strip()
        model = str(exif.get(0x0110) or '').strip()
        if model:
            # Many models already start with the make ("Canon EOS R6").
            camera = model if model.lower().startswith(make.lower()) \
                else f'{make} {model}'.strip()
            out.append(('Camera', camera))
        try:
            sub = exif.get_ifd(0x8769)          # EXIF sub-IFD
        except Exception:
            sub = {}
        lens = str(sub.get(0xA434) or '').strip()   # LensModel
        if lens:
            out.append(('Lens', lens))
        focal = sub.get(0x920A)                     # FocalLength
        if focal:
            try:
                out.append(('Focal length', f'{float(focal):g} mm'))
            except (TypeError, ValueError):
                pass
        exposure = sub.get(0x829A)                  # ExposureTime
        if exposure:
            out.append(('Exposure', _fmt_exposure(exposure)))
        fnumber = sub.get(0x829D)                   # FNumber
        if fnumber:
            try:
                out.append(('Aperture', f'f/{float(fnumber):g}'))
            except (TypeError, ValueError):
                pass
        iso = sub.get(0x8827)                       # ISOSpeedRatings
        if iso:
            if isinstance(iso, (tuple, list)):
                iso = iso[0] if iso else ''
            out.append(('ISO', str(iso)))
        date = sub.get(36867) or exif.get(306)      # DateTimeOriginal/DateTime
        if date:
            out.append(('Taken', str(date).replace(':', '-', 2).strip()))
    except Exception as e:
        if log:
            log.debug('Could not read EXIF summary for %s: %s', filepath, e)
        return []
    return out


# ── Target filename on Commons ──────────────────────────────────────────────────

# Extensions accepted as a valid file extension.
