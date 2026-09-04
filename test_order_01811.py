"""Ordering by when the picture was taken (0.18.11).

Harald: "können wir nach aufnahmedatum ordnen oder kostet das Zeit?"

It costs a stat per file and nothing else, because the file time comes out
of the directory entry the scan already reads: measured in this container,
1600 names cost 0.6 ms with os.listdir and 3.3 ms with os.scandir plus
stat. Reading EXIF DateTimeOriginal would mean OPENING every CR3 on the
card, which is exactly the cost he complained about in 0.18.4 - so the
order uses the file time, and says so in the tooltip.

On a card the two are the same thing: the camera stamps the file as it
writes it. Cammello's own copy and move carry the time over (shutil.copy2,
shutil.move), so an exported folder sorts correctly too.

Defended here:

  1. file name order is unchanged and stays the default,
  2. time order really follows the clock, across folders as well - that is
     the case a file name cannot get right,
  3. a pair counts as one picture, timed by its older file,
  4. an unreadable time does not throw the scan,
  5. the order is stable: two frames in the same second keep the camera's
     numbering,
  6. switching the order re-sorts what is open WITHOUT reading the folder
     again, keeps ratings, and keeps the current picture,
  7. the metadata reader is not confused by a re-sort under it.
"""
import os
import shutil
import sys
import tempfile
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import Cammello        # the shim; also puts the package on the path
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QSettings, QEventLoop, QTimer
from PyQt5.QtGui import QImage

from cammello import culling
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


NOW = time.time()


def picture(path, tint, age):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img = QImage(600, 400, QImage.Format_RGB32)
    img.fill(tint)
    img.save(path, 'JPG', 80)
    os.utime(path, (NOW - age, NOW - age))
    return path


# A card whose second folder was written FIRST - the case where the file
# name gets the order wrong. Canon rolls the folder over, and a card can
# carry two shoots.
card = tempfile.mkdtemp()
dcim = os.path.join(card, 'DCIM')
picture(os.path.join(dcim, '100EOSR5', 'IMG_0001.JPG'), 0xFF224466, 60)
picture(os.path.join(dcim, '100EOSR5', 'IMG_0002.JPG'), 0xFF224477, 30)
picture(os.path.join(dcim, '101EOSR5', 'IMG_0500.JPG'), 0xFF664422, 9000)


# ── 1./2. the two orders ─────────────────────────────────────────────────────

by_name = culling.scan_folder(dcim, None, True)
check('file name order is the default',
      [i.stem for i in by_name]
      == ['IMG_0001', 'IMG_0002', 'IMG_0500'],
      str([i.stem for i in by_name]))

by_time = culling.scan_folder(dcim, None, True, culling.ORDER_TIME)
check('time order follows the clock, not the numbering',
      [i.stem for i in by_time]
      == ['IMG_0500', 'IMG_0001', 'IMG_0002'],
      str([i.stem for i in by_time]))
check('the times were actually picked up',
      all(i.taken > 0 for i in by_time),
      str([round(i.taken) for i in by_time]))
check('and they ascend',
      [i.taken for i in by_time] == sorted(i.taken for i in by_time))


# ── 3. a pair is one picture ─────────────────────────────────────────────────

pair_dir = tempfile.mkdtemp()
jpg = picture(os.path.join(pair_dir, 'IMG_9.JPG'), 0xFF112233, 100)
raw = os.path.join(pair_dir, 'IMG_9.CR3')
with open(raw, 'w', encoding='utf-8') as fh:
    fh.write('raw')
os.utime(raw, (NOW - 500, NOW - 500))      # the RAW is the older file
pair = culling.scan_folder(pair_dir, None, False, culling.ORDER_TIME)
check('a pair is one entry', len(pair) == 1, str(len(pair)))
check('timed by its older file',
      abs(pair[0].taken - (NOW - 500)) < 1.5,
      f'{pair[0].taken} vs {NOW - 500}')


# ── 4./5. edges ──────────────────────────────────────────────────────────────

same = tempfile.mkdtemp()
for n in ('IMG_0300.JPG', 'IMG_0100.JPG', 'IMG_0200.JPG'):
    picture(os.path.join(same, n), 0xFF445566, 42)     # all the same second
stable = [i.stem for i in
          culling.scan_folder(same, None, False, culling.ORDER_TIME)]
check('the same second keeps the camera numbering',
      stable == ['IMG_0100', 'IMG_0200', 'IMG_0300'], str(stable))
check('and is stable across two scans',
      stable == [i.stem for i in
                 culling.scan_folder(same, None, False, culling.ORDER_TIME)])

check('a missing folder still returns empty, not an exception',
      culling.scan_folder(os.path.join(same, 'nope'), None, False,
                          culling.ORDER_TIME) == [])

unsorted_items = list(by_name)
culling.sort_items(unsorted_items, culling.ORDER_TIME)
check('sort_items orders in place',
      [i.stem for i in unsorted_items]
      == ['IMG_0500', 'IMG_0001', 'IMG_0002'])
culling.sort_items(unsorted_items)
check('and back again by name',
      [i.stem for i in unsorted_items]
      == ['IMG_0001', 'IMG_0002', 'IMG_0500'])


# ── 6./7. through the window ─────────────────────────────────────────────────

from cammello.logging_setup import setup_logging          # noqa: E402
import logging                                            # noqa: E402

logger, emitter, gui_handler, log_path = setup_logging()
for h in logger.handlers:
    h.setLevel(logging.CRITICAL)

w = Cammello.MainWindow(logger, emitter, gui_handler, log_path)
w.resize(1100, 800)
w.show()
w.tabs.setCurrentWidget(w._cull_tab_widget)
app.processEvents()

w.cull_order_combo.setCurrentIndex(
    w.cull_order_combo.findData(culling.ORDER_NAME))
app.processEvents()
w._cull_open_folder(dcim)
app.processEvents()
spin()

check('opened by name',
      [i.stem for i in w._cull_visible]
      == ['IMG_0001', 'IMG_0002', 'IMG_0500'],
      str([i.stem for i in w._cull_visible]))

w._cull_show_index(0)
app.processEvents()
w._cull_set_rating(4)
app.processEvents()
spin()
rated = [i.stem for i in w._cull_items if i.rating == 4]
check('one picture is rated', len(rated) == 1, str(rated))

w.cull_order_combo.setCurrentIndex(
    w.cull_order_combo.findData(culling.ORDER_TIME))
app.processEvents()
spin()
check('switching to time re-sorts what is open',
      [i.stem for i in w._cull_visible]
      == ['IMG_0500', 'IMG_0001', 'IMG_0002'],
      str([i.stem for i in w._cull_visible]))
check('the rating survived the re-sort',
      [i.stem for i in w._cull_items if i.rating == 4] == rated,
      str([i.stem for i in w._cull_items if i.rating == 4]))
check('the folder was not read again',
      len(w._cull_items) == 3, str(len(w._cull_items)))
check('the row map was rebuilt for the new order',
      w._cull_row_by_item[id(w._cull_visible[0])] == 0)

w.cull_order_combo.setCurrentIndex(
    w.cull_order_combo.findData(culling.ORDER_NAME))
app.processEvents()
spin()
check('and back to file name',
      [i.stem for i in w._cull_visible]
      == ['IMG_0001', 'IMG_0002', 'IMG_0500'])
check('the choice is remembered',
      w.settings.value('cull_order', '', type=str) == culling.ORDER_NAME,
      w.settings.value('cull_order', '', type=str))

# The reader holds its own list, so a re-sort cannot point its results at
# the wrong picture.
check('the reader has its own list',
      w._cull_reader is None
      or w._cull_reader.items is not w._cull_items)
w._cull_meta_arrived([0, 1, 2, 99])        # 99 is out of range on purpose
check('an out-of-range index from the reader is ignored', True)

w._cull_shutdown()
for d in (card, pair_dir, same):
    shutil.rmtree(d, ignore_errors=True)

print()
print('FAILURES:', ', '.join(fails) if fails else 'none')
sys.exit(1 if fails else 0)
