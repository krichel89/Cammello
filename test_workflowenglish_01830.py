#!/usr/bin/env python3
"""0.18.30: the parameters of a workflow file are English (key, name,
hide_fields, show_fields, [workflow.prefill|set|example], field names like
`templates`) - the German spelling of 0.18.29 and before is still read.
Plus the QK hardening of the .cammello loader: full preview, the bytes that
are stored are the bytes that were checked, safe file names.

Run headless:  QT_QPA_PLATFORM=offscreen python3 test_workflowenglish_01830.py
"""
import os
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
_HOME = tempfile.mkdtemp()
os.environ['HOME'] = _HOME
os.environ['USERPROFILE'] = _HOME
os.environ['CAMMELLO_WORKFLOWS'] = os.path.join(_HOME, 'workflows.toml')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cammello import workflow_config as wc

fails = []
PASSED = 0


def check(name, cond, detail=''):
    global PASSED
    if cond:
        PASSED += 1
    else:
        fails.append(name)
        print('FAIL', name, detail)


def write(path, text):
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(text)


EN = '''
[[workflow]]
key = "en-one"
name = "English One"
hide_fields = ["camera_position", "base_captions"]
show_fields = ["composer"]

  [workflow.prefill]
  author = "A. Author"
  license = "{{self|cc-by-sa-4.0}}"

  [workflow.set]
  templates = "{{T}}"
  categories = "C1; C2"
  created_during = "Q1"

  [workflow.example]
  source = "hint"
'''
DE = '''
[[workflow]]
schluessel = "de-one"
name = "Deutsch Eins"
felder_aus = ["kamerastandort", "captions_basis"]
felder_an = ["komponist"]

  [workflow.vorbelegung]
  autor = "A. Author"
  lizenz = "{{self|cc-by-sa-4.0}}"

  [workflow.setzen]
  vorlagen = "{{T}}"
  kategorien = "C1; C2"
  entstanden_waehrend = "Q1"

  [workflow.beispiel]
  quelle = "hint"
'''

tmp = tempfile.mkdtemp()
en_path = os.path.join(tmp, 'en.cammello')
de_path = os.path.join(tmp, 'de.cammello')
write(en_path, EN)
write(de_path, DE)
en, w1, e1 = wc.inspect_file(en_path)
de, w2, e2 = wc.inspect_file(de_path)
check('English file parses without warnings', e1 is None and w1 == [], str((e1, w1)))
check('German file still parses without warnings', e2 is None and w2 == [], str((e2, w2)))
strip = lambda e: {k: v for k, v in e[0].items() if k not in ('key', 'label')}
check('both spellings give the same entry', strip(en) == strip(de), f'{strip(en)}\n{strip(de)}')
check('and it is the internal field names',
      en[0]['hide'] == ['kamerastandort', 'captions_basis']
      and en[0]['show'] == ['komponist']
      and en[0]['set']['kategorien'] == 'C1; C2', str(en[0]))

# a single name without brackets, mixed spellings, unknown names
mix = os.path.join(tmp, 'mix.cammello')
write(mix, '[[workflow]]\nkey="m"\nname="M"\nhide_fields="camera_position"\n'
           'show_fields=["composer","komponist","nonsense"]\n'
           '  [workflow.prefill]\n  author="x"\n  autor="y"\n  nonsense="z"\n')
m, mw, me = wc.inspect_file(mix)
check('single name accepted', m[0]['hide'] == ['kamerastandort'], str(m))
check('duplicates folded, unknown reported',
      m[0]['show'] == ['komponist'] and any('nonsense' in x for x in mw), str((m, mw)))
check('the warnings speak English keys',
      all('schluessel' not in x for x in mw))
nokey = os.path.join(tmp, 'nokey.cammello')
write(nokey, '[[workflow]]\nname="x"\n')
r = wc.inspect_file(nokey)
check('a block without key is refused', r[2] is not None, str(r))

# templates and generated blocks are English
tpl = wc.template_text()
for word in ('key ', 'hide_fields', 'show_fields', '[workflow.prefill]',
             '[workflow.set]', '[workflow.example]', 'templates',
             'created_during', 'camera_position', 'base_captions'):
    check(f'template mentions {word.strip()}', word in tpl)
check('template block uses English keys',
      'hide_fields = [' in tpl and 'felder_aus = [' not in tpl)
blk = wc.render_block(dict(wc.BUILTIN[0], set={'vorlagen': '{{X}}'},
                           preset={'autor': 'Me'}))
check('render_block is English', 'hide_fields' in blk and 'prefill.author = ' in blk
      and 'set.templates = ' in blk and 'vorbelegung' not in blk, blk)
import tomllib
back = wc._parse(tomllib.loads(blk), [])
check('and reads back', back[0]['set'] == {'vorlagen': '{{X}}'}
      and back[0]['preset'] == {'autor': 'Me'}, str(back))
tpl_data = tomllib.loads(tpl)
check('the generated template parses', len(wc._parse(tpl_data, [])) == len(wc.BUILTIN))
check('portraits hides the base captions by default',
      'captions_basis' in wc._parse(tpl_data, [])[0]['hide'])
check('every field has an English name',
      all(n in wc.ENGLISH_NAMES for n in wc.FIELD_NAMES)
      and len(set(wc.ENGLISH_NAMES.values())) == len(wc.ENGLISH_NAMES))
check('field_name round-trips', all(wc.field_name(wc.external_name(n)) == n
                                    for n in wc.FIELD_NAMES))

# ── QK hardening ────────────────────────────────────────────────────────────
long_val = 'X' * 300 + ' {{Hidden}}'
big = os.path.join(tmp, 'long.cammello')
write(big, f'[[workflow]]\nkey="l"\nname="L"\n  [workflow.set]\n  templates="{long_val}"\n')
le, _lw, _lerr = wc.inspect_file(big)
pv = wc.preview_text(le)
check('the preview shows long values IN FULL', '{{Hidden}}' in pv and '…' not in pv, pv[-60:])
hv = wc.preview_text([dict(wc.BUILTIN[0])])
check('the preview names hidden fields', 'hides' in hv and 'Camera' in hv, hv)

# the stored bytes are the checked bytes
os.environ['HOME'] = _HOME
src = os.path.join(tmp, 'swap.cammello')
write(src, EN.replace('en-one', 'swap'))
wc.reload()
orig_inspect_ok = wc.inspect_file(src)[2] is None
write(src, 'this is not toml [[')               # swapped after the preview
dest, replaced, err = wc.install_file(src)
check('a swapped, broken file is not stored',
      dest is None and err is not None
      and not os.path.exists(os.path.join(wc.extras_dir(), 'swap.cammello')), str((dest, err)))
write(src, EN.replace('en-one', 'swap') + '\n# ' + 'x' * (wc.MAX_FILE_BYTES + 10))
dest, replaced, err = wc.install_file(src)
check('an oversized file is not stored', dest is None and err is not None, str((dest, err)))
check('no .part file is left behind',
      not [n for n in os.listdir(wc.extras_dir()) if n.endswith('.part')]
      if os.path.isdir(wc.extras_dir()) else True)
write(src, EN.replace('en-one', 'swap'))
dest, replaced, err = wc.install_file(src)
check('the good file is stored', err is None and os.path.exists(dest), str((dest, err)))

# file names
for given, want in (('CON.cammello', '_CON.cammello'),
                    ('nul.cammello', '_nul.cammello'),
                    ('COM1.cammello', '_COM1.cammello'),
                    ('lpt9.txt', '_lpt9.txt.cammello'),
                    ('../../etc/passwd.cammello', 'passwd.cammello'),
                    ('a' * 300 + '.cammello', 'a' * 80 + '.cammello'),
                    ('Berlinale 2026.cammello', 'Berlinale 2026.cammello')):
    check(f'safe_name {given[:20]!r}', wc.safe_name(given) == want, wc.safe_name(given))

# ── labels from Wikidata cannot break out of the wikitext ───────────────────
from cammello import captions, wikidata
ents = {'Q1': {'human': True, 'labels': {'en': 'Evil }}{{Delete}} [[x|y]]'},
               'sitelinks': {}},
        'QE': {'labels': {'en': 'Fair | bad {{x}}'}, 'sitelinks': {}}}
tb = captions.FuegungTable()
tb.learn('QE', 'en', 'at', '')
ld = captions.linked_description(['Q1'], 'QE', ents, tb, 'en', ['en'])
check('no template/link markup survives in the linked description',
      not any(c in ld for c in '[]{}|<>'), ld)
ld2 = captions.linked_description(['Q1'], 'QE', ents, captions.FuegungTable(),
                                  'en', ['en'])
check('also in the caseless fallback', not any(c in ld2 for c in '[]{}|<>'), ld2)
check('wiki_safe on clean text is a no-op',
      captions.wiki_safe('Anna  Müller') == 'Anna Müller')
fetched = {'Q1': ('Good cat', 'L1'), 'Q2': ('Bad]]{{Delete}}[[Category:X', 'L2'),
           'Q3': (None, 'Label|pipe'), 'Q4': (None, 'Fine label')}
got = wikidata.category_suggestions(['Q1', 'Q2', 'Q3', 'Q4'], '', fetched, '', [])
check('invalid category names are dropped, valid ones kept',
      got == ['Good cat', 'Fine label'], str(got))

print(f'\n{PASSED} Pruefungen bestanden, {len(fails)} gescheitert')
sys.exit(1 if fails else 0)
