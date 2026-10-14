#!/usr/bin/env python3
"""0.18.32: Rename (F2) in the upload table renames the files ON DISK -
with the RAW/JPEG partner and the sidecar, all-or-nothing, collision-safe.

Run headless:  QT_QPA_PLATFORM=offscreen python3 test_diskrename_01832.py
"""
import os
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
_HOME = tempfile.mkdtemp()
os.environ['HOME'] = _HOME
os.environ['USERPROFILE'] = _HOME
os.environ['CAMMELLO_WORKFLOWS'] = os.path.join(_HOME, 'workflows.toml')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication, QMessageBox, QDialog
from PyQt5.QtGui import QImage

import Cammello
from cammello import culling, mw_files
from cammello.logging_setup import setup_logging

app = QApplication(sys.argv)
logger, emitter, gui_handler, log_path = setup_logging()
fails = []


def check(name, cond, detail=''):
    print(('PASS' if cond else 'FAIL'), name, detail)
    if not cond:
        fails.append(name)


def touch(path):
    with open(path, 'wb') as fh:
        fh.write(b'x')


d = tempfile.mkdtemp()

# ── core ─────────────────────────────────────────────────────────────────
for n in ('A.CR3', 'A.JPG', 'A.xmp', 'B.JPG', 'C.JPG', 'Other.JPG'):
    touch(os.path.join(d, n))
comp = [os.path.basename(p) for p in
        culling.companion_paths(os.path.join(d, 'A.JPG'))]
check('companions: pair + sidecar', sorted(comp) == ['A.CR3', 'A.JPG',
                                                     'A.xmp'], str(comp))
plan, probs = culling.plan_disk_renames([(os.path.join(d, 'A.JPG'), 'New1')])
check('plan renames the whole picture', len(plan) == 3 and not probs)
plan, probs = culling.plan_disk_renames([(os.path.join(d, 'B.JPG'), 'C')])
check('clash detected', [c for c, _ in probs] == ['clash'], str(probs))
plan, probs = culling.plan_disk_renames([(os.path.join(d, 'B.JPG'), 'a/b')])
check('bad characters', [c for c, _ in probs] == ['chars'])
plan, probs = culling.plan_disk_renames([(os.path.join(d, 'B.JPG'), 'CON')])
check('reserved name', [c for c, _ in probs] == ['reserved'])
plan, probs = culling.plan_disk_renames(
    [(os.path.join(d, 'B.JPG'), 'Same'), (os.path.join(d, 'C.JPG'), 'Same')])
check('two pictures, one name', 'twice' in [c for c, _ in probs], str(probs))
# a batch that shifts names along: B->C and C->D (C is freed by the batch)
plan, probs = culling.plan_disk_renames(
    [(os.path.join(d, 'B.JPG'), 'C'), (os.path.join(d, 'C.JPG'), 'D')])
check('name freed by the batch is fine', not probs, str(probs))
culling.execute_disk_renames(plan)
check('shifted: C.JPG is old B, D.JPG is old C',
      os.path.exists(os.path.join(d, 'C.JPG'))
      and os.path.exists(os.path.join(d, 'D.JPG'))
      and not os.path.exists(os.path.join(d, 'B.JPG')))
plan, probs = culling.plan_disk_renames([(os.path.join(d, 'A.JPG'), 'New1')])
culling.execute_disk_renames(plan)
check('pair + sidecar renamed on disk',
      all(os.path.exists(os.path.join(d, 'New1' + e))
          for e in ('.CR3', '.JPG', '.xmp'))
      and not os.path.exists(os.path.join(d, 'A.JPG')))
# case-only change
plan, probs = culling.plan_disk_renames([(os.path.join(d, 'Other.JPG'),
                                          'OTHER')])
check('case-only change allowed', not probs, str(probs))

# ── GUI ──────────────────────────────────────────────────────────────────
shown = []
QMessageBox.warning = staticmethod(lambda *a, **k: shown.append(a[2]))
w = Cammello.MainWindow(logger, emitter, gui_handler, log_path)

e = tempfile.mkdtemp()
for n in ('P1.JPG', 'P2.JPG'):
    img = os.path.join(e, n)
    QImage(40, 30, QImage.Format_RGB32).save(img, 'JPG')
touch(os.path.join(e, 'P1.xmp'))
w._add_paths([os.path.join(e, 'P1.JPG'), os.path.join(e, 'P2.JPG')])
app.processEvents()


class FakeDlg:
    result = ['Event_001', 'Event_002']

    def __init__(self, *a, **k):
        pass

    def exec(self):
        return QDialog.Accepted

    def names(self):
        return list(FakeDlg.result)


mw_files.BulkRenameDialog = FakeDlg
w.table.selectAll()
w._rename_selected()
names = sorted(os.listdir(e))
check('files renamed on disk', names == ['Event_001.JPG', 'Event_001.xmp',
                                         'Event_002.JPG'], str(names))
check('table points at the new files',
      w._row_path(0) == os.path.join(e, 'Event_001.JPG')
      and w.table.item(0, w.COL_FILENAME).text() == 'Event_001.JPG')
check('target name set', w.table.item(0, w.COL_TITLE).text()
      == 'Event_001.JPG')

# collision: nothing at all changes
touch(os.path.join(e, 'Taken.JPG'))
FakeDlg.result = ['Fresh_1', 'Taken']
before = sorted(os.listdir(e))
tbefore = w.table.item(0, w.COL_TITLE).text()
w.table.selectAll()
w._rename_selected()
check('collision: disk untouched', sorted(os.listdir(e)) == before)
check('collision: table untouched',
      w.table.item(0, w.COL_TITLE).text() == tbefore)
check('collision: user told', bool(shown) and 'Nothing was renamed' in shown[-1],
      str(shown[-1:]))

print('FAILURES:', fails or 'none')
os._exit(1 if fails else 0)
