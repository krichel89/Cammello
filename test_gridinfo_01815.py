"""Daten im Grid, per i-Taste (0.18.15).

Harald: "Und ich muss im Grid die Daten anzeigen koennen, vielleicht per
Overlay" - gewaehlt: Dateizeit, Dateiname und Groesse, ein- und
ausschaltbar per Taste.

Der Punkt ist, dass es NICHTS kostet: der Scan stattet ohnehin jeden Namen
ab (fuer die Sortierung nach Aufnahmezeit seit 0.18.11), also faellt die
Groesse im selben stat mit an. Kein EXIF, keine geoeffnete CR3 - sonst
waere ein Bildschirm voller Kacheln ein Bildschirm voller Dateizugriffe.

Geprueft wird:

  1. der Scan traegt die Groesse ein, RAW plus JPEG bei einem Paar,
  2. die Textbausteine stimmen und halten leere Werte aus,
  3. jede Kachel traegt den Text, ohne dass er sichtbar waere,
  4. die i-Taste schaltet ihn an und wieder aus,
  5. ein Umschalten liest nichts neu ein.
"""
import os
import sys
import tempfile
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import Cammello        # the shim; also puts the package on the path
from cammello import culling

fails = []


def check(name, cond, detail=''):
    print(('PASS' if cond else 'FAIL'), name, detail)
    if not cond:
        fails.append(name)


check('the shim still exposes the package', hasattr(Cammello, 'main'))


# ── 1. the scan carries the size ─────────────────────────────────────────────

folder = tempfile.mkdtemp(prefix='cammello-grid-')
with open(os.path.join(folder, 'IMG_0001.JPG'), 'wb') as fh:
    fh.write(b'x' * 8_000_000)
with open(os.path.join(folder, 'IMG_0001.CR3'), 'wb') as fh:
    fh.write(b'x' * 45_000_000)
with open(os.path.join(folder, 'IMG_0002.JPG'), 'wb') as fh:
    fh.write(b'x' * 7_000_000)

items = culling.scan_folder(folder, {})
by_stem = {i.stem: i for i in items}
check('a pair counts both files',
      by_stem['IMG_0001'].size == 53_000_000,
      str(by_stem['IMG_0001'].size))
check('a single file counts once',
      by_stem['IMG_0002'].size == 7_000_000)
check('and the time is still there', by_stem['IMG_0001'].taken > 0)


# ── 2. the text ──────────────────────────────────────────────────────────────

check('bytes stay bytes', culling.size_text(999) == '999 B')
check('megabytes are rounded once',
      culling.size_text(45_300_000) == '45.3 MB', culling.size_text(45_300_000))
check('gigabytes too', culling.size_text(2_400_000_000) == '2.4 GB')


class Bare:
    taken = 0
    size = 0


check('an entry with neither gives an empty line',
      culling.item_info_text(Bare()) == '')


class Timed:
    taken = time.mktime((2026, 2, 14, 20, 5, 0, 0, 0, -1))
    size = 45_300_000


text = culling.item_info_text(Timed())
check('the line holds time and size',
      '20:05' in text and '45.3 MB' in text, text)


# ── 3. to 5. the grid ────────────────────────────────────────────────────────

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt, QEvent, QSettings
from PyQt5.QtGui import QKeyEvent, QImage
from cammello.constants import APP_NAME
from cammello.main_window import setup_logging

app = QApplication.instance() or QApplication(sys.argv)
_ts = QSettings(APP_NAME, 'Main')
_ts.setValue('feature_culling', True)
_ts.sync()
logger, emitter, gui_handler, log_path = setup_logging()
import logging as _logging
for _h in logger.handlers:
    if isinstance(_h, _logging.StreamHandler) and not hasattr(_h,
                                                              'baseFilename'):
        _h.setLevel(_logging.CRITICAL)

real = tempfile.mkdtemp(prefix='cammello-grid2-')
for i in range(3):
    img = QImage(400, 300, QImage.Format_RGB32)
    img.fill(0xFF224466 + i * 16)
    img.save(os.path.join(real, f'IMG_{i:04d}.JPG'), 'JPG', 80)

w = Cammello.MainWindow(logger, emitter, gui_handler, log_path)
if not hasattr(w, 'cull_strip'):                          # pragma: no cover
    print('SKIP - culling tab not built in this environment')
else:
    w._cull_open_folder(real)
    w._cull_decorate_visible() if hasattr(w, '_cull_decorate_visible') \
        else w._cull_decorate_row(0)
    row0 = w.cull_strip.item(0)
    info = row0.data(Qt.UserRole + 5)
    check('every row carries the info text', bool(info), str(info))
    check('the name is NOT in it - it has its own line',
          info and 'IMG_0000' not in info, str(info))
    check('but it is on the row', bool(row0.data(Qt.UserRole + 2)))
    check('and it stays hidden until asked for',
          not w._cull_delegate.show_info)

    before = row0.data(Qt.UserRole + 5)
    w._cull_key(QKeyEvent(QEvent.KeyPress, Qt.Key_I, Qt.NoModifier))
    check('i turns the line on', w._cull_delegate.show_info)
    check('and reads nothing new to do it',
          row0.data(Qt.UserRole + 5) == before)
    w._cull_key(QKeyEvent(QEvent.KeyPress, Qt.Key_I, Qt.NoModifier))
    check('i turns it off again', not w._cull_delegate.show_info)

    # The loupe overlay is the same switch, so the two cannot disagree.
    w._cull_key(QKeyEvent(QEvent.KeyPress, Qt.Key_I, Qt.NoModifier))
    check('the loupe overlay follows the same state',
          w._cull_show_exif and w._cull_delegate.show_info)

    w._cull_shutdown()

print()
print('FAILURES:', ', '.join(fails) if fails else 'none')
sys.exit(1 if fails else 0)
