"""EXIF capture-date reading."""
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
