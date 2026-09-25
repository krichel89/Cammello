#!/usr/bin/env python3
"""0.18.24, the window side of both features:

  * loupe/grid select-all (Ctrl+A / Cmd+A) that drives rating AND sending;
  * the Generate-captions action end to end, with the network and the
    review dialog stubbed so the write path itself is exercised.

Run headless:  QT_QPA_PLATFORM=offscreen python3 test_captions_ui_01824.py
"""
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication, QDialog, QLineEdit
from PyQt5.QtGui import QKeySequence
from PyQt5.QtCore import QSettings

app = QApplication.instance() or QApplication([])

import Cammello                                            # noqa: E402,F401
from cammello import mw_files, widgets, captions           # noqa: E402
from cammello.constants import APP_NAME, CAPTION_LANGS_DEFAULT   # noqa: E402
from cammello.logging_setup import setup_logging           # noqa: E402
from cammello.sdc import decompose_fields                  # noqa: E402

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


# ── entities the stubbed fetch will return ──────────────────────────────────
ENT = {
    'Q1': {'human': True, 'labels': {'en': 'Anna Müller', 'de': 'Anna Müller'},
           'sitelinks': {'dewiki': 'Anna Müller'}},
    'QE': {'human': False, 'labels': {'en': 'Berlinale', 'de': 'Berlinale'},
           'sitelinks': {'dewiki': 'Internationale Filmfestspiele Berlin'}},
}

# ═══ Part A: the Generate-captions dialog, headless ═════════════════════════
rows = [{'row': 0, 'depicts': ['Q1'], 'event': 'QE',
         'captions': {'de': 'Anna Müller bei der Berlinale'}}]
tbl = captions.FuegungTable()
tbl.merge_from(captions.derive_table(rows, ENT, ['en', 'de']))
dlg = widgets.GenerateCaptionsDialog(ENT, rows, tbl, ['en', 'de', 'fr'])
check('every language starts ticked',
      dlg.languages() == ['en', 'de', 'fr'], str(dlg.languages()))
check('linked descriptions are off by default', not dlg.with_links())
# The German conjunction learned from the caption is in the grid and drives
# the example.
out = dlg.result_table()
eq('the learned German conjunction is in the dialog table',
   out.tail('QE', 'de'), ' bei der Berlinale')
# Untick French: it drops out of the languages and the grid.
dlg._lang_boxes['fr'].setChecked(False)
check('unticking a language drops it', 'fr' not in dlg.languages())

# ═══ Part B: the window ═════════════════════════════════════════════════════
ts = QSettings(APP_NAME, 'Main')
ts.setValue('feature_culling', True)
ts.sync()
QSettings(APP_NAME, 'Captions').remove('fuegungen')     # a clean table
logger, emitter, gui_handler, log_path = setup_logging()
import logging as _logging                                 # noqa: E402
for _h in logger.handlers:
    if isinstance(_h, _logging.StreamHandler) and not hasattr(_h,
                                                              'baseFilename'):
        _h.setLevel(_logging.CRITICAL)
w = Cammello.MainWindow(logger, emitter, gui_handler, log_path)

# ── B1: select-all in the culling page drives rating and sending ────────────
if not hasattr(w, '_cull_select_all'):                     # pragma: no cover
    check('the culling page exists', False, 'no _cull_select_all')
else:
    check('there is a Select all action',
          getattr(w, 'act_select_all', None) is not None)
    eq('it carries the platform select-all shortcut',
       w.act_select_all.shortcut(), QKeySequence(QKeySequence.SelectAll))

    class FakeItem:
        def __init__(self, path):
            self.display_path = path
            self.rating = 0
            self.label = ''
            self.is_pair = False

    items = [FakeItem(f'/tmp/s{i}.jpg') for i in range(5)]
    w._cull_visible = items
    # Fill the strip so selectAll has rows to select.
    w.cull_strip.clear()
    from PyQt5.QtWidgets import QListWidgetItem
    for it in items:
        w.cull_strip.addItem(QListWidgetItem(os.path.basename(it.display_path)))

    w.cull_strip.clearSelection()
    w._cull_select_all()
    eq('select-all marks every visible row',
       len(w.cull_strip.selectedItems()), 5)
    eq('and the rating targets are all of them',
       sorted(w._cull_target_rows()), [0, 1, 2, 3, 4])
    eq('and a send targets all of them too',
       sorted(w._cull_send_rows()), [0, 1, 2, 3, 4])

    # A rating now applies to the whole selection in ONE undo step.
    class FakeQueue:
        def __init__(self):
            self.seen = []

        def enqueue(self, item):
            self.seen.append(item.display_path)

    w._cull_wb = FakeQueue()
    w._cull_decorate_row = lambda r: None
    w._cull_set_status = lambda: None
    w.cull_advance_cb.setChecked(False)
    w._cull_actions.clear()
    w._cull_set_rating(2)
    check('rating the selection touches all five',
          all(it.rating == 2 for it in items))
    eq('and it is a single undo step', len(w._cull_actions), 1)

    # The focus guard: a text field keeps its own select-all.
    le = QLineEdit('hello world')
    le.setParent(w)
    le.setFocus()
    app.processEvents()
    if app.focusWidget() is le:
        w.cull_strip.clearSelection()
        w._cull_select_all()
        check('a focused text field keeps its own select-all, images untouched',
              len(w.cull_strip.selectedItems()) == 0
              and le.selectedText() == 'hello world', le.selectedText())
    else:            # offscreen focus can be unreliable; do not fail on it
        check('focus guard (skipped - no focus offscreen)', True)

# ── B2: Generate captions end to end, network and dialog stubbed ────────────
if hasattr(w, '_generate_captions'):
    # A file whose description already carries depicts and the event.
    from PyQt5.QtWidgets import QTableWidgetItem
    from PyQt5.QtCore import Qt
    r = w.table.rowCount()
    w.table.insertRow(r)
    fn = QTableWidgetItem('anna.jpg')
    fn.setData(Qt.UserRole, '/tmp/anna.jpg')
    w.table.setItem(r, w.COL_FILENAME, fn)
    w.table.setItem(r, w.COL_DESC, QTableWidgetItem(
        'depicts=Q1\ncreated_during=QE'))
    if w.COL_TITLE < w.table.columnCount():
        w.table.setItem(r, w.COL_TITLE, QTableWidgetItem(''))
    w.table.selectRow(r)

    # Stub the network and the dialog.
    def fake_fetch(parent, label, fn_, *a, **k):
        return (ENT, None, False)

    class FakeDlg:
        def __init__(self, *a, **k):
            pass

        def exec(self):
            return QDialog.Accepted

        def languages(self):
            return ['en', 'de']

        def result_table(self):
            t = captions.FuegungTable()
            t.learn('QE', 'de', ' bei der ', 'Berlinale')
            return t

        def with_links(self):
            return True

    orig_fetch = mw_files.fetch_in_background
    orig_dlg = mw_files.GenerateCaptionsDialog
    mw_files.fetch_in_background = fake_fetch
    mw_files.GenerateCaptionsDialog = FakeDlg
    try:
        w._generate_captions()
    finally:
        mw_files.fetch_in_background = orig_fetch
        mw_files.GenerateCaptionsDialog = orig_dlg

    text = w.table.item(r, w.COL_DESC).text()
    fields, _c = decompose_fields(text)
    eq('the German caption is the learned sentence',
       fields.get('caption_de'), 'Anna Müller bei der Berlinale')
    eq('the English caption is the caseless fallback',
       fields.get('caption_en'), 'Anna Müller, Berlinale')
    check('a linked German description was written',
          '[[:de:Internationale Filmfestspiele Berlin|Berlinale]]'
          in (fields.get('info:de') or ''), fields.get('info:de'))
    check('the caption itself carries no link markup',
          '[[' not in (fields.get('caption_de') or ''))
    # The conjunction was remembered for next time.
    saved = captions.FuegungTable.from_json(
        QSettings(APP_NAME, 'Captions').value('fuegungen', '', type=str))
    eq('the conjunction is persisted', saved.tail('QE', 'de'),
       ' bei der Berlinale')

    # No depicts/event -> a clear message, nothing written (checked by not
    # raising and leaving a blank row alone).
    r2 = w.table.rowCount()
    w.table.insertRow(r2)
    w.table.setItem(r2, w.COL_FILENAME, QTableWidgetItem('empty.jpg'))
    w.table.setItem(r2, w.COL_DESC, QTableWidgetItem(''))
    w.table.clearSelection()
    w.table.selectRow(r2)
    from cammello import widgets as _wm
    calls = []
    orig_info = _wm.QMessageBox.information if hasattr(_wm, 'QMessageBox') \
        else None
    # Patch QMessageBox.information in mw_files to avoid a modal.
    orig_mb = mw_files.QMessageBox.information
    mw_files.QMessageBox.information = staticmethod(
        lambda *a, **k: calls.append(a))
    try:
        w._generate_captions()
    finally:
        mw_files.QMessageBox.information = staticmethod(orig_mb)
    check('a row with no depicts/event is reported, not written',
          len(calls) == 1 and w.table.item(r2, w.COL_DESC).text() == '')

print(f'\n{PASSED} Pruefungen bestanden, {len(FAILED)} gescheitert')
for f in FAILED:
    print('  -', f)
sys.exit(1 if FAILED else 0)
