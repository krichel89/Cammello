"""Import straight from a camera whose card is never mounted (0.18.3).

Harald: "Die Karten in der Kamera (hier: Canon R5 und R6) erscheinen nicht
im Finder oder explorer. Lightroom kann aber auf sie zugreifen. Das soll
Cammello auch können." - "ja, neues Modul. Als Backup für fehlenden
Kartenleser, für alle Plattformen."

What can be defended without hardware is the PLANNING half, and that is
where the damage would be done anyway: overwriting an original, or
re-fetching two hundred files after a cancel. The transport half needs a
camera on a cable and is verified by Harald.

Defended here:

  1. camera.py stays Qt-free (it is the plain-logic layer, like edits.py),
  2. wanted() takes RAW/JPEG/sidecar names and refuses the card's own
     bookkeeping files,
  3. scan_dest() reports names and sizes without opening a file,
  4. plan_import() skips what is already there byte-for-byte (this is what
     makes a cancelled import resumable) and never plans an overwrite,
  5. a name clash - same name, different size, two cards - is reported,
     not renamed and not overwritten,
  6. downloads go through a .part file, so a broken transfer cannot leave a
     short file that the next run would mistake for a finished one,
  7. the Windows path fails with an instruction, not a traceback,
  8. the wiring in mw_culling exists under the names the handlers use.
"""
import ast
import os
import shutil
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import Cammello        # the shim; also puts the package on the path
from cammello import camera

fails = []


def check(name, cond, detail=''):
    print(('PASS' if cond else 'FAIL'), name, detail)
    if not cond:
        fails.append(name)


check('the shim still exposes the package', hasattr(Cammello, 'main'))


# ── 1. no Qt in the logic module ─────────────────────────────────────────────

src = open(os.path.join(os.path.dirname(camera.__file__), 'camera.py'),
           encoding='utf-8').read()
tree = ast.parse(src)
imported = set()
for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        imported.update(a.name.split('.')[0] for a in node.names)
    elif isinstance(node, ast.ImportFrom) and node.module:
        imported.add(node.module.split('.')[0])
check('camera.py imports no Qt', 'PyQt5' not in imported, str(sorted(imported)))


# ── 2. what belongs on the way in ────────────────────────────────────────────

check('CR3 is wanted', camera.wanted('IMG_0042.CR3'))
check('lowercase raw is wanted too', camera.wanted('img_0042.cr3'))
check('JPEG is wanted', camera.wanted('IMG_0042.JPG'))
check('a sidecar is wanted', camera.wanted('IMG_0042.xmp'))
check('MP4 is wanted', camera.wanted('MVI_0042.MP4'))
check('the card index is not wanted', not camera.wanted('MEDIAPRO.XML'))
check('a folder-ish name is not wanted', not camera.wanted('DCIM'))


# ── 3./4./5. planning ────────────────────────────────────────────────────────

dest = tempfile.mkdtemp()
with open(os.path.join(dest, 'IMG_0001.CR3'), 'wb') as fh:
    fh.write(b'x' * 100)
with open(os.path.join(dest, 'IMG_0003.CR3'), 'wb') as fh:
    fh.write(b'x' * 7)
os.mkdir(os.path.join(dest, 'subfolder'))

existing = camera.scan_dest(dest)
check('scan_dest reports names and sizes',
      existing.get('img_0001.cr3') == 100 and existing.get('img_0003.cr3') == 7,
      str(existing))
check('scan_dest ignores folders', 'subfolder' not in existing)
check('scan_dest survives a missing folder',
      camera.scan_dest(os.path.join(dest, 'nope')) == {})

card = [
    camera.CameraFile('/store/DCIM/100EOSR5', 'IMG_0001.CR3', 100),  # there
    camera.CameraFile('/store/DCIM/100EOSR5', 'IMG_0002.CR3', 200),  # new
    camera.CameraFile('/store/DCIM/100EOSR5', 'IMG_0003.CR3', 300),  # clash
    camera.CameraFile('/store/DCIM/101EOSR5', 'IMG_0004.JPG', 400),  # new
]
todo, skipped, conflicts = camera.plan_import(card, existing)
check('only the unseen files are planned',
      [f.name for f in todo] == ['IMG_0002.CR3', 'IMG_0004.JPG'],
      str([f.name for f in todo]))
check('an identical file counts as already imported',
      [f.name for f in skipped] == ['IMG_0001.CR3'])
check('same name, different size is a clash',
      [f.name for f in conflicts] == ['IMG_0003.CR3'])
check('nothing in the plan would overwrite',
      not any(f.key in existing for f in todo))

# Resuming: after the two new ones arrive, a second run has nothing to do.
for f in todo:
    with open(os.path.join(dest, f.name), 'wb') as fh:
        fh.write(b'y' * f.size)
todo2, skipped2, conflicts2 = camera.plan_import(card, camera.scan_dest(dest))
check('a second run after a cancel copies nothing twice',
      todo2 == [] and len(skipped2) == 3 and len(conflicts2) == 1,
      f'{len(todo2)}/{len(skipped2)}/{len(conflicts2)}')

# A zero-length file on the card is never treated as "already there" - the
# size is the only evidence there is, and 0 is what a failed stat looks like.
zero = [camera.CameraFile('/store', 'IMG_0009.CR3', 0)]
with open(os.path.join(dest, 'IMG_0009.CR3'), 'wb') as fh:
    fh.write(b'')
todo3, skipped3, conflicts3 = camera.plan_import(zero, camera.scan_dest(dest))
check('a file of unknown size is a clash, not a skip',
      todo3 == [] and skipped3 == [] and len(conflicts3) == 1)

check('total_bytes adds up', camera.total_bytes(card) == 1000)
check('format_size is short', camera.format_size(1536) == '1.5 KB',
      camera.format_size(1536))


# ── 6. the .part rule ────────────────────────────────────────────────────────

check('downloads are staged under .part',
      camera.part_path('/tmp/IMG_0001.CR3') == '/tmp/IMG_0001.CR3.part')
check('a .part leftover is not mistaken for an image',
      not camera.wanted('IMG_0001.CR3.part'))


# ── 7. the platform gates ────────────────────────────────────────────────────

real_platform = sys.platform
try:
    sys.platform = 'win32'
    check('Windows picks the WPD backend',
          camera.platform_backend() == camera.BACKEND_WPD)
    problem = camera.backend_problem()
    check('Windows says what to do instead',
          bool(problem) and 'card reader' in problem, str(problem))
    raised = None
    try:
        camera.make_backend()
    except camera.CameraError as exc:
        raised = exc
    check('Windows raises CameraError, not a traceback', raised is not None)
finally:
    sys.platform = real_platform

check('this platform picks a backend',
      camera.platform_backend() in (camera.BACKEND_GPHOTO2,
                                    camera.BACKEND_WPD))
if not sys.platform.startswith('win'):
    problem = camera.backend_problem()
    if problem:
        check('a missing gphoto2 names the install command',
              'pip install gphoto2' in problem, problem)
    else:
        check('gphoto2 present: a backend can be built',
              camera.make_backend().name == camera.BACKEND_GPHOTO2)

check('the summary counts everything',
      camera.summary_text(3, 2, 1, 1) ==
      '3 copied, 2 already there, 1 name clash(es) left alone, 1 failed.',
      camera.summary_text(3, 2, 1, 1))
check('a clean run stays short', camera.summary_text(3, 0, 0, 0) ==
      '3 copied.')


# ── 8. the wiring exists under the expected names ────────────────────────────

mw = os.path.join(os.path.dirname(camera.__file__), 'mw_culling.py')
mw_tree = ast.parse(open(mw, encoding='utf-8').read())
names = {n.name for n in ast.walk(mw_tree)
         if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
for wanted_name in ('_CameraImportWorker', '_cull_import_from_camera',
                    '_cull_on_camera_ready', '_cull_on_camera_listing',
                    '_cull_on_camera_finished', '_cull_on_camera_fatal'):
    check(f'{wanted_name} exists', wanted_name in names)

from cammello.widgets import UploadProgressDialog
check('the progress dialog can learn its total later',
      hasattr(UploadProgressDialog, 'set_total')
      and hasattr(UploadProgressDialog, 'set_detail'))

shutil.rmtree(dest, ignore_errors=True)

print()
print('FAILURES:', ', '.join(fails) if fails else 'none')
sys.exit(1 if fails else 0)
