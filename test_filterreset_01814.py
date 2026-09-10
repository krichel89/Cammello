"""Filter aufheben, und wo die Ordnerdialoge anfangen (0.18.14).

Harald: "wenn eine SD Karte neu geladen wird oder das Verzeichnis
gewechselt wird muss der Filter aufgehoben werden. Dafuer haette ich auch
gerne einen Schalter" und: "Bei 'Open' soll zuerst eine SD-Karte o.ae.
vorgeschlagen werden, bei 'Move to' zuerst ein Bilder-Systemordner. Dann
natuerlich merken."

Geprueft wird:

  1. der Schalter hebt Sterne, Ausschuss-Haken und Farben zusammen auf,
  2. er ist aus, solange nichts gefiltert ist,
  3. jedes Oeffnen und jedes Neuladen hebt den Filter auf,
  4. suggest_card() nimmt einen Datentraeger nur mit DCIM,
  5. der Oeffnen-Dialog faengt bei der Karte an, sonst beim gemerkten
     Ordner,
  6. Verschieben faengt beim Bilder-Ordner an und merkt sich sein Ziel
     getrennt vom Oeffnen-Ordner.
"""
import os
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import Cammello        # the shim; also puts the package on the path
from cammello import camera
from cammello import constants

fails = []


def check(name, cond, detail=''):
    print(('PASS' if cond else 'FAIL'), name, detail)
    if not cond:
        fails.append(name)


check('the shim still exposes the package', hasattr(Cammello, 'main'))


# ── 4. what counts as a card ─────────────────────────────────────────────────

tmp = tempfile.mkdtemp(prefix='cammello-vol-')
plain = os.path.join(tmp, 'Backup')
card = os.path.join(tmp, 'EOS_DIGITAL')
os.makedirs(os.path.join(plain, 'Fotos', '2026'))
os.makedirs(os.path.join(card, 'DCIM', '100EOSR5'))

real_volumes = camera.list_volumes
camera.list_volumes = lambda: {plain}
check('a drive without DCIM is not a card', camera.suggest_card() is None)
camera.list_volumes = lambda: {plain, card}
check('a card is found by its DCIM folder',
      camera.suggest_card() == os.path.join(card, 'DCIM'),
      str(camera.suggest_card()))


# ── 5. and 6. where the dialogs start ────────────────────────────────────────

class FakeSettings:
    def __init__(self):
        self.store = {}

    def value(self, key, default='', type=str):
        return self.store.get(key, default)

    def setValue(self, key, value):
        self.store[key] = value

    def sync(self):
        pass


settings = FakeSettings()
work_dir = tempfile.mkdtemp(prefix='cammello-work-')
keep_dir = tempfile.mkdtemp(prefix='cammello-keep-')

constants.remember_dir(settings, work_dir)
start = camera.suggest_card() or constants.remembered_dir(settings)
check('with a card mounted, Open starts on the card',
      start == os.path.join(card, 'DCIM'), start)
camera.list_volumes = lambda: set()
start = camera.suggest_card() or constants.remembered_dir(settings)
check('without a card it starts where it was last time',
      start == work_dir, start)

pictures = constants.transfer_dest_dir(FakeSettings())
check('Move to starts at a place to keep pictures, not at the card',
      pictures != work_dir and os.path.isdir(pictures), pictures)
constants.remember_transfer_dest(settings, keep_dir)
check('and then remembers its own folder',
      constants.transfer_dest_dir(settings) == keep_dir)
check('without touching the Open folder',
      constants.remembered_dir(settings) == work_dir)
check('the three memories are three keys',
      len({constants.LAST_DIR_KEY, constants.TRANSFER_DEST_KEY,
           constants.CAMERA_DEST_KEY}) == 3)
camera.list_volumes = real_volumes


# ── 1. to 3. the switch and the automatic reset ──────────────────────────────

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QSettings
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
w = Cammello.MainWindow(logger, emitter, gui_handler, log_path)

if not hasattr(w, 'cull_hide_rejects_cb'):               # pragma: no cover
    print('SKIP - culling tab not built in this environment')
else:
    check('the switch exists', hasattr(w, 'cull_clear_filter_btn'))
    check('it is disabled while nothing is filtered',
          not w.cull_clear_filter_btn.isEnabled())

    w._cull_set_min_rating(3)
    w.cull_hide_rejects_cb.setChecked(True)
    w._cull_color_btns[0].setChecked(True)
    w._cull_apply_filter()
    check('a filter makes it active', w._cull_filter_active()
          and w.cull_clear_filter_btn.isEnabled())

    w._cull_clear_filter()
    check('the switch clears the stars', w._cull_min_rating() == 0)
    check('and the rejects checkbox', not w.cull_hide_rejects_cb.isChecked())
    check('and the colour swatches',
          not any(b.isChecked() for b in w._cull_color_btns))
    check('and turns itself off again',
          not w.cull_clear_filter_btn.isEnabled())

    # ── 3. opening a folder does the same by itself ──────────────────────
    folder = tempfile.mkdtemp(prefix='cammello-open-')
    w._cull_set_min_rating(4)
    w.cull_hide_rejects_cb.setChecked(True)
    w._cull_apply_filter()
    check('filter set before opening', w._cull_filter_active())
    w._cull_open_folder(folder)
    check('opening a folder clears the filter', not w._cull_filter_active())

    w._cull_set_min_rating(2)
    w._cull_apply_filter()
    w._cull_open_folder(folder)          # the same folder again = reload
    check('reloading the same card clears it too',
          not w._cull_filter_active())

    w._cull_shutdown()

print()
print('FAILURES:', ', '.join(fails) if fails else 'none')
sys.exit(1 if fails else 0)
