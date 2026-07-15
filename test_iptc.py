"""IPTC module (0.10.0): roundtrip, mapping, FTP worker, and the guarantee
that the MediaWiki side survives a missing pyexiv2."""
import os
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QEventLoop, QTimer, QSettings
from cammello.constants import APP_NAME
from PyQt5.QtGui import QPixmap

import Cammello
from cammello import iptc
from cammello.ftp_workers import FtpUploadWorker
from cammello.logging_setup import setup_logging

app = QApplication(sys.argv)
logger, emitter, gui_handler, log_path = setup_logging()

import logging
for h in logger.handlers:
    if isinstance(h, logging.StreamHandler) and not hasattr(h, 'baseFilename'):
        h.setLevel(logging.CRITICAL)

fails = []


def check(name, cond, detail=''):
    print(('PASS' if cond else 'FAIL'), name, detail)
    if not cond:
        fails.append(name)


check('pyexiv2 available in the sandbox', iptc.available())

tmp = tempfile.mkdtemp()
src = os.path.join(tmp, 'source.jpg')
QPixmap(320, 200).save(src, 'JPG', 92)

# ── Roundtrip: write to a COPY, original untouched ────────────────────────────
data = {
    'caption': 'Bauer at Oh See Málaga 2026',
    'keywords': 'festival; Málaga; band',
    'byline': 'Harald Krichel',
    'city': 'Málaga',
    'date_created': '2026-05-23',
    'object_name': 'Bauer-1',
}
copy = os.path.join(tmp, 'export', 'Bauer-1.jpg')
written = iptc.write_iptc(src, data, target_path=copy)
check('write goes to the copy', written == copy and os.path.exists(copy))
check('original has no IPTC', iptc.read_iptc(src) == {})

back = iptc.read_iptc(copy)
check('caption roundtrip incl. umlauts',
      back.get('caption') == 'Bauer at Oh See Málaga 2026', str(back.get('caption')))
check('keywords roundtrip as ;-list',
      back.get('keywords') == 'festival; Málaga; band', str(back.get('keywords')))
check('date roundtrip', back.get('date_created') == '2026-05-23')

# Deleting: empty string removes the tag.
iptc.write_iptc(copy, {'city': ''})
check('empty value deletes the tag', 'city' not in iptc.read_iptc(copy))
check('other tags survive the delete',
      iptc.read_iptc(copy).get('byline') == 'Harald Krichel')

# In-place write.
written2 = iptc.write_iptc(src, {'caption': 'in place'})
check('in-place write returns the original path', written2 == src)
check('in-place write lands', iptc.read_iptc(src).get('caption') == 'in place')

# ── MW -> IPTC mapping ────────────────────────────────────────────────────────
MERGED = """caption_de=Bauer auf der Bühne
caption_en=Bauer on stage
creator=Q640
depicts=Q1; Q2
{{en|1=Some wikitext}}
[[Category:Oh See Málaga Festival 2026]]
[[Category:Bands|Sortkey]]
[[Category:Uploaded with Cammello]]"""

m = iptc.mw_to_iptc(MERGED, author='Pedro J Pacheco', date='2026-05-23 17:41:31',
                    target_filename='Oh See 2026 - Bauer -1.jpg')
check('caption prefers de', m.get('caption') == 'Bauer auf der Bühne')
check('keywords from categories, maintenance dropped, sortkey stripped',
      m.get('keywords') == 'Oh See Málaga Festival 2026; Bands',
      str(m.get('keywords')))
check('byline from author', m.get('byline') == 'Pedro J Pacheco')
check('date_created = date prefix', m.get('date_created') == '2026-05-23')
check('object_name without extension',
      m.get('object_name') == 'Oh See 2026 - Bauer -1')
check('QIDs are not mapped anywhere',
      all('Q640' not in v and 'Q1' not in v for v in m.values()), str(m))

m2 = iptc.mw_to_iptc('caption_fr=Seulement français', caption_langs=('de', 'en'))
check('fallback to any caption language', m2.get('caption') == 'Seulement français')

check('IPTC -> caption line',
      iptc.iptc_to_caption_line({'caption': 'Hello'}, 'en') == 'caption_en=Hello')
check('empty caption -> no line',
      iptc.iptc_to_caption_line({}, 'en') == '')

# ── FTP worker against a fake client (no network) ─────────────────────────────
class FakeClient:
    instances = []

    def __init__(self, fail_on=None):
        self.sent, self.dir, self.closed = [], None, False
        self.fail_on = fail_on or set()
        FakeClient.instances.append(self)

    def chdir(self, d): self.dir = d
    def put(self, local, remote):
        if remote in self.fail_on:
            raise IOError('disk full')
        self.sent.append(remote)
    def close(self): self.closed = True


files = [(copy, 'Bauer-1.jpg'), (src, 'source.jpg')]
fc = {}
w = FtpUploadWorker('ftp', 'example.invalid', '', 'u', 'pw', '/upload',
                    files, logger,
                    client_factory=lambda *a: fc.setdefault('c', FakeClient()))
summary = {}
loop = QEventLoop()
w.finished.connect(lambda s: (summary.update(s=s), loop.quit()))
QTimer.singleShot(15000, loop.quit)
w.start(); loop.exec_(); w.wait(3000)
c = fc['c']
check('both files sent', c.sent == ['Bauer-1.jpg', 'source.jpg'], str(c.sent))
check('remote dir was set', c.dir == '/upload')
check('client closed', c.closed)
check('summary says 2/2', summary.get('s') == 'Done: 2/2 file(s) sent.',
      summary.get('s', ''))

# One file fails -> the run continues, the summary is honest.
fc2 = {}
w2 = FtpUploadWorker('ftp', 'example.invalid', '', 'u', 'pw', '',
                     files, logger,
                     client_factory=lambda *a: fc2.setdefault(
                         'c', FakeClient(fail_on={'Bauer-1.jpg'})))
summary2 = {}
loop2 = QEventLoop()
w2.finished.connect(lambda s: (summary2.update(s=s), loop2.quit()))
QTimer.singleShot(15000, loop2.quit)
w2.start(); loop2.exec_(); w2.wait(3000)
check('failure of one file does not stop the run',
      fc2['c'].sent == ['source.jpg'], str(fc2['c'].sent))
check('summary counts 1/2', summary2.get('s') == 'Done: 1/2 file(s) sent.',
      summary2.get('s', ''))

# Connection failure -> global error, clean summary.
def boom(*a):
    raise ConnectionError('no route')
w3 = FtpUploadWorker('sftp', 'example.invalid', '', 'u', 'pw', '', files,
                     logger, client_factory=boom)
summary3, errors3 = {}, []
loop3 = QEventLoop()
w3.error.connect(lambda i, m: errors3.append((i, m)))
w3.finished.connect(lambda s: (summary3.update(s=s), loop3.quit()))
QTimer.singleShot(15000, loop3.quit)
w3.start(); loop3.exec_(); w3.wait(3000)
check('connection failure -> global error (-1)',
      errors3 and errors3[0][0] == -1, str(errors3))
check('connection failure summary',
      summary3.get('s', '').startswith('Failed'), summary3.get('s', ''))

# ── The MediaWiki side must survive a missing pyexiv2 ─────────────────────────
_saved = iptc.pyexiv2
iptc.pyexiv2 = None
try:
    check('available() reports False', not iptc.available())
    w4 = Cammello.MainWindow(logger, emitter, gui_handler, log_path)
    tabs = [w4.tabs.tabText(i) for i in range(w4.tabs.count())]
    check('no IPTC tab without pyexiv2', 'IPTC' not in tabs, str(tabs))
    check('no Culling tab without pyexiv2', 'Culling' not in tabs, str(tabs))
    check('no FTP tab without pyexiv2', 'FTP' not in tabs, str(tabs))
    check('Settings tab exists even without pyexiv2 (MW settings live '
          'there)', 'Settings' in tabs, str(tabs))
    check('MediaWiki and Log tabs still there',
          'MediaWiki' in tabs and 'Log' in tabs, str(tabs))
    img = os.path.join(tmp, 'x.png')
    QPixmap(50, 50).save(img)
    w4._add_paths([img])
    check('file table still works', w4.table.rowCount() == 1)
finally:
    iptc.pyexiv2 = _saved

# With pyexiv2 AND the feature switch on, the tab is there and the list
# follows the table (release default is OFF, so the test opts in).
_s5 = QSettings(APP_NAME, 'Main')
_saved_feat = {k: _s5.value(k) for k in
               ('feature_iptc', 'feature_culling', 'feature_ftp',
                'feature_flickr')}
for _k in _saved_feat:
    _s5.setValue(_k, True)
_s5.sync()
w5 = Cammello.MainWindow(logger, emitter, gui_handler, log_path)
tabs5 = [w5.tabs.tabText(i) for i in range(w5.tabs.count())]
check('IPTC tab present with pyexiv2',
      tabs5 == ['Culling', 'MediaWiki', 'IPTC', 'FTP / Flickr', 'Settings',
                'Log', 'About'],
      str(tabs5))
w5._add_paths([src])
w5.tabs.setCurrentWidget(w5._iptc_tab_widget)
check('IPTC list mirrors the file table', w5.iptc_list.count() == 1)
check('selecting a file reads its IPTC',
      w5._iptc_edits['caption'].text() == 'in place',
      w5._iptc_edits['caption'].text())

print('\nFAILURES:', fails if fails else 'none')
sys.exit(1 if fails else 0)

# restore feature switches touched above
for _k, _v in _saved_feat.items():
    (_s5.remove(_k) if _v is None else _s5.setValue(_k, _v))
_s5.sync()
