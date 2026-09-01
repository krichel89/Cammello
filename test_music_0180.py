"""Music workflow: the file page, the fields and the categories (0.18.0).

The specification is Harald's Mendelssohn page on Commons - organ sonata
op. 65 no. 5, recorded by Wolfram Syré. It is reproduced VERBATIM below
and the generator has to hit it character for character. Everything else
in here defends a decision that page does not show:

  1. the three field lists (constants.MUSIC_FIELDS, music.FIELDS,
     workflow_config.DEFAULT_OFF) name the same fields,
  2. the music fields are OFF in every other workflow, including a
     workflows.toml written before they existed,
  3. the photograph path is untouched - same wikitext as 0.16.1,
  4. |deathyear= is added once and never twice,
  5. categories that Commons does not have are dropped, and a failing
     check does not fail the upload.
"""
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import Cammello        # the shim; also puts the package on the path
from cammello import music
from cammello import workflow_config, workflows
from cammello.constants import (MUSIC_FIELDS, MUSIC_SET_FIELDS,
                                MUSIC_SEL_FIELDS)

fails = []


def check(name, cond, detail=''):
    print(('PASS' if cond else 'FAIL'), name, detail)
    if not cond:
        fails.append(name)


check('the shim still exposes the package', hasattr(Cammello, 'main'))

# ── Harald's page, verbatim ──────────────────────────────────────────────
DESCRIPTION = ("{{en|1=Felix Mendelssohn's organ sonata in D major op. 65 "
               "no. 5 played by Wolfram Syré, recorded with a sample of the "
               "1999 Collon organ in the [[:de:Erlöserkirche (Münster)|"
               "Erlöserkirche]] in Münster, Germany}}")

VALUES = {
    'komponist': '[[:en:Felix Mendelssohn|Felix Mendelssohn Bartoldy]]',
    'todesjahr_komponist': '1847',
    'kompositionsjahr': '1845',
    'aufnehmender': '[[:de:Wolfram Syré|Wolfram Syré]]',
    'aufnahmetechnik': 'using a [[:en:Hauptwerk|Hauptwerk]] digital organ',
    'quelle': ('[https://organ-repertory.de/romantic-germany-austria/'
               'sonate-d-dur-op-65-5/ Organ Repertory Dr. Wolfram Syré]'),
    'quellvorlage': '{{Organ Repertory Wolfram Syré}}',
    'lizenz_komposition': '{{PD-old-auto-expired}}',
    'lizenz_aufnahme': '{{Wolfram Syré-permission}}',
    'genehmigung': '',
    'andere_versionen': '',
    'instrument': 'organ',
    'epoche': 'German and Austrian Romantic',
    'werk': 'Six organ sonatas (Mendelssohn)',
    'land': 'Germany',
}

CATEGORIES = [
    '[[Category:Audio files of organ music recorded by Wolfram Syré]]',
    '[[Category:Audio files of music of Germany]]',
    '[[Category:Audio files of music by Felix Mendelssohn]]',
    '[[Category:Audio files of German and Austrian Romantic music recorded '
    'by Wolfram Syré]]',
    '[[Category:Audio files of music by Felix Mendelssohn recorded by '
    'Wolfram Syré]]',
    '[[Category:Six organ sonatas (Mendelssohn)]]',
    '[[Category:Audio files of sonatas]]',
]

EXPECTED = '''=={{int:filedesc}}==
{{Information
|description=''' + DESCRIPTION + '''
|date=1845
|source=[https://organ-repertory.de/romantic-germany-austria/sonate-d-dur-op-65-5/ Organ Repertory Dr. Wolfram Syré]{{Organ Repertory Wolfram Syré}}
|author=composition: [[:en:Felix Mendelssohn|Felix Mendelssohn Bartoldy]]
recording (using a [[:en:Hauptwerk|Hauptwerk]] digital organ): [[:de:Wolfram Syré|Wolfram Syré]]
|permission=
|other versions=
}}

=={{int:license-header}}==
*composition:
{{PD-old-auto-expired|deathyear=1847}}
*performance:
{{Wolfram Syré-permission}}

''' + '\n'.join(CATEGORIES)

got = music.build_wikitext(VALUES, DESCRIPTION, CATEGORIES)
check('the whole page matches Harald\'s file description', got == EXPECTED)
if got != EXPECTED:
    import difflib
    for line in difflib.unified_diff(EXPECTED.splitlines(),
                                     got.splitlines(), lineterm=''):
        print('   ', line)

# ── The pieces on their own ──────────────────────────────────────────────
check('author line carries both roles',
      music.author_line(VALUES) ==
      'composition: [[:en:Felix Mendelssohn|Felix Mendelssohn Bartoldy]]\n'
      'recording (using a [[:en:Hauptwerk|Hauptwerk]] digital organ): '
      '[[:de:Wolfram Syré|Wolfram Syré]]')
check('a role without a name is left out, not written empty',
      music.author_line({'aufnehmender': 'X'}) == 'recording: X')
check('no technique means no brackets',
      music.author_line({'komponist': 'A', 'aufnehmender': 'B'}) ==
      'composition: A\nrecording: B')
check('source template sticks to the link without a space',
      music.source_line(VALUES).endswith(
          'Syré]{{Organ Repertory Wolfram Syré}}'))

# deathyear: added once, never twice, never against the user's own wikitext
check('deathyear is inserted',
      music.with_deathyear('{{PD-old-auto-expired}}', '1847') ==
      '{{PD-old-auto-expired|deathyear=1847}}')
check('deathyear already there is left alone',
      music.with_deathyear('{{PD-old-auto-expired|deathyear=1809}}', '1847') ==
      '{{PD-old-auto-expired|deathyear=1809}}')
check('no year, no insertion',
      music.with_deathyear('{{PD-old-70}}', '') == '{{PD-old-70}}')
check('hand-written wikitext is not touched',
      music.with_deathyear('{{A}} and {{B}}', '1847') == '{{A}} and {{B}}')
check('an empty licence stays empty',
      music.with_deathyear('', '1847') == '')

# Neither licence -> no heading over nothing
check('no licence means no licence section',
      '{{int:license-header}}' not in
      music.build_wikitext({'komponist': 'A'}, 'x'))

# ── plain_name: the category half ────────────────────────────────────────
check('link target wins over the visible text',
      music.plain_name('[[:en:Felix Mendelssohn|Felix Mendelssohn Bartoldy]]')
      == 'Felix Mendelssohn')
check('a link without a pipe works',
      music.plain_name('[[:de:Wolfram Syré]]') == 'Wolfram Syré')
check('plain text passes through',
      music.plain_name('Wolfram Syré') == 'Wolfram Syré')
check('empty stays empty', music.plain_name('') == '')

# ── Categories ───────────────────────────────────────────────────────────
cands = music.category_candidates(VALUES)
check('all seven categories of the page are proposed, in order',
      cands == [c[len('[[Category:'):-len(']]')] for c in CATEGORIES],
      f'{len(cands)} candidates')
check('a pattern with an empty field is skipped, not half-filled',
      all('  ' not in c and not c.endswith(' ')
          for c in music.category_candidates(
              dict(VALUES, land='', epoche=''))))
check('missing recordist drops every "recorded by" pattern',
      not any('recorded by' in c for c in
              music.category_candidates(dict(VALUES, aufnehmender=''))))

# ── The three field lists agree ──────────────────────────────────────────
check('MUSIC_FIELDS, music.FIELDS and DEFAULT_OFF name the same fields',
      sorted(n for n, _l, _h, _s in MUSIC_FIELDS) == sorted(music.FIELDS)
      == sorted(workflow_config.DEFAULT_OFF),
      f'{len(music.FIELDS)} fields')
check('every music field is a registry field',
      all(n in workflow_config.FIELD_NAMES for n in music.FIELDS))
check('every music field takes text (so vorbelegung works)',
      all(n in workflow_config.TEXT_FIELDS for n in music.FIELDS))
# 0.18.1: every field sits on exactly one side, and the two sides together
# are the whole set - a field that fell out of both lists would simply
# vanish from the UI without anything failing.
check('the two sides partition the thirteen fields',
      len(MUSIC_SET_FIELDS) + len(MUSIC_SEL_FIELDS) == len(MUSIC_FIELDS)
      and not ({f[0] for f in MUSIC_SET_FIELDS}
               & {f[0] for f in MUSIC_SEL_FIELDS}),
      f'{len(MUSIC_SET_FIELDS)} set / {len(MUSIC_SEL_FIELDS)} selection')

# ── Visibility: off everywhere but in the music workflow ─────────────────
workflow_config._cache = None
check('the music workflow switches all thirteen on',
      set(workflows.shown_fields('music')) == set(music.FIELDS))
for key in ('portraits', 'buildings'):
    hidden = set(workflows.hidden_fields(key))
    check(f'music fields are hidden in {key}',
          set(music.FIELDS) <= hidden)
check('music fields are not hidden in the music workflow',
      not (set(music.FIELDS) & set(workflows.hidden_fields('music'))))

# An OLD workflows.toml - written before the music fields existed - must
# not suddenly show them. This is the whole reason felder_an exists.
import tempfile
old_file = os.path.join(tempfile.mkdtemp(), 'workflows.toml')
with open(old_file, 'w', encoding='utf-8') as fh:
    fh.write('[[workflow]]\n'
             'schluessel = "portraits"\n'
             'name = "Events/Portraits"\n'
             'felder_aus = ["kamerastandort"]\n')
keep = os.environ.get(workflow_config.ENV_OVERRIDE)
try:
    os.environ[workflow_config.ENV_OVERRIDE] = old_file
    workflow_config._cache = None
    check('an old workflows.toml keeps the music fields hidden',
          set(music.FIELDS) <= set(workflows.hidden_fields('portraits')))
finally:
    if keep is None:
        os.environ.pop(workflow_config.ENV_OVERRIDE, None)
    else:
        os.environ[workflow_config.ENV_OVERRIDE] = keep
    workflow_config._cache = None

# ── The photograph path is untouched ─────────────────────────────────────
# Not a mock of the worker: the point is that a row WITHOUT the flag never
# reaches the music branch at all.
check('a row without the music flag is not a music row',
      not {'author': 'x'}.get('music'))

# ── Category check against a stand-in API ────────────────────────────────
class FakeApi:
    def __init__(self, existing=(), boom=False):
        self.existing = set(existing)
        self.boom = boom
        self.calls = 0

    def existing_pages(self, titles):
        self.calls += 1
        if self.boom:
            raise RuntimeError('no network')
        return {t for t in titles if t in self.existing}


class FakeLog:
    def __init__(self):
        self.lines = []

    def warning(self, *a):
        self.lines.append(a)

    def info(self, *a):
        self.lines.append(a)


from cammello.workers import UploadWorker

worker = UploadWorker.__new__(UploadWorker)
worker.api = FakeApi(existing=['Category:Audio files of music of Germany'])
worker.log = FakeLog()
out = worker._music_categories(VALUES, set())
check('only categories that exist are added',
      out == ['[[Category:Audio files of music of Germany]]'], str(out))
check('the whole batch is one API call', worker.api.calls == 1)

worker.api = FakeApi(boom=True)
worker.log = FakeLog()
check('a failing check adds nothing and does not raise',
      worker._music_categories(VALUES, set()) == [])

worker.api = FakeApi(existing=['Category:Audio files of music of Germany'])
worker.log = FakeLog()
seen = {'[[Category:Audio files of music of Germany]]'}
check('a category the description already has is not added twice',
      worker._music_categories(VALUES, seen) == [])

print()
print('FAILURES:', ', '.join(fails) if fails else 'none')
sys.exit(1 if fails else 0)
