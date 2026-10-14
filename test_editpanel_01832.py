#!/usr/bin/env python3
"""0.18.32: 'Other templates' show in the Wikitext column; the floating edit
panel hides with its cross and the toolbar pencil brings it back.

Run headless:  QT_QPA_PLATFORM=offscreen python3 test_editpanel_01832.py
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

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QImage
from PyQt5.QtCore import QSettings

import Cammello
from cammello.constants import APP_NAME
from cammello.logging_setup import setup_logging

app = QApplication(sys.argv)
QSettings(APP_NAME, 'Main').remove('cull_edit_panel')
logger, emitter, gui_handler, log_path = setup_logging()
fails = []


def check(name, cond, detail=''):
    print(('PASS' if cond else 'FAIL'), name, detail)
    if not cond:
        fails.append(name)


w = Cammello.MainWindow(logger, emitter, gui_handler, log_path)
w.show()
app.processEvents()

# 1) other templates in the Wikitext column
img = os.path.join(_HOME, 'a.jpg')
QImage(40, 30, QImage.Format_RGB32).save(img, 'JPG')
w._add_paths([img])
app.processEvents()
check('row added', w.table.rowCount() == 1)
w.other_templates_edit.setText('{{WikiPortraits at X}}')
w._do_refresh_all_effective()
eff = w.table.item(0, w.COL_EFFECTIVE).text()
check('templates in Wikitext column', '{{WikiPortraits at X}}' in eff, eff)
w.other_templates_edit.setText('')
w._do_refresh_all_effective()
eff2 = w.table.item(0, w.COL_EFFECTIVE).text()
check('removed again', '{{WikiPortraits at X}}' not in eff2, eff2)
# the upload text itself is unchanged by the preview addition
check('upload text has no templates',
      '{{WikiPortraits at X}}' not in w._effective_text(''))

# 2) edit panel toggle
if hasattr(w, 'cull_edit_panel'):
    check('shown by default', w._cull_edit_panel_shown())
    w.cull_edit_panel.close_btn.click()
    check('cross hides + remembers', not w._cull_edit_panel_shown()
          and w.cull_edit_panel.isHidden())
    w.cull_edit_toggle.click()
    check('pencil shows again', w._cull_edit_panel_shown())
    w.cull_edit_toggle.click()
    check('pencil hides', not w._cull_edit_panel_shown())
    from cammello.widgets import lucide
    check('pencil icon exists', not lucide('pencil', '#000000').isNull())
else:
    print('SKIP edit panel (culling off)')

QSettings(APP_NAME, 'Main').remove('cull_edit_panel')
if hasattr(w, '_cull_wb'):
    w._cull_shutdown()
print('FAILURES:', fails or 'none')
os._exit(1 if fails else 0)
