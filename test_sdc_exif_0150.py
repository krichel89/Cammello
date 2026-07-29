"""Required-field dots, the collapsed group, and capture-settings SDC
(0.15.0)."""
import os
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtWidgets import QApplication

import Cammello
from cammello import exif
from cammello.logging_setup import setup_logging

app = QApplication(sys.argv)
logger, emitter, gui_handler, log_path = setup_logging()
w = Cammello.MainWindow(logger, emitter, gui_handler, log_path)

fails = []


def check(name, cond, detail=''):
    if cond:
        print('PASS', name, detail)
    else:
        print('FAIL', name, detail)
        fails.append(name)


# ── the collapsed group and its dots ─────────────────────────────────────────
grp = w._settings_group
check('Author and license starts collapsed', not grp.isChecked())

w.author_edit.setText('')
w.source_edit.setText('')
w.license_edit.setText('')
w._refresh_required_marks()
check('empty required fields raise the group dot', grp.attention())
lbl = w._label_for(grp, w.author_edit)
check('the empty field label carries the dot',
      lbl is not None and lbl.text().startswith('\u25cf'),
      lbl.text() if lbl else 'no label')

w.author_edit.setText('[[User:Seewolf|Harald Krichel]]')
w.source_edit.setText('{{own}}')
w.license_edit.setText('{{Cc-by-sa-4.0}}')
check('filling all three clears the group dot', not grp.attention())
check('and the field label loses its dot',
      lbl is not None and not lbl.text().startswith('\u25cf'))

w.source_edit.setText('')
check('emptying one raises it again', grp.attention())
w.source_edit.setText('{{own}}')

# ── capture settings from a real JPEG ────────────────────────────────────────
try:
    from PIL import Image
    import piexif  # noqa: F401 - only to check availability
    HAVE_PIEXIF = True
except ImportError:
    HAVE_PIEXIF = False

d = tempfile.mkdtemp()
jpg = os.path.join(d, 'shot.jpg')
if HAVE_PIEXIF:
    import piexif
    from PIL import Image
    exif_bytes = piexif.dump({'Exif': {
        piexif.ExifIFD.ExposureTime: (1, 250),
        piexif.ExifIFD.FNumber: (28, 10),
        piexif.ExifIFD.ISOSpeedRatings: 400,
        piexif.ExifIFD.FocalLength: (85, 1),
    }})
    Image.new('RGB', (8, 8)).save(jpg, exif=exif_bytes)
    cap = exif.read_capture_settings(jpg, logger)
    check('exposure time is read', abs(cap.get('exposure_time', 0) - 0.004) < 1e-9,
          str(cap))
    check('f-number is read', abs(cap.get('f_number', 0) - 2.8) < 1e-9)
    check('ISO is read', cap.get('iso') == 400)
    check('focal length is read', cap.get('focal_length') == 85)
else:
    print('SKIP capture settings from a real JPEG - piexif unavailable')

check('a file without EXIF yields an empty dict',
      exif.read_capture_settings(os.path.join(d, 'missing.jpg'), logger)
      == {})

# ── quantity claims in the API layer ─────────────────────────────────────────
amt = '%+.10g' % 0.004
check('the quantity amount is a signed string', amt == '+0.004', amt)
amt2 = '%+.10g' % 85.0
check('whole numbers stay clean', amt2 == '+85', amt2)

# The worker maps the four keys to the right properties.
from cammello import workers as workers_mod
src = open(os.path.join(os.path.dirname(workers_mod.__file__),
                        'workers.py'), encoding='utf-8').read()
for pair in ("'exposure_time', 'P6757', 'Q11574'",
             "'f_number', 'P6790', None",
             "'iso', 'P6789', None",
             "'focal_length', 'P2151', 'Q174789'"):
    check(f'worker maps ({pair.split(",")[0].strip()})', pair in src)
check('the API layer shapes quantity claims',
      "value[0] == 'quantity'" in open(
          os.path.join(os.path.dirname(workers_mod.__file__), 'api.py'),
          encoding='utf-8').read())

# ── the settings switch ──────────────────────────────────────────────────────
check('the settings page offers the capture switch',
      hasattr(w, 'exif_capture_cb'))
check('it defaults to on', w.exif_capture_cb.isChecked())



# ── camera map (appended, 0.15.0 round 2) ────────────────────────────────────
from cammello import camera_map

n_cams, n_lenses = camera_map.counts()
check('the camera table is loaded and non-trivial', n_cams > 5000,
      f'{n_cams} cameras, {n_lenses} lenses')
check('the R8 example maps to its item',
      camera_map.camera_qid('Canon', 'Canon EOS R8') == 'Q116742776')
check('an unknown camera yields None',
      camera_map.camera_qid('Nokame', 'Gibtsnicht 9000') is None)
check('ambiguous strings are NOT in the table',
      camera_map.camera_qid(None, 'DigitalCAM') is None)
check('the lens list starts empty', camera_map.lens_qid('whatever') is None)

if HAVE_PIEXIF:
    import piexif
    from PIL import Image
    jpg2 = os.path.join(d, 'r8.jpg')
    exif_bytes = piexif.dump({
        '0th': {piexif.ImageIFD.Make: b'Canon',
                piexif.ImageIFD.Model: b'Canon EOS R8'},
        'Exif': {piexif.ExifIFD.LensModel: b'RF85mm F2 MACRO IS STM'},
    })
    Image.new('RGB', (8, 8)).save(jpg2, exif=exif_bytes)
    ids = exif.read_camera_ids(jpg2, logger)
    check('make/model/lens come out of the file',
          ids.get('make') == 'Canon' and ids.get('model') == 'Canon EOS R8'
          and ids.get('lens_model') == 'RF85mm F2 MACRO IS STM', str(ids))
    check('and the model maps to the item',
          camera_map.camera_qid(ids.get('make'), ids.get('model'))
          == 'Q116742776')

# The worker wires camera, lens, inception and media type.
wsrc = open(os.path.join(os.path.dirname(workers_mod.__file__),
                         'workers.py'), encoding='utf-8').read()
for needle in ("camera_map.camera_qid", "camera_map.lens_qid",
               "('P571', ('time'", "('P1163', ('string'"):
    check(f'worker carries {needle.split("(")[0] or needle}', needle in wsrc,
          needle)
asrc = open(os.path.join(os.path.dirname(workers_mod.__file__),
                         'api.py'), encoding='utf-8').read()
check('the API shapes time claims', "value[0] == 'time'" in asrc)
check('the API shapes string claims', "value[0] == 'string'" in asrc)
check('day precision for inception', "'precision': 11" in asrc)

# ── the upload sends the EDITED copy (0.15.0) ────────────────────────────────
from cammello import edits as edits_mod
from cammello.workers import UploadWorker


class _NoApi:
    log = logger


if HAVE_PIEXIF or True:
    from PIL import Image as _Img
    up = os.path.join(d, 'upload.jpg')
    _Img.new('RGB', (400, 300), (200, 30, 30)).save(up)

    w_plain = UploadWorker(_NoApi(), [], '', False, edits_store={})
    check('an unedited file is uploaded as it is',
          w_plain._path_to_send(up, 'upload.jpg') == up)

    store = {}
    edits_mod.set_crop(store, up, (0.1, 0.1, 0.5, 0.5))
    w_edit = UploadWorker(_NoApi(), [], '', False, edits_store=store)
    sent = w_edit._path_to_send(up, 'upload.jpg')
    check('an edited file is uploaded as a rendered copy', sent != up,
          os.path.basename(sent))
    if sent != up:
        check('and the copy really carries the crop',
              _Img.open(sent).size == (200, 150), str(_Img.open(sent).size))
    check('the source path is untouched (metadata still read from it)',
          os.path.exists(up) and _Img.open(up).size == (400, 300))
    w_edit._cleanup_edit_tmp()
    check('the temporary copy is removed afterwards', not os.path.exists(sent))

# ── version bump ─────────────────────────────────────────────────────────────
from cammello.constants import __version__
# Not pinned to one number: this file outlives the version it was born in.
# What has to hold is that the three places AGREE - the recurring mistake
# is bumping constants.py and forgetting release.sh.
root = os.path.dirname(os.path.dirname(workers_mod.__file__))
rel_path = os.path.join(root, 'release.sh')
if os.path.exists(rel_path):
    rel = open(rel_path, encoding='utf-8').read()
    check('release.sh carries the current version',
          f'VERSION="{__version__}"' in rel, __version__)
    notes = 'notes_' + __version__.replace('.', '') + '.md'
    check('release.sh points at the matching notes',
          f'NOTES_FILE="{notes}"' in rel, notes)
    check('and those notes exist', os.path.exists(os.path.join(root, notes)))

print()
print('FAILURES:', ', '.join(fails) if fails else 'none')
sys.exit(1 if fails else 0)
