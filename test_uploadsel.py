"""Upload targets the selection; all rows when nothing is selected (0.9.10)."""
import os
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QPixmap

import Cammello
from cammello.logging_setup import setup_logging

app = QApplication(sys.argv)
logger, emitter, gui_handler, log_path = setup_logging()
w = Cammello.MainWindow(logger, emitter, gui_handler, log_path)

fails = []


def check(name, cond, detail=''):
    print(('PASS' if cond else 'FAIL'), name, detail)
    if not cond:
        fails.append(name)


tmp = tempfile.mkdtemp()
paths = []
for i in range(5):
    p = os.path.join(tmp, f'img{i}.png')
    QPixmap(800, 600).save(p)
    paths.append(p)
w._add_paths(paths)
check('5 rows added', w.table.rowCount() == 5)

# Nothing selected -> all rows.
w.table.clearSelection()
check('no selection -> all rows', w._upload_rows() == [0, 1, 2, 3, 4],
      str(w._upload_rows()))
check('button says "Upload all"', w.upload_btn.text() == 'Upload all (5)',
      w.upload_btn.text())

# Select rows 1 and 3 -> only those.
w.table.selectRow(1)
w.table.selectRow(3)   # ExtendedSelection: selectRow replaces unless modified
sel = sorted({i.row() for i in w.table.selectedIndexes()})
check('selection is what the test set up', sel == [3], str(sel))
check('selected rows only', w._upload_rows() == [3], str(w._upload_rows()))
check('button says "Upload selected"',
      w.upload_btn.text() == 'Upload selected (1)', w.upload_btn.text())

# Multi-select via the selection model.
from PyQt5.QtCore import QItemSelection, QItemSelectionModel
sm = w.table.selectionModel()
sm.clearSelection()
for r in (1, 3):
    sm.select(w.table.model().index(r, 0),
              QItemSelectionModel.Select | QItemSelectionModel.Rows)
check('multi-select -> rows 1 and 3', w._upload_rows() == [1, 3],
      str(w._upload_rows()))
check('button counts 2', w.upload_btn.text() == 'Upload selected (2)',
      w.upload_btn.text())

# The worker index -> table row mapping is what makes status land in the right
# row. With rows [1, 3] uploaded, worker index 0 is table row 1, index 1 is 3.
w.upload_row_map = [1, 3]
check('_table_row maps worker index to table row',
      (w._table_row(0), w._table_row(1)) == (1, 3))

# Status from the worker must reach the correct table row.
w.on_progress(1, 'Uploading…')
check('status written to table row 3, not row 1',
      w.table.item(3, w.COL_STATUS).text() == 'Uploading…'
      and w.table.item(1, w.COL_STATUS).text() != 'Uploading…')

# _qid_problems only inspects the rows about to be uploaded.
w.table.item(0, w.COL_DESC).setText('depicts=NOT_A_QID')
check('bad QID in an unselected row does not block a selected upload',
      w._qid_problems([1, 3]) == [])
check('bad QID in row 0 is found when row 0 is uploaded',
      len(w._qid_problems([0])) == 1, str(w._qid_problems([0])))

# Row count changes update the label.
w.table.clearSelection()
w.clear_all()
check('label after clear_all', w.upload_btn.text() == 'Upload all',
      w.upload_btn.text())

print('\nFAILURES:', fails if fails else 'none')
sys.exit(1 if fails else 0)
