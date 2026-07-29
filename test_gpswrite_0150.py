"""Writing and clearing GPS in the file, and the safe P7482 source claim
(0.15.0).

The write path is exercised against native_ops DIRECTLY, not through
native_exec: the helper process is a multiprocessing detour that adds
nothing to what is being checked here and would make the run fragile.
"""
import os
import struct
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from cammello import geo, native_ops
from cammello.constants import (OWN_WORK_TEMPLATES, SOURCE_OWN_WORK,
                                SOURCE_PROPERTY)
from cammello.logging_setup import setup_logging

logger, _emitter, _gui, _log_path = setup_logging()

fails = []


def check(name, cond, detail=''):
    if cond:
        print('PASS', name, detail)
    else:
        print('FAIL', name, detail)
        fails.append(name)


# ── which files may be written ───────────────────────────────────────────────
check('JPEG is writable', geo.is_writable_image('/x/a.JPG'))
check('TIFF is writable', geo.is_writable_image('/x/a.tif'))
check('RAW is NOT writable - struck by Harald',
      not geo.is_writable_image('/x/a.CR3'))
check('a RAW is skipped rather than failed',
      geo.clear_gps_in_file('/x/a.CR3', logger) == (True, 'skipped'))

# ── degrees -> exiv2 rationals ───────────────────────────────────────────────
s, neg = native_ops._dms_strings(48.775846)
check('degrees become a rational triple', s == '48/1 46/1 3305/100', s)
check('a northern value is not negative', not neg)
s, neg = native_ops._dms_strings(-33.8688)
check('the sign lives in the reference, not the numbers',
      neg and not s.startswith('-'), s)

# ── the real thing, against a real JPEG ──────────────────────────────────────
try:
    from PIL import Image
    import pyexiv2
    HAVE = True
except ImportError:
    HAVE = False

if not HAVE:
    print('SKIP file round trip - PIL or pyexiv2 unavailable')
else:
    d = tempfile.mkdtemp()
    p = os.path.join(d, 'shot.jpg')
    Image.new('RGB', (64, 64)).save(p)

    check('a file without GPS clears without error',
          native_ops.clear_gps_raw(p) == 0)

    native_ops.write_gps_raw(p, 48.775846, 9.182932)
    hit = geo.read_camera_position(p, log=logger)
    check('what was written is read back',
          hit is not None and abs(hit[0][0] - 48.775846) < 1e-4
          and abs(hit[0][1] - 9.182932) < 1e-4, str(hit))

    # The bytes really have to be gone - this is a privacy feature, not a
    # display filter. 3305/100 is the seconds rational of the latitude.
    raw_before = open(p, 'rb').read()
    needle = struct.pack('<II', 3305, 100)
    check('the coordinate is in the raw bytes before clearing',
          raw_before.find(needle) >= 0)

    n = native_ops.clear_gps_raw(p)
    check('clearing reports the keys it removed', n >= 4, f'{n} keys')
    check('the position no longer reads back',
          geo.read_camera_position(p, log=logger) is None)
    raw_after = open(p, 'rb').read()
    check('AND the coordinate bytes are gone from the file',
          raw_after.find(needle) < 0)
    img = Image.open(p)
    left = dict(img.getexif().get_ifd(0x8825))
    check('what remains carries no position',
          not any(k in left for k in (2, 4)), str(left))

    # Southern and western hemispheres.
    native_ops.write_gps_raw(p, -33.8688, 151.2093)
    hit = geo.read_camera_position(p, log=logger)
    check('a southern latitude comes back negative',
          hit is not None and hit[0][0] < 0, str(hit))
    native_ops.write_gps_raw(p, 51.5, -0.12)
    hit = geo.read_camera_position(p, log=logger)
    check('a western longitude comes back negative',
          hit is not None and hit[0][1] < 0, str(hit))
    check('overwriting leaves no stale reference letter',
          hit is not None and abs(hit[0][0] - 51.5) < 1e-4)

# ── the safe source statement ────────────────────────────────────────────────
check('own work is recognised', '{{own}}'.strip('{} ').lower()
      in OWN_WORK_TEMPLATES)
check('a Flickr source is NOT own work',
      'flickr.com/photos/x'.strip('{} ').lower() not in OWN_WORK_TEMPLATES)
check('the property and item are the verified ones',
      SOURCE_PROPERTY == 'P7482' and SOURCE_OWN_WORK == 'Q66458942')

wsrc = open(os.path.join(os.path.dirname(geo.__file__), 'workers.py'),
            encoding='utf-8').read()
check('the worker only claims it for own work',
      'OWN_WORK_TEMPLATES' in wsrc and 'SOURCE_PROPERTY' in wsrc)

print()
print('FAILURES:', ', '.join(fails) if fails else 'none')
sys.exit(1 if fails else 0)
