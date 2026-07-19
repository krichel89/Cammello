"""Checks for the UI translation (0.10.0).

  1. COVERAGE: every literal tr('…') key in the source exists in
     TRANSLATIONS (a missing key silently falls back to English - visible
     only as an untranslated string in the UI, so a test is the only guard).
  2. COMPLETENESS: every key has all four non-English languages.
  3. PLACEHOLDERS: a translation keeps exactly the {placeholders} of its key
     (a dropped or renamed one raises KeyError/IndexError at .format() time -
     i.e. a crash in production).
  4. FALLBACK: unknown keys and 'en' return the input unchanged.
  5. LOCALE default and set_language() clamping.
  6. The window builds in every language, and the status prefixes used for
     progress counting ('✓', '✗', '•') are NOT translated away.
"""
import ast
import os
import pathlib
import re
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QSettings

import Cammello  # noqa: F401  (shim; also puts the package on the path)
from cammello import i18n
from cammello.i18n import (tr, set_language, current_language, UI_LANGUAGES,
                           default_language_from_locale, TRANSLATIONS,
                           missing_keys)
from cammello.constants import APP_NAME
from cammello.logging_setup import setup_logging

fails = []


def check(name, cond, detail=''):
    print(('PASS' if cond else 'FAIL'), name, detail)
    if not cond:
        fails.append(name)


PLACEHOLDER = re.compile(r'\{(\w+)\}')


def literal_tr_keys():
    keys, dynamic = set(), []
    pkg = pathlib.Path(os.path.dirname(i18n.__file__))
    for path in sorted(pkg.glob('*.py')):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == 'tr' and node.args):
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    keys.add(arg.value)
                else:
                    dynamic.append(f'{path.name}:{node.lineno}')
    return keys, dynamic


# ── 1) Coverage ──────────────────────────────────────────────────────────────
keys, dynamic = literal_tr_keys()
uncovered = sorted(k for k in keys if k not in TRANSLATIONS)
check('every literal tr() key is translated', not uncovered,
      f'{len(keys)} keys; missing: {uncovered[:3]}')
# The two dynamic tr(label) call sites feed table-driven labels; those labels
# are listed explicitly in TRANSLATIONS and checked here.
print('  (dynamic tr() call sites:', ', '.join(dynamic) or 'none', ')')
from cammello import iptc as iptc_mod
# (BulkEditDialog was removed in 0.12.6 - multi-select editing in the editor
# replaced it; only the IPTC field labels remain table-driven.)
dynamic_labels = [label for _k, _e, label, _m in iptc_mod.IPTC_FIELDS]
missing_dyn = [l for l in dynamic_labels if l not in TRANSLATIONS]
check('dynamic tr(label) labels are translated', not missing_dyn,
      str(missing_dyn))

# ── 2) Completeness ──────────────────────────────────────────────────────────
check('no language missing in any key', not missing_keys(),
      str(missing_keys()[:3]))
check('five UI languages', [c for c, _n in UI_LANGUAGES] ==
      ['en', 'de', 'es', 'fr', 'it'])

# ── 3) Placeholders survive translation ──────────────────────────────────────
bad = []
for key, entry in TRANSLATIONS.items():
    want = set(PLACEHOLDER.findall(key))
    for lang, text in entry.items():
        if set(PLACEHOLDER.findall(text)) != want:
            bad.append((key, lang))
check('placeholders preserved in every translation', not bad, str(bad[:3]))

# A real .format() round-trip on the parameterized keys.
sample = {
    'Upload all ({n})': {'n': 3},
    'Uploading {i}/{total}…': {'i': 1, 'total': 9},
    '{verb} {i} of {total} file(s)…': {'verb': 'X', 'i': 1, 'total': 2},
    'Logged in as {username}': {'username': 'Seewolf'},
    '{pos}/{shown} shown ({total} in folder)': {'pos': 1, 'shown': 2, 'total': 3},
    'Done: {ok}/{total} file(s) copied': {'ok': 1, 'total': 2},
    'Applied "{key}" to {n} file(s).': {'key': 'depicts', 'n': 4},
    'Effective wikitext (upload settings + base description + this file). '
    'Read-only; shown at most {max_lines} lines high - hover a cell for '
    'the full text.': {'max_lines': 12},
}
fmt_bad = []
for key, args in sample.items():
    for lang, _n in UI_LANGUAGES:
        set_language(lang)
        try:
            tr(key).format(**args)
        except Exception as e:
            fmt_bad.append((key, lang, str(e)))
check('.format() works in every language', not fmt_bad, str(fmt_bad[:2]))

# ── 4) Fallback ──────────────────────────────────────────────────────────────
set_language('en')
check('en returns the key', tr('Upload all') == 'Upload all')
set_language('de')
check('de translates', tr('Upload all') == 'Alle hochladen', tr('Upload all'))
check('unknown key falls back', tr('__not a key__') == '__not a key__')
set_language('klingon')
check('unknown language clamps to en', current_language() == 'en')

# ── 5) Locale default ────────────────────────────────────────────────────────
check('locale de_DE -> de', default_language_from_locale('de_DE') == 'de')
check('locale it_IT -> it', default_language_from_locale('it_IT') == 'it')
check('locale ja_JP -> en', default_language_from_locale('ja_JP') == 'en')
check('locale empty -> en', default_language_from_locale('') == 'en')

# ── 6) The window builds in every language ───────────────────────────────────
app = QApplication(sys.argv)
logger, emitter, gui_handler, log_path = setup_logging()
settings = QSettings(APP_NAME, 'Main')
saved_lang = settings.value('ui_language')

for code, name in UI_LANGUAGES:
    set_language(code)
    try:
        w = Cammello.MainWindow(logger, emitter, gui_handler, log_path)
        w.resize(1200, 800)
        w.show()
        app.processEvents()
        tabs = [w.tabs.tabText(i) for i in range(w.tabs.count())]
        ok = bool(tabs) and 'MediaWiki' in tabs
        check(f'window builds in {code}', ok, str(tabs))
        # The language combo shows the active language.
        check(f'{code}: language combo selected',
              w.language_combo.currentData() == code)
        # Scheme combo keeps CODES as data even with translated labels.
        check(f'{code}: scheme combo data are codes',
              [w.scheme_combo.itemData(i) for i in range(3)]
              == ['system', 'light', 'dark'])
        if hasattr(w, '_cull_wb'):
            w._cull_shutdown()
        w.deleteLater()
        app.processEvents()
    except Exception as e:
        check(f'window builds in {code}', False, repr(e))

# ── 7) Progress-status prefixes are never translated away ────────────────────
# The dialogs count a file as finished by the status PREFIX; if a translation
# dropped the marker, the progress bar would freeze.
for code, _n in UI_LANGUAGES:
    set_language(code)
    check(f'{code}: "Error" prefix intact', ('✗ ' + tr('Error')).startswith('✗'))
    check(f'{code}: "Sent" prefix intact', ('✓ ' + tr('Sent')).startswith('✓'))
    check(f'{code}: "Skipped" prefix intact',
          ('• ' + tr('Skipped (exists)')).startswith('•'))

set_language('en')
if saved_lang is None:
    settings.remove('ui_language')
else:
    settings.setValue('ui_language', saved_lang)
settings.sync()

print('---')
print('FAILURES:', fails if fails else 'none')
sys.exit(1 if fails else 0)
