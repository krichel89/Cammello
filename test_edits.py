"""0.13 foundation: non-destructive edits (edits.py) - pure logic, no Qt.

Covers the EV LUT, crop validation and box math, the QSettings round-trip,
record cleanup, real rendering of an edited JPEG (crop + EV + EXIF), and the
upload-path substitution. Run as a file.
"""
import os
import sys
import tempfile

FAILURES = []


def check(name, cond, detail=''):
    print(('PASS ' if cond else 'FAIL ') + name, detail)
    if not cond:
        FAILURES.append(name)


class FakeSettings:
    """Just enough of QSettings for the store: a string value store."""
    def __init__(self):
        self.d = {}

    def value(self, key, default=None):
        return self.d.get(key, default)

    def setValue(self, key, val):
        self.d[key] = val

    def sync(self):
        pass


def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from cammello import edits

    # ── EV LUT ──────────────────────────────────────────────────────────
    lut0 = edits._ev_lut(0.0)
    check('EV 0 is the identity table', lut0 == list(range(256)))
    lut_up = edits._ev_lut(1.0)
    lut_dn = edits._ev_lut(-1.0)
    check('every LUT is monotonic non-decreasing',
          all(lut_up[i] <= lut_up[i + 1] for i in range(255))
          and all(lut_dn[i] <= lut_dn[i + 1] for i in range(255)))
    check('+EV brightens the midtones', lut_up[128] > 128)
    check('-EV darkens the midtones', lut_dn[128] < 128)
    check('highlights are clipped, not wrapped',
          lut_up[255] == 255 and 0 <= lut_dn[0])

    # ── Crop validation ─────────────────────────────────────────────────
    check('a full frame is not a crop', edits._valid_crop((0, 0, 1, 1)) is None)
    check('a real box passes',
          edits._valid_crop((0.1, 0.1, 0.5, 0.5)) == (0.1, 0.1, 0.5, 0.5))
    check('a box running past the edge is rejected',
          edits._valid_crop((0.6, 0.6, 0.6, 0.6)) is None)
    check('negative origin is rejected',
          edits._valid_crop((-0.1, 0, 0.5, 0.5)) is None)
    check('zero size is rejected',
          edits._valid_crop((0, 0, 0, 0.5)) is None)
    check('garbage is rejected, not crashed',
          edits._valid_crop('nonsense') is None)

    # ── EV clamping ─────────────────────────────────────────────────────
    check('EV clamps to the ±3 range',
          edits._clamp_ev(99) == 3.0 and edits._clamp_ev(-99) == -3.0)
    check('non-numeric EV becomes 0', edits._clamp_ev('x') == 0.0)

    # ── Store round-trip and cleanup ────────────────────────────────────
    s = FakeSettings()
    e = edits.load_edits(s)
    check('an empty store loads as empty', e == {})
    edits.set_crop(e, '/a/photo.jpg', (0.1, 0.1, 0.6, 0.6))
    edits.set_ev(e, '/a/photo.jpg', 1.5)
    edits.set_ev(e, '/b/other.jpg', -0.7)
    edits.save_edits(s, e)
    e2 = edits.load_edits(s)
    check('crop and EV survive a save/load round-trip',
          edits.get_edit(e2, '/a/photo.jpg') == {'crop': [0.1, 0.1, 0.6, 0.6],
                                                 'ev': 1.5})
    check('an EV-only record round-trips too',
          edits.get_edit(e2, '/b/other.jpg') == {'ev': -0.7})
    edits.set_ev(e2, '/a/photo.jpg', 0.0)
    check('clearing EV keeps the crop',
          edits.get_edit(e2, '/a/photo.jpg') == {'crop': [0.1, 0.1, 0.6, 0.6]})
    edits.set_crop(e2, '/a/photo.jpg', None)
    check('clearing the last edit removes the record',
          not edits.has_edit(e2, '/a/photo.jpg'))

    # ── Defensive loading ───────────────────────────────────────────────
    bad = FakeSettings()
    bad.d['edits'] = '{not valid json'
    check('corrupt JSON loads as empty', edits.load_edits(bad) == {})
    bad.d['edits'] = '{"/x": {"ev": 99, "crop": [0.1,0.1,0.5,0.5]}}'
    loaded = edits.load_edits(bad)
    check('an out-of-range EV is clamped on load',
          loaded.get('/x', {}).get('ev') == 3.0)
    bad.d['edits'] = '{"/y": {"ev": 0, "crop": null}}'
    check('a record with no real edit is dropped on load',
          '/y' not in edits.load_edits(bad))

    # ── Real rendering ──────────────────────────────────────────────────
    try:
        from PIL import Image
    except ImportError:
        print('\n(PIL missing - skipping render checks)')
        print('ALL EDIT CHECKS PASSED' if not FAILURES
              else f'FAILURES: {FAILURES}')
        return 1 if FAILURES else 0

    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, 'shot.jpg')
        img = Image.new('RGB', (400, 300), (128, 128, 128))
        ex = img.getexif()
        ex[0x010f] = 'TestCam'
        img.save(src, exif=ex.tobytes(), quality=95)

        out = os.path.join(tmp, 'out.jpg')
        rendered = edits.render_edited(
            src, {'crop': [0.25, 0.25, 0.5, 0.5], 'ev': 1.0}, out)
        check('an edited copy is rendered', rendered == out
              and os.path.exists(out))
        res = Image.open(out)
        check('the crop halves each dimension',
              abs(res.size[0] - 200) <= 2 and abs(res.size[1] - 150) <= 2,
              str(res.size))
        check('the +1 EV brightens the pixels',
              res.getpixel((100, 75))[0] > 128)
        check('the EXIF is carried over',
              bool(Image.open(out).info.get('exif')))

        check('a no-op record renders nothing',
              edits.render_edited(src, {'ev': 0.0}, out + '2') is None)

        # Upload-path substitution.
        e3 = {}
        edits.set_ev(e3, src, 0.7)
        p = edits.effective_upload_path(src, e3, tmp)
        check('an edited file uploads a rendered copy',
              p != src and p.endswith('_edit.jpg') and os.path.exists(p))
        check('an unedited file uploads its original path',
              edits.effective_upload_path('/nope.jpg', {}, tmp) == '/nope.jpg')

        # A crop-only edit on a bright image: EV=0 leaves the value alone.
        white = os.path.join(tmp, 'white.jpg')
        Image.new('RGB', (100, 100), (200, 200, 200)).save(white)
        o2 = os.path.join(tmp, 'w.jpg')
        edits.render_edited(white, {'crop': [0, 0, 0.5, 0.5]}, o2)
        check('a crop-only edit leaves the tone unchanged',
              abs(Image.open(o2).getpixel((10, 10))[0] - 200) <= 3)

    print('\n' + ('ALL EDIT CHECKS PASSED' if not FAILURES
                  else f'FAILURES: {FAILURES}'))
    return 1 if FAILURES else 0


if __name__ == '__main__':
    sys.exit(main())
