"""Export label, move-or-copy, and the RAW-only scope (0.18.5).

Harald's three notes, taken off the n: list:

  1. "Save to…" soll wieder "Export" heißen.
  2. Der Verschieben-Weg soll auch kopieren können - seine Vorgabe war
     ausdrücklich: eine Wahl im Dialog, kein dritter Knopf.
  3. Option "nur RAW + Sidecar" statt der ganzen Gruppe.

Point 3 undoes the reason 0.18.2 FORCED the whole group (half a moved pair
is worthless). So the whole group stays the default and the narrow scope is
a visible choice - the tests below pin exactly that.

Defended here:

  1. group_paths() keeps its old behaviour when nobody asks for a scope,
  2. the RAW scope drops the JPEG of a pair but never drops an entry that
     has no RAW at all,
  3. the dialog reports (folder, operation, scope) and refuses a folder
     that is not there,
  4. the default answer of the dialog is move + whole group, i.e. exactly
     what 0.18.2 did,
  5. copying through that dialog leaves the source in place and skips a
     name that is already in the target, while a move still refuses the
     whole run on a collision,
  6. the button says Export, and there is no third button.
"""
import os
import shutil
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import Cammello        # the shim; also puts the package on the path
from PyQt5.QtWidgets import QApplication, QDialog

from cammello import culling
from cammello.mw_culling import _TransferDialog, _FolderCopyWorker
from cammello.i18n import tr, set_language

fails = []


def check(name, cond, detail=''):
    print(('PASS' if cond else 'FAIL'), name, detail)
    if not cond:
        fails.append(name)


check('the shim still exposes the package', hasattr(Cammello, 'main'))

app = QApplication.instance() or QApplication([])


class Item:
    """The four attributes group_paths reads off a strip entry."""

    def __init__(self, raw=None, jpg=None, sidecar=None):
        self.raw_path = raw
        self.jpg_path = jpg
        self.display_path = raw or jpg
        self.sidecar_path = sidecar


# ── 1./2. the scope ──────────────────────────────────────────────────────────

pair = Item('/c/IMG_1.CR3', '/c/IMG_1.JPG', '/c/IMG_1.xmp')
check('no scope given = the whole group, exactly as in 0.18.2',
      culling.group_paths(pair)
      == ['/c/IMG_1.CR3', '/c/IMG_1.JPG', '/c/IMG_1.xmp'],
      str(culling.group_paths(pair)))
check('the default constant is the group',
      culling.group_paths(pair, culling.SCOPE_GROUP)
      == culling.group_paths(pair))
check('the RAW scope leaves the JPEG behind',
      culling.group_paths(pair, culling.SCOPE_RAW)
      == ['/c/IMG_1.CR3', '/c/IMG_1.xmp'],
      str(culling.group_paths(pair, culling.SCOPE_RAW)))

jpeg_only = Item(None, '/c/IMG_2.JPG')
check('an entry without a RAW still travels under the RAW scope',
      culling.group_paths(jpeg_only, culling.SCOPE_RAW) == ['/c/IMG_2.JPG'],
      str(culling.group_paths(jpeg_only, culling.SCOPE_RAW)))

raw_only = Item('/c/IMG_3.CR3', None, '/c/IMG_3.xmp')
check('a RAW without a JPEG is the same under both scopes',
      culling.group_paths(raw_only, culling.SCOPE_RAW)
      == culling.group_paths(raw_only, culling.SCOPE_GROUP)
      == ['/c/IMG_3.CR3', '/c/IMG_3.xmp'])

dup = Item('/c/IMG_4.CR3', '/c/IMG_4.CR3', '/c/IMG_4.xmp')
check('no path twice, whatever the scope',
      len(set(culling.group_paths(dup))) == len(culling.group_paths(dup)))


# ── 3./4. the dialog ─────────────────────────────────────────────────────────

target = tempfile.mkdtemp()
dlg = _TransferDialog(None, target)
check('the dialog opens on move + whole group (the 0.18.2 answer)',
      dlg.move_rb.isChecked() and dlg.group_rb.isChecked()
      and not dlg.copy_rb.isChecked() and not dlg.raw_rb.isChecked())
dest, move, scope = dlg.result_values()
check('the default answer is the old behaviour',
      (dest, move, scope) == (target, True, culling.SCOPE_GROUP),
      f'{dest!r} {move} {scope}')

dlg.copy_rb.setChecked(True)
dlg.raw_rb.setChecked(True)
dest, move, scope = dlg.result_values()
check('copy + RAW scope is reported back',
      move is False and scope == culling.SCOPE_RAW)

# The refusal path shows a modal warning; swap it out, the point here is
# that accept() does NOT happen.
import cammello.mw_culling as mwc                     # noqa: E402
warned = []
_real_warning = mwc.QMessageBox.warning
mwc.QMessageBox.warning = staticmethod(
    lambda *a, **k: warned.append(a[2] if len(a) > 2 else ''))

dlg.dest_edit.setText(os.path.join(target, 'does-not-exist'))
dlg._accept_if_valid()
check('the refusal says so instead of failing silently', bool(warned))
check('a folder that is not there is refused', dlg.result() != QDialog.Accepted)
dlg.dest_edit.setText(target)
dlg._accept_if_valid()
check('an existing folder is accepted', dlg.result() == QDialog.Accepted)
mwc.QMessageBox.warning = _real_warning
dlg.deleteLater()


# ── 5. copy vs move through the worker ───────────────────────────────────────

class Log:
    def info(self, *a, **k):
        pass
    warning = error = info


src = tempfile.mkdtemp()
dst = tempfile.mkdtemp()
paths = []
for name in ('IMG_9.CR3', 'IMG_9.xmp'):
    p = os.path.join(src, name)
    with open(p, 'w', encoding='utf-8') as fh:
        fh.write(name)
    paths.append(p)

worker = _FolderCopyWorker(paths, dst, Log(), move=False)
worker.run()
check('copying leaves the source in place',
      all(os.path.exists(p) for p in paths))
check('copying puts the files in the target',
      sorted(os.listdir(dst)) == ['IMG_9.CR3', 'IMG_9.xmp'],
      str(sorted(os.listdir(dst))))

# A name already in the target: a COPY skips it (the source is safe),
# a MOVE is refused before it starts (that guard lives in the dialog path,
# so it is checked through move_collisions).
before = open(os.path.join(dst, 'IMG_9.CR3'), encoding='utf-8').read()
with open(os.path.join(dst, 'IMG_9.CR3'), 'w', encoding='utf-8') as fh:
    fh.write('older export, must survive')
worker2 = _FolderCopyWorker(paths, dst, Log(), move=False)
worker2.run()
check('a copy never overwrites what is already there',
      open(os.path.join(dst, 'IMG_9.CR3'),
           encoding='utf-8').read() == 'older export, must survive')
check('and the source is still there afterwards',
      all(os.path.exists(p) for p in paths), before[:0] or '')
check('a move would be refused on the same collision',
      culling.move_collisions(paths, dst) == ['IMG_9.CR3', 'IMG_9.xmp'],
      str(culling.move_collisions(paths, dst)))

# The RAW scope end to end: only the RAW and the sidecar travel.
src2 = tempfile.mkdtemp()
dst2 = tempfile.mkdtemp()
for name in ('IMG_8.CR3', 'IMG_8.JPG', 'IMG_8.xmp'):
    with open(os.path.join(src2, name), 'w', encoding='utf-8') as fh:
        fh.write(name)
item = Item(os.path.join(src2, 'IMG_8.CR3'),
            os.path.join(src2, 'IMG_8.JPG'),
            os.path.join(src2, 'IMG_8.xmp'))
narrow = culling.group_paths(item, culling.SCOPE_RAW)
_FolderCopyWorker(narrow, dst2, Log(), move=True).run()
check('the RAW scope moves RAW + sidecar only',
      sorted(os.listdir(dst2)) == ['IMG_8.CR3', 'IMG_8.xmp'],
      str(sorted(os.listdir(dst2))))
check('and the JPEG really stayed behind',
      os.listdir(src2) == ['IMG_8.JPG'], str(os.listdir(src2)))


# ── 6. the label, and no third button ────────────────────────────────────────

check('the export button is called Export again', tr('Export…') == 'Export…')
set_language('de')
check('German says Export too', tr('Export…') == 'Export…')
check('the move button keeps its name', tr('Move to…') == 'Verschieben nach…',
      tr('Move to…'))
set_language('en')

mw = open(os.path.join(os.path.dirname(culling.__file__), 'mw_culling.py'),
          encoding='utf-8').read()
check('no "Save to…" left in the code', "tr('Save to…')" not in mw)
check('no third button was added',
      mw.count("QPushButton(tr('Move to…'))") == 1
      and "tr('Copy to…')" not in mw)

for d in (target, src, dst, src2, dst2):
    shutil.rmtree(d, ignore_errors=True)

print()
print('FAILURES:', ', '.join(fails) if fails else 'none')
sys.exit(1 if fails else 0)
