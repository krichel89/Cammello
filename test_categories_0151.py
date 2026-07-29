"""Content vs. meta categories, and the per-file red dots (0.15.1)."""
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtWidgets import QApplication, QTableWidgetItem

import Cammello
from cammello import categories
from cammello.logging_setup import setup_logging

app = QApplication(sys.argv)
logger, emitter, gui_handler, log_path = setup_logging()
w = Cammello.MainWindow(logger, emitter, gui_handler, log_path)

fails = []


def check(name, cond, detail=''):
    if cond:
        print('PASS', name, detail)
    else:
        print('FAIL', name, detail)
        fails.append(name)


# ── the pattern list ─────────────────────────────────────────────────────────
check('the pattern file is found and read', categories.count_patterns() > 5,
      f'{categories.count_patterns()} patterns')
check('no read error', categories.LAST_ERROR is None,
      str(categories.LAST_ERROR))

# ── Harald's own examples ────────────────────────────────────────────────────
check('"Photographs by …" is meta',
      categories.is_meta('Photographs by Harald Krichel'))
check('"WikiPortraits …" is meta',
      categories.is_meta('WikiPortraits at Berlinale 2026'))
check('our own tracking category is meta',
      categories.is_meta('Uploaded with Cammello'))
check('a maintenance bucket is meta',
      categories.is_meta('Media needing categories as of 2026'))
check('a real subject is NOT meta', not categories.is_meta('Brandenburg Gate'))
check('an event category is NOT meta',
      not categories.is_meta('Berlinale 2026'))

# ── matching details ─────────────────────────────────────────────────────────
check('the Category: prefix is ignored',
      categories.is_meta('Category:Photographs by Someone'))
check('matching is case-insensitive',
      categories.is_meta('photographs by someone'))
check('an empty name is not meta', not categories.is_meta('   '))

content, meta = categories.split(
    ['Photographs by X', 'Brandenburg Gate', 'Uploaded with Cammello'])
check('splitting keeps the subject on the content side',
      content == ['Brandenburg Gate'], str(content))
check('and everything else on the meta side', len(meta) == 2)

check('meta alone does not count as categorised',
      not categories.has_content_category(
          ['Photographs by X', 'Uploaded with Cammello']))
check('one subject is enough',
      categories.has_content_category(['Photographs by X', 'Cathedral']))

check('the field is split on semicolons',
      categories.parse_field('Berlinale 2026; Portraits ; ')
      == ['Berlinale 2026', 'Portraits'])

# ── the dots in the window ───────────────────────────────────────────────────
struct = w.file_struct
check('the file group is remembered', hasattr(w, '_file_group'))
check('the captions editor can show the marker',
      hasattr(struct.captions_editor, 'set_attention'))

w.table.setRowCount(1)
w.table.setItem(0, w.COL_FILENAME, QTableWidgetItem('a.jpg'))
w.table.selectRow(0)

struct.categories.setText('Photographs by Harald Krichel')
if struct.depicts is not None:
    struct.depicts.setText('')
w._refresh_file_marks()
lbl = w._label_for(struct, struct.categories)
check('meta-only categories raise the dot',
      lbl is not None and lbl.text().startswith('●'),
      lbl.text() if lbl else 'no label')
check('the group heading follows', w._file_group.attention())
check('the caption marker is visible',
      not struct.captions_editor._attention_label.isHidden())

struct.categories.setText('Photographs by Harald Krichel; Brandenburg Gate')
w._refresh_file_marks()
check('adding a subject clears the category dot',
      lbl is not None and not lbl.text().startswith('●'), lbl.text())

if struct.depicts is not None:
    dep_lbl = w._label_for(struct, struct.depicts)
    check('an empty depicts is marked',
          dep_lbl is not None and dep_lbl.text().startswith('●'),
          dep_lbl.text() if dep_lbl else 'no label')
    struct.depicts.setText('Q64')
    w._refresh_file_marks()
    check('a filled depicts is not',
          dep_lbl is not None and not dep_lbl.text().startswith('●'))

w.table.clearSelection()
w._refresh_file_marks()
check('with nothing selected nothing is marked',
      not w._file_group.attention()
      and struct.captions_editor._attention_label.isHidden())

# ── version ──────────────────────────────────────────────────────────────────
from cammello.constants import __version__
# Not pinned to a number - this file outlives the version it was born in.
# What must hold is that the three places AGREE.
root = os.path.dirname(os.path.dirname(categories.__file__))
rel = open(os.path.join(root, 'release.sh'), encoding='utf-8').read()
check('release.sh carries the current version',
      f'VERSION="{__version__}"' in rel, __version__)
_notes = 'notes_' + __version__.replace('.', '') + '.md'
check('and points at the matching notes',
      f'NOTES_FILE="{_notes}"' in rel, _notes)
check('the notes exist', os.path.exists(os.path.join(root, _notes)))

print()
print('FAILURES:', ', '.join(fails) if fails else 'none')
sys.exit(1 if fails else 0)
