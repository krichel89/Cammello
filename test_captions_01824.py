#!/usr/bin/env python3
"""0.18.24: structured-data captions generated in every language from
depicts and created-during, with a learned per-event/per-language
conjunction and a caseless fallback.

The whole rulebook is Qt-free, so this test needs neither a window nor a
network. Run:  python3 test_captions_01824.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cammello import captions                                 # noqa: E402
from cammello.constants import CAPTION_MAX_LEN                 # noqa: E402

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


# ── a small normalized entity store, the shape the fetch layer returns ──────
ENT = {
    'Q1': {'human': True,
           'labels': {'en': 'Anna Müller', 'de': 'Anna Müller',
                      'fr': 'Anna Müller'},
           'sitelinks': {'dewiki': 'Anna Müller'}},
    'Q2': {'human': True,
           'labels': {'en': 'Bob Meyer', 'de': 'Bob Meyer'},
           'sitelinks': {}},
    'QE': {'human': False,
           'labels': {'en': 'Berlinale', 'de': 'Berlinale',
                      'fr': 'Berlinale'},
           'sitelinks': {'dewiki': 'Internationale Filmfestspiele Berlin',
                         'enwiki': 'Berlin International Film Festival'}},
    'QB': {'human': False,        # a depicted THING, no person in the picture
           'labels': {'en': 'Brandenburg Gate', 'de': 'Brandenburger Tor'},
           'sitelinks': {'dewiki': 'Brandenburger Tor'}},
}

# ── 1. reading entities ─────────────────────────────────────────────────────
check('a human is recognised', captions.is_human(ENT['Q1']))
check('a thing is not a human', not captions.is_human(ENT['QB']))
check('a missing entity is not a human', not captions.is_human(None))
eq('the label prefers the asked language',
   captions.entity_label(ENT['QE'], 'fr'), 'Berlinale')
eq('and falls back when the language is absent',
   captions.entity_label(ENT['Q2'], 'fr'), 'Bob Meyer')   # -> en fallback
eq('a bare entity has no label', captions.entity_label({}, 'en'), '')

# ── 2. the subject: humans win, else the things ─────────────────────────────
eq('the human among the depicts is the subject',
   captions.subject_qids(['QB', 'Q1'], ENT), ['Q1'])
eq('two people are both the subject',
   captions.subject_qids(['Q1', 'Q2'], ENT), ['Q1', 'Q2'])
eq('with no person, the things are the subject',
   captions.subject_qids(['QB'], ENT), ['QB'])
eq('two names are joined', captions.subject_name(['Q1', 'Q2'], ENT, 'en'),
   'Anna Müller, Bob Meyer')

# ── 3. the caption itself ───────────────────────────────────────────────────
tbl = captions.FuegungTable()
# Nothing learned yet -> the caseless "Name, Event".
eq('unlearned language is caseless',
   captions.build_caption('Anna Müller', 'QE', 'Berlinale', 'de', tbl),
   'Anna Müller, Berlinale')
# Learn the German conjunction, then it reads as a sentence.
tbl.learn('QE', 'de', ' bei der ', 'Berlinale')
eq('a learned conjunction makes a sentence',
   captions.build_caption('Anna Müller', 'QE', 'Berlinale', 'de', tbl),
   'Anna Müller bei der Berlinale')
eq('a different language stays caseless until it too is learned',
   captions.build_caption('Anna Müller', 'QE', 'Berlinale', 'fr', tbl),
   'Anna Müller, Berlinale')
eq('no event gives just the name',
   captions.build_caption('Anna Müller', '', '', 'en', tbl), 'Anna Müller')
eq('no subject and no event gives nothing',
   captions.build_caption('', '', '', 'en', tbl), '')
eq('an event with no subject is the event alone',
   captions.build_caption('', 'QE', 'Berlinale', 'en', tbl), 'Berlinale')

# ── 4. all languages at once ────────────────────────────────────────────────
caps = captions.all_captions(['Q1'], 'QE', ENT, tbl,
                             ['en', 'de', 'fr'])
eq('German uses the learned sentence', caps['de'], 'Anna Müller bei der Berlinale')
eq('English is caseless', caps['en'], 'Anna Müller, Berlinale')
eq('French is caseless', caps['fr'], 'Anna Müller, Berlinale')
# A depicts-only picture (no event) still gets a caption in every language.
caps2 = captions.all_captions(['QB'], '', ENT, tbl, ['en', 'de'])
eq('a thing with no event is captioned by its name',
   caps2['de'], 'Brandenburger Tor')

# ── 5. deriving a conjunction from a hand-written caption ───────────────────
eq('a sentence caption yields its conjunction',
   captions.derive_fuegung('Anna Müller bei der Berlinale', 'Anna Müller',
                           'Berlinale'), (' bei der ', 'Berlinale'))
check('the caseless form is NOT learned as a conjunction',
      captions.derive_fuegung('Anna Müller, Berlinale', 'Anna Müller',
                              'Berlinale') is None)
check('a caption that does not start with the name yields nothing',
      captions.derive_fuegung('At the Berlinale: Anna', 'Anna Müller',
                              'Berlinale') is None)
check('an event label not present yields nothing',
      captions.derive_fuegung('Anna Müller in Berlin', 'Anna Müller',
                              'Berlinale') is None)

# Round trip: derive, learn, rebuild -> the very caption comes back.
d = captions.derive_fuegung('Bob Meyer beim Festival', 'Bob Meyer', 'Festival')
check('an arbitrary conjunction round-trips', d is not None)
t2 = captions.FuegungTable()
t2.learn('QX', 'de', *d)
eq('and rebuilds the same caption for another person',
   captions.build_caption('Carla Roth', 'QX', 'Festival', 'de', t2),
   'Carla Roth beim Festival')

# ── 6. the table persists as JSON, corruption is survived ───────────────────
blob = tbl.to_json()
back = captions.FuegungTable.from_json(blob)
eq('a saved table reloads', back.tail('QE', 'de'), ' bei der Berlinale')
eq('garbage JSON yields an empty table',
   captions.FuegungTable.from_json('{not json').events(), [])
eq('a non-dict payload yields an empty table',
   captions.FuegungTable.from_json('[1,2,3]').events(), [])
# Learning empty forgets the entry.
back.learn('QE', 'de', '', '')
check('learning an empty pair forgets it', back.get('QE', 'de') is None)

# ── 7. length is clamped to the label limit ─────────────────────────────────
long_name = 'Verylongname ' * 30
cap = captions.build_caption(long_name.strip(), 'QE', 'Berlinale', 'de', tbl)
check('a caption never exceeds the label limit',
      len(cap) <= CAPTION_MAX_LEN, str(len(cap)))
check('and is not cut mid-word', not cap.endswith('Verylongnam'))

# ── 8. interwiki links, only for the description ────────────────────────────
eq('a German sitelink becomes a German interwiki link',
   captions.interwiki_link(ENT['QE'], ['de', 'en']),
   '[[:de:Internationale Filmfestspiele Berlin|Berlinale]]')
eq('the preferred language is honoured',
   captions.interwiki_link(ENT['QE'], ['en', 'de']),
   '[[:en:Berlin International Film Festival|Berlinale]]')
eq('no sitelink, no link', captions.interwiki_link(ENT['Q2'], ['de', 'en']), '')
# A hostile label must not break out of the link into other wikitext.
evil = {'labels': {'de': 'Bad]]{{Delete}}|x'},
        'sitelinks': {'dewiki': 'Real Title'}}
link = captions.interwiki_link(evil, ['de'])
check('a label cannot break out of the interwiki link',
      ']]' not in link.split('|', 1)[1][:-2] and '{{' not in link, link)

# A linked description carries the links; the caption never does.
desc = captions.linked_description(['Q1'], 'QE', ENT, tbl, 'de', ['de', 'en'])
check('the linked description links the person',
      '[[:de:Anna Müller|Anna Müller]]' in desc, desc)
check('and links the event inside the learned form',
      '[[:de:Internationale Filmfestspiele Berlin|Berlinale]]' in desc, desc)
plain = captions.build_caption('Anna Müller', 'QE', 'Berlinale', 'de', tbl)
check('the caption has no link markup at all', '[[' not in plain, plain)

# ── 9. learning across a whole selection, and merging with the store ────────
rows = [
    {'depicts': ['Q1'], 'event': 'QE',
     'captions': {'de': 'Anna Müller bei der Berlinale',
                  'en': 'Anna Müller, Berlinale'}},   # en is caseless -> not learned
    {'depicts': ['Q2'], 'event': 'QE', 'captions': {}},
]
learned = captions.derive_table(rows, ENT, ['en', 'de', 'fr'])
eq('German is learned from the hand-written caption',
   learned.tail('QE', 'de'), ' bei der Berlinale')
check('the caseless English caption teaches nothing',
      learned.get('QE', 'en') is None)
# It propagates to the OTHER person at the same event.
eq('the learned conjunction names the second person too',
   captions.build_caption('Bob Meyer', 'QE', 'Berlinale', 'de', learned),
   'Bob Meyer bei der Berlinale')

store = captions.FuegungTable()
store.learn('QE', 'fr', ' à la ', 'Berlinale')
store.merge_from(learned)              # gaps only: keeps the French it had
eq('merge keeps the stored French', store.tail('QE', 'fr'), ' à la Berlinale')
eq('and gains the learned German', store.tail('QE', 'de'), ' bei der Berlinale')
store.learn('QE', 'de', ' beim ', 'Festival')
store.merge_from(learned)              # gaps only -> the dialog value stands
eq('a value already set is not overwritten by a later merge',
   store.tail('QE', 'de'), ' beim Festival')

print(f'\n{PASSED} Pruefungen bestanden, {len(FAILED)} gescheitert')
for f in FAILED:
    print('  -', f)
sys.exit(1 if FAILED else 0)
