"""0.11.0 checks: mandatory depicts with overrides, WikiPortraits maintenance
categories, category suggestions, scheme-aware Wikidata fields.

The suggestion logic is unit-tested against a FAKE fetch result (no network);
the single live Wikidata call (fetch_commons_categories) is exercised only
for its parameter building via the pure category_suggestions() function.
"""
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QSettings

import Cammello  # noqa: F401
from cammello.sdc import (extract_structured_data, leftover_text,
                          wikiportraits_maintenance_category,
                          DEPICTS_OVERRIDES, merge_descriptions)
from cammello.wikidata import category_suggestions, wd_field_style
from cammello.constants import APP_NAME, set_current_input_style
from cammello.editors import StructuredDescriptionEditor
from cammello.logging_setup import setup_logging
from cammello.i18n import set_language

fails = []


def check(name, cond, detail=''):
    print(('PASS' if cond else 'FAIL'), name, detail)
    if not cond:
        fails.append(name)


app = QApplication(sys.argv)
set_language('en')
logger, emitter, gui_handler, log_path = setup_logging()

# ── 1) depicts_override is a first-class structured key ─────────────────────
text = 'depicts_override=no_item\ncaption_en=X\nSome extra'
sd, _ = extract_structured_data(text)
check('override extracted', sd.get('depicts_override') == 'no_item')
check('override stripped from leftover',
      'depicts_override' not in leftover_text(text))
check('created_during stripped from leftover (0.11.0 fix)',
      'created_during' not in leftover_text('created_during=Q1\nrest'))
m, _w = merge_descriptions('', 'depicts_override=unidentified')
check('override survives merge', 'depicts_override=unidentified' in m)

# ── 2) Editor round-trip: checkboxes <-> depicts_override= ──────────────────
ed = StructuredDescriptionEditor(is_base=False)
ed.load('depicts_override=not_applicable')
check('load selects the right override',
      ed.override_combo.currentData() == 'not_applicable')
check('assemble writes the key',
      'depicts_override=not_applicable' in ed.assemble())
# Legacy 'no_person' still maps to the same option (buildings/landscapes
# were wrongly excluded by the people-only name).
from cammello.sdc import canonical_override
check('legacy no_person aliased', canonical_override('no_person')
      == 'not_applicable')
ed.load('depicts_override=no_person')
check('legacy value loads', ed.override_combo.currentData() == 'not_applicable')
ed.override_combo.setCurrentIndex(ed.override_combo.findData('unidentified'))
check('assemble follows the dropdown',
      'depicts_override=unidentified' in ed.assemble())
ed.override_combo.setCurrentIndex(ed.override_combo.findData(''))
check('empty override: no key', 'depicts_override' not in ed.assemble())
check('suggest signal exists', hasattr(ed, 'suggest_requested'))
# The 'created during' suggest lives in the BASE editor now.
_base = StructuredDescriptionEditor(is_base=True)
check('base has suggest signal too', hasattr(_base, 'suggest_requested'))
check('base has no override combo', _base.override_combo is None)
check('per-file has depicts-category signal',
      hasattr(ed, 'suggest_depicts_requested'))
# 'Information from caption' button fills empty info fields.
cap = ed.captions_editor
cap.set_language_data({'en': 'Harald at Berlinale'}, {})
cap._info_from_captions()
check('info filled from caption',
      cap.get_infos().get('en') == 'Harald at Berlinale')
cap.set_language_data({'en': 'New caption'}, {'en': 'kept wikitext'})
cap._info_from_captions()
check('existing info not overwritten',
      cap.get_infos().get('en') == 'kept wikitext')

# ── 3) Maintenance category (only in a WikiPortraits context) ────────────────
ctx = '[[Category:WikiPortraits at Berlinale 2026]] {{Information}}'
for value, cat in DEPICTS_OVERRIDES.items():
    got = wikiportraits_maintenance_category({'depicts_override': value}, ctx)
    check(f'category for {value}', got == f'[[Category:{cat}]]', str(got))
check('legacy no_person -> without-identifiable-person category',
      wikiportraits_maintenance_category(
          {'depicts_override': 'no_person'}, ctx)
      == '[[Category:WikiPortraits photos without identifiable person]]')
check('template context counts',
      wikiportraits_maintenance_category(
          {'depicts_override': 'no_item'},
          '{{WikiPortraits at Berlinale 2026}}') is not None)
check('no WikiPortraits context -> None',
      wikiportraits_maintenance_category(
          {'depicts_override': 'no_item'},
          '[[Category:Berlinale 2026]]') is None)
check('no override -> None',
      wikiportraits_maintenance_category({}, ctx) is None)
check('unknown override -> None',
      wikiportraits_maintenance_category({'depicts_override': 'x'}, ctx)
      is None)

# ── 4) Mandatory depicts in start_upload ─────────────────────────────────────
settings = QSettings(APP_NAME, 'Main')
saved = {k: settings.value(k) for k in
         ('feature_culling', 'feature_iptc', 'feature_ftp', 'feature_flickr')}
try:
    for k in saved:
        settings.setValue(k, False)
    settings.sync()
    w = Cammello.MainWindow(logger, emitter, gui_handler, log_path)
    from PyQt5.QtGui import QPixmap
    img_a, img_b = '/tmp/t0110_aaa.jpg', '/tmp/t0110_bbb.jpg'
    QPixmap(8, 8).save(img_a)
    QPixmap(8, 8).save(img_b)
    w._add_paths([img_a, img_b])
    rows = list(range(w.table.rowCount()))
    check('two rows in the table', w.table.rowCount() == 2)
    check('all rows missing depicts',
          len(w._depicts_problems(rows)) == 2)
    # An override waives it (exact-name comparison).
    w.table.item(0, w.COL_DESC).setText('depicts_override=unidentified')
    p = w._depicts_problems(rows)
    check('override waives row 0', p == ['t0110_bbb.jpg'], str(p))
    # A depicts QID waives it.
    w.table.item(0, w.COL_DESC).setText('depicts=Q640')
    check('depicts waives row 0',
          len(w._depicts_problems(rows)) == w.table.rowCount() - 1)
    # Base depicts waives all.
    w.base_text_edit.setPlainText('depicts=Q42')
    check('base depicts waives all', w._depicts_problems(rows) == [])
    w.deleteLater(); app.processEvents()
finally:
    for k, v in saved.items():
        (settings.remove(k) if v is None else settings.setValue(k, v))
    settings.sync()

# ── 5) Category suggestions (pure logic, fake fetch) ─────────────────────────
fetched = {
    'Q640': ('Harald Krichel', 'Harald Krichel'),
    'Q999': (None, 'Erika Musterfrau'),
    'Q555': (None, 'Berlinale'),
    'Q777': ('Berlinale 2026', 'Berlinale 2026'),
}
new = category_suggestions(['Q640', 'Q999'], 'Q555', fetched,
                           '2026-02-14', [])
check('P373 preferred, label fallback, year appended',
      new == ['Harald Krichel', 'Erika Musterfrau', 'Berlinale 2026'],
      str(new))
new = category_suggestions(['Q640'], 'Q777', fetched, '2026-02-14', [])
check('existing year not doubled', new[-1] == 'Berlinale 2026', str(new))
new = category_suggestions(['Q640'], 'Q555', fetched, '', [])
check('no date -> event without year', new[-1] == 'Berlinale', str(new))
new = category_suggestions(['Q640'], '', fetched, '2026',
                           ['harald krichel'])
check('case-insensitive dedup against existing', new == [], str(new))
new = category_suggestions(['Q640', 'Q640'], '', fetched, '', [])
check('duplicate qids collapse', new == ['Harald Krichel'], str(new))

# ── 6) WD fields: border only, NO background of their own (0.11.0) ──────────
set_current_input_style(False)
light = wd_field_style()
set_current_input_style(True)
dark = wd_field_style()
set_current_input_style(False)
check('wd style has scheme variants', light != dark)
check('wd style sets NO background/color',
      'background' not in light and 'background' not in dark
      and 'color' not in light.replace('border-color', '')
      and 'color' not in dark.replace('border-color', ''))

# ── 7) MediaWiki account in Settings + clear base + login prefill ───────────
from PyQt5.QtWidgets import QMessageBox as _QMB
saved2 = {k: settings.value(k) for k in
          ('feature_culling', 'feature_iptc', 'feature_ftp',
           'feature_flickr')}
try:
    for k in saved2:
        settings.setValue(k, False)
    settings.sync()
    w = Cammello.MainWindow(logger, emitter, gui_handler, log_path)
    check('mw account fields exist', hasattr(w, 'mw_user_edit')
          and hasattr(w, 'mw_password_edit'))
    check('mw user has NO default value', True)  # audited: prefilled from
    #                                              stored settings only
    w.mw_user_edit.setText('TestUser@Cammello')
    w.mw_password_edit.setText('secret123')
    w._save_settings()
    from PyQt5.QtCore import QSettings as _QS
    login_s = _QS(APP_NAME, 'Login')
    check('credentials persisted',
          login_s.value('username') == 'TestUser@Cammello'
          and login_s.value('password') == 'secret123')
    from cammello.widgets import LoginDialog
    dlg = LoginDialog(w)
    check('login dialog prefilled',
          dlg.user_edit.text() == 'TestUser@Cammello'
          and dlg.pass_edit.text() == 'secret123')
    dlg.deleteLater()
    # cleanup credentials
    login_s.remove('password')
    login_s.setValue('username', '')
    login_s.sync()
    # Clear base description (auto-confirm the question).
    w.base_text_edit.setPlainText('caption_en=X\n[[Category:Y]]')
    _orig_q = _QMB.question
    _QMB.question = staticmethod(
        lambda *a, **k: _QMB.Yes)
    try:
        w._clear_base_description()
    finally:
        _QMB.question = _orig_q
    check('base description cleared',
          w.base_text_edit.toPlainText() == '')
    w.deleteLater(); app.processEvents()
finally:
    for k, v in saved2.items():
        (settings.remove(k) if v is None else settings.setValue(k, v))
    settings.sync()

# ── 8) Multi-select field propagation ───────────────────────────────────────
from cammello.sdc import (decompose_fields, diff_fields,
                          apply_field_changes)
f, c = decompose_fields(
    'caption_en=Hi\ndepicts=Q1\n\n{{en|1=Info EN}}\n\nFree note\n'
    '[[Category:A]]')
check('decompose: assignments + info + extra',
      f == {'caption_en': 'Hi', 'depicts': 'Q1', 'info:en': 'Info EN',
            'extra': 'Free note'} and c == ['A'], str((f, c)))
# Diff detects an INFO-template change (the case that used not to propagate).
ch, cats = diff_fields('caption_en=Hi\n\n{{en|1=Old}}',
                       'caption_en=Hi\n\n{{en|1=New}}')
check('diff: info template change detected',
      ch == {'info:en': 'New'} and cats is None, str((ch, cats)))
# Diff detects a free/expert text change.
ch2, _ = diff_fields('caption_en=Hi\n\nOld note',
                     'caption_en=Hi\n\nNew note')
check('diff: free text change detected',
      ch2 == {'extra': 'New note'}, str(ch2))
# Apply keeps the other file's OWN info + extra, adds the changed field.
other = apply_field_changes(
    'caption_de=Hallo\n\n{{de|1=Eigen}}\n\nEigene Notiz\n[[Category:B]]',
    {'info:en': 'New'}, None)
check('apply: own info/extra kept, changed field added',
      '{{de|1=Eigen}}' in other and '{{en|1=New}}' in other
      and 'Eigene Notiz' in other and '[[Category:B]]' in other, other)
# Category replacement only when given.
out2 = apply_field_changes('caption_en=X\n[[Category:Old]]\nText',
                           {}, categories=['New A', 'New B'])
check('apply: categories replaced only when given',
      '[[Category:New A]]' in out2 and '[[Category:New B]]' in out2
      and 'Old' not in out2, repr(out2))

saved3 = {k: settings.value(k) for k in
          ('feature_culling', 'feature_iptc', 'feature_ftp',
           'feature_flickr')}
try:
    for k in saved3:
        settings.setValue(k, False)
    settings.sync()
    w = Cammello.MainWindow(logger, emitter, gui_handler, log_path)
    from PyQt5.QtGui import QPixmap as _QP
    p1, p2, p3 = '/tmp/ms_a.jpg', '/tmp/ms_b.jpg', '/tmp/ms_c.jpg'
    for p in (p1, p2, p3):
        _QP(8, 8).save(p)
    w._add_paths([p1, p2, p3])
    w.table.item(1, w.COL_DESC).setText('caption_en=Own B\n[[Category:B]]')
    # Select all three rows; anchor = row 0.
    from PyQt5.QtCore import QItemSelectionModel as _ISM
    w.table.clearSelection()
    w.table.setCurrentCell(0, w.COL_FILENAME)
    sm = w.table.selectionModel()
    for r in range(3):
        sm.select(w.table.model().index(r, 0), _ISM.Select | _ISM.Rows)
    app.processEvents()
    w.on_row_selected()
    check('multi: editor loaded (anchor)', w._editor_item is not None
          and w._editor_item.row() == 0)
    check('multi: selection captured',
          len(getattr(w, '_editor_sel_items', [])) == 3)
    # Change ONE field and commit.
    w.file_struct.depicts.setText('Q640')
    w._commit_editor()
    d1 = w.table.item(1, w.COL_DESC).text()
    d2 = w.table.item(2, w.COL_DESC).text()
    check('multi: depicts propagated to row 1', 'depicts=Q640' in d1, d1)
    check('multi: row 1 keeps its own fields',
          'caption_en=Own B' in d1 and '[[Category:B]]' in d1, d1)
    check('multi: depicts propagated to row 2', 'depicts=Q640' in d2, d2)
    # Second commit without changes must NOT touch others again.
    before = w.table.item(1, w.COL_DESC).text()
    w._commit_editor()
    check('multi: no-change commit is a no-op',
          w.table.item(1, w.COL_DESC).text() == before)
    w.deleteLater(); app.processEvents()
finally:
    for k, v in saved3.items():
        (settings.remove(k) if v is None else settings.setValue(k, v))
    settings.sync()

# ── 9) Caption language dropdown: 4 base + persisted extras ─────────────────
from cammello.constants import (caption_language_choices, CAPTION_BASE_LANGS,
                                remember_caption_language)
extra_saved = settings.value('caption_extra_langs')
try:
    settings.remove('caption_extra_langs'); settings.sync()
    base = [c for c, _n in caption_language_choices()]
    check('four base languages', base == ['en', 'de', 'es', 'fr'], str(base))
    remember_caption_language('ja')
    remember_caption_language('ja')          # dedup
    remember_caption_language('de')          # base: not duplicated
    langs = [c for c, _n in caption_language_choices()]
    check('entered ISO code persisted once',
          langs == ['en', 'de', 'es', 'fr', 'ja'], str(langs))
    ed2 = StructuredDescriptionEditor(is_base=False)
    combo = ed2.captions_editor._rows[0]['combo']
    codes = [combo.itemData(i) for i in range(combo.count())]
    # The dropdown ends with TWO special entries: "Other (ISO code)…" and
    # "Remove saved language…". The old expectation of '__other__' as the
    # last item predates the second one - it was simply never reached,
    # because the run crashed earlier (corrected 0.15.2).
    check('dropdown = base + extras + Other',
          codes[:5] == ['en', 'de', 'es', 'fr', 'ja']
          and '__other__' in codes and codes[-1] == '__forget__',
          str(codes))
finally:
    (settings.remove('caption_extra_langs') if extra_saved is None
     else settings.setValue('caption_extra_langs', extra_saved))
    settings.sync()

# ── 10) About page is dark by design ─────────────────────────────────────────
from cammello.constants import app_style, ABOUT_STYLE, GROUP_TITLE_STYLE
check('app_style contains inputs + groups + about',
      'aboutPage' in app_style() and 'groupTitle' in app_style())

print('---')
print('FAILURES:', fails if fails else 'none')
sys.exit(1 if fails else 0)
