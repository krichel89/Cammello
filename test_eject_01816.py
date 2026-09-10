"""Auswurftaste fuer die SD-Karte (0.18.16).

Harald: "Ich brauche fuer die SD-Karte noch eine Auswurftaste."

Nichts davon ist hier echt pruefbar - in der Sandbox gibt es keinen
Wechseldatentraeger und weder diskutil noch udisksctl noch PowerShell.
Geprueft wird darum das, was auch ohne Karte falsch sein koennte: welcher
Befehl auf welchem System gebaut wird, ob der Knopf nur bei einer Karte
angeht, und vor allem die REIHENFOLGE - schreiben, schliessen, aushaengen.
Genau daran scheitert ein Auswurf sonst: der Leser haelt noch Dateien
offen.

  1. volume_of() findet den Datentraeger zum Pfad, und nur einen echten,
  2. eject_command() baut je System den richtigen Befehl,
  3. eject_volume() bricht sauber ab, wenn es das Programm nicht gibt,
  4. der Knopf ist aus, solange der Ordner keine Karte ist,
  5. gedrueckt wird erst geschrieben, dann geschlossen, dann ausgehaengt,
  6. bei ungeschriebenen Bewertungen wird NICHT ausgehaengt,
  7. bleibt die Karte trotz Erfolgsmeldung eingehaengt, gilt das als
     Fehlschlag (Windows meldet den Auswurf, bevor er passiert ist).
"""
import os
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


# ── 1. which volume a path is on ─────────────────────────────────────────────

tmp = tempfile.mkdtemp(prefix='cammello-eject-')
card = os.path.join(tmp, 'EOS_DIGITAL')
deep = os.path.join(card, 'DCIM', '100EOSR5')
os.makedirs(deep)
decoy = os.path.join(tmp, 'EOS_DIGITAL-Backup')
os.makedirs(decoy)

real_volumes = camera.list_volumes
camera.list_volumes = lambda: {card}
check('a folder on the card reports the card',
      camera.volume_of(deep) == os.path.abspath(card), str(camera.volume_of(deep)))
check('a folder next to it does not',
      camera.volume_of(decoy) is None, str(camera.volume_of(decoy)))
check('and neither does a name that merely starts the same',
      camera.volume_of(card + '-Backup') is None)
check('no path, no volume', camera.volume_of('') is None)


# ── 2. the command per system ────────────────────────────────────────────────

real_platform = sys.platform
try:
    sys.platform = 'darwin'
    check('macOS uses diskutil eject',
          camera.eject_command('/Volumes/EOS') == ['diskutil', 'eject',
                                                   '/Volumes/EOS'],
          str(camera.eject_command('/Volumes/EOS')))
    sys.platform = 'linux'
    argv = camera.eject_command('/media/harald/EOS')
    check('Linux uses udisksctl without asking questions',
          argv[:2] == ['udisksctl', 'unmount']
          and '--no-user-interaction' in argv and argv[-1] ==
          '/media/harald/EOS', str(argv))
    sys.platform = 'win32'
    argv = camera.eject_command('E:\\')
    check('Windows falls back to the shell verb',
          argv[0] == 'powershell' and 'InvokeVerb' in argv[-1]
          and "'E:'" in argv[-1], str(argv[-1])[:80])
finally:
    sys.platform = real_platform


# ── 3. a missing tool is a message, not a crash ──────────────────────────────

saved_cmd = camera.eject_command
camera.eject_command = lambda v: ['definitely-not-a-real-command', v]
ok, detail = camera.eject_volume(card)
camera.eject_command = saved_cmd
check('a missing tool reports instead of raising',
      ok is False and 'not available' in detail, str(detail))


# ── 4. to 7. the button ──────────────────────────────────────────────────────

from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import QSettings
from PyQt5.QtGui import QImage
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

# Modal boxes hang the suite - the 0.13 lesson.
QMessageBox.warning = staticmethod(lambda *a, **k: None)
QMessageBox.information = staticmethod(lambda *a, **k: None)

for i in range(3):
    img = QImage(320, 240, QImage.Format_RGB32)
    img.fill(0xFF446688 + i * 16)
    img.save(os.path.join(deep, f'IMG_{i:04d}.JPG'), 'JPG', 75)

plain = tempfile.mkdtemp(prefix='cammello-plain-')
img = QImage(320, 240, QImage.Format_RGB32)
img.fill(0xFF112233)
img.save(os.path.join(plain, 'IMG_9000.JPG'), 'JPG', 75)

w = Cammello.MainWindow(logger, emitter, gui_handler, log_path)
if not hasattr(w, 'cull_eject_btn'):                      # pragma: no cover
    print('SKIP - culling tab not built in this environment')
else:
    w._cull_open_folder(plain)
    check('an ordinary folder leaves the button off',
          not w.cull_eject_btn.isEnabled())

    w._cull_open_folder(deep)
    check('a folder on a card turns it on', w.cull_eject_btn.isEnabled())
    check('and it knows which volume',
          w._cull_eject_volume == os.path.abspath(card))
    check('the card was opened whole (0.18.10)', len(w._cull_items) == 3)

    order = []
    real_flush = w._cull_wb.flush
    real_close = w._cull_close_folder

    def note_flush(timeout=30):
        order.append('flush')
        return real_flush(timeout)

    def note_close():
        order.append('close')
        return real_close()

    w._cull_wb.flush = note_flush
    w._cull_close_folder = note_close
    camera.eject_volume = lambda v, timeout=30: (order.append('eject')
                                                 or (True, ''))
    camera.still_mounted = lambda v: False

    w._cull_eject_card()
    # _cull_close_folder() flushes again on its way out, so the exact list
    # is flush, close, flush, eject. What matters is the ends: a write
    # first, the unmount last, and the close in between.
    check('written, closed, unmounted - in that order',
          order[0] == 'flush' and order[-1] == 'eject'
          and 'close' in order
          and order.index('close') < order.index('eject')
          and order.count('eject') == 1, str(order))
    check('the folder really is closed', w._cull_items == []
          and w.cull_strip.count() == 0)
    check('and the button goes off with it',
          not w.cull_eject_btn.isEnabled())

    # ── 6. unwritten ratings stop the eject ──────────────────────────────
    w._cull_open_folder(deep)
    order.clear()
    w._cull_wb.errors.append('disk full')
    w._cull_eject_card()
    check('a write error stops the eject', order == ['flush'], str(order))
    check('and the card stays open', len(w._cull_items) == 3)
    w._cull_wb.errors.clear()

    # ── 7. still mounted afterwards = failure ────────────────────────────
    order.clear()
    caught = []

    class Catch(_logging.Handler):
        def emit(self, record):
            caught.append(record)

    catcher = Catch(level=_logging.WARNING)
    logger.addHandler(catcher)
    camera.still_mounted = lambda v: True     # the shell verb lied
    w._cull_eject_card()
    logger.removeHandler(catcher)
    check('it still writes, closes and tries',
          order[0] == 'flush' and order[-1] == 'eject'
          and 'close' in order, str(order))
    check('a card that is still mounted is a failure, and says so',
          any(r.levelno >= _logging.WARNING and 'Eject' in r.getMessage()
              for r in caught),
          str([r.getMessage()[:40] for r in caught]))

    w._cull_wb.flush = real_flush
    w._cull_close_folder = real_close
    w._cull_shutdown()

camera.list_volumes = real_volumes

print()
print('FAILURES:', ', '.join(fails) if fails else 'none')
sys.exit(1 if fails else 0)
