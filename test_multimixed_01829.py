#!/usr/bin/env python3
"""0.18.29: several files selected -> the structured editor shows ONE merged
view, "<mixed>" where the files differ; typing over it sets all files; an
untouched "<mixed>" never changes anything. Plus "Clear description" and the
removed "Information from caption" button.

Run headless:  QT_QPA_PLATFORM=offscreen python3 test_multimixed_01829.py
"""
import os
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
_HOME = tempfile.mkdtemp()
os.environ['HOME'] = _HOME
os.environ['USERPROFILE'] = _HOME
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication, QMessageBox, QPushButton, QTableWidgetItem
from PyQt5.QtCore import Qt

import Cammello
from cammello import editors, sdc
from cammello.sdc import MIXED, merged_view, has_mixed, decompose_fields, diff_fields
from cammello.logging_setup import setup_logging

app = QApplication.instance() or QApplication([])
logger, emitter, gui_handler, log_path = setup_logging()
fails = []
PASSED = 0


def check(name, cond, detail=''):
    global PASSED
    if cond:
        PASSED += 1
    else:
        fails.append(name)
        print('FAIL', name, detail)


def eq(name, got, want):
    check(name, got == want, f'{got!r} statt {want!r}')


# ── 1. the merged view ──────────────────────────────────────────────────────
A = ('caption_en=Anna at X\ncaption_de=Anna bei X\ndepicts=Q1\n'
     'depicts_override=unidentified\n\n{{en|1=Same info}}\n{{de|1=Eins}}\n'
     '[[Category:Common]]\n[[Category:OnlyA]]')
B = ('caption_en=Bob at X\ncaption_de=Anna bei X\ndepicts=Q2\n\n'
     '{{en|1=Same info}}\nFree text\n[[Category:Common]]')
v = merged_view([A, B])
f, c = decompose_fields(v)
eq('a field both share keeps its value', f['caption_de'], 'Anna bei X')
eq('a field they differ in is mixed', f['caption_en'], MIXED)
eq('depicts differs -> mixed', f['depicts'], MIXED)
eq('a field only one has is mixed', f['depicts_override'], MIXED)
eq('shared info stays', f['info:en'], 'Same info')
eq('info only one has is mixed', f['info:de'], MIXED)
eq('free text only one has is mixed', f['extra'], MIXED)
eq('differing categories are ONE mixed link', [x.strip() for x in c], [MIXED])
check('has_mixed sees it', has_mixed(v))
same = merged_view([A, A])
eq('identical files: the view is the file', decompose_fields(same),
   decompose_fields(A))
check('and has no mixed', not has_mixed(same))
eq('one file: unchanged', decompose_fields(merged_view([A])),
   decompose_fields(A))
eq('no files: empty', merged_view([]), '')

# ── 2. the editor does not turn the marker into a change ─────────────────────
for label, texts in (('mixed everything', [A, B]),
                     ('mixed override only', [A, A.replace('unidentified', '')]),
                     ('mixed categories only', [A, A + '\n[[Category:More]]'])):
    view = merged_view(texts)
    ed = editors.StructuredDescriptionEditor(is_base=False)
    ed.load(view)
    changes, cats = diff_fields(view, ed.assemble())
    eq(f'untouched editor, no change ({label})', (changes, cats), ({}, None))
ed = editors.StructuredDescriptionEditor(is_base=False)
ed.load(merged_view([A, B]))
check('override combo shows <mixed>',
      ed.override_combo.currentData() == MIXED
      and ed.override_combo.currentText() == MIXED)
ed.load(A)
check('and the entry is gone again for one file',
      ed.override_combo.findData(MIXED) < 0)
check('the Information-from-caption button is gone',
      'Information from caption' not in
      [b.text() for b in ed.findChildren(QPushButton)])

# ── 3. in the window ────────────────────────────────────────────────────────
QMessageBox.information = staticmethod(lambda *a, **k: None)
QMessageBox.warning = staticmethod(lambda *a, **k: None)
ANSWER = [QMessageBox.Yes]
QMessageBox.question = staticmethod(lambda *a, **k: ANSWER[0])
w = Cammello.MainWindow(logger, emitter, gui_handler, log_path)


def add_row(name, desc):
    r = w.table.rowCount()
    w.table.insertRow(r)
    fn = QTableWidgetItem(name)
    fn.setData(Qt.UserRole, '/tmp/' + name)
    w.table.setItem(r, w.COL_FILENAME, fn)
    w.table.setItem(r, w.COL_DESC, QTableWidgetItem(desc))
    if w.COL_TITLE < w.table.columnCount():
        w.table.setItem(r, w.COL_TITLE, QTableWidgetItem(''))
    return r


def select(*rows):
    w.table.clearSelection()
    sm = w.table.selectionModel()
    for r in rows:
        sm.select(w.table.model().index(r, 0),
                  sm.Select | sm.Rows)
    sm.setCurrentIndex(w.table.model().index(rows[0], 0), sm.NoUpdate)
    w.on_row_selected()


def text_of(r):
    return w.table.item(r, w.COL_DESC).text()


def fields_of(r):
    return decompose_fields(text_of(r))


r1 = add_row('a.jpg', A)
r2 = add_row('b.jpg', B)
before = (text_of(r1), text_of(r2))
select(r1, r2)
fs = w.file_struct
eq('depicts shows <mixed>', fs.depicts.text(), MIXED)
eq('a shared caption shows its value',
   fs.captions_editor.get_captions().get('de'), 'Anna bei X')
eq('a differing caption shows <mixed>',
   fs.captions_editor.get_captions().get('en'), MIXED)
w._commit_editor()
eq('merely looking changes no file', (text_of(r1), text_of(r2)), before)
select(r2)
select(r1, r2)
# (a single-file commit re-serializes layout - blank lines - as it always
# did; the FIELDS must be identical)
eq('selecting around changes no field',
   (decompose_fields(text_of(r1)), decompose_fields(text_of(r2))),
   (decompose_fields(before[0]), decompose_fields(before[1])))

# overwrite one mixed field -> both files
fs.depicts.setText('Q9')
fs.changed.emit()
eq('typing over <mixed> sets depicts in file 1', fields_of(r1)[0]['depicts'],
   'Q9')
eq('... and in file 2', fields_of(r2)[0]['depicts'], 'Q9')
eq('other mixed fields stay per file (caption_en 1)',
   fields_of(r1)[0]['caption_en'], 'Anna at X')
eq('(caption_en 2)', fields_of(r2)[0]['caption_en'], 'Bob at X')
check('the marker never reaches a file',
      MIXED not in text_of(r1) and MIXED not in text_of(r2))
eq('file 2 keeps its free text', fields_of(r2)[0].get('extra'), 'Free text')

# a half-typed marker is not written
fs.depicts.setText('Q9' + MIXED)
fs.changed.emit()
check('a value containing the marker is not written',
      fields_of(r1)[0]['depicts'] == 'Q9')

# categories: keep <mixed>, add one -> added to each file's own
select(r1, r2)
eq('categories show <mixed>', fs.categories.text().strip(), MIXED)
fs.categories.setText(MIXED + '; Added')
fs.changed.emit()
c1 = [x.strip() for x in fields_of(r1)[1]]
c2 = [x.strip() for x in fields_of(r2)[1]]
check('kept <mixed> + new category: each keeps its own and gains it',
      c1 == ['Common', 'OnlyA', 'Added'] and c2 == ['Common', 'Added'],
      f'{c1} / {c2}')
check('no marker category written', MIXED not in c1 + c2)
select(r1, r2)
fs.categories.setText('Only this')
fs.changed.emit()
eq('typing over <mixed> categories replaces them everywhere',
   ([x.strip() for x in fields_of(r1)[1]],
    [x.strip() for x in fields_of(r2)[1]]), (['Only this'], ['Only this']))

# removing a caption row clears that language everywhere
select(r1, r2)
ce = fs.captions_editor
row_en = next(e for e in ce._rows if e['combo'].currentData() == 'en')
ce._remove(row_en)
check('removing a <mixed> caption row clears it in all files',
      'caption_en' not in fields_of(r1)[0]
      and 'caption_en' not in fields_of(r2)[0])
eq('the shared German caption survives', fields_of(r1)[0]['caption_de'],
   'Anna bei X')

# single selection is as before
select(r1)
check('one file: its own text, no marker', MIXED not in fs.depicts.text()
      and fs.depicts.text() == 'Q9')
fs.depicts.setText('Q7')
fs.changed.emit()
eq('one file: only that file changes', (fields_of(r1)[0]['depicts'],
                                         fields_of(r2)[0]['depicts']),
   ('Q7', 'Q9'))

# ── 4. clear description ────────────────────────────────────────────────────
btn = w.clear_file_desc_btn
check('the button exists', btn.text() == 'Clear description')
select(r1, r2)
ANSWER[0] = QMessageBox.No
btn.click()
check('"No" clears nothing', text_of(r1) != '' and text_of(r2) != '')
ANSWER[0] = QMessageBox.Yes
r3 = add_row('c.jpg', 'depicts=Q5')
select(r1, r2)
btn.click()
eq('"Yes" empties both selected files', (text_of(r1), text_of(r2)), ('', ''))
eq('an unselected file stays', text_of(r3), 'depicts=Q5')
eq('and the editor is empty', fs.depicts.text(), '')
w.table.clearSelection()
w.on_row_selected()
btn.click()
check('nothing selected: nothing happens', text_of(r3) == 'depicts=Q5')

for k in ('Clear description', 'Clear the description of {n} selected file(s)? '
          'The base description stays.',
          'Description cleared for {n} file(s).'):
    from cammello import i18n
    check(f'translated: {k[:30]}',
          set(i18n.TRANSLATIONS.get(k, {})) >= {'de', 'es', 'fr', 'it'})
w.close()

print(f'\n{PASSED} Pruefungen bestanden, {len(fails)} gescheitert')
sys.exit(1 if fails else 0)
