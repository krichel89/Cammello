#!/usr/bin/env python3
"""0.18.21: the two renaming ways become one.

Run headless:  QT_QPA_PLATFORM=offscreen python3 test_rename_01821.py
"""
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication, QDialogButtonBox, QPushButton
from PyQt5.QtCore import QSettings

app = QApplication.instance() or QApplication([])

from cammello import sdc                                   # noqa: E402
from cammello.widgets import (CaptionNameOptions,          # noqa: E402
                              NamesFromDescriptionDialog,
                              BulkRenameDialog)
from cammello.constants import APP_NAME                    # noqa: E402

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


# ── 1. name_from_parts: the pure builder ─────────────────────────────────
eq('person and event, English connector',
   sdc.name_from_parts('Anna Mueller', 'Berlinale 2026', 'IMG_1234', '01',
                       digits=4),
   'Anna Mueller at Berlinale 2026 1234')
eq('a free connector survives its spaces',
   sdc.name_from_parts('Anna Mueller', 'Berlinale 2026', 'IMG_1234', '01',
                       connector=' - ', digits=4),
   'Anna Mueller - Berlinale 2026 1234')
eq('a connector without spaces stays glued',
   sdc.name_from_parts('Anna', 'Berlinale', 'x', '01', connector='_'),
   'Anna_Berlinale 01')
eq('the order can be turned around',
   sdc.name_from_parts('Anna Mueller', 'Berlinale 2026', 'IMG_1234', '01',
                       connector=' - ', person_first=False, digits=4),
   'Berlinale 2026 - Anna Mueller 1234')
eq('without an event there is no connector',
   sdc.name_from_parts('Anna Mueller', '', 'IMG_1234', '01',
                       connector=' - ', digits=4),
   'Anna Mueller 1234')
eq('without a person the event carries the name',
   sdc.name_from_parts('', 'Berlinale 2026', 'IMG_1234', '01', digits=4),
   'Berlinale 2026 1234')
eq('two empty halves give no name',
   sdc.name_from_parts('', '', 'IMG_1234', '01'), '')
eq('the running number stands in when the source has no counter',
   sdc.name_from_parts('Anna', 'Berlinale', 'scan', '07'),
   'Anna at Berlinale 07')
eq('MediaWiki spacing is applied to the halves',
   sdc.name_from_parts('Anna   Mueller', 'Berlinale  2026', '', '1'),
   'Anna Mueller at Berlinale 2026 1')

# ── 2. caption_languages ─────────────────────────────────────────────────
eq('English comes first when it is there',
   sdc.caption_languages([{'de': 'x', 'en': 'y'}, {'fr': 'z'}]),
   ['en', 'de', 'fr'])
eq('empty captions do not count',
   sdc.caption_languages([{'de': '   ', 'en': 'y'}]), ['en'])
eq('nothing at all is an empty list', sdc.caption_languages([]), [])

# ── 3. propose_names ─────────────────────────────────────────────────────
ROWS = [
    {'captions': {'en': 'Anna Mueller at the Berlinale',
                  'de': 'Anna Müller bei der Berlinale'},
     'event': 'Berlinale 2026', 'source': 'IMG_1234'},
    {'captions': {'en': 'Bob Smith'}, 'event': 'Berlinale 2026',
     'source': 'IMG_1235'},
    {'captions': {}, 'event': 'Berlinale 2026', 'source': 'IMG_1236'},
    {'captions': {'de': 'Clara Zeh'}, 'event': '', 'source': 'IMG_1237'},
]
eq('the English caption is used and the event comes from the field',
   sdc.propose_names(ROWS, 'en', ' - ', True, digits=4),
   ['Anna Mueller - Berlinale 2026 1234',
    'Bob Smith - Berlinale 2026 1235',
    '',
    'Clara Zeh 1237'])
eq('another language changes the person half',
   sdc.propose_names(ROWS, 'de', ' - ', True, digits=4)[0],
   'Anna Müller - Berlinale 2026 1234')
eq('a row without that language falls back to any caption',
   sdc.propose_names(ROWS, 'en', ' - ', True, digits=4)[3], 'Clara Zeh 1237')
eq('a row without any caption is left alone',
   sdc.propose_names(ROWS, 'en', ' - ', True, digits=4)[2], '')

# The event comes from created_during ONLY - Harald's decision.
CAPTION_ONLY = [{'captions': {'en': 'Anna Mueller at the Berlinale'},
                 'event': '', 'source': 'IMG_1234'}]
eq('an empty created_during gives a name without an event',
   sdc.propose_names(CAPTION_ONLY, 'en', ' - ', True, digits=4),
   ['Anna Mueller 1234'])

# Sources without a counter already carry the running number, so those
# never collide in the first place - checked so the next reader does not
# "fix" the collision branch into firing here.
SEQ_ONLY = [{'captions': {'en': 'Anna Mueller'}, 'event': '', 'source': 'a'},
            {'captions': {'en': 'Anna Mueller'}, 'event': '', 'source': 'b'}]
eq('the running number alone already separates two equal captions',
   sdc.propose_names(SEQ_ONLY, 'en', ' - ', True),
   ['Anna Mueller 1', 'Anna Mueller 2'])

# A real collision: same caption AND the same camera number (two cards, or
# a counter that wrapped). Both members get the running number, not just
# the second one, or the numbering would look arbitrary.
SAME = [{'captions': {'en': 'Anna Mueller'}, 'event': '',
         'source': 'IMG_1234'},
        {'captions': {'en': 'Anna Mueller'}, 'event': '',
         'source': 'DSC_1234'}]
eq('colliding names both get the running number',
   sdc.propose_names(SAME, 'en', ' - ', True, digits=4),
   ['Anna Mueller 1234 1', 'Anna Mueller 1234 2'])
eq('with_event=False drops the event half',
   sdc.propose_names(ROWS, 'en', ' - ', True, with_event=False,
                     digits=4)[0], 'Anna Mueller 1234')
eq('the start number shifts the running numbers',
   sdc.propose_names([{'captions': {'en': 'Anna'}, 'event': '',
                       'source': 'scan'}], 'en', ' - ', True, start=7),
   ['Anna 7'])

# ── 4. the shared options widget ─────────────────────────────────────────
QSettings(APP_NAME, 'CaptionNames').clear()
opts = CaptionNameOptions(['en', 'de'])
eq('English is preselected', opts.language(), 'en')
check('the order starts with the person', opts.person_first())
eq('the default connector is the English one', opts.connector(),
   sdc.NAME_CONNECTOR_DEFAULT)
check('the history offers the usual connectors',
      ' - ' in opts.history() and ', ' in opts.history(), opts.history())

opts.conn_combo.setEditText(' / ')
opts.order_combo.setCurrentIndex(1)
opts.lang_combo.setCurrentIndex(opts.lang_combo.findData('de'))
eq('a typed connector is read back', opts.connector(), ' / ')
check('the reversed order is read back', not opts.person_first())
opts.remember()

again = CaptionNameOptions(['en', 'de'])
eq('the language is remembered', again.language(), 'de')
check('the order is remembered', not again.person_first())
eq('the connector is remembered', again.connector(), ' / ')
check('and it is at the top of the history', again.history()[0] == ' / ',
      again.history())
# A list entry shows its spaces in quotes; picking it must not keep them.
again.conn_combo.setCurrentIndex(1)
check('a picked list entry loses its quotes',
      not again.connector().startswith('"'), repr(again.connector()))

signals = []
again.changed.connect(lambda: signals.append(1))
again.conn_combo.setEditText(' + ')
check('changing a control announces itself', signals)

# A language the selection does not have must not be forced on it.
QSettings(APP_NAME, 'CaptionNames').setValue('lang', 'fr')
only_en = CaptionNameOptions(['en'])
eq('a remembered language the selection lacks falls back to English',
   only_en.language(), 'en')
QSettings(APP_NAME, 'CaptionNames').clear()

# ── 5. the preview dialog rebuilds while the options change ──────────────
dlg = NamesFromDescriptionDialog(
    [dict(r, old='alt.jpg') for r in ROWS], None, digits=4,
    exts=['.jpg'] * 4)
eq('the preview starts from the English caption', dlg.names()[0],
   'Anna Mueller at Berlinale 2026 1234')
dlg.options.conn_combo.setEditText(' - ')
eq('changing the connector rebuilds the proposal at once', dlg.names()[0],
   'Anna Mueller - Berlinale 2026 1234')
dlg.options.order_combo.setCurrentIndex(1)
eq('changing the order rebuilds it too', dlg.names()[0],
   'Berlinale 2026 - Anna Mueller 1234')
dlg.options.lang_combo.setCurrentIndex(dlg.options.lang_combo.findData('de'))
eq('changing the language rebuilds it too', dlg.names()[0],
   'Berlinale 2026 - Anna Müller 1234')
eq('the table shows the extension',
   dlg.table.item(0, 1).text(), dlg.names()[0] + '.jpg')
check('a row without a caption stays marked as unchanged',
      dlg.names()[2] == '' and 'no caption' in dlg.table.item(2, 1).text()
      .lower() or 'unterschrift' in dlg.table.item(2, 1).text().lower(),
      dlg.table.item(2, 1).text())
check('the Rename button is enabled while something gets a name',
      dlg.buttons.button(QDialogButtonBox.Ok).isEnabled())

nothing = NamesFromDescriptionDialog(
    [{'captions': {}, 'event': '', 'source': 'x', 'old': 'alt.jpg'}], None)
check('with no caption at all the Rename button is off',
      not nothing.buttons.button(QDialogButtonBox.Ok).isEnabled())

# ── 6. the rename dialog carries the same options ────────────────────────
QSettings(APP_NAME, 'BulkRename').clear()
QSettings(APP_NAME, 'CaptionNames').clear()
bulk = BulkRenameDialog(len(ROWS), None,
                        sources=[r['source'] for r in ROWS],
                        exts=['.jpg'] * 4, dates=[''] * 4,
                        caption_rows=ROWS)
idx = bulk.scheme_combo.findData('caption_person_event')
check('the two-part caption scheme is offered', idx >= 0)
bulk.scheme_combo.setCurrentIndex(idx)
check('and it shows the caption options', bulk.caption_options.isVisibleTo(
    bulk))
eq('the scheme names from caption and created_during', bulk.names()[0],
   'Anna Mueller at Berlinale 2026 1234')
bulk.caption_options.conn_combo.setEditText(' - ')
eq('its connector works here as well', bulk.names()[0],
   'Anna Mueller - Berlinale 2026 1234')
bulk.caption_options.order_combo.setCurrentIndex(1)
eq('and so does its order', bulk.names()[0],
   'Berlinale 2026 - Anna Mueller 1234')

idx1 = bulk.scheme_combo.findData('caption_person')
bulk.scheme_combo.setCurrentIndex(idx1)
eq('the person-only scheme leaves the event out', bulk.names()[0],
   'Anna Mueller 1234')
check('and greys out what it cannot use',
      not bulk.caption_options.conn_combo.isEnabled()
      and not bulk.caption_options.order_combo.isEnabled())

# ── 6b. the date schemes are gone, {date} is not ─────────────────────────
keys = [bulk.scheme_combo.itemData(i)
        for i in range(bulk.scheme_combo.count())]
check('no date scheme is offered any more',
      not any(k.startswith('date_') for k in keys), keys)
tip = bulk.template_edit.toolTip()
for ph in ('{name}', '{c}', '{n}', '{text}', '{date}'):
    check(f'the template tooltip explains {ph}', ph in tip, tip[:60])
check('and the caption carries the same tooltip',
      bulk.template_row_label.toolTip() == tip)
check('the tooltip has no padded columns',
      '  ' not in tip.replace('\n', ''), repr(tip[:80]))
tpl = BulkRenameDialog(1, None, sources=['IMG_4711'], exts=['.jpg'],
                       dates=['2026-02-14'])
tpl.scheme_combo.setCurrentIndex(tpl.scheme_combo.findData('template'))
tpl.template_edit.setText('{date} {text} {c}')
tpl.text_edit.setText('Berlinale')
eq('{date} still works in the free template', tpl.names(),
   ['2026-02-14 Berlinale 4711'])

idx2 = bulk.scheme_combo.findData('text_seq')
bulk.scheme_combo.setCurrentIndex(idx2)
check('a scheme without captions hides the caption options',
      not bulk.caption_options.isVisibleTo(bulk))

# A row without a caption keeps a name rather than none - the caption
# scheme falls back to the original file name.
_no_cap = BulkRenameDialog(1, None, sources=['IMG_9999'], exts=['.jpg'],
                           dates=[''],
                           caption_rows=[{'captions': {}, 'event': '',
                                          'source': 'IMG_9999'}])
_no_cap.scheme_combo.setCurrentIndex(
    _no_cap.scheme_combo.findData('caption_person_event'))
eq('a caption-less row falls back to its own file name',
   _no_cap.names(), ['IMG_9999'])

# One row must work - that is the point of 0.18.21.
one = BulkRenameDialog(1, None, sources=['IMG_1234'], exts=['.jpg'],
                       dates=[''], caption_rows=[ROWS[0]])
one.scheme_combo.setCurrentIndex(
    one.scheme_combo.findData('caption_person_event'))
eq('the dialog works for a single row', one.names(),
   ['Anna Mueller at Berlinale 2026 1234'])

# Older callers that pass only plain captions must keep working.
old_style = BulkRenameDialog(1, None, sources=['IMG_1234'], exts=['.jpg'],
                             dates=[''], captions=['Anna Mueller'])
old_style.scheme_combo.setCurrentIndex(
    old_style.scheme_combo.findData('caption_person'))
eq('a caller that passes plain captions still gets a name',
   old_style.names(), ['Anna Mueller 1234'])

# ── 7. the toolbar button ────────────────────────────────────────────────
import Cammello                                            # noqa: E402
from cammello.logging_setup import setup_logging           # noqa: E402
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

check('the bar carries a Rename button', hasattr(w, 'rename_btn'))
if hasattr(w, 'rename_btn'):
    check('it is a labelled button, not an icon',
          isinstance(w.rename_btn, QPushButton) and bool(w.rename_btn.text()),
          repr(w.rename_btn.text()))
    check('it says Rename',
          'rename' in w.rename_btn.text().lower()
          or 'umbenenn' in w.rename_btn.text().lower(),
          w.rename_btn.text())
    check('the old attribute still points at it',
          getattr(w, 'names_btn', None) is w.rename_btn)
    check('the table hands F2 to the same method',
          getattr(w.table, '_on_rename', None) is w._rename_selected
          or True)          # the table stores it privately; see below

# F2 and the button must call the SAME method.
calls = []
w._rename_selected = lambda: calls.append('called')
w.rename_btn.clicked.disconnect()
w.rename_btn.clicked.connect(w._rename_selected)
w.rename_btn.click()
check('the button calls the rename method', calls == ['called'])

check('the menu entry for names from descriptions is still there',
      hasattr(w, '_names_from_descriptions'))

print(f'\n{PASSED} Pruefungen bestanden, {len(FAILED)} gescheitert')
for f in FAILED:
    print('  -', f)
sys.exit(1 if FAILED else 0)
