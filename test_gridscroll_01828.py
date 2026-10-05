"""Grid scrolling in large folders (0.18.28).

Harald (Windows): "Die Grid-Ansicht ist bei großen Verzeichnissen langsam.
Wenn ich bei FastRawViewer ein paar Seiten springe, werden die Ansichten
schnell aufgebaut, bei Cammello warte ich."

Causes, all on the scroll path:

  * the visible range was found by scanning from row 0 (one visualItemRect
    per row above the viewport, on every scroll tick),
  * every tick of a scrollbar drag or page jump queued thumbs for the page it
    passed over, and equal-priority jobs run first in, first out: the page
    you LANDED on waited behind all of them,
  * a row that was decorated and cached was requested again on every tick;
    the cache hit emitted `loaded`, and each signal re-decorated its row.

Defended here:

  1. the binary-search visible range equals a scan from row 0, in grid and
     filmstrip, at the top, in the middle, at the end,
  2. thumb jobs outside the wanted set are dropped; inside it they run,
  3. on-screen thumbs outrank the margin, both stay below the prefetch,
  4. a burst of scroll ticks requests only where it ended,
  5. the page that was jumped to gets its thumbs,
  6. settled rows are not requested (and not re-decorated) again.
"""
import os
import sys
import tempfile
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import Cammello        # the shim; also puts the package on the path
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QSettings, QEventLoop, QTimer
from PyQt5.QtGui import QImage, QColor

from cammello import previews
from cammello.constants import APP_NAME

_ts = QSettings(APP_NAME, 'Main')
_ts_saved = {k: _ts.value(k) for k in ('feature_culling',)}
_ts.setValue('feature_culling', True)
_ts.sync()

fails = []


def check(name, cond, detail=''):
    print(('PASS' if cond else 'FAIL'), name, detail)
    if not cond:
        fails.append(name)


app = QApplication.instance() or QApplication([])


def spin(ms=120):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec_()


# ── 2./3. the loader on its own ──────────────────────────────────────────────

folder = tempfile.mkdtemp()
COUNT = 900
for i in range(COUNT):
    img = QImage(96, 64, QImage.Format_RGB32)
    img.fill(QColor(i % 256, (i * 7) % 256, 90))
    img.save(os.path.join(folder, f'IMG_{i:04d}.JPG'), 'JPG')
paths = sorted(os.path.join(folder, f) for f in os.listdir(folder))

L = previews.PreviewLoader(threads=2)
check('visible thumbs outrank the margin',
      L.P_THUMBS < L.P_THUMBS_NEAR)
check('both stay below the prefetch',
      L.P_THUMBS_NEAR < L.P_PREFETCH)

L.set_wanted_thumbs({paths[10]})
for p in paths[:20]:
    L.request(p, 'thumb', L.P_THUMBS)
L.wait_idle(20000)
check('a thumb job outside the wanted set is dropped',
      L.cache.get('thumb', paths[5]) is None)
check('a thumb job inside the wanted set runs',
      L.cache.get('thumb', paths[10]) is not None)
check('a dropped job can be requested again later',
      (paths[5], 'thumb') not in L._inflight)
L.set_wanted_thumbs({paths[5]})
L.request(paths[5], 'thumb', L.P_THUMBS)
L.wait_idle(20000)
check('... and then runs', L.cache.get('thumb', paths[5]) is not None)
# The restriction is for thumbs only.
L.set_wanted_thumbs(set())
L.request(paths[30], 'screen', L.P_CURRENT)
L.wait_idle(20000)
check('the wanted set does not touch the screen level',
      L.cache.get('screen', paths[30]) is not None)
L.new_generation()
check('a new generation lifts the restriction', L._wanted_thumbs is None)


# ── through the real window ──────────────────────────────────────────────────

from cammello.logging_setup import setup_logging      # noqa: E402

logger, emitter, gui_handler, log_path = setup_logging()
import logging                                        # noqa: E402
for h in logger.handlers:
    if isinstance(h, logging.StreamHandler) and not hasattr(h, 'baseFilename'):
        h.setLevel(logging.CRITICAL)

w = Cammello.MainWindow(logger, emitter, gui_handler, log_path)
w.resize(1200, 800)
w.show()
w.tabs.setCurrentWidget(w._cull_tab_widget)
app.processEvents()

if not hasattr(w, '_cull_reader'):
    check('culling tab available (pyexiv2 present)', False,
          'skipped the window half')
else:
    w._cull_open_folder(folder)
    app.processEvents()
    spin(300)
    strip = w.cull_strip
    n = strip.count()
    check('the folder is open', n == COUNT, str(n))

    def scan_from_zero():
        vp = strip.viewport().rect()
        first = last = None
        for i in range(strip.count()):
            if strip.visualItemRect(strip.item(i)).intersects(vp):
                if first is None:
                    first = i
                last = i
            elif first is not None:
                break
        return (first, last) if first is not None else (None, None)

    # 1. binary search == scan from row 0
    for mode in (True, False):
        w._cull_set_grid(mode)
        app.processEvents()
        sb = strip.verticalScrollBar() if mode else strip.horizontalScrollBar()
        label = 'grid' if mode else 'filmstrip'
        for frac in (0.0, 0.37, 0.8, 1.0):
            sb.setValue(int(sb.maximum() * frac))
            app.processEvents()
            check(f'visible range matches a scan from row 0 '
                  f'({label}, {frac:.0%})',
                  w._cull_visible_range() == scan_from_zero(),
                  f'{w._cull_visible_range()} vs {scan_from_zero()}')
    w.cull_strip.clear()
    check('an empty strip has no range', w._cull_visible_range()
          == (None, None))
    w._cull_apply_filter()
    app.processEvents()

    # Time it, for the record (not asserted: machine dependent).
    w._cull_set_grid(True)
    app.processEvents()
    sb = strip.verticalScrollBar()
    sb.setValue(sb.maximum())
    app.processEvents()
    t = time.perf_counter()
    for _ in range(20):
        w._cull_visible_range()
    print('INFO  visible range at the end of the grid: '
          f'{(time.perf_counter() - t) / 20 * 1000:.2f} ms per call')

    # 4./5. a burst of scroll ticks, then settle
    loader = w._cull_loader
    sb.setValue(0)
    spin(300)
    maxv = sb.maximum()
    asked = []
    real_request = loader.request

    def recording(path, level='screen', priority=100):
        if level == 'thumb':
            asked.append(path)
        return real_request(path, level, priority)

    loader.request = recording
    for frac in (0.2, 0.4, 0.6, 0.8):    # no event processing between ticks
        sb.setValue(int(maxv * frac))
    sb.setValue(maxv)
    spin(500)
    loader.request = real_request
    first, last = w._cull_visible_range()
    row_of = {it.display_path: i for i, it in enumerate(w._cull_visible)}
    lowest = min((row_of[p] for p in asked), default=None)
    check('a burst of ticks asks only where it ended',
          asked and lowest >= first - 24,
          f'lowest requested row {lowest}, landing page {first}..{last}')
    check('after the jump the landing page has its thumbs',
          all(loader.cache.get('thumb', w._cull_visible[i].display_path)
              is not None for i in range(first, last + 1)),
          f'{first}..{last}')

    # 6. settled rows are not requested again
    spin(300)
    seen = []
    loader.signals.loaded.connect(lambda k, lv: seen.append((k, lv)))
    for _ in range(3):
        w._cull_request_visible_thumbs()
    spin(100)
    thumb_signals = [s for s in seen if s[1] == 'thumb']
    check('settled rows are not requested again',
          not thumb_signals, f'{len(thumb_signals)} loaded signals')

    # Row decoration still follows a thumb that arrives late.
    sb.setValue(0)
    spin(500)
    check('scrolling back decorates and fills the first page',
          0 in w._cull_decorated)

    w._cull_shutdown()

_ts.setValue('feature_culling', _ts_saved['feature_culling'])
_ts.sync()
print()
print('FAILURES:', ', '.join(fails) if fails else 'none')
sys.exit(1 if fails else 0)
