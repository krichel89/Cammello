#!/usr/bin/env python3
"""0.18.29: "Suggest captions" under depicts in the per-file editor - captions
in every configured language, the linked description for each language and
the categories of the depicts entries, filling ONLY what is still empty.

Run headless:  QT_QPA_PLATFORM=offscreen python3 test_suggestcaps_01829.py
"""
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication, QPushButton, QTableWidgetItem
from PyQt5.QtCore import QSettings, Qt

app = QApplication.instance() or QApplication([])

import Cammello                                            # noqa: E402
from cammello import captions, editors, i18n, mw_files    # noqa: E402
from cammello.constants import APP_NAME                    # noqa: E402
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


# ── 1. the Qt-free rule: fill only what is empty ────────────────────────────
caps = {'en': 'Anna, Berlinale', 'de': 'Anna bei der Berlinale',
        'fr': 'Anna, Berlinale'}
linked = {'en': '[[:en:Anna|Anna]]', 'de': '[[:de:Anna|Anna]] bei'}

eq('nothing there: everything is filled',
   captions.fill_missing({}, {}, caps, linked),
   {'caption_en': 'Anna, Berlinale', 'caption_de': 'Anna bei der Berlinale',
    'caption_fr': 'Anna, Berlinale', 'info:en': '[[:en:Anna|Anna]]',
    'info:de': '[[:de:Anna|Anna]] bei'})
eq('a hand-written caption is kept',
   sorted(captions.fill_missing({'de': 'meine Fassung'}, {}, caps, {})),
   ['caption_en', 'caption_fr'])
eq('a hand-written description is kept',
   sorted(captions.fill_missing({}, {'en': 'x'}, {}, linked)),
   ['info:de'])
eq('whitespace counts as empty',
   sorted(captions.fill_missing({'de': '  \n'}, {}, {'de': 'neu'}, {})),
   ['caption_de'])
eq('everything there: no change at all',
   captions.fill_missing({'en': 'a', 'de': 'b', 'fr': 'c'},
                         {'en': 'a', 'de': 'b'}, caps, linked), {})
eq('empty generated text is never written',
   captions.fill_missing({}, {}, {'en': ''}, {'en': ''}), {})

# ── 2. the button in the per-file editor ────────────────────────────────────
ed = editors.StructuredDescriptionEditor(is_base=False)
btn = getattr(ed, 'suggest_captions_btn', None)
check('the per-file editor has the button', isinstance(btn, QPushButton))
check('it sits in the depicts widget, so hiding depicts hides it',
      btn is not None and ed._depicts_row_widget.isAncestorOf(btn))
lay = ed._depicts_row_widget.layout()
check('and BELOW the field: the depicts row comes first, the button row second',
      lay.count() == 2 and lay.itemAt(0).layout().indexOf(ed.depicts) >= 0
      and lay.itemAt(1).layout().indexOf(btn) >= 0)
fired = []
ed.suggest_captions_requested.connect(lambda: fired.append(1))
if btn:
    btn.click()
eq('clicking emits the signal once', fired, [1])
check('the old "New item" button stays next to the field',
      ed.new_person_btn.parent() is ed.depicts.parent())
check('the base editor has no such button',
      not hasattr(editors.StructuredDescriptionEditor(is_base=True),
                  'suggest_captions_btn'))
check('label is translated in all four languages',
      set(i18n.TRANSLATIONS.get('Suggest captions', {}))
      >= {'de', 'es', 'fr', 'it'})
tip = btn.toolTip() if btn else ''
check('the tooltip is a translation key', tip in i18n.TRANSLATIONS, tip[:50])

# ── 2a. blanks around a connector ───────────────────────────────────────────
jt = captions.join_tail
eq('bare connector gets blanks both sides', jt('bei', 'Berlinale', 'de'),
   ' bei Berlinale')
eq('a connector with blanks is left alone', jt(' bei der ', 'Berlinale', 'de'),
   ' bei der Berlinale')
eq('a comma connector gets no blank before', jt(', ', 'Berlinale', 'de'),
   ', Berlinale')
eq('an apostrophe gets no blank after', jt(" à l'", 'Berlinale', 'fr'),
   " à l'Berlinale")
eq('a bare dash is spaced', jt('-', 'Berlinale', 'de'), ' - Berlinale')
eq('CJK is taken as typed', jt('の', 'ベルリン', 'ja'), 'のベルリン')
eq('form only gets a blank', jt('', 'Berlinale', 'en'), ' Berlinale')
tb = captions.FuegungTable()
tb.learn('QE', 'en', 'at', 'the Berlinale')
eq('a bare "at" yields a readable caption',
   captions.build_caption('Anna', 'QE', 'Berlinale', 'en', tb),
   'Anna at the Berlinale')

tb2 = captions.FuegungTable()
tb2.learn('QE', 'de', 'bei', '')
eq('a connector without an event form still names the event',
   captions.build_caption('Anna', 'QE', 'Berlinale', 'de', tb2),
   'Anna bei Berlinale')
check('and the linked description links it',
      '[[:de:IFB|Berlinale]]' in captions.linked_description(
          [], 'QE', {'QE': {'labels': {'de': 'Berlinale'},
                            'sitelinks': {'dewiki': 'IFB'}}}, tb2, 'de',
          ['de']))
eq('empty connector and form stay the caseless fallback',
   captions.build_caption('Anna', 'QE', 'Berlinale', 'de',
                          captions.FuegungTable()), 'Anna, Berlinale')

# ── 2b. 429: patient retry, plain words, one request ───────────────────────
import requests                                             # noqa: E402
from cammello import wikidata, constants                    # noqa: E402

eq('commons_categories shape',
   captions.commons_categories(ENT_ := {
       'Q1': {'labels': {'de': 'Anna'}, 'commons_category': 'Anna C'},
       'Q2': {'labels': {'fr': 'Bob'}}}, ['Q1', 'Q2', 'Q3']),
   {'Q1': ('Anna C', 'Anna'), 'Q2': (None, 'Bob'), 'Q3': (None, '')})


class _Resp:
    def __init__(self, code, headers=None, data=None):
        self.status_code = code
        self.headers = headers or {}
        self._d = data or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            e = requests.HTTPError(f'{self.status_code} Client Error')
            e.response = self
            raise e

    def json(self):
        return self._d


def run_get(codes, headers=None):
    seq = list(codes)
    sleeps, seen = [], []
    og, os_ = wikidata.requests.get, wikidata.time.sleep

    def fake_get(url, params=None, headers=None, timeout=None):
        seen.append(headers)
        c = seq.pop(0)
        return _Resp(c, (hdrs if c == 429 else {}), {'ok': c})
    hdrs = headers or {}
    wikidata.requests.get = fake_get
    wikidata.time.sleep = lambda t: sleeps.append(t)
    try:
        try:
            return wikidata.wd_get_json({'a': 1}), sleeps, seen
        except requests.HTTPError as exc:
            return exc, sleeps, seen
    finally:
        wikidata.requests.get, wikidata.time.sleep = og, os_


res, sl, seen = run_get([200])
eq('no limit: answer at once, no waiting', (res, sl), ({'ok': 200}, []))
res, sl, seen = run_get([429, 200])
eq('one 429 is waited out', (res, sl), ({'ok': 200}, [1.0]))
res, sl, seen = run_get([429, 200], {'Retry-After': '3'})
eq('Retry-After is honoured', sl, [3.0])
res, sl, seen = run_get([429, 200], {'Retry-After': '999'})
eq('and capped at six seconds', sl, [6.0])
res, sl, seen = run_get([429, 200], {'Retry-After': 'Wed, 1 Jan'})
eq('a date in Retry-After falls back', sl, [1.0])
res, sl, seen = run_get([503, 429, 200])
eq('503 and 429 are retried, with growing waits', (res, sl),
   ({'ok': 200}, [1.0, 2.0]))
res, sl, seen = run_get([429, 429, 429])
check('after the retries the error is raised',
      isinstance(res, requests.HTTPError) and len(sl) == 2, str(res))
res, sl, seen = run_get([404])
check('other errors are not retried',
      isinstance(res, requests.HTTPError) and sl == [], str(res))
check('the User-Agent names the repo and a contact page',
      'github.com/krichel89/Cammello' in constants.WD_USER_AGENT
      and 'User:Seewolf' in constants.WD_USER_AGENT, constants.WD_USER_AGENT)
check('and is the one that is sent',
      seen[-1] == {'User-Agent': constants.WD_USER_AGENT}, str(seen))

exc = requests.HTTPError('429 Client Error')
exc.response = _Resp(429)
check('429 gets plain words',
      'Wait' in wikidata.wd_error_text(exc)
      or i18n.tr('Wikidata is limiting requests at the moment (429). Wait '
                 'a minute, then try again.') == wikidata.wd_error_text(exc),
      wikidata.wd_error_text(exc))
check('other errors keep the technical text',
      '500' in wikidata.wd_error_text(ValueError('500 boom')))
check('the 429 text is translated',
      set(i18n.TRANSLATIONS.get('Wikidata is limiting requests at the moment '
                                '(429). Wait a minute, then try again.', {}))
      >= {'de', 'es', 'fr', 'it'})

# ── 3. inside the main window ───────────────────────────────────────────────
logger, emitter, gui_handler, log_path = setup_logging()
w = Cammello.MainWindow(logger, emitter, gui_handler, log_path)
fs = w.file_struct
w._set_field_visible('zeigt', False)
check('hiding "zeigt" hides the button with it',
      fs._depicts_row_widget.isHidden())
w._set_field_visible('zeigt', True)
check('showing brings it back', not fs._depicts_row_widget.isHidden())

ENT = {
    'Q1': {'human': True, 'labels': {'en': 'Anna Müller', 'de': 'Anna Müller'},
           'sitelinks': {'dewiki': 'Anna Müller'},
           'commons_category': 'Anna Müller'},
    'Q2': {'human': True, 'labels': {'en': 'Bob Beta', 'de': 'Bob Beta'},
           'sitelinks': {}},
    'QE': {'human': False, 'labels': {'en': 'Berlinale', 'de': 'Berlinale'},
           'sitelinks': {'dewiki': 'Internationale Filmfestspiele Berlin'}},
}
calls = {'fetch': 0}


def fake_fetch(parent, label, fn_, *a, **k):
    calls['fetch'] += 1
    return (ENT, None, False)


settings = QSettings(APP_NAME, 'Captions')
saved_langs = settings.value('languages', '', type=str)
saved_fueg = settings.value('fuegungen', '', type=str)
settings.setValue('languages', 'en|de')

infos = []
orig_fetch = mw_files.fetch_in_background
orig_info = mw_files.QMessageBox.information
mw_files.fetch_in_background = fake_fetch
# The event belongs to the BASE description (the per-file editor has no
# created-during field), exactly as in real use.
base_event_before = w.base_struct.created_during.text()
w.base_struct.created_during.setText('QE')
mw_files.QMessageBox.information = staticmethod(
    lambda *a, **k: infos.append(a))


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


def fields_of(r):
    return decompose_fields(w.table.item(r, w.COL_DESC).text())


# The languages: four defaults, plus what the user added, until removed.
from cammello.constants import (remember_caption_language,           # noqa: E402
                                forget_caption_language)
main_settings = QSettings(APP_NAME, 'Main')
saved_extra = main_settings.value('caption_extra_langs', '')
try:
    settings.remove('languages')
    main_settings.setValue('caption_extra_langs', '')
    eq('default: exactly en, de, fr, it', w._caption_langs(),
       ['en', 'de', 'fr', 'it'])
    remember_caption_language('ja')
    eq('an added language joins the four', w._caption_langs(),
       ['en', 'de', 'fr', 'it', 'ja'])
    eq('and stays: asked again', w._caption_langs(),
       ['en', 'de', 'fr', 'it', 'ja'])
    remember_caption_language('es')
    eq('Spanish is no longer a default but can be added',
       w._caption_langs(), ['en', 'de', 'fr', 'it', 'ja', 'es'])
    forget_caption_language('ja')
    eq('removing it takes it out again', w._caption_langs(),
       ['en', 'de', 'fr', 'it', 'es'])
    forget_caption_language('es')
    eq('back to the four', w._caption_langs(), ['en', 'de', 'fr', 'it'])
finally:
    main_settings.setValue('caption_extra_langs', saved_extra or '')
    settings.setValue('languages', 'en|de')

try:
    # nothing selected
    w.table.clearSelection()
    w._suggest_captions()
    eq('no selection: no request is made', calls['fetch'], 0)

    # no depicts: a message, nothing written, no request
    r0 = add_row('leer.jpg', '')
    w.table.clearSelection()
    w.table.selectRow(r0)
    w._suggest_captions()
    eq('no depicts: one message', len(infos), 1)
    eq('and no Wikidata request', calls['fetch'], 0)
    eq('and nothing written', w.table.item(r0, w.COL_DESC).text(), '')

    # one file, one caption already written by hand
    r1 = add_row('anna.jpg', 'depicts=Q1\ncaption_de=Meine eigene Fassung')
    w.table.clearSelection()
    w.table.selectRow(r1)
    w._suggest_captions()
    eq('one request for the whole selection', calls['fetch'], 1)
    f, cats = fields_of(r1)
    eq('the hand-written caption is untouched', f.get('caption_de'),
       'Meine eigene Fassung')
    eq('the missing English caption is made', f.get('caption_en'),
       'Anna Müller, Berlinale')
    check('the English description is linked',
          '[[:en:' not in (f.get('info:en') or '')
          or 'Berlinale' in (f.get('info:en') or ''), f.get('info:en'))
    check('both languages got a description',
          bool(f.get('info:en')) and bool(f.get('info:de')),
          f'{f.get("info:en")!r} / {f.get("info:de")!r}')
    check('the German description links the event',
          '[[:de:Internationale Filmfestspiele Berlin|Berlinale]]'
          in (f.get('info:de') or ''), f.get('info:de'))
    check('the caption itself carries no link markup',
          '[[' not in (f.get('caption_en') or ''))
    check('only the two configured languages', 'caption_fr' not in f)
    eq('the depicts category is added', [c.strip() for c in cats],
       ['Anna Müller'])
    eq('the editor shows the new categories',
       fs.categories.text().strip(), 'Anna Müller')
    eq('and the new English caption',
       fs.captions_editor.get_captions().get('en'), 'Anna Müller, Berlinale')

    # pressing it again changes nothing
    before = w.table.item(r1, w.COL_DESC).text()
    w._suggest_captions()
    eq('pressing again: text unchanged',
       w.table.item(r1, w.COL_DESC).text(), before)
    check('and says so',
          'Nothing to fill' in w.status_bar.currentMessage()
          or i18n.tr('Nothing to fill - captions, descriptions and '
                     'categories are already there.')
          == w.status_bar.currentMessage(), w.status_bar.currentMessage())

    # a hand-corrected description survives a depicts change
    f1, c1 = fields_of(r1)
    w.table.item(r1, w.COL_DESC).setText(
        w.table.item(r1, w.COL_DESC).text().replace(
            f1['info:en'], 'Von Hand geschrieben'))
    w.table.item(r1, w.COL_DESC).setText(
        w.table.item(r1, w.COL_DESC).text().replace('depicts=Q1',
                                                    'depicts=Q1; Q2'))
    w._load_selected_desc()          # the editor shows the changed text
    w._suggest_captions()
    f2, c2 = fields_of(r1)
    eq('a hand-written description survives', f2.get('info:en'),
       'Von Hand geschrieben')
    check('the second person gets a category (label fallback)',
          'Bob Beta' in [c.strip() for c in c2], str(c2))
    eq('the first category is not doubled',
       [c.strip() for c in c2].count('Anna Müller'), 1)

    # two files selected: each one uses its own depicts
    ra = add_row('a.jpg', 'depicts=Q1')
    rb = add_row('b.jpg', 'depicts=Q2')
    w.table.clearSelection()
    w.table.selectRow(ra)
    w.table.selectionModel().select(
        w.table.model().index(rb, 0),
        w.table.selectionModel().Select | w.table.selectionModel().Rows)
    n = calls['fetch']
    w._suggest_captions()
    eq('two files, still one request', calls['fetch'], n + 1)
    fa, _ = fields_of(ra)
    fb, _ = fields_of(rb)
    eq('file A names Anna', fa.get('caption_en'), 'Anna Müller, Berlinale')
    eq('file B names Bob', fb.get('caption_en'), 'Bob Beta, Berlinale')

    # the conjunctions are NOT stored behind the user's back
    eq('no conjunction was persisted',
       settings.value('fuegungen', '', type=str), saved_fueg)
finally:
    mw_files.fetch_in_background = orig_fetch
    mw_files.QMessageBox.information = orig_info
    w.base_struct.created_during.setText(base_event_before)
    settings.setValue('languages', saved_langs)
    w.close()

print(f'\n{PASSED} Pruefungen bestanden, {len(FAILED)} gescheitert')
for f_ in FAILED:
    print('  -', f_)
sys.exit(1 if FAILED else 0)
