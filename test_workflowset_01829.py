"""[workflow.setzen] (0.18.29): an event workflow REPLACES its templates,
categories and "created during" when the user picks it in the dropdown.

Not a fill-if-empty preset: last year's event must not survive. And not
applied by anything but the user's pick - neither the start-up restore nor
"Reload workflows" may overwrite fields the user has tuned since.

HOME is redirected so no real ~/Cammello/workflows.toml is touched.
Run headless:  QT_QPA_PLATFORM=offscreen python3 test_workflowset_01829.py
"""
import os
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
_HOME = tempfile.mkdtemp()
os.environ['HOME'] = _HOME
os.environ['USERPROFILE'] = _HOME          # Windows
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication, QMessageBox

import Cammello
from cammello import workflows
from cammello import workflow_config as wc
from cammello.logging_setup import setup_logging

app = QApplication(sys.argv)
logger, emitter, gui_handler, log_path = setup_logging()

fails = []

# The deliberately flawed file makes "Reload workflows" speak: no modal
# boxes in a headless run.
QMessageBox.information = staticmethod(lambda *a, **k: None)
QMessageBox.warning = staticmethod(lambda *a, **k: None)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)


def check(name, cond, detail=''):
    if cond:
        print('PASS', name, detail)
    else:
        print('FAIL', name, detail)
        fails.append(name)


def write(text):
    os.makedirs(os.path.dirname(wc.path()), exist_ok=True)
    with open(wc.path(), 'w', encoding='utf-8') as fh:
        fh.write(text)
    return wc.reload()


FILE = '''
[[workflow]]
schluessel = "portraits"
name = "Events/Portraits"
felder_aus = ["kamerastandort", "objektstandort"]

[[workflow]]
schluessel = "buchmesse"
name = "Frankfurter Buchmesse 2026"
felder_aus = ["kamerastandort", "objektstandort"]

  [workflow.setzen]
  vorlagen = "{{WikiPortraits Test Fair 2026}}"
  kategorien = "Test Fair 2026; Test Fair"
  entstanden_waehrend = "Q42"
  nonsense = "x"
  zeigt = 7

  [workflow.vorbelegung]
  autor = "Test Author"
'''

# ── 1. the file format ──────────────────────────────────────────────────────
entries = write(FILE)
by = {w['key']: w for w in entries}
check('the setzen section is read',
      by['buchmesse']['set'] == {
          'vorlagen': '{{WikiPortraits Test Fair 2026}}',
          'kategorien': 'Test Fair 2026; Test Fair',
          'entstanden_waehrend': 'Q42'}, str(by['buchmesse']['set']))
check('an unknown field is ignored with a warning',
      any('nonsense' in w for w in wc.LAST_WARNINGS), str(wc.LAST_WARNINGS))
check('a value that is not text is ignored with a warning',
      any('zeigt' in w and 'not text' in w for w in wc.LAST_WARNINGS),
      str(wc.LAST_WARNINGS))
check('a workflow without the section sets nothing',
      by['portraits']['set'] == {})
check('sets_of() hands out a copy',
      workflows.sets_of('buchmesse') == by['buchmesse']['set']
      and workflows.sets_of('buchmesse') is not by['buchmesse']['set'])
check('sets_of() of an unknown key does not raise',
      isinstance(workflows.sets_of('does-not-exist'), dict))
check('the built-ins set nothing',
      all(w.get('set') == {} for w in wc.BUILTIN))
check('a fresh template documents the section',
      'setzen' in wc.template_text() and 'REPLACES' in wc.template_text())
check('render_block writes setzen back out',
      'setzen.vorlagen = ' in wc.render_block(
          dict(wc.BUILTIN[0], set={'vorlagen': '{{X}}'})))
write('[[workflow]\nschluessel = "a"\n')
check('a broken file falls back to the built-ins (which set nothing)',
      all(w['set'] == {} for w in wc.load()))
write(FILE)

# ── 2. in the window ────────────────────────────────────────────────────────
w = Cammello.MainWindow(logger, emitter, gui_handler, log_path)
cb = w.workflow_combo
check('the new workflow is in the dropdown',
      cb.findData('buchmesse') >= 0)

base = w.base_struct
# State left over from "last year's event", filled by hand.
w.other_templates_edit.setText('{{WikiPortraits Old Fair 2025}}')
base.categories.setText('Old Fair 2025')
base.created_during.setText('Q1')
w.file_struct.categories.setText('Per file category')

cb.setCurrentIndex(cb.findData('buchmesse'))
check('the templates are REPLACED, not filled',
      w.other_templates_edit.text() == '{{WikiPortraits Test Fair 2026}}',
      w.other_templates_edit.text())
check('the base categories are replaced',
      base.categories.text() == 'Test Fair 2026; Test Fair',
      base.categories.text())
check('created during is replaced', base.created_during.text() == 'Q42',
      base.created_during.text())
check('the categories of the selected FILE are not touched',
      w.file_struct.categories.text() == 'Per file category',
      w.file_struct.categories.text())
check('vorbelegung still fills a field that was empty',
      w.author_edit.text() == 'Test Author', w.author_edit.text())
check('the status line says what was set',
      'Buchmesse' in w.status_bar.currentMessage(),
      w.status_bar.currentMessage())

# The user tunes the fields afterwards ...
base.categories.setText('Test Fair 2026; Test Fair; Extra by hand')
# ... and "Reload workflows" must NOT put the template back.
w._reload_workflows()
check('Reload workflows does not overwrite tuned fields',
      base.categories.text() == 'Test Fair 2026; Test Fair; Extra by hand',
      base.categories.text())
check('and keeps the selected workflow', w.current_workflow() == 'buchmesse')

# Switching away leaves the fields alone (that workflow sets nothing).
cb.setCurrentIndex(cb.findData('portraits'))
check('switching to a workflow without setzen leaves the fields',
      w.other_templates_edit.text() == '{{WikiPortraits Test Fair 2026}}'
      and base.created_during.text() == 'Q42')

# Picking it again applies it again (the one-click promise).
base.created_during.setText('Q99')
cb.setCurrentIndex(cb.findData('buchmesse'))
check('picking it again sets it again', base.created_during.text() == 'Q42',
      base.created_during.text())

# The start-up restore (signals blocked) never applies it.
calls = []
orig = w._apply_workflow_sets
w._apply_workflow_sets = lambda key: calls.append(key)
w._restore_settings()
check('the restore at start-up does not call setzen', calls == [], str(calls))
w._on_workflow_changed(apply_set=False)
check('apply_set=False never calls setzen either', calls == [], str(calls))
w._on_workflow_changed()
check('a normal switch does', len(calls) == 1, str(calls))
w._apply_workflow_sets = orig
w.close()

print()
print('FAILURES:', fails or 'none')
sys.exit(1 if fails else 0)
