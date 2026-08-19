"""The workflow switch at the top of the MediaWiki tab (0.15.0).

Checks the DATA module on its own (Qt-free, like channels/edits) and the
dropdown that drives it: position, entries, persistence, and the promise
that switching never overwrites something already entered.
"""
import os
import tempfile
# 0.16.1: point the workflow file at a scratch copy BEFORE cammello is
# imported. Without this every window test would read the user's own
# workflows.toml, so editing it could break tests unrelated to workflows.
os.environ.setdefault('CAMMELLO_WORKFLOWS',
                      os.path.join(tempfile.mkdtemp(), 'workflows.toml'))
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtWidgets import QApplication, QComboBox

import Cammello
from cammello import workflows
from cammello.i18n import TRANSLATIONS, UI_LANGUAGES
from cammello.logging_setup import setup_logging

app = QApplication(sys.argv)
logger, emitter, gui_handler, log_path = setup_logging()
w = Cammello.MainWindow(logger, emitter, gui_handler, log_path)

fails = []


def check(name, cond, detail=''):
    if cond:
        print('PASS', name, detail)
    else:
        print('FAIL', name, detail)
        fails.append(name)


# ── the data module ──────────────────────────────────────────────────────────
# 0.18.0: three built-in workflows - the music one joined the two of
# 0.15.0. Checked by name rather than by count so that adding a fourth is
# a decision, not a test failure to be silenced.
check('the built-in workflows are there',
      workflows.keys() == ['portraits', 'buildings', 'music'],
      str(workflows.keys()))
check('the default key resolves',
      workflows.by_key(workflows.DEFAULT_KEY)['key'] == workflows.DEFAULT_KEY)
check('an unknown key falls back to the default',
      workflows.by_key('nonsense-key')['key'] == workflows.DEFAULT_KEY)
check('portraits offers no object location',
      not workflows.offers_object_location('portraits'))
check('buildings offers the object location',
      workflows.offers_object_location('buildings'))
# 0.16.1: the camera position is hidden in the event workflow just like the
# object position - "alles mit Location brauchen wir nicht im
# Event-Workflow". Until 0.16.0 the flag said the opposite of what the UI
# did: camera_location was True for portraits, while
# _apply_workflow_visibility hid BOTH coordinate rows there. Nothing was
# broken because nobody read the flag; now that the file drives the UI, the
# two agree.
check('portraits offers no camera location either',
      not workflows.offers_camera_location('portraits'))
check('buildings offers the camera location',
      workflows.offers_camera_location('buildings'))
# 'show' joined in 0.18.0: the fields a workflow switches ON, needed
# because felder_aus alone could not carry fields that are off by default.
check('every entry carries the full set of fields',
      all(set(wf) == {'key', 'label', 'hide', 'show', 'preset', 'example'}
          for wf in workflows.all_workflows()),
      str([sorted(wf) for wf in workflows.all_workflows()][:1]))
check('the keys are unique',
      len(set(workflows.keys())) == len(workflows.keys()))

# Every label must be translatable in all four non-source languages -
# test_i18n only sees literal tr('...') calls, and these labels reach tr()
# through a variable.
for wf in workflows.all_workflows():
    entry = TRANSLATIONS.get(wf['label'])
    check(f'label of {wf["key"]} is in the i18n table', entry is not None,
          wf['label'])
    if entry:
        missing = [c for c, _n in UI_LANGUAGES
                   if c != 'en' and not entry.get(c)]
        check(f'label of {wf["key"]} has all languages', not missing,
              str(missing))

# ── the dropdown ─────────────────────────────────────────────────────────────
cb = getattr(w, 'workflow_combo', None)
check('the MediaWiki tab has a workflow dropdown', isinstance(cb, QComboBox))

if isinstance(cb, QComboBox):
    check('the dropdown lists every workflow',
          cb.count() == len(workflows.keys()), f'{cb.count()} entries')
    check('the entries carry the workflow keys as data',
          [cb.itemData(i) for i in range(cb.count())] == workflows.keys())
    check('current_workflow() matches the dropdown',
          w.current_workflow() == cb.currentData())

    # Position: the dropdown must sit ABOVE the toolbar, i.e. in the first
    # row of the page layout (Harald: "an der Spitze vom MediaWiki-Tab").
    page = cb.parentWidget()
    while page is not None and page.layout() is None:
        page = page.parentWidget()
    layout = page.layout() if page is not None else None
    first = layout.itemAt(0) if layout is not None else None
    first_layout = first.layout() if first is not None else None
    in_first_row = False
    if first_layout is not None:
        in_first_row = any(first_layout.itemAt(i).widget() is cb
                           for i in range(first_layout.count()))
    check('the dropdown sits in the first row of the tab', in_first_row)

    # Switching must not throw away entered text.
    w.other_templates_edit.setText('{{WikiPortraits at Berlinale 2026}}')
    other = [k for k in workflows.keys() if k != w.current_workflow()][0]
    cb.setCurrentIndex(cb.findData(other))
    check('switching keeps text the user entered',
          w.other_templates_edit.text() == '{{WikiPortraits at Berlinale 2026}}',
          w.other_templates_edit.text())
    check('switching persists the choice',
          w.settings.value('workflow') == other,
          str(w.settings.value('workflow')))
    check('current_workflow() follows the switch',
          w.current_workflow() == other)

print()
print('FAILURES:', ', '.join(fails) if fails else 'none')
sys.exit(1 if fails else 0)
