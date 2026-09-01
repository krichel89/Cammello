"""Music fields split between the whole set and the selection (0.18.1).

Harald: "Die Musikdaten sollten auch zwischen dem Gesamtset und der Auswahl
aufgeteilt werden." One delivery is normally one performer on one
instrument from one source - but the pieces on it have different
composers. So:

  * whole set  - recorded by, recording technique, source template,
                 licence of the recording, instrument, period, country,
                 other versions
  * selection  - composer, year of death, year of composition, work,
                 licence of the composition

The selection half rides in the description cell as SD_KEYS, which buys
the whole per-file machinery for free: storage, editing several selected
files at once, and "the per-file value wins over the base value".

What is defended here:

  1. the split itself, and that it is a partition,
  2. the five are SD_KEYS and survive a round trip through the editor
     WITHOUT being duplicated into the free-text box,
  3. base and per-file merge with the file winning,
  4. the worker prefers the selection value over the batch value,
  5. the whole-set fields are NOT in the per-file editor and vice versa.
"""
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import Cammello        # the shim; also puts the package on the path
from PyQt5.QtWidgets import QApplication

from cammello import music
from cammello.constants import (MUSIC_FIELDS, MUSIC_SET_FIELDS,
                                MUSIC_SEL_FIELDS, MUSIC_SEL_NAMES, SD_KEYS)
from cammello.sdc import (extract_structured_data, merge_descriptions,
                          leftover_text)
from cammello.editors import StructuredDescriptionEditor

app = QApplication.instance() or QApplication([])

fails = []


def check(name, cond, detail=''):
    print(('PASS' if cond else 'FAIL'), name, detail)
    if not cond:
        fails.append(name)


check('the shim still exposes the package', hasattr(Cammello, 'main'))

# ── The split ────────────────────────────────────────────────────────────
set_names = [f[0] for f in MUSIC_SET_FIELDS]
sel_names = [f[0] for f in MUSIC_SEL_FIELDS]

check('the selection half is composer, death year, year, work, licence',
      sorted(sel_names) == sorted(['komponist', 'todesjahr_komponist',
                                   'kompositionsjahr', 'werk',
                                   'lizenz_komposition']),
      str(sel_names))
check('the recording side stays with the whole set',
      'aufnehmender' in set_names and 'lizenz_aufnahme' in set_names
      and 'instrument' in set_names)
check('the two sides are a partition of the thirteen',
      len(set_names) + len(sel_names) == len(MUSIC_FIELDS)
      and not (set(set_names) & set(sel_names)))
check('MUSIC_SEL_NAMES matches the selection half',
      MUSIC_SEL_NAMES == sel_names)
check('every music field still exists in music.FIELDS',
      sorted(set_names + sel_names) == sorted(music.FIELDS))

# ── They are structured-data keys ────────────────────────────────────────
check('all five are SD_KEYS', all(n in SD_KEYS for n in sel_names))
check('none of the whole-set fields is an SD_KEY',
      not any(n in SD_KEYS for n in set_names), str(set_names))

# ── Round trip through the editor ────────────────────────────────────────
ed = StructuredDescriptionEditor(is_base=False)
check('the per-file editor has the five selection fields',
      sorted(ed.music) == sorted(sel_names), str(sorted(ed.music)))
base_ed = StructuredDescriptionEditor(is_base=True)
check('the base editor has none of them (they are the selection half)',
      base_ed.music == {}, str(base_ed.music))

ed.music['komponist'].setText('[[:en:Felix Mendelssohn|Felix Mendelssohn]]')
ed.music['todesjahr_komponist'].setText('1847')
ed.music['kompositionsjahr'].setText('1845')
ed.music['werk'].setText('Six organ sonatas (Mendelssohn)')
ed.music['lizenz_komposition'].setText('{{PD-old-auto-expired}}')
ed.coordinates.setText('51.96, 7.63')
ed.extra.setPlainText('freier Text')
text = ed.assemble()

back = StructuredDescriptionEditor(is_base=False)
back.load(text)
check('every value comes back unchanged',
      all(back.music[n].text() == ed.music[n].text() for n in sel_names))

# The fault this caught while it was being built: the key=value lines were
# ALSO left in the leftover text, so they appeared in the free-text box and
# the next save wrote them a second time. _ASSIGN_RE is built from SD_KEYS
# now instead of repeating the list by hand.
check('the lines do not leak into the free-text box',
      back.extra.toPlainText() == 'freier Text',
      repr(back.extra.toPlainText()))
check('a second save is identical - no growth per round trip',
      back.assemble() == text)
check('leftover_text keeps none of the assignments',
      not any(f'{n}=' in leftover_text(text) for n in sel_names))
check('the old drift is gone too (coordinates was missing from the list)',
      'coordinates=' not in leftover_text(text))

# ── Base and per-file ────────────────────────────────────────────────────
base_text = ('komponist=[[:en:Johann Sebastian Bach|Bach]]\n'
             'todesjahr_komponist=1750')
file_text = 'komponist=[[:en:Felix Mendelssohn|Mendelssohn]]'
merged, _warnings = merge_descriptions(base_text, file_text)
sd, _rest = extract_structured_data(merged)
check('the selected file overrides the whole set',
      sd['komponist'] == '[[:en:Felix Mendelssohn|Mendelssohn]]',
      sd.get('komponist', ''))
check('a value only the base has still comes through',
      sd['todesjahr_komponist'] == '1750')

# ── The worker prefers the selection ─────────────────────────────────────
# Not the whole worker: the three lines that decide which value wins.
row = {'music': True, 'komponist': 'batch', 'werk': 'batch work',
       'aufnehmender': '[[:de:Wolfram Syré|Wolfram Syré]]'}
per_file = {'komponist': 'selected', 'werk': ''}
values = dict(row)
for key in MUSIC_SEL_NAMES:
    if per_file.get(key):
        values[key] = per_file[key]
check('a filled selection value wins', values['komponist'] == 'selected')
check('an EMPTY selection value does not erase the batch value',
      values['werk'] == 'batch work')
check('the whole-set value is untouched',
      values['aufnehmender'] == '[[:de:Wolfram Syré|Wolfram Syré]]')

# And the page built from the merged values still names both roles.
page = music.build_wikitext(values, '{{en|1=x}}')
check('the author line carries the selection composer',
      'composition: selected' in page)
check('and the whole-set performer', 'Wolfram Syré]]' in page)

print()
print('FAILURES:', ', '.join(fails) if fails else 'none')
sys.exit(1 if fails else 0)
