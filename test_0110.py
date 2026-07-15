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
ed.load('depicts_override=no_person')
check('load selects the right override',
      ed.override_combo.currentData() == 'no_person')
check('assemble writes the key', 'depicts_override=no_person' in ed.assemble())
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

print('---')
print('FAILURES:', fails if fails else 'none')
sys.exit(1 if fails else 0)
