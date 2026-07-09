"""EXIF capture-date reading."""
import os
from datetime import datetime
try:
    from PIL import Image
    from PIL.ExifTags import TAGS
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


# ── Target filename on Commons ──────────────────────────────────────────────────

# Extensions accepted as a valid file extension.
