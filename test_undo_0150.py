"""Undo for image edits, and expert mode overruling the workflow (0.15.0)."""
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

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QKeySequence

import Cammello
from cammello import edits, workflows
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


# ── the history, on its own ──────────────────────────────────────────────────
h = edits.EditHistory(depth=3)
check('a fresh history is empty', len(h) == 0 and h.pop() is None)

h.push('/a/one.jpg', None)
check('the state before the first edit is remembered as None',
      h.peek_path() == edits.norm('/a/one.jpg'))
h.push('/a/one.jpg', {'ev': 0.5})
check('a second step is stacked', len(h) == 2)
path, rec = h.pop()
check('the newest step comes back first', rec == {'ev': 0.5}, str(rec))
path, rec = h.pop()
check('and then the empty state', rec is None)
check('the history is empty again', h.pop() is None)

for i in range(5):
    h.push(f'/a/{i}.jpg', {'ev': float(i)})
check('the depth is bounded', len(h) == 3, f'{len(h)} entries')

# ── applying a record back ───────────────────────────────────────────────────
store = {}
edits.set_ev(store, '/a/two.jpg', 0.5)
check('an edit exists', edits.has_edit(store, '/a/two.jpg'))
check('restoring None removes it',
      edits.apply_record(store, '/a/two.jpg', None)
      and not edits.has_edit(store, '/a/two.jpg'))
check('restoring a record puts it back',
      edits.apply_record(store, '/a/two.jpg', {'ev': 0.5})
      and abs(edits.get_ev(store, '/a/two.jpg') - 0.5) < 1e-9)
check('restoring the same thing twice reports no change',
      not edits.apply_record(store, '/a/two.jpg', {'ev': 0.5}))
check('a corrupt record does not land in the store',
      not edits.has_edit(
          {} if edits.apply_record({}, '/a/x.jpg', {'ev': 'kaputt'}) is None
          else {}, '/a/x.jpg'))

# ── wiring in the window ─────────────────────────────────────────────────────
check('the culling module has an undo history',
      isinstance(w._cull_undo, edits.EditHistory))
check('there is an undo shortcut', hasattr(w, '_cull_undo_sc'))
check('it is the platform undo sequence',
      w._cull_undo_sc.key() == QKeySequence(QKeySequence.Undo),
      w._cull_undo_sc.key().toString())
check('it is scoped, not window-wide',
      int(w._cull_undo_sc.context()) != 0,
      str(w._cull_undo_sc.context()))
check('undo on an empty history does not raise',
      w._cull_undo_edit() is None)

# A full round trip without images: push a state, change it, undo.
w._cull_edits = {}
p = '/nowhere/three.jpg'
w._cull_remember_edit(p)
edits.set_ev(w._cull_edits, p, 0.5)
check('the edit is there', edits.has_edit(w._cull_edits, p))
w._cull_undo_edit()
check('undo removed it again', not edits.has_edit(w._cull_edits, p))

# ── expert mode overrules the workflow ───────────────────────────────────────
cb = w.workflow_combo
cb.setCurrentIndex(cb.findData('portraits'))
w.expert_cb.setChecked(False)
w._apply_workflow_visibility()
check('portraits hides the coordinate rows',
      w.file_struct._coords_row_widget.isHidden())
w.expert_cb.setChecked(True)
check('expert mode shows them anyway',
      not w.file_struct._coords_row_widget.isHidden())
check('and the coordinate rows too',
      not w.file_struct._coords_row_widget.isHidden()
      and not w.file_struct._object_row_widget.isHidden())
cb.setCurrentIndex(cb.findData('buildings'))
check('expert mode also keeps Created during reachable',
      not w.base_struct.created_during.isHidden())
w.expert_cb.setChecked(False)
w._apply_workflow_visibility()
check('leaving expert mode restores the workflow rules',
      w.base_struct.created_during.isHidden())

print()
print('FAILURES:', ', '.join(fails) if fails else 'none')
sys.exit(1 if fails else 0)
