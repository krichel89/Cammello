"""Offscreen checks for the 0.9.8 table changes (thumbnails, Wikitext column)."""
import os
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtWidgets import QApplication, QStyleOptionViewItem
from PyQt5.QtCore import QSize, Qt

import Cammello  # backwards-compatible shim
from cammello.constants import (THUMB_W, THUMB_H, THUMB_COL_WIDTH,
                                THUMB_ROW_HEIGHT, WIKITEXT_MAX_LINES,
                                __version__)
from cammello.widgets import CappedRowHeightDelegate
from cammello.logging_setup import setup_logging

app = QApplication(sys.argv)

logger, emitter, gui_handler, log_path = setup_logging()
w = Cammello.MainWindow(logger, emitter, gui_handler, log_path)

fails = []


def check(name, cond, detail=''):
    print(('PASS' if cond else 'FAIL'), name, detail)
    if not cond:
        fails.append(name)


check('version', tuple(map(int, __version__.split('.'))) >= (0, 9, 8), __version__)

# 1) Column header renamed.
hdr = w.table.horizontalHeaderItem(w.COL_EFFECTIVE).text()
check('header COL_EFFECTIVE == Wikitext', hdr == 'Wikitext', hdr)

# 2) Thumbnails 50% larger (96x64 -> 144x96).
check('icon size', w.table.iconSize() == QSize(144, 96), str(w.table.iconSize()))
check('constants +50%', (THUMB_W, THUMB_H) == (144, 96))
check('thumb column width', w.table.columnWidth(w.COL_THUMB) == THUMB_COL_WIDTH,
      str(w.table.columnWidth(w.COL_THUMB)))
check('default row height', w.table.verticalHeader().defaultSectionSize() == THUMB_ROW_HEIGHT)

# 3) Neighbour columns shrunk, Wikitext still stretching.
check('source file width 180', w.table.columnWidth(w.COL_FILENAME) == 180)
check('target width 200', w.table.columnWidth(w.COL_TITLE) == 200)
check('status width 110', w.table.columnWidth(w.COL_STATUS) == 110)
from PyQt5.QtWidgets import QHeaderView
# 0.14.0: Interactive (drag-resizable); Stretch sections cannot be dragged.
check('COL_EFFECTIVE is drag-resizable',
      w.table.horizontalHeader().sectionResizeMode(w.COL_EFFECTIVE) == QHeaderView.Interactive)
check('last section stretches instead',
      w.table.horizontalHeader().stretchLastSection())
w.table.setColumnWidth(w.COL_EFFECTIVE, 333)
check('dragging (setColumnWidth) sticks',
      w.table.columnWidth(w.COL_EFFECTIVE) == 333)

# 4) Delegate on the Wikitext column, capping the height at 12 lines.
d = w.table.itemDelegateForColumn(w.COL_EFFECTIVE)
check('delegate installed', isinstance(d, CappedRowHeightDelegate))
check('max lines = 12', WIKITEXT_MAX_LINES == 12 and d.max_lines == 12)

# Feed a very long text through the delegate's sizeHint and compare with the
# uncapped hint of the same cell content.
img = os.path.join(tempfile.mkdtemp(), 'x.png')
from PyQt5.QtGui import QPixmap
QPixmap(4000, 3000).save(img)
w._add_row(img)
long_text = '\n'.join(f'line {i} with quite a bit of wikitext content' for i in range(60))
w.table.item(0, w.COL_EFFECTIVE).setText(long_text)

opt = QStyleOptionViewItem()
opt.initFrom(w.table)
opt.features |= QStyleOptionViewItem.WrapText
opt.rect = w.table.visualRect(w.table.model().index(0, w.COL_EFFECTIVE))
idx = w.table.model().index(0, w.COL_EFFECTIVE)
capped = d.sizeHint(opt, idx).height()
line = opt.fontMetrics.lineSpacing()
check('capped hint <= 12 lines + padding', capped <= line * 12 + 8,
      f'{capped} px, lineSpacing={line}')
check('capped hint is a real cap (< 60 lines)', capped < line * 60,
      f'{capped} px')

# Row height with the long text still in the cell: the cap must bite.
w.table.resizeRowsToContents()
h_long = w.table.rowHeight(0)
check('row height capped with 60-line text', h_long <= line * 12 + 40,
      f'{h_long} px')
check('row height not below the thumbnail', h_long >= THUMB_H, f'{h_long} px')

# Tooltip keeps the full text available.
w._refresh_effective(0)
tip = w.table.item(0, w.COL_EFFECTIVE).toolTip()
check('tooltip carries full effective text',
      tip == w.table.item(0, w.COL_EFFECTIVE).text())

# 5) Short text: the row is driven by the (bigger) thumbnail.
w.table.resizeRowsToContents()
h = w.table.rowHeight(0)
check('row height with short text >= thumbnail height', h >= THUMB_H, f'{h} px')

print('\nFAILURES:', fails if fails else 'none')
sys.exit(1 if fails else 0)
