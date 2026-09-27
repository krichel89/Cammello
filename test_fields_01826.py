#!/usr/bin/env python3
"""0.18.26: the four points from Harald's list.

  1. Ctrl/Cmd-click selects and deselects single files (grid and filmstrip).
  2. The selection frame is clearly visible (accent blue, contrast checked).
  3. Templates in the wrong field are caught before the upload.
  4. The heading "== {{int:filedesc}} ==" always sits right - above
     {{Information}}, exactly once, typed copies removed.

Run headless:  QT_QPA_PLATFORM=offscreen python3 test_fields_01826.py
"""
import os
import re
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication, QTableWidgetItem
from PyQt5.QtCore import Qt, QTimer, QEventLoop, QSettings
from PyQt5.QtGui import QImage, QColor
from PyQt5.QtTest import QTest

app = QApplication.instance() or QApplication([])

import Cammello                                            # noqa: E402
from cammello import sdc                                   # noqa: E402
from cammello.constants import APP_NAME, cull_bg           # noqa: E402
from cammello.workers import UploadWorker                  # noqa: E402
from cammello.logging_setup import setup_logging           # noqa: E402

logger, emitter, gui_handler, log_path = setup_logging()
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


def spin(ms=80):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec_()


# ── 4a. strip_section_headings ──────────────────────────────────────────────
eq('text without a heading is returned unchanged',
   sdc.strip_section_headings('{{en|1=x}}\n[[Category:A]]'),
   ('{{en|1=x}}\n[[Category:A]]', 0))
t, n = sdc.strip_section_headings(
    '== {{int:filedesc}} ==\n{{en|1=x}}\n=={{int:license-header}}==\n{{Cc0}}')
eq('both typed headings are removed', (t, n), ('{{en|1=x}}\n{{Cc0}}', 2))
t, n = sdc.strip_section_headings('  ===  {{ Int:FileDesc }}  ===  \nabc')
eq('spacing, case and heading level do not matter', (t, n), ('abc', 1))
t, n = sdc.strip_section_headings('see == {{int:filedesc}} == inline')
eq('a heading inside a line of prose is not a heading', n, 0)


# ── 4b. the worker writes exactly one heading, above {{Information}} ────────
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


base_row = {
    'filepath': '/tmp/x.jpg', 'target_name': 'X.jpg', 'source_name': 'x.jpg',
    'date': '2026-09-05', 'author': '[[User:Seewolf|Harald Krichel]]',
    'source': '{{own}}', 'permission': '', 'license_text': '{{Cc-by-sa-4.0}}',
    'other_templates': '', 'other_fields': '', 'template': 'Information',
    'description_all': '{{en|1=A photo}}\n[[Category:Test]]',
}
wt = run_worker(dict(base_row))
check('the page starts with the filedesc heading',
      wt.startswith('== {{int:filedesc}} ==\n{{Information\n'), wt[:60])
eq('exactly one filedesc heading', wt.count('{{int:filedesc}}'), 1)
eq('exactly one licence heading', wt.count('{{int:license-header}}'), 1)
check('filedesc comes before the licence heading',
      wt.index('{{int:filedesc}}') < wt.index('{{int:license-header}}'))

typed = dict(base_row,
             description_all='== {{int:filedesc}} ==\n{{en|1=A photo}}\n'
                             '[[Category:Test]]',
             license_text='== {{int:license-header}} ==\n{{Cc-by-sa-4.0}}',
             other_templates='=={{int:filedesc}}==\n{{Do not crop}}')
wt2 = run_worker(typed)
eq('typed filedesc headings do not double it', wt2.count('{{int:filedesc}}'), 1)
eq('a typed licence heading does not double it',
   wt2.count('{{int:license-header}}'), 1)
m = re.search(r'\|description=(.*?)\n\|', wt2, re.DOTALL)
check('no heading inside |description=',
      m is not None and '==' not in m.group(1), m.group(1) if m else wt2)
check('the page still starts with Cammello\'s heading',
      wt2.startswith('== {{int:filedesc}} ==\n{{Information\n'), wt2[:60])
check('Do not crop still after the box', '}}\n{{Do not crop}}' in wt2, wt2)


# ── 3a. misplaced_template_problems (Qt-free rules) ─────────────────────────
F = sdc
clean = {F.FIELD_AUTHOR: '[[User:Seewolf|Harald Krichel]]',
         F.FIELD_SOURCE: '{{own}}', F.FIELD_PERMISSION: '',
         F.FIELD_LICENSE: '{{Cc-by-sa-4.0}}',
         F.FIELD_OTHER_FIELDS: '{{Credit line|Author=H|Other=WikiPortraits}}',
         F.FIELD_OTHER_TEMPLATES: '{{WikiPortraits at Berlinale 2026}}'}
eq('Haralds normal setup triggers nothing',
   sdc.misplaced_template_problems(clean,
                                   [('a.jpg', '{{en|1=x}}\ncaption_de=Harald '
                                     'Krichel bei der Berlinale')]), [])


def advices(fields, descs=()):
    return [(p[1], p[3]) for p in
            sdc.misplaced_template_problems(dict(clean, **fields), descs)]


eq('licence template in Other templates',
   advices({F.FIELD_OTHER_TEMPLATES: '{{Cc-by-4.0}}'}),
   [(F.FIELD_OTHER_TEMPLATES, F.ADVICE_LICENSE)])
eq('self|… in the source field counts as licence',
   advices({F.FIELD_SOURCE: '{{own}} {{self|cc-by-sa-4.0}}'}),
   [(F.FIELD_SOURCE, F.ADVICE_LICENSE)])
eq('Do not crop inside |author=',
   advices({F.FIELD_AUTHOR: 'Harald {{Do not crop}}'}),
   [(F.FIELD_AUTHOR, F.ADVICE_PAGE)])
eq('WikiPortraits template in Other fields',
   advices({F.FIELD_OTHER_FIELDS: '{{WikiPortraits at Berlinale 2026}}'}),
   [(F.FIELD_OTHER_FIELDS, F.ADVICE_PAGE)])
eq('category in the permission field',
   advices({F.FIELD_PERMISSION: '[[Category:Foo]]'}),
   [(F.FIELD_PERMISSION, F.ADVICE_CATEGORY)])
eq('a category in Other templates is fine (lands after the box)',
   advices({F.FIELD_OTHER_TEMPLATES: '[[Category:Foo]]'}), [])
eq('a language template in Other templates',
   advices({F.FIELD_OTHER_TEMPLATES: '{{de|1=Ein Foto}}'}),
   [(F.FIELD_OTHER_TEMPLATES, F.ADVICE_LANG)])
eq('a Creator template in author is legitimate',
   advices({F.FIELD_AUTHOR: '{{Creator:Harald Krichel}}'}), [])
eq('a template in a caption',
   advices({}, [('a.jpg', 'caption_en={{w|Tom Tykwer}} at the Berlinale')]),
   [('Caption (en)', F.ADVICE_CAPTION)])
eq('a link in a caption',
   advices({}, [('a.jpg', 'caption_de=[[Tom Tykwer]] bei der Berlinale')]),
   [('Caption (de)', F.ADVICE_CAPTION)])
eq('a licence template in the description',
   advices({}, [('a.jpg', '{{en|1=x}}\n{{Cc-by-sa-4.0}}')]),
   [(F.FIELD_DESCRIPTION, F.ADVICE_LICENSE)])
probs = sdc.misplaced_template_problems(
    dict(clean), [('a.jpg', 'caption_en={{x}}'), ('b.jpg', 'caption_en={{x}}')])
eq('the row label is carried, per file', [p[0] for p in probs],
   ['a.jpg', 'b.jpg'])
probs = sdc.misplaced_template_problems(
    dict(clean, **{F.FIELD_AUTHOR: '{{Do not crop}} {{Do not crop}}'}))
eq('the same snippet in one field is reported once', len(probs), 1)


# ── 3b. the upload stops and asks ───────────────────────────────────────────
w = Cammello.MainWindow(logger, emitter, gui_handler, log_path)
w.api = FakeApi()
tmpd = tempfile.mkdtemp()
img = os.path.join(tmpd, 'IMG_1.jpg')
QImage(40, 30, QImage.Format_RGB32).save(img, 'JPG')
w._add_paths([img])
spin(200)
check('one row in the file table', w.table.rowCount() == 1,
      str(w.table.rowCount()))
# Satisfy depicts so only the new check can stop the upload.
desc_item = w.table.item(0, w.COL_DESC)
if desc_item is None:
    desc_item = QTableWidgetItem('')
    w.table.setItem(0, w.COL_DESC, desc_item)
desc_item.setText('depicts_override=no_item\n{{en|1=x}}')
w.other_templates_edit.setText('{{Cc-by-4.0}}')

asked = []
launched = []
w._confirm_misplaced = lambda probs: (asked.append(probs), False)[1]
w._launch_upload_worker = lambda rows, journal, resumed=False: \
    launched.append(rows)
w.start_upload()
check('the check asked the user', len(asked) == 1, str(asked))
check('and the finding names the field',
      asked and asked[0][0][1] == sdc.FIELD_OTHER_TEMPLATES, str(asked))
check('"Fix first" stops the upload', launched == [], str(len(launched)))
msg = w._misplaced_message(asked[0]) if asked else ''
check('the message shows snippet and advice',
      '{{Cc-by-4.0}}' in msg and 'License' in msg, msg)

w._confirm_misplaced = lambda probs: True
w.start_upload()
check('"Upload anyway" goes ahead', len(launched) == 1, str(len(launched)))

w.other_templates_edit.setText('{{WikiPortraits at Berlinale 2026}}')
asked.clear()
launched.clear()
w._confirm_misplaced = lambda probs: (asked.append(probs), False)[1]
w.start_upload()
check('clean fields: no question at all', asked == [], str(asked))
check('clean fields: the upload starts', len(launched) == 1)


# ── 2. the selection frame ──────────────────────────────────────────────────
d = w._cull_delegate


def contrast(a, b):
    def lum(c):
        vals = []
        for v in (c.redF(), c.greenF(), c.blueF()):
            vals.append(v / 12.92 if v <= 0.03928
                        else ((v + 0.055) / 1.055) ** 2.4)
        return 0.2126 * vals[0] + 0.7152 * vals[1] + 0.0722 * vals[2]
    la, lb = lum(a) + 0.05, lum(b) + 0.05
    return max(la, lb) / min(la, lb)


old_gray = QColor('#8a8a8a')
for dark in (True, False):
    bg = QColor(cull_bg(dark))
    d.set_dark(dark)
    sel = d.sel_frame
    scheme = 'dark' if dark else 'light'
    check(f'{scheme}: the selection frame is blue, not gray any more',
          200 <= sel.hsvHue() <= 225 and sel.hsvSaturation() >= 80,
          f'{sel.name()} h={sel.hsvHue()} s={sel.hsvSaturation()}')
    check(f'{scheme}: frame stands out against the surround (>= 3:1)',
          contrast(sel, bg) >= 3.0, f'{contrast(sel, bg):.2f}')
    check(f'{scheme}: and clearly more than the old gray did',
          contrast(sel, bg) > 2 * contrast(old_gray, bg),
          f'{contrast(sel, bg):.2f} vs {contrast(old_gray, bg):.2f}')
    check(f'{scheme}: frame differs from the current-image frame',
          sel.name() != d.frame_color.name())


# ── 1. Ctrl/Cmd-click selects and deselects single files ────────────────────
_ts = QSettings(APP_NAME, 'Main')
_ts.setValue('feature_culling', True)
_ts.sync()
card = os.path.join(tmpd, 'card')
os.makedirs(card)
for i in range(5):
    im = QImage(200, 120, QImage.Format_RGB32)
    im.fill(0xFF224466 + i * 16)
    im.save(os.path.join(card, f'IMG_{i:04d}.JPG'), 'JPG', 80)
w.tabs.setCurrentWidget(w._cull_tab_widget)
w._cull_open_folder(card)
for _ in range(40):
    spin(50)
    if w._cull_reader is not None and w._cull_reader.isFinished():
        break
strip = w.cull_strip
check('five thumbnails', strip.count() == 5, str(strip.count()))
w.show()
spin(150)


def click(row, mods=Qt.NoModifier):
    rect = strip.visualItemRect(strip.item(row))
    QTest.mouseClick(strip.viewport(), Qt.LeftButton, mods, rect.center())
    spin(40)


def selected():
    return sorted(strip.row(it) for it in strip.selectedItems())


for grid in (False, True):
    view = 'grid' if grid else 'filmstrip'
    if w._cull_grid != grid:
        w._cull_set_grid(grid)
        spin(150)
    eq(f'{view}: the view is really switched', w._cull_grid, grid)
    strip.clearSelection()
    click(0)
    eq(f'{view}: plain click selects one', selected(), [0])
    click(2, Qt.ControlModifier)
    click(4, Qt.ControlModifier)
    eq(f'{view}: Ctrl/Cmd-click adds single files', selected(), [0, 2, 4])
    click(2, Qt.ControlModifier)
    eq(f'{view}: Ctrl/Cmd-click on a selected file removes it',
       selected(), [0, 4])
    click(1)
    eq(f'{view}: plain click starts over', selected(), [1])

w.hide()
w.close()

print(f'\n{PASSED} Pruefungen bestanden, {len(FAILED)} gescheitert')
for f in FAILED:
    print('  -', f)
sys.exit(1 if FAILED else 0)
