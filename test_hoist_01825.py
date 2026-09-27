#!/usr/bin/env python3
"""0.18.25: only language templates {{xx|1=…}} belong in the Information
|description=; standalone page templates ({{Do not crop}}, {{WikiPortraits
…}}) are hoisted out and placed after the {{Information}} block.

Run headless:  QT_QPA_PLATFORM=offscreen python3 test_hoist_01825.py
"""
import os
import re
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer, QEventLoop

app = QApplication.instance() or QApplication([])

import Cammello                                            # noqa: E402,F401
from cammello import sdc                                   # noqa: E402
from cammello.workers import UploadWorker                  # noqa: E402
from cammello.logging_setup import setup_logging           # noqa: E402

logger = setup_logging()[0]
import logging as _logging                                 # noqa: E402
for _h in logger.handlers:
    if isinstance(_h, _logging.StreamHandler) and not hasattr(_h,
                                                              'baseFilename'):
        _h.setLevel(_logging.CRITICAL)

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


# ── 1. the pure splitter ────────────────────────────────────────────────────
desc, hoist = sdc.hoist_nonlang_templates(
    '{{WikiPortraits Dragon Con 2026}}{{Do not crop}}\n'
    '{{en|1=X-Men 97 panel at Dragon Con}}')
eq('the language template stays in the description', desc,
   '{{en|1=X-Men 97 panel at Dragon Con}}')
eq('both page templates are hoisted, in order', hoist,
   ['{{WikiPortraits Dragon Con 2026}}', '{{Do not crop}}'])

desc2, hoist2 = sdc.hoist_nonlang_templates(
    '{{WikiPortraits Dragon Con 2026}}{{Do not crop}}\n{{en|1=hi}}\n\n'
    '{{WikiPortraits Dragon Con 2026}}{{Do not crop}}')
eq('a template entered twice is hoisted once', hoist2,
   ['{{WikiPortraits Dragon Con 2026}}', '{{Do not crop}}'])
eq('and the description keeps only the language template', desc2, '{{en|1=hi}}')

d3, h3 = sdc.hoist_nonlang_templates('{{de|1=Foto von {{w|Berlin}}}}\n'
                                     '{{Do not crop}}')
eq('a nested template inside {{de|1=…}} is not hoisted', d3,
   '{{de|1=Foto von {{w|Berlin}}}}')
eq('only the standalone one is hoisted', h3, ['{{Do not crop}}'])

d4, h4 = sdc.hoist_nonlang_templates(
    'A nice photo [[:de:Berlin|Berlin]]\n{{Do not crop}}')
eq('prose and interwiki links stay', d4, 'A nice photo [[:de:Berlin|Berlin]]')
d5, h5 = sdc.hoist_nonlang_templates('{{en|1=hello}}\n{{de|1=hallo}}')
eq('several language templates all stay', d5, '{{en|1=hello}}\n{{de|1=hallo}}')
eq('and nothing is hoisted', h5, [])
plain = 'caption stays\n{{fr|1=une photo}}'
eq('a description with no page template is returned unchanged',
   sdc.hoist_nonlang_templates(plain), (plain, []))

d6, h6 = sdc.hoist_nonlang_templates('{{de}}\n{{en|1=x}}')
eq('a language code without a parameter is hoisted', h6, ['{{de}}'])


# ── 2. the worker puts the pieces where Harald wants them ────────────────────
class FakeApi:
    log = logger
    timeout = 5

    def __init__(self):
        self.wikitext = {}

    def upload(self, filename, filepath, wikitext, comment,
               ignore_warnings=False):
        self.wikitext[filename] = wikitext

    def clear_token(self):
        pass

    def get_page_id(self, filename):
        return None

    def update_gallery(self, page, entries):
        pass


def run_worker(row):
    api = FakeApi()
    w = UploadWorker(api, [row], '', False)
    loop = QEventLoop()
    w.finished.connect(lambda _s: loop.quit())
    QTimer.singleShot(15000, loop.quit)
    w.start()
    loop.exec_()
    w.wait(3000)
    return api.wikitext.get(row['target_name'], '')


def description_param(wikitext):
    m = re.search(r'\|description=(.*?)\n\|', wikitext, re.DOTALL)
    return m.group(1) if m else '<none>'


base_row = {
    'filepath': '/tmp/x.jpg', 'target_name': 'X.jpg', 'source_name': 'x.jpg',
    'date': '2026-09-05', 'author': '[[User:npgeek73|John]]',
    'source': '{{own}}', 'permission': '', 'license_text': '{{Cc-by-sa-4.0}}',
    'other_templates': '', 'other_fields': '', 'template': 'Information',
    'description_all':
        'created_during=Q141575502\n'
        '{{WikiPortraits Dragon Con 2026}}{{Do not crop}}\n'
        '{{en|1=X-Men 97 panel at Dragon Con}}\n'
        '[[Category:Dragon Con]]',
}

wt = run_worker(dict(base_row))
dp = description_param(wt)
check('the language template is in |description=', '{{en|1=' in dp, dp)
check('the page templates are NOT in |description=',
      'WikiPortraits' not in dp and 'Do not crop' not in dp, dp)
check('the page templates are in the page at all',
      '{{WikiPortraits Dragon Con 2026}}' in wt and '{{Do not crop}}' in wt)
check('the hoisted templates sit AFTER the Information block',
      wt.index('{{WikiPortraits Dragon Con 2026}}') > wt.index('|source='),
      'templates landed before the source line')
check('and before the licence header',
      wt.index('{{Do not crop}}') < wt.index('{{int:license-header}}'))
check('the category is still collected', '[[Category:Dragon Con]]' in wt)

row2 = dict(base_row, other_templates='{{WikiPortraits Dragon Con 2026}}')
wt2 = run_worker(row2)
eq('a template in both the global slot and the description appears once',
   wt2.count('{{WikiPortraits Dragon Con 2026}}'), 1)
check('the second page template is still present once',
      wt2.count('{{Do not crop}}') == 1, str(wt2.count('{{Do not crop}}')))

row3 = dict(base_row, other_templates='',
            description_all='{{en|1=just a caption}}\n[[Category:Test]]')
wt3 = run_worker(row3)
check('a clean description still lands in |description=',
      '{{en|1=just a caption}}' in description_param(wt3))
check('and nothing is hoisted when there is no page template',
      wt3.count('{{en|1=just a caption}}') == 1)

print(f'\n{PASSED} Pruefungen bestanden, {len(FAILED)} gescheitert')
for f in FAILED:
    print('  -', f)
sys.exit(1 if FAILED else 0)
