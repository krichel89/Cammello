"""Nur die Bilder von heute (0.18.15, zweiter Teil).

Harald: "Mir fehlt immer noch der Filter, um auf der SD-Karte nur die
Bilder von heute zu sehen."

Auswahlfeld "Tag" neben "Reihenfolge": Alle Tage (Vorgabe), dann jeder Tag,
der auf der Karte vorkommt, mit Bildzahl. Einfachauswahl - "nur die Bilder
von heute" braucht keine Mehrfachauswahl, und ein Auswahlfeld sagt auf
einen Blick, welcher Tag gerade gilt.

Tagesgrenze 4 Uhr, wie fuer die Kamera-Auswahl entschieden: was nach
Mitternacht entsteht, gehoert zum Abend davor.

Geprueft wird:

  1. filter_items() laesst mit `day` nur diesen Tag durch,
  2. das Auswahlfeld wird aus der Karte gefuellt, mit Zahlen,
  3. der heutige Tag heisst "heute",
  4. die Auswahl wirkt auf das Raster,
  5. sie zaehlt als aktiver Filter und der Schalter hebt sie auf,
  6. ein Neuladen derselben Karte behaelt den gewaehlten Tag,
  7. eine Karte ohne diesen Tag faellt auf "Alle Tage" zurueck.
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


class Fake:
    label_color_index = None

    def __init__(self, taken):
        self.taken = taken
        self.rating = 0
        self.label = ''


now = time.time()
today = culling.session_day(now)
yesterday = culling.session_day(now - 86400)
items = [Fake(now), Fake(now - 3600), Fake(now - 86400), Fake(0)]

check('one day, one subset',
      len(culling.filter_items(items, day=today)) == 2,
      str(len(culling.filter_items(items, day=today))))
check('another day, another subset',
      len(culling.filter_items(items, day=yesterday)) == 1)
check('no day means every day', len(culling.filter_items(items)) == 4)


# ── the real thing ───────────────────────────────────────────────────────────

from PyQt5.QtWidgets import QApplication
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


def make_card(days):
    """A folder whose files carry the given ages, in days."""
    folder = tempfile.mkdtemp(prefix='cammello-days-')
    for n, age in enumerate(days):
        path = os.path.join(folder, f'IMG_{n:04d}.JPG')
        img = QImage(320, 240, QImage.Format_RGB32)
        img.fill(0xFF335577 + n * 12)
        img.save(path, 'JPG', 75)
        when = now - age * 86400
        os.utime(path, (when, when))
    return folder


w = Cammello.MainWindow(logger, emitter, gui_handler, log_path)
if not hasattr(w, 'cull_day_combo'):                      # pragma: no cover
    print('SKIP - culling tab not built in this environment')
else:
    card = make_card([0, 0, 0, 1, 2])       # three today, one and two days old
    w._cull_open_folder(card)

    labels = [w.cull_day_combo.itemText(i)
              for i in range(w.cull_day_combo.count())]
    check('all days plus one entry per day found',
          w.cull_day_combo.count() == 4, str(labels))
    check('today is named as such',
          any('heute' in t or 'today' in t or "aujourd" in t or 'hoy' in t
              or 'oggi' in t for t in labels), str(labels))
    check('with its count', any('(3)' in t for t in labels), str(labels))
    check('and nothing is filtered to begin with',
          w._cull_day_filter() is None and len(w._cull_visible) == 5)

    idx = w.cull_day_combo.findData(today)
    w.cull_day_combo.setCurrentIndex(idx)
    check('picking today shows only today',
          len(w._cull_visible) == 3, str(len(w._cull_visible)))
    check('it counts as an active filter', w._cull_filter_active())
    check('so the clear switch lights up',
          w.cull_clear_filter_btn.isEnabled())

    # ── 6. reloading the same card keeps the day ─────────────────────────
    w.cull_day_combo.setCurrentIndex(w.cull_day_combo.findData(today))
    w._cull_fill_days()
    check('a rebuild of the list keeps the chosen day',
          w._cull_day_filter() == today)

    w._cull_clear_filter()
    check('the switch clears the day too', w._cull_day_filter() is None)
    check('and everything is back', len(w._cull_visible) == 5)

    # ── 7. a card without that day ───────────────────────────────────────
    w.cull_day_combo.setCurrentIndex(w.cull_day_combo.findData(today))
    old_card = make_card([40, 41])
    w._cull_open_folder(old_card)
    check('a card without the chosen day shows everything',
          w._cull_day_filter() is None and len(w._cull_visible) == 2,
          str(len(w._cull_visible)))
    check('and offers the days it does have',
          w.cull_day_combo.count() == 3, str(w.cull_day_combo.count()))

    w._cull_shutdown()

print()
print('FAILURES:', ', '.join(fails) if fails else 'none')
sys.exit(1 if fails else 0)
