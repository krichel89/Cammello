"""A card is opened as one shoot, not as three folders (0.18.10).

Harald: "und ich möchte die Ordner einer Karte zusammen angezeigt bekommen"

100EOSR5, 101EOSR5 and their successors are the camera's file-numbering
housekeeping, not the photographer's idea of an order. So opening any part
of a card - the volume, its DCIM folder, or one of the numbered folders -
opens the WHOLE card. An ordinary working folder is left exactly as it is:
this must not turn every folder into a recursive scan behind the user's
back.

The widening only happens when the caller left the scope open. A reload and
the automatic card open both pass an explicit scope, and an explicit scope
already knows what it wants.

Defended here:

  1. card_scope() finds the card from the volume, from DCIM, and from one
     of the numbered folders,
  2. and returns None for a working folder, however deep,
  3. opening a numbered folder shows the pictures of the OTHER folders too,
  4. opening an ordinary folder does not become recursive,
  5. the strip says which folder a picture is in, but only when there is
     more than one,
  6. an explicit scope is never widened.
"""
import os
import shutil
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import Cammello        # the shim; also puts the package on the path
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QSettings, QEventLoop, QTimer
from PyQt5.QtGui import QImage

from cammello import camera
from cammello.constants import APP_NAME

_ts = QSettings(APP_NAME, 'Main')
_ts.setValue('feature_culling', True)
_ts.sync()

fails = []


def check(name, cond, detail=''):
    print(('PASS' if cond else 'FAIL'), name, detail)
    if not cond:
        fails.append(name)


check('the shim still exposes the package', hasattr(Cammello, 'main'))

app = QApplication.instance() or QApplication([])


def spin(ms=200):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec_()


def picture(path, tint):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img = QImage(900, 600, QImage.Format_RGB32)
    img.fill(tint)
    img.save(path, 'JPG', 85)


card = tempfile.mkdtemp()
dcim = os.path.join(card, 'DCIM')
first = os.path.join(dcim, '100EOSR5')
second = os.path.join(dcim, '101EOSR5')
for i in range(3):
    picture(os.path.join(first, f'IMG_{i:04d}.JPG'), 0xFF224466 + i * 32)
for i in range(2):
    picture(os.path.join(second, f'IMG_{i + 50:04d}.JPG'), 0xFF664422 + i * 32)
picture(os.path.join(card, 'MISC', 'IMG_9000.JPG'), 0xFF888888)

work = tempfile.mkdtemp()
for i in range(2):
    picture(os.path.join(work, f'shoot_{i}.JPG'), 0xFF446622 + i * 32)
picture(os.path.join(work, 'archive', 'old.JPG'), 0xFF222222)


# ── 1./2. finding the card ───────────────────────────────────────────────────

check('from the volume', camera.card_scope(card) == dcim,
      str(camera.card_scope(card)))
check('from DCIM itself', camera.card_scope(dcim) == dcim)
check('from a numbered folder', camera.card_scope(first) == dcim,
      str(camera.card_scope(first)))
check('from the second numbered folder', camera.card_scope(second) == dcim)
check('a working folder is not a card', camera.card_scope(work) is None)
check('nor is a subfolder of one',
      camera.card_scope(os.path.join(work, 'archive')) is None)
check('an empty path is not a card', camera.card_scope('') is None)
check('a path that does not exist is not a card',
      camera.card_scope(os.path.join(work, 'nope', 'deeper')) is None)


# ── the window ───────────────────────────────────────────────────────────────

from cammello.logging_setup import setup_logging          # noqa: E402
import logging                                            # noqa: E402

logger, emitter, gui_handler, log_path = setup_logging()
for h in logger.handlers:
    h.setLevel(logging.CRITICAL)

w = Cammello.MainWindow(logger, emitter, gui_handler, log_path)
w.resize(1200, 800)
w.show()
w.tabs.setCurrentWidget(w._cull_tab_widget)
app.processEvents()

# The subfolder checkbox is OFF: the widening must not depend on it.
w.cull_subfolders_cb.setChecked(False)
app.processEvents()


# ── 4. an ordinary folder stays an ordinary folder ───────────────────────────

w._cull_open_folder(work)
app.processEvents()
spin()
check('a working folder is read flat',
      [os.path.basename(i.display_path) for i in w._cull_items]
      == ['shoot_0.JPG', 'shoot_1.JPG'],
      str([os.path.basename(i.display_path) for i in w._cull_items]))
check('and the open folder is the one that was asked for',
      os.path.normpath(w._cull_folder) == os.path.normpath(work))
check('one folder, so no folder note in the row',
      len(w._cull_folders) == 1, str(w._cull_folders))
w._cull_decorate_row(0)
check('and none in the tooltip either',
      'Folder:' not in (w.cull_strip.item(0).toolTip() or ''),
      repr(w.cull_strip.item(0).toolTip()))


# 0.18.11: opening DCIM itself must find the pictures too. DCIM holds none
# of its own, so a flat scan of it came back empty - fixed by making the
# card scope always recursive.
w._cull_open_folder(dcim)
app.processEvents()
spin()
check('opening DCIM itself finds the pictures', len(w._cull_items) == 5,
      str(len(w._cull_items)))


# ── 3./5. one numbered folder brings the whole card ──────────────────────────

w._cull_open_folder(first)
app.processEvents()
spin()
names = sorted(os.path.basename(i.display_path) for i in w._cull_items)
check('opening 100EOSR5 shows 101EOSR5 as well',
      names == ['IMG_0000.JPG', 'IMG_0001.JPG', 'IMG_0002.JPG',
                'IMG_0050.JPG', 'IMG_0051.JPG'], str(names))
check('the open folder became the card',
      os.path.normpath(w._cull_folder) == os.path.normpath(dcim),
      w._cull_folder)
check('two folders are counted', len(w._cull_folders) == 2,
      str(w._cull_folders))
check('MISC is not part of the card',
      not any('MISC' in i.display_path for i in w._cull_items))

w._cull_decorate_row(0)
tip = w.cull_strip.item(0).toolTip() or ''
check('the row says which folder the picture is in',
      'Folder:' in tip and ('100EOSR5' in tip or '101EOSR5' in tip),
      repr(tip))
w._cull_show_index(0)
app.processEvents()
check('and the status line names the folder count',
      'folders' in w.cull_status.text(), w.cull_status.text())
check('and the subfolder of the current picture',
      'EOSR5/' in w.cull_status.text(), w.cull_status.text())

# The volume itself is the same card.
w._cull_open_folder(card)
app.processEvents()
spin()
check('opening the volume opens the same card',
      os.path.normpath(w._cull_folder) == os.path.normpath(dcim)
      and len(w._cull_items) == 5,
      f'{w._cull_folder} / {len(w._cull_items)}')


# ── 6. an explicit scope is left alone ───────────────────────────────────────

w._cull_open_folder(first, False)
app.processEvents()
spin()
check('an explicit flat scope stays on the folder it was given',
      os.path.normpath(w._cull_folder) == os.path.normpath(first)
      and len(w._cull_items) == 3,
      f'{w._cull_folder} / {len(w._cull_items)}')
check('and reports one folder', len(w._cull_folders) == 1)

w._cull_reload_folder()
app.processEvents()
spin()
check('a reload keeps that scope too',
      os.path.normpath(w._cull_folder) == os.path.normpath(first)
      and len(w._cull_items) == 3,
      f'{w._cull_folder} / {len(w._cull_items)}')

w._cull_shutdown()
for d in (card, work):
    shutil.rmtree(d, ignore_errors=True)

print()
print('FAILURES:', ', '.join(fails) if fails else 'none')
sys.exit(1 if fails else 0)
