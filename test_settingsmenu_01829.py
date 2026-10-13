#!/usr/bin/env python3
"""0.18.29: "Save settings" and the settings-file import/export moved from
the right column into the File menu ("Save base_description ..."), and the
base captions can be hidden by a workflow ('captions_basis').

Run headless:  QT_QPA_PLATFORM=offscreen python3 test_settingsmenu_01829.py
"""
import os
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
_HOME = tempfile.mkdtemp()
os.environ['HOME'] = _HOME
os.environ['USERPROFILE'] = _HOME
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication, QPushButton, QMessageBox

import Cammello
from cammello import i18n, workflow_config as wc
from cammello.logging_setup import setup_logging

app = QApplication.instance() or QApplication([])
QMessageBox.information = staticmethod(lambda *a, **k: None)
QMessageBox.warning = staticmethod(lambda *a, **k: None)
logger, emitter, gui_handler, log_path = setup_logging()
fails = []


def check(name, cond, detail=''):
    if not cond:
        fails.append(name)
        print('FAIL', name, detail)


w = Cammello.MainWindow(logger, emitter, gui_handler, log_path)
file_menu = next(a.menu() for a in w.menuBar().actions()
                 if a.text().replace('&', '') == 'File')
texts = [a.text() for a in file_menu.actions()]
for t in ('Save base_description', 'Save base_description to file…',
          'Load base_description from file…'):
    check(f'File menu has "{t}"', t in texts, str(texts))
check('the "incl. selected file" tick is gone',
      'incl. selected file' not in texts
      and not hasattr(w, 'export_file_desc_act'))
check('the export helper says no', w._export_file_desc() is False)

labels = [b.text() for b in w.findChildren(QPushButton)]
for gone in ('Save settings', 'Save to file…', 'Load from file…'):
    check(f'no "{gone}" button in the window', gone not in labels)
check('no old checkbox attribute left', not hasattr(w, 'export_file_desc_cb'))

# The menu entry still saves.
w.status_bar.clearMessage()
next(a for a in file_menu.actions()
     if a.text() == 'Save base_description').trigger()
check('saving from the menu reports it',
      w.status_bar.currentMessage() == i18n.tr('Settings saved.'),
      w.status_bar.currentMessage())

for k in ('Save base_description', 'Save base_description to file…',
          'Load base_description from file…', 'Captions (all files):'):
    check(f'translated: {k}',
          set(i18n.TRANSLATIONS.get(k, {})) >= {'de', 'es', 'fr', 'it'})

# ── base captions hidden by a workflow ──────────────────────────────────────
base = w.base_struct
check('the field is in the registry, on by default',
      'captions_basis' in wc.FIELD_NAMES
      and 'captions_basis' not in wc.DEFAULT_OFF)
check('portraits hides it, buildings does not',
      'captions_basis' in wc.BUILTIN[0]['hide']
      and 'captions_basis' not in wc.BUILTIN[1]['hide'])
w._set_field_visible('captions_basis', False)
check('hiding hides editor AND label', base.captions_editor.isHidden()
      and base.captions_label.isHidden())
check('the per-file captions stay',
      not w.file_struct.captions_editor.isHidden())
w._set_field_visible('captions_basis', True)
check('showing brings both back', not base.captions_editor.isHidden()
      and not base.captions_label.isHidden())

# ── one suggest button per file: "Suggest captions" does the categories ─────
def suggest_btns(ed):
    return [b for b in ed.findChildren(QPushButton) if b.text() == 'Suggest']


check('the per-file editor has no separate category button',
      suggest_btns(w.file_struct) == [], str(suggest_btns(w.file_struct)))
check('the base editor keeps its created-during one',
      len(suggest_btns(base)) == 1)
check('Suggest captions is still there',
      w.file_struct.suggest_captions_btn.text() == 'Suggest captions')

# ── the raw base text is for expert mode only ───────────────────────────────
w.show()
app.processEvents()
check('normal mode: the raw base text field is hidden',
      w.base_text_edit.isHidden() and not w.base_struct.isHidden())
for key in ('portraits', 'buildings', 'music'):
    w.workflow_combo.setCurrentIndex(w.workflow_combo.findData(key))
    app.processEvents()
    check(f'still hidden after switching to {key}',
          w.base_text_edit.isHidden())
w.expert_cb.setChecked(True)
app.processEvents()
check('expert mode: shown, the structured view hidden',
      not w.base_text_edit.isHidden() and w.base_struct.isHidden())
w.expert_cb.setChecked(False)
app.processEvents()
check('and hidden again afterwards', w.base_text_edit.isHidden())
w.close()

print('FAILURES:', fails or 'none')
sys.exit(1 if fails else 0)
