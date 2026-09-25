#!/usr/bin/env python3
"""0.18.23: Ctrl+Z takes back ratings and colour labels, a bulk action in
one step, with redo and an Edit menu.

Run headless:  QT_QPA_PLATFORM=offscreen python3 test_undo_01823.py
"""
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QKeySequence
from PyQt5.QtCore import QSettings

app = QApplication.instance() or QApplication([])

import Cammello                                            # noqa: E402,F401
from cammello import edits                                 # noqa: E402
from cammello.constants import APP_NAME                    # noqa: E402
from cammello.logging_setup import setup_logging           # noqa: E402

FAILED = []
PASSED = 0


def check(what, ok, detail=''):
    global PASSED
    if ok:
        PASSED += 1
    else:
        FAILED.append(f'{what}: {detail}')
        print(f'  FAIL {what} {detail}')


def eq(what, got, want):
    check(what, got == want, f'{got!r} statt {want!r}')


# ── 1. ActionHistory, the pure bookkeeping ───────────────────────────────
h = edits.ActionHistory(depth=3)
check('a fresh stack can neither undo nor redo',
      not h.can_undo() and not h.can_redo())
eq('and has no labels', (h.undo_label(), h.redo_label()), ('', ''))
check('pushing nothing is ignored', h.push('x', []) is None and not h)

h.push('A', [('p1', 1, '')])
h.push('B', [('p2', 2, '')])
eq('the newest label is on top', h.undo_label(), 'B')
eq('two actions are two entries', len(h), 2)

h.push('C', [('p3', 3, '')])
h.push('D', [('p4', 4, '')])
eq('the depth is honoured', len(h), 3)
label, steps = h.pop_undo()
eq('the newest comes off first', label, 'D')
h.push_redo(label, steps)
check('and lands on the redo stack', h.can_redo() and h.redo_label() == 'D')

# A NEW action must kill the redo branch - redoing against a changed state
# would put back values that no longer fit.
h.push('E', [('p5', 5, '')])
check('a new action clears the redo branch', not h.can_redo())

# push_undo_only must NOT clear it, or a second redo is impossible.
h2 = edits.ActionHistory()
h2.push('A', [('p', 0, '')])
lab, st = h2.pop_undo()
h2.push_redo(lab, st)
lab2, st2 = h2.pop_redo()
h2.push_undo_only(lab2, st2)
check('redoing keeps the undo stack usable', h2.can_undo())
h2.push_redo('again', [('p', 1, '')])
check('and the redo branch survives it', h2.can_redo())

h2.clear()
check('clear empties both', not h2.can_undo() and not h2.can_redo())
eq('depth below one is clamped', len(edits.ActionHistory(depth=0)._undo), 0)
check('the default depth is ten', edits.ACTION_DEPTH == 10,
      str(edits.ACTION_DEPTH))

# ── the window ───────────────────────────────────────────────────────────
ts = QSettings(APP_NAME, 'Main')
ts.setValue('feature_culling', True)
ts.sync()
logger, emitter, gui_handler, log_path = setup_logging()
import logging as _logging                                 # noqa: E402
for _h in logger.handlers:
    if isinstance(_h, _logging.StreamHandler) and not hasattr(_h,
                                                              'baseFilename'):
        _h.setLevel(_logging.CRITICAL)
w = Cammello.MainWindow(logger, emitter, gui_handler, log_path)

if not hasattr(w, '_cull_actions'):                        # pragma: no cover
    print('SKIP - culling tab not built in this environment')
else:
    # ── 2. the Edit menu ─────────────────────────────────────────────────
    titles = [m.title() for m in w.menuBar().findChildren(type(
        w.menuBar().addMenu('x'))) if m.title()]
    check('there is an Edit menu',
          any('edit' in t.lower() or 'bearbeit' in t.lower()
              for t in titles), str(titles))
    check('with an Undo entry', getattr(w, 'act_undo', None) is not None)
    check('and a Redo entry', getattr(w, 'act_redo', None) is not None)
    eq('Undo carries the platform Undo shortcut',
       w.act_undo.shortcut(), QKeySequence(QKeySequence.Undo))
    eq('Redo carries the platform Redo shortcut',
       w.act_redo.shortcut(), QKeySequence(QKeySequence.Redo))
    check('both start greyed out',
          not w.act_undo.isEnabled() and not w.act_redo.isEnabled())
    # Two owners for one key sequence make Qt fire NEITHER.
    for name in ('_cull_undo_sc', '_cull_redo_sc'):
        sc = getattr(w, name, None)
        check(f'{name} stands down for the menu action',
              sc is not None and not sc.isEnabled())

    # ── 3. a bulk rating is ONE undo step ────────────────────────────────
    class FakeItem:
        def __init__(self, path):
            self.display_path = path
            self.rating = 0
            self.label = ''

    class FakeQueue:
        def __init__(self):
            self.seen = []

        def enqueue(self, item):
            self.seen.append(item.display_path)

    items = [FakeItem(f'/tmp/img{i}.jpg') for i in range(200)]
    w._cull_visible = items
    w._cull_wb = FakeQueue()
    w._cull_target_rows = lambda: list(range(len(items)))
    w._cull_decorate_row = lambda r: None
    w._cull_set_status = lambda: None
    w.cull_advance_cb.setChecked(False)
    w._cull_actions.clear()

    w._cull_set_rating(-1)                       # the bulk rejection
    check('200 images were rejected',
          all(it.rating == -1 for it in items))
    eq('and that is exactly one undo step', len(w._cull_actions), 1)
    label = w._cull_actions.undo_label()
    check('the step names the action and the count',
          '200' in label and label, label)
    check('the Undo entry woke up and says what it would do',
          w.act_undo.isEnabled() and '200' in w.act_undo.text(),
          w.act_undo.text())

    w._cull_undo_action()
    check('one Ctrl+Z gives all 200 back',
          all(it.rating == 0 for it in items))
    check('the writeback queue heard about every one of them',
          len(set(w._cull_wb.seen)) == 200, str(len(set(w._cull_wb.seen))))
    check('and redo is now offered', w.act_redo.isEnabled())

    w._cull_redo_action()
    check('redo rejects them again', all(it.rating == -1 for it in items))
    check('and undo is offered again', w.act_undo.isEnabled())
    w._cull_undo_action()
    check('and it can be taken back once more',
          all(it.rating == 0 for it in items))

    # ── 4. labels, mixed previous values, no-ops ─────────────────────────
    items[0].rating = 5
    items[1].rating = 3
    w._cull_target_rows = lambda: [0, 1]
    w._cull_actions.clear()
    w._cull_set_rating(1)
    eq('a mixed selection is still one step', len(w._cull_actions), 1)
    w._cull_undo_action()
    eq('every image gets its OWN old value back',
       (items[0].rating, items[1].rating), (5, 3))

    w._cull_actions.clear()
    items[0].rating = 2
    items[1].rating = 2
    w._cull_set_rating(2)                        # changes nothing
    eq('an action that changes nothing is not remembered',
       len(w._cull_actions), 0)

    w._cull_actions.clear()
    w.cull_labelset_combo.setCurrentIndex(0)
    w._cull_set_label(0)
    eq('a colour label is remembered too', len(w._cull_actions), 1)
    coloured = items[0].label
    check('and it really set one', bool(coloured), repr(coloured))
    w._cull_undo_action()
    eq('undo clears it again', items[0].label, '')

    # ── 5. ten deep, and the oldest falls off ────────────────────────────
    w._cull_actions.clear()
    w._cull_target_rows = lambda: [0]
    for n in range(1, 13):
        items[0].rating = 0
        w._cull_set_rating(n % 6)
    eq('the stack stops at ten', len(w._cull_actions), 10)

    # ── 6. images that are gone are skipped, not guessed ─────────────────
    w._cull_actions.clear()
    w._cull_target_rows = lambda: [0, 1]
    items[0].rating = 0
    items[1].rating = 0
    w._cull_set_rating(4)
    w._cull_visible = [items[0]]                 # item 1 no longer visible
    w._cull_undo_action()
    eq('the reachable one is restored', items[0].rating, 0)
    eq('the missing one keeps what it had', items[1].rating, 4)

    # ── 7. the two QK findings ───────────────────────────────────────────
    from cammello.mw_culling import _menu_safe
    eq('a lone ampersand is doubled for the menu',
       _menu_safe('Fashion & Beauty'), 'Fashion && Beauty')
    eq('and text without one is untouched', _menu_safe('Reject'), 'Reject')

    w._cull_actions.clear()
    w._cull_undo.clear()
    w._cull_update_edit_menu()
    check('with both stacks empty Undo is greyed out',
          not w.act_undo.isEnabled())
    # An IMAGE edit must wake the entry too - it did not before the QK.
    w._cull_remember_edit('/tmp/img0.jpg')
    check('an image edit wakes the Undo entry', w.act_undo.isEnabled())
    check('and it stays generic, because that stack carries no labels',
          '(' not in w.act_undo.text(), w.act_undo.text())

    # A colour label with an ampersand must survive into the menu.
    w._cull_undo.clear()
    w._cull_actions.clear()
    w._cull_target_rows = lambda: [0]
    w._cull_visible = items
    items[0].label = ''
    w._cull_apply_to_targets(lambda it: setattr(it, 'label', 'A & B'),
                             'Colour A & B')
    check('the ampersand reaches the menu doubled',
          '&&' in w.act_undo.text(), w.act_undo.text())

    # ── 8. with nothing on the rating stack, Ctrl+Z falls through ────────
    w._cull_actions.clear()
    reached = []
    w._cull_undo_edit = lambda: reached.append('edits')
    w._cull_undo_action()
    eq('an empty rating stack hands over to the image edits', reached,
       ['edits'])

print(f'\n{PASSED} Pruefungen bestanden, {len(FAILED)} gescheitert')
for f in FAILED:
    print('  -', f)
sys.exit(1 if FAILED else 0)
