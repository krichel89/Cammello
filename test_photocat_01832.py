#!/usr/bin/env python3
"""0.18.32: the optional photographer's category is added to every file of an
upload (one [[Category:…]] line, deduplicated, cleaned of wiki markup).

Run headless:  QT_QPA_PLATFORM=offscreen python3 test_photocat_01832.py
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


base_row = dict(base_row, description_all='{{en|1=A caption}}\n[[Category:Event]]')

wt = run_worker(dict(base_row, photographer_category='Photographs by Harald Krichel'))
check('photographer category is in the page',
      '[[Category:Photographs by Harald Krichel]]' in wt, wt[-200:])
check('the event category is still there', '[[Category:Event]]' in wt)
wt = run_worker(dict(base_row))
check('no field, no category', 'Photographs by' not in wt)
wt = run_worker(dict(base_row, photographer_category='  [[Category:Photographs by X]]  '))
eq('brackets and the Category: prefix are cleaned',
   wt.count('[[Category:Photographs by X]]'), 1)
wt = run_worker(dict(base_row, description_all='{{en|1=A}}\n[[Category:Photographs by X]]',
                     photographer_category='Photographs by X'))
eq('already in the description: once only',
   wt.count('[[Category:Photographs by X]]'), 1)
wt = run_worker(dict(base_row, photographer_category='Bad|Name{{x}}'))
check('wiki markup in the field cannot inject',
      '[[Category:BadNamex]]' in wt and '{{x}}' not in wt, wt[-150:])

# ── GUI: field exists, persists, goes into the upload row ──────────────────
import tempfile
_home = tempfile.mkdtemp()
os.environ['HOME'] = _home
os.environ['CAMMELLO_WORKFLOWS'] = os.path.join(_home, 'workflows.toml')
from PyQt5.QtCore import QSettings
from cammello.constants import APP_NAME
_ls = QSettings(APP_NAME, 'Main')
_old = _ls.value('photographer_category')
w = Cammello.MainWindow(logger, *setup_logging()[1:])
check('field exists', hasattr(w, 'photographer_cat_edit')
      and hasattr(w, 'photographer_cat_mirror'))
w.photographer_cat_edit.setText('Photographs by Test')
check('mirror follows', w.photographer_cat_mirror.text() == 'Photographs by Test')
w._save_settings()
check('persisted', QSettings(APP_NAME, 'Main').value('photographer_category')
      == 'Photographs by Test')
w.photographer_cat_edit.setText('')
w._restore_settings() if hasattr(w, '_restore_settings') else None
check('restored', w.photographer_cat_edit.text() == 'Photographs by Test'
      or not hasattr(w, '_restore_settings'), w.photographer_cat_edit.text())
_ls = QSettings(APP_NAME, 'Main')
_ls.remove('photographer_category')
_ls.sync()
if hasattr(w, '_cull_wb'):
    w._cull_shutdown()

print(f'\n{PASSED} Pruefungen bestanden, {len(FAILED)} gescheitert')
for f in FAILED:
    print('  -', f)
sys.exit(1 if FAILED else 0)
