"""Schmalere Leiste, einklappbarer Filter, gemerkter M-Zustand (0.18.18).

Harald: "Die Tool-Leiste ist zu breit, wir muessen Text-Buttons in Symbole
aendern. Open, Kamera, Eject Card, Clear Filter bieten sich an. Das Filter
Menue koennte man einklappen." Und: "cammello soll sich bitte merken, ob
ich Sterne oder Farben eingeben will."

Die Symbole sind GEZEICHNET, nicht aus einem Zeichensatz und nicht aus
Dateien: Qt hat fuer Kamera, Auswurf und Trichter nichts im Standardsatz,
und der Zeichensatz-Weg ist in dieser App schon einmal schiefgegangen (das
Neuladen-Zeichen wurde zur Haarlinie, anderswo zu Tofu).

Geprueft wird:

  1. jedes Piktogramm entsteht und ist nicht leer,
  2. die vier Knoepfe tragen ein Symbol und KEINEN Text mehr,
  3. der Text ist nicht verloren - er steht im Tooltip,
  4. die Leiste ist dadurch messbar schmaler,
  5. der Trichter klappt den Filterbereich weg und wieder auf,
  6. eingeklappt bleibt der Trichter selbst sichtbar,
  7. eingeklappt mit aktivem Filter traegt er einen Punkt,
  8. Einklappen ist nicht Aufheben - die Werte bleiben stehen,
  9. der Zustand wird gemerkt,
 10. der M-Zustand wird gemerkt.
"""
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import Cammello        # the shim; also puts the package on the path
from cammello import widgets

fails = []


def check(name, cond, detail=''):
    print(('PASS' if cond else 'FAIL'), name, detail)
    if not cond:
        fails.append(name)


check('the shim still exposes the package', hasattr(Cammello, 'main'))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt, QEvent, QSettings
from PyQt5.QtGui import QKeyEvent
from cammello.constants import APP_NAME
from cammello.main_window import setup_logging

app = QApplication.instance() or QApplication(sys.argv)


# ── 1. the pictograms ────────────────────────────────────────────────────────

for kind in widgets.PICTOGRAMS:
    icon = widgets.pictogram(kind, '#202020')
    pm = icon.pixmap(18, 18)
    check(f'the {kind} pictogram is drawn',
          not icon.isNull() and not pm.isNull() and pm.width() > 0)

image = widgets.pictogram('filter', '#202020').pixmap(40, 40).toImage()
inked = sum(1 for x in range(image.width()) for y in range(image.height())
            if image.pixelColor(x, y).alpha() > 40)
check('and it actually puts ink on the pixmap', inked > 20, str(inked))

# Two colours must give two different images, or the dark scheme would get
# an invisible icon.
light = widgets.pictogram('eject', '#ffffff').pixmap(24, 24).toImage()
dark = widgets.pictogram('eject', '#000000').pixmap(24, 24).toImage()
check('the ink colour is honoured', light != dark)

bad = None
try:
    widgets.pictogram('no-such-thing', '#000')
except ValueError as exc:
    bad = exc
check('an unknown pictogram is refused, not drawn blank', bad is not None)


# ── the window ───────────────────────────────────────────────────────────────

_ts = QSettings(APP_NAME, 'Main')
_ts.setValue('feature_culling', True)
_ts.setValue('cull_filter_collapsed', False)
_ts.setValue('cull_number_mode', 'rating')
_ts.sync()
logger, emitter, gui_handler, log_path = setup_logging()
import logging as _logging
for _h in logger.handlers:
    if isinstance(_h, _logging.StreamHandler) and not hasattr(_h,
                                                              'baseFilename'):
        _h.setLevel(_logging.CRITICAL)

w = Cammello.MainWindow(logger, emitter, gui_handler, log_path)
if not hasattr(w, 'cull_filter_toggle'):                  # pragma: no cover
    print('SKIP - culling tab not built in this environment')
else:
    # ── 2. and 3. icons instead of labels ────────────────────────────────
    named = (('cull_open_btn', 'Open'), ('cull_camera_btn', 'camera'),
             ('cull_eject_btn', 'Eject'),
             ('cull_clear_filter_btn', 'Clear filter'))
    for attr, word in named:
        btn = getattr(w, attr)
        check(f'{attr} carries an icon', not btn.icon().isNull())
        check(f'{attr} carries no label any more', btn.text() == '',
              repr(btn.text()))
        check(f'{attr} keeps its wording in the tooltip',
              word.lower() in btn.toolTip().lower(), btn.toolTip()[:40])

    # ── 4. the bar really is narrower ────────────────────────────────────
    wide = sum(getattr(w, a).sizeHint().width() for a, _ in named)
    from PyQt5.QtWidgets import QPushButton
    from cammello.i18n import tr
    reference = 0
    for label in ('Open…', 'From camera…', 'Eject card', 'Clear filter'):
        probe = QPushButton(tr(label))
        reference += probe.sizeHint().width()
        probe.deleteLater()
    check('the four buttons take less room than their labels did',
          wide < reference, f'{wide} px statt {reference} px')

    # ── 5. to 8. folding ─────────────────────────────────────────────────
    w.show()                      # visibility is only real on a shown window
    app.processEvents()
    check('the filter starts unfolded',
          all(x.isVisible() for x in w._cull_filter_widgets))

    w._cull_set_filter_collapsed(True)
    app.processEvents()
    check('folding hides the whole cluster',
          not any(x.isVisible() for x in w._cull_filter_widgets))
    check('but the funnel stays', w.cull_filter_toggle.isVisible())

    # ── 8. folded is not cleared ─────────────────────────────────────────
    w._cull_set_min_rating(3)
    w._cull_apply_filter()
    check('a filter set while folded still filters',
          w._cull_filter_active() and w._cull_min_rating() == 3)
    check('and the funnel says so', 'active' in
          w.cull_filter_toggle.toolTip().lower()
          or 'aktiv' in w.cull_filter_toggle.toolTip().lower(),
          w.cull_filter_toggle.toolTip())
    dotted = w.cull_filter_toggle.icon().pixmap(24, 24).toImage()

    w._cull_clear_filter()
    plain = w.cull_filter_toggle.icon().pixmap(24, 24).toImage()
    check('the dot goes away with the filter', dotted != plain)
    check('and clearing does not unfold anything',
          not any(x.isVisible() for x in w._cull_filter_widgets))

    w._cull_set_filter_collapsed(False)
    app.processEvents()
    check('unfolding brings the cluster back',
          all(x.isVisible() for x in w._cull_filter_widgets))

    # ── 9. remembered ────────────────────────────────────────────────────
    w._cull_set_filter_collapsed(True, remember=True)
    check('folding is remembered',
          _ts.value('cull_filter_collapsed', False, type=bool) is True)
    w._cull_set_filter_collapsed(False, remember=True)
    check('and so is unfolding',
          _ts.value('cull_filter_collapsed', True, type=bool) is False)

    # ── 10. the M mode ───────────────────────────────────────────────────
    check('M starts on stars', w._cull_number_mode == 'rating')
    w._cull_key(QKeyEvent(QEvent.KeyPress, Qt.Key_M, Qt.NoModifier))
    check('M switches to colours', w._cull_number_mode == 'color')
    check('and that is written down',
          _ts.value('cull_number_mode', '', type=str) == 'color')

    w2 = Cammello.MainWindow(logger, emitter, gui_handler, log_path)
    check('a new window comes up in colour mode',
          w2._cull_number_mode == 'color', w2._cull_number_mode)
    check('and the label agrees',
          'COLOR' in w2.cull_mode_lbl.text().upper()
          or 'FARB' in w2.cull_mode_lbl.text().upper(),
          w2.cull_mode_lbl.text())
    w2._cull_shutdown()

    _ts.setValue('cull_number_mode', 'rating')
    _ts.setValue('cull_filter_collapsed', False)
    _ts.sync()
    w._cull_shutdown()

print()
print('FAILURES:', ', '.join(fails) if fails else 'none')
sys.exit(1 if fails else 0)
