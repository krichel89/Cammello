#!/usr/bin/env python3
"""0.18.27: "New item" next to depicts - a menu of occupations that opens a
tool (new-q5) for a new Wikidata person item with the properties that fit
the occupation; the caption's name goes to the clipboard.

Run headless:  QT_QPA_PLATFORM=offscreen python3 test_newperson_01827.py
"""
import os
import sys
from urllib.parse import urlparse, parse_qs

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication, QToolButton

app = QApplication.instance() or QApplication([])

from cammello import new_person, i18n, editors            # noqa: E402
from cammello.sdc import extract_name_from_caption        # noqa: E402

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


def query(url):
    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


# ── 1. the Qt-free builder ──────────────────────────────────────────────────
url = new_person.new_person_url('actor')
eq('actor = exactly Haralds example link', url,
   'https://new-q5.toolforge.org/?property=P345%7CP106%7CP69')
check('https address', url.startswith('https://'), url)
eq('the list survives decoding',
   query(new_person.new_person_url('musician')).get('property'),
   'P434|P1953|P106|P1303')
eq('unknown role falls back to "other"', new_person.role('nonsense')[0],
   'other')
eq('"other" offers only occupation',
   query(new_person.new_person_url('other')).get('property'), 'P106')
tmpl = 'https://example.org/new?p={properties}&keep={other}'
u = new_person.new_person_url('politician', template=tmpl)
eq('a changed template gets the same list',
   query(u).get('p'), 'P106|P102|P39')
check('unknown placeholders stay untouched', '{other}' in u, u)

keys = [r[0] for r in new_person.NEW_PERSON_ROLES]
eq('twelve roles, actor first, other last',
   (len(keys), keys[0], keys[-1]), (12, 'actor', 'other'))
check('every entry is a PID',
      all(p.startswith('P') and p[1:].isdigit()
          for r in new_person.NEW_PERSON_ROLES for p in r[2]))
check('every set offers occupation (P106)',
      all('P106' in r[2] for r in new_person.NEW_PERSON_ROLES))
check('no PID twice within one set',
      all(len(set(r[2])) == len(r[2]) for r in new_person.NEW_PERSON_ROLES))
check('every menu label is translated in all four languages',
      all(set(i18n.TRANSLATIONS.get(r[1], {})) >= {'de', 'es', 'fr', 'it'}
          for r in new_person.NEW_PERSON_ROLES))

# name from the captions
split = extract_name_from_caption
eq('name cut from "X at Y"',
   new_person.name_from_captions(
       {'en': 'Alison Sealy-Smith at Dragon Con 2026'}, split=split),
   'Alison Sealy-Smith')
eq('the preferred language wins',
   new_person.name_from_captions(
       {'en': 'Tom Tykwer at the Berlinale', 'de': 'Tom Tykwer bei der '
        'Berlinale'}, prefer=('de', 'en'), split=split), 'Tom Tykwer')
eq('any other language when the preferred ones are empty',
   new_person.name_from_captions({'fr': 'Juliette Binoche'},
                                 prefer=('de', 'en'), split=split),
   'Juliette Binoche')
eq('no caption, no name', new_person.name_from_captions({}, split=split), '')


# ── 2. the button in the per-file editor ────────────────────────────────────
opened = []
editors.QDesktopServices.openUrl = lambda qurl: opened.append(qurl.toString())

ed = editors.StructuredDescriptionEditor(is_base=False)
btn = getattr(ed, 'new_person_btn', None)
check('the per-file editor has the button', isinstance(btn, QToolButton))
check('it opens a menu on click',
      btn is not None and btn.popupMode() == QToolButton.InstantPopup)
acts = ed.new_person_menu.actions() if btn else []
eq('one menu entry per role', [a.data() for a in acts], keys)
check('the button sits in the depicts row, right of the field',
      btn is not None and btn.parent() is ed.depicts.parent())

base = editors.StructuredDescriptionEditor(is_base=True)
check('the base editor has no such button (no depicts there)',
      not hasattr(base, 'new_person_btn'))

ed.captions_editor.set_captions({'en': 'Alison Sealy-Smith at Dragon Con'})
QApplication.clipboard().setText('vorher')
acts[0].trigger()
eq('clicking "Actor" opens exactly one address', len(opened), 1)
eq('the actor link', opened[0] if opened else '',
   'https://new-q5.toolforge.org/?property=P345%7CP106%7CP69')
eq('the name from the caption is on the clipboard',
   QApplication.clipboard().text(), 'Alison Sealy-Smith')

opened.clear()
ed.captions_editor.set_captions({})
QApplication.clipboard().setText('bleibt')
acts[-1].trigger()
eq('without a caption the clipboard is left alone',
   QApplication.clipboard().text(), 'bleibt')
eq('and the tool opens anyway', len(opened), 1)

opened.clear()
new_person_url_orig = new_person.NEW_PERSON_URL
new_person.NEW_PERSON_URL = 'javascript:alert(1)'
ed._open_new_person('actor')
new_person.NEW_PERSON_URL = new_person_url_orig
eq('a non-https address is never handed to the browser', opened, [])

tip = btn.toolTip() if btn else ''
check('the tooltip text is a translation key', tip in i18n.TRANSLATIONS,
      tip[:60])

# ── 3. inside the main window: label and workflow hiding still work ────────
from cammello.logging_setup import setup_logging           # noqa: E402
import Cammello                                            # noqa: E402
logger, emitter, gui_handler, log_path = setup_logging()
w = Cammello.MainWindow(logger, emitter, gui_handler, log_path)
fs = w.file_struct
lbl = w._label_for(fs, fs.depicts)
check('the depicts label is still found (red attention mark)',
      lbl is not None and 'P180' in lbl.text(), str(lbl))
check('and it carries the depicts tooltip',
      lbl is not None and lbl.toolTip() == fs.depicts.toolTip())
w._set_field_visible('zeigt', False)
check('hiding "zeigt" hides field AND button',
      fs.depicts.isHidden() or fs._depicts_row_widget.isHidden())
check('the button goes with it', fs._depicts_row_widget.isHidden())
check('and the label', lbl is not None and lbl.isHidden())
w._set_field_visible('zeigt', True)
check('showing brings all back',
      not fs._depicts_row_widget.isHidden() and not lbl.isHidden())
w.close()

print(f'\n{PASSED} Pruefungen bestanden, {len(FAILED)} gescheitert')
for f in FAILED:
    print('  -', f)
sys.exit(1 if FAILED else 0)
