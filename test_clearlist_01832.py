#!/usr/bin/env python3
"""0.18.32: the "Clear list" button empties the upload table (asks only when
a file has a description of its own) and the culling [T] badges follow.

Run headless:  QT_QPA_PLATFORM=offscreen python3 test_clearlist_01832.py
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

from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtGui import QImage

import Cammello
from cammello.logging_setup import setup_logging

app = QApplication(sys.argv)
logger, emitter, gui_handler, log_path = setup_logging()
fails = []


def check(name, cond, detail=''):
    print(('PASS' if cond else 'FAIL'), name, detail)
    if not cond:
        fails.append(name)


asked = []
answer = [QMessageBox.Yes]
QMessageBox.question = staticmethod(
    lambda *a, **k: (asked.append(a[2]), answer[0])[1])

w = Cammello.MainWindow(logger, emitter, gui_handler, log_path)
check('button exists', hasattr(w, 'clear_list_btn'))
paths = []
for n in ('a.jpg', 'b.jpg'):
    p = os.path.join(_HOME, n)
    QImage(40, 30, QImage.Format_RGB32).save(p, 'JPG')
    paths.append(p)
w._add_paths(paths)
check('two rows', w.table.rowCount() == 2)

# culling badge follows
if hasattr(w, '_cull_items'):
    from cammello import culling
    ci = culling.CullItem('a', jpg_path=paths[0])
    ci.in_table = True
    w._cull_items = [ci]
    w._cull_visible = []
    w._cull_refresh_table_badges()
    check('badge stays while the file is listed', ci.in_table)

w.clear_list_btn.click()
check('no description: cleared without asking',
      w.table.rowCount() == 0 and not asked, str(asked))
if hasattr(w, '_cull_items'):
    check('culling badge removed', not ci.in_table)

w._add_paths(paths)
from cammello.constants import *  # noqa
w.table.item(0, w.COL_DESC).setText('caption_en=Mine')
answer[0] = QMessageBox.No
w.clear_list_btn.click()
check('typed description: asked, "No" keeps the list',
      len(asked) == 1 and w.table.rowCount() == 2)
answer[0] = QMessageBox.Yes
w.clear_list_btn.click()
check('"Yes" clears', w.table.rowCount() == 0)
w.clear_list_btn.click()
check('empty list: nothing happens', len(asked) == 2)

print('FAILURES:', fails or 'none')
os._exit(1 if fails else 0)
