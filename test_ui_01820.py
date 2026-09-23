#!/usr/bin/env python3
"""0.18.20: one icon set (Lucide), the filter in a row of its own, and
tooltips that are labels again.

Run headless:  QT_QPA_PLATFORM=offscreen python3 test_ui_01820.py
"""
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication, QHBoxLayout
from PyQt5.QtCore import QSettings

app = QApplication.instance() or QApplication([])

import Cammello                                            # noqa: E402
from cammello import widgets                               # noqa: E402
from cammello.constants import APP_NAME, app_style, TOOLTIP_STYLE  # noqa: E402
from cammello.logging_setup import setup_logging           # noqa: E402

FAILED = []
PASSED = 0


def check(what, ok, detail=''):
    global PASSED
    if ok:
        PASSED += 1
    else:
        FAILED.append(f'{what}: {detail}')
        print(f'  FAIL {what} {detail}')


# ── 1. the Lucide files are really there ─────────────────────────────────
for name in sorted(set(widgets.LUCIDE_NAMES.values())):
    path = os.path.join(widgets.LUCIDE_DIR, name + '.svg')
    check(f'{name}.svg ships', os.path.isfile(path))
    if os.path.isfile(path):
        body = open(path, encoding='utf-8').read()
        check(f'{name}.svg paints with currentColor',
              'currentColor' in body)
check('the licence ships with the icons',
      os.path.isfile(os.path.join(widgets.LUCIDE_DIR, 'LICENSE')))

# ── 2. every kind renders, in both inks ──────────────────────────────────
for kind in widgets.LUCIDE_NAMES:
    for ink in ('#000000', '#ffffff'):
        icon = widgets.lucide(kind, ink, 18)
        check(f'lucide({kind}, {ink}) renders', not icon.isNull())
        img = icon.pixmap(18, 18).toImage()
        painted = sum(1 for y in range(img.height())
                      for x in range(img.width())
                      if img.pixelColor(x, y).alpha() > 200
                      and img.pixelColor(x, y).name() == ink)
        check(f'lucide({kind}, {ink}) is inked in that colour',
              painted > 10, f'{painted} px')

black = widgets.lucide('camera', '#000000', 18).pixmap(18, 18).toImage()
white = widgets.lucide('camera', '#ffffff', 18).pixmap(18, 18).toImage()
check('the same icon differs between the two schemes', black != white)

dot = widgets.lucide('filter_dot', '#000000', 18).pixmap(18, 18).toImage()
plain = widgets.lucide('filter', '#000000', 18).pixmap(18, 18).toImage()
check('filter_dot is distinguishable from filter', dot != plain)

# ── 3. the fallback still works without QtSvg ────────────────────────────
_real, widgets.QSvgRenderer = widgets.QSvgRenderer, None
widgets._LUCIDE_CACHE.clear()
try:
    fallback = widgets.lucide('camera', '#000000', 17)
    check('without QtSvg lucide() falls back to a drawn pictogram',
          not fallback.isNull())
finally:
    widgets.QSvgRenderer = _real
    widgets._LUCIDE_CACHE.clear()

# ── 4. the tooltip is a label, not an essay ──────────────────────────────
check('the stylesheet enlarges tooltips',
      'QToolTip' in TOOLTIP_STYLE and 'font-size' in TOOLTIP_STYLE)
check('and the application sheet carries it', TOOLTIP_STYLE in app_style())

# ── the window ───────────────────────────────────────────────────────────
ts = QSettings(APP_NAME, 'Main')
ts.setValue('feature_culling', True)
ts.setValue('cull_filter_collapsed', False)
ts.sync()
logger, emitter, gui_handler, log_path = setup_logging()
import logging as _logging                                 # noqa: E402
for _h in logger.handlers:
    if isinstance(_h, _logging.StreamHandler) and not hasattr(_h,
                                                              'baseFilename'):
        _h.setLevel(_logging.CRITICAL)

w = Cammello.MainWindow(logger, emitter, gui_handler, log_path)

if not hasattr(w, 'cull_filter_toggle'):                   # pragma: no cover
    print('SKIP - culling tab not built in this environment')
else:
    ink = w._cull_ink()
    # ── 5. the toolbar icons come from Lucide, not from the platform ────
    for attr, kind in (('cull_open_btn', 'folder'),
                       ('cull_reload_btn', 'reload'),
                       ('cull_camera_btn', 'camera'),
                       ('cull_eject_btn', 'eject'),
                       ('cull_clear_filter_btn', 'filter_off'),
                       ('cull_filter_toggle', 'filter')):
        btn = getattr(w, attr)
        mine = btn.icon().pixmap(18, 18).toImage()
        want = widgets.lucide(kind, ink, 18).pixmap(18, 18).toImage()
        check(f'{attr} shows the Lucide {kind}', mine == want)
        check(f'{attr} has a short tooltip',
              0 < len(btn.toolTip()) <= 40 and '\n' not in btn.toolTip(),
              repr(btn.toolTip()))

    if hasattr(w, 'names_btn'):
        mine = w.names_btn.icon().pixmap(18, 18).toImage()
        want = widgets.lucide('nametag', ink, 18).pixmap(18, 18).toImage()
        check('the name button shows the Lucide tag', mine == want)
        check('and its tooltip is short too',
              len(w.names_btn.toolTip()) <= 40, repr(w.names_btn.toolTip()))

    # ── 6. the filter sits in a row of its own ──────────────────────────
    row = getattr(w, 'cull_filter_row', None)
    check('there is a filter row', row is not None)
    if row is not None:
        in_row = []
        lay = row.layout()
        for i in range(lay.count()):
            item = lay.itemAt(i)
            if item.widget() is not None:
                in_row.append(item.widget())
        for wid in w._cull_filter_widgets:
            check('a filter widget sits in the filter row', wid in in_row,
                  type(wid).__name__)
        check('the funnel does NOT sit in the filter row',
              w.cull_filter_toggle not in in_row)
        check('the row is a sibling of the toolbar, not inside it',
              isinstance(lay, QHBoxLayout)
              and row.parent() is w.cull_filter_toggle.parent())

    # ── 7. folding hides the row, and the toolbar keeps its width ───────
    w.show()
    app.processEvents()
    check('the filter row starts open', row.isVisible())
    open_width = w.cull_filter_toggle.parent().sizeHint().width()

    w._cull_set_filter_collapsed(True)
    app.processEvents()
    check('closing hides the row', not row.isVisible())
    check('and hides its contents',
          not any(x.isVisible() for x in w._cull_filter_widgets))
    check('the funnel stays', w.cull_filter_toggle.isVisible())
    closed_width = w.cull_filter_toggle.parent().sizeHint().width()
    check('the toolbar width does not change when the filter opens',
          open_width == closed_width, f'{open_width} vs {closed_width}')

    # ── 8. closed is not cleared, and the dot says so ───────────────────
    w._cull_set_min_rating(3)
    w._cull_apply_filter()
    check('a filter set while closed still filters',
          w._cull_filter_active() and w._cull_min_rating() == 3)
    marked = w.cull_filter_toggle.icon().pixmap(24, 24).toImage()
    want = widgets.lucide('filter_dot', w._cull_ink(), 18).pixmap(24, 24) \
                  .toImage()
    check('the closed funnel carries the dot', marked == want)
    w._cull_clear_filter()
    check('and loses it again with the filter',
          w.cull_filter_toggle.icon().pixmap(24, 24).toImage() != marked)

    w._cull_set_filter_collapsed(False)
    app.processEvents()
    check('opening brings the row back', row.isVisible())
    check('and its contents with it',
          all(x.isVisible() for x in w._cull_filter_widgets))

    # ── 9. still remembered ─────────────────────────────────────────────
    w._cull_set_filter_collapsed(True, remember=True)
    check('closing is remembered',
          ts.value('cull_filter_collapsed', False, type=bool) is True)
    w._cull_set_filter_collapsed(False, remember=True)

    # ── 10. a scheme change repaints every icon ─────────────────────────
    before = w.cull_eject_btn.icon().pixmap(18, 18).toImage()
    w.palette()                              # ink comes from the palette
    w._cull_update_icons()
    check('repainting keeps the icons intact',
          not w.cull_eject_btn.icon().isNull()
          and w.cull_eject_btn.icon().pixmap(18, 18).toImage() == before)

print(f'\n{PASSED} Pruefungen bestanden, {len(FAILED)} gescheitert')
for f in FAILED:
    print('  -', f)
sys.exit(1 if FAILED else 0)
