"""Merge rules for base description + per-file description (0.9.12).

Agreed rules:
  depicts        -> merged, deduplicated, order kept
  caption_XX     -> the file overrides the base
  creator / copyright / license / created_during -> the file overrides the base
  gallery_suffix -> base only, a per-file value is ignored
  free wikitext  -> base first, then the file
And: the Wikitext preview column and the upload path must produce the SAME text.
"""
import os
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QPixmap

import Cammello
from cammello.sdc import merge_descriptions, extract_structured_data
from cammello.logging_setup import setup_logging

app = QApplication(sys.argv)
logger, emitter, gui_handler, log_path = setup_logging()

fails = []


def check(name, cond, detail=''):
    print(('PASS' if cond else 'FAIL'), name, detail)
    if not cond:
        fails.append(name)


BASE = """caption_en=Festival 2026
caption_de=Festival 2026 (de)
creator=Q640
license=Q18199165
depicts=Q1
created_during=Q999
gallery_suffix=Bands
{{en|1=Base wikitext}}
[[Category:Base]]"""

FILE = """caption_en=Bauer on stage
depicts=Q2; Q1; Q3
creator=Q12345
gallery_suffix=Ignored
{{en|1=File wikitext}}
[[Category:File]]"""

merged, warns = merge_descriptions(BASE, FILE)
sd, rest = extract_structured_data(merged)
print('--- merged ---')
print(merged)
print('--- warnings ---')
for w in warns:
    print('  *', w)
print('---')

# depicts: merged, deduplicated, base order first
check('depicts merged and deduplicated', sd['depicts'] == 'Q1; Q2; Q3',
      sd['depicts'])

# captions: the file wins, base-only languages survive
check('caption_en: file overrides base', sd['caption_en'] == 'Bauer on stage',
      sd['caption_en'])
check('caption_de from the base survives',
      sd['caption_de'] == 'Festival 2026 (de)', sd['caption_de'])

# override keys: the file wins, and NOT merged (a "Q640;Q12345" would be an
# invalid QID for the single-value property P170).
check('creator: file overrides base, single value', sd['creator'] == 'Q12345',
      sd['creator'])
check('creator is not merged', ';' not in sd['creator'] and ',' not in sd['creator'])
check('license from the base survives', sd['license'] == 'Q18199165')
check('created_during from the base survives', sd['created_during'] == 'Q999')

# gallery_suffix: base only
check('gallery_suffix comes from the base', sd['gallery_suffix'] == 'Bands',
      sd['gallery_suffix'])
check('a per-file gallery_suffix is dropped', 'Ignored' not in merged)

# free wikitext: base first, then file; both categories kept
check('base wikitext kept', '{{en|1=Base wikitext}}' in rest)
check('file wikitext kept', '{{en|1=File wikitext}}' in rest)
check('base comes before the file',
      rest.index('Base wikitext') < rest.index('File wikitext'))
check('both categories kept',
      '[[Category:Base]]' in rest and '[[Category:File]]' in rest)

# warnings name what was overridden / dropped
joined = ' | '.join(warns)
check('warning about the ignored gallery_suffix', 'gallery_suffix' in joined)
check('warning about the overridden creator', 'creator' in joined)
check('warning about the overridden caption', 'caption_en' in joined)
check('no warning about depicts (merging is not an override)',
      'depicts' not in joined, joined)

# Empty inputs must not blow up.
check('empty base', merge_descriptions('', 'depicts=Q5')[0].strip() == 'depicts=Q5')
check('empty file', merge_descriptions('creator=Q640', '')[0].strip() == 'creator=Q640')
check('both empty', merge_descriptions('', '')[0] == '')


# ── The preview column and the upload path must agree ─────────────────────────
w = Cammello.MainWindow(logger, emitter, gui_handler, log_path)
tmp = tempfile.mkdtemp()
img = os.path.join(tmp, 'a.png')
QPixmap(600, 400).save(img)
w._add_paths([img])

w.creator_edit.setText('Q640')
w.copyright_sdc_edit.setText('Q73566113')
w.license_sdc_edit.setText('Q18199165')
w.base_text_edit.setPlainText('caption_en=Base caption\ndepicts=Q1\n{{en|1=Base}}')
w.table.item(0, w.COL_DESC).setText('caption_en=File caption\ndepicts=Q2\n{{en|1=File}}')
w._refresh_effective(0)

preview = w.table.item(0, w.COL_EFFECTIVE).text()
psd, _ = extract_structured_data(preview)

# The settings SDC must actually be in there - it never reached the upload
# before, because the worker's base_text argument was dead.
check('preview contains creator from the upload settings',
      psd.get('creator') == 'Q640', str(psd.get('creator')))
check('preview contains copyright', psd.get('copyright') == 'Q73566113')
check('preview contains license', psd.get('license') == 'Q18199165')
check('preview merges depicts', psd.get('depicts') == 'Q1; Q2',
      str(psd.get('depicts')))
check('preview caption: file wins', psd.get('caption_en') == 'File caption')

# What start_upload would build for that row.
per_file = w.table.item(0, w.COL_DESC).text()
upload_text, _ = w._effective_text(per_file, with_warnings=True)
check('upload text == preview text', upload_text == preview)

print('\nFAILURES:', fails if fails else 'none')
sys.exit(1 if fails else 0)
