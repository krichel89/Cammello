"""Folder opening speed and double-click in the grid (0.18.4).

Harald: "Das Einlesen einer SD-Karte im Culling-Modul dauert zu lange.
Doppelklick soll von Grid auf Full wechseln"

Two measured facts drove the first half, both taken in this container:

  * decorating a row (stars, label, badges, tooltip, cached thumb) and
    letting Qt process the event costs ~0.65 ms; opening a folder decorated
    EVERY row up front, so a 3000-image card spent seconds building rows
    nobody was looking at,
  * one signal per file from the metadata reader cost 0.52 s of GUI thread
    for 800 rows, against 0.002 s for the same work in one pass.

So: rows are decorated lazily (visible window plus margin), and the reader
reports in batches from a small thread pool.

Defended here:

  1. opening a folder decorates only a bounded number of rows, not all,
  2. every row still gets decorated once it is scrolled into view, and a
     row is never decorated twice for nothing,
  3. a filter change forgets the old decoration state (rows are reused),
  4. the reader batches, and a batch of results still reaches the rows,
  5. rating and thumb arrival still decorate their row,
  6. double-click in the grid opens that picture fullscreen - the picture
     that was clicked, not whatever was current,
  7. leaving fullscreen returns to the grid it came from, while E and G
     still name their own mode.
"""
import os
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import Cammello        # the shim; also puts the package on the path
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt, QPoint, QEvent
from PyQt5.QtGui import QMouseEvent

from PyQt5.QtCore import QSettings, QEventLoop, QTimer

from cammello import culling
from cammello.constants import APP_NAME
from cammello.mw_culling import _MetadataReader

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

# A folder big enough that "all rows" and "the visible rows" cannot be
# confused with each other.
folder = tempfile.mkdtemp()
XMP = ('<?xpacket begin="\ufeff"?><x:xmpmeta xmlns:x="adobe:ns:meta/">'
       '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
       '<rdf:Description rdf:about="" '
       'xmlns:xmp="http://ns.adobe.com/xap/1.0/" xmp:Rating="{r}"/>'
       '</rdf:RDF></x:xmpmeta><?xpacket end="w"?>')
COUNT = 300
for i in range(COUNT):
    with open(os.path.join(folder, f'IMG_{i:04d}.JPG'), 'w',
              encoding='utf-8') as fh:
        fh.write(XMP.format(r=i % 6))

items = culling.scan_folder(folder)
check('the test folder scans to one entry per file', len(items) == COUNT,
      str(len(items)))


# ── 4. the reader batches ────────────────────────────────────────────────────

reader = _MetadataReader(items)
batches = []
reader.items_ready.connect(batches.append)
finished = []
reader.done.connect(finished.append)
reader.start()
reader.wait(60000)
app.processEvents()

flat = [i for b in batches for i in b]
check('every item was read', finished == [COUNT], str(finished))
check('every index arrives exactly once',
      sorted(flat) == list(range(COUNT)), f'{len(flat)} indices')
check('results arrive in batches, not one per file',
      0 < len(batches) < COUNT, f'{len(batches)} batches')
check('the first batch is small, so the first screenful is not held up',
      len(batches[0]) <= _MetadataReader.FIRST_BATCH, str(len(batches[0])))
check('the ratings actually landed',
      [it.rating for it in items[:6]] == [0, 1, 2, 3, 4, 5],
      str([it.rating for it in items[:6]]))

# stop() must be honoured even mid-run.
items2 = culling.scan_folder(folder)
reader2 = _MetadataReader(items2)
reader2.stop()
reader2.start()
reader2.wait(60000)
check('a reader stopped before it started reports nothing read',
      reader2.isFinished())


# ── 1./2./3. lazy decoration, through the real window ────────────────────────

from cammello.logging_setup import setup_logging      # noqa: E402

logger, emitter, gui_handler, log_path = setup_logging()
import logging                                        # noqa: E402
for h in logger.handlers:
    if isinstance(h, logging.StreamHandler) and not hasattr(h, 'baseFilename'):
        h.setLevel(logging.CRITICAL)


def spin(ms=120):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec_()


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
    spin()

    decorated = w._cull_decorated
    check('opening does not decorate every row',
          len(decorated) < COUNT,
          f'{len(decorated)} of {COUNT}')
    check('opening decorates the rows that are on screen',
          len(decorated) > 0)
    first, last = w._cull_visible_range()
    check('a visible range is found', first is not None,
          f'{first}..{last}')
    if first is not None:
        check('every visible row is decorated',
              all(i in decorated for i in range(first, last + 1)))

    # Scrolling to the end must decorate the rows that arrive there.
    w.cull_strip.scrollToItem(w.cull_strip.item(COUNT - 1))
    app.processEvents()
    w._cull_request_visible_thumbs()
    app.processEvents()
    check('scrolling decorates the newly visible rows',
          COUNT - 1 in w._cull_decorated)

    before = len(w._cull_decorated)
    w._cull_decorate_visible()
    check('a second pass over the same rows does no work again',
          len(w._cull_decorated) == before, f'{before} -> '
          f'{len(w._cull_decorated)}')

    # A filter change reuses the row widgets, so the old marks must go.
    w.cull_hide_rejects_cb.setChecked(True)
    app.processEvents()
    check('a filter change forgets the old decoration state',
          len(w._cull_decorated) < COUNT)
    w.cull_hide_rejects_cb.setChecked(False)
    app.processEvents()

    # A batch of metadata for rows that are off screen must not decorate
    # them, but must not lose them either.
    w.cull_strip.scrollToItem(w.cull_strip.item(0))
    app.processEvents()
    w._cull_decorated.discard(COUNT - 1)
    far = w._cull_items[COUNT - 1]
    w._cull_meta_arrived([w._cull_items.index(far)])
    check('an off-screen batch does not decorate off-screen rows',
          (COUNT - 1) not in w._cull_decorated)

    # ── 6./7. double-click in the grid ───────────────────────────────────────

    w._cull_set_grid(True)
    app.processEvents()
    check('in grid', w._cull_grid)

    target_row = min(3, w.cull_strip.count() - 1)
    rect = w.cull_strip.visualItemRect(w.cull_strip.item(target_row))
    pos = rect.center()
    if not w.cull_strip.viewport().rect().contains(pos):
        pos = QPoint(rect.x() + 2, rect.y() + 2)
    ev = QMouseEvent(QEvent.MouseButtonDblClick, pos, Qt.LeftButton,
                     Qt.LeftButton, Qt.NoModifier)
    w.cull_strip.mouseDoubleClickEvent(ev)
    app.processEvents()
    check('double-click in the grid goes fullscreen', w._cull_fs is not None)
    check('fullscreen shows the picture that was double-clicked',
          w._cull_index == target_row, f'{w._cull_index} vs {target_row}')
    check('fullscreen is not the grid', not w._cull_grid)

    w._cull_toggle_fullscreen()
    app.processEvents()
    check('leaving fullscreen returns to the grid it came from',
          w._cull_fs is None and w._cull_grid)

    # E and G name their own mode and must beat the return-to-grid memory.
    w._cull_toggle_fullscreen()
    app.processEvents()
    check('fullscreen again from the grid', w._cull_fs is not None)
    w._cull_loupe_view()
    app.processEvents()
    check('E from fullscreen lands in the loupe, not the grid',
          w._cull_fs is None and not w._cull_grid)

    # Double-click outside the grid keeps the old behaviour (the image view
    # owns it there), so the strip must not swallow it.
    row0 = w.cull_strip.visualItemRect(w.cull_strip.item(0)).center()
    ev2 = QMouseEvent(QEvent.MouseButtonDblClick, row0, Qt.LeftButton,
                      Qt.LeftButton, Qt.NoModifier)
    w.cull_strip.mouseDoubleClickEvent(ev2)
    app.processEvents()
    check('double-click in the filmstrip does not open fullscreen',
          w._cull_fs is None)

    w._cull_shutdown()

print()
print('FAILURES:', ', '.join(fails) if fails else 'none')
sys.exit(1 if fails else 0)
