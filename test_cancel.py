"""Progress dialog + cancel (0.9.11).

The cancel path is tested against a fake API so nothing touches the network:
the worker's upload() blocks briefly per file, cancel() is called after the
first one, and the run must stop without starting the remaining files.
"""
import os
import sys
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QEventLoop, QTimer

from cammello.widgets import UploadProgressDialog
from cammello.workers import UploadWorker
from cammello.logging_setup import setup_logging

app = QApplication(sys.argv)
logger, emitter, gui_handler, log_path = setup_logging()

fails = []


def check(name, cond, detail=''):
    print(('PASS' if cond else 'FAIL'), name, detail)
    if not cond:
        fails.append(name)


# ── Dialog ────────────────────────────────────────────────────────────────────
dlg = UploadProgressDialog(4)
check('dialog starts at 0', dlg.bar.value() == 0 and dlg.bar.maximum() == 4)
dlg.set_current(2, 'Berlinale 2026 - Foo.jpg')
check('headline counts 1-based', '3 of 4' in dlg.headline.text(),
      dlg.headline.text())
check('detail shows the filename',
      dlg.detail.text() == 'Berlinale 2026 - Foo.jpg')
dlg.set_done(2)
check('bar follows finished files', dlg.bar.value() == 2)

got = []
dlg.cancel_requested.connect(lambda: got.append(True))
dlg.cancel_btn.click()
check('cancel emits once', got == [True])
check('cancel button disables itself', not dlg.cancel_btn.isEnabled())
dlg.cancel_btn.click()
check('second click does not re-emit', got == [True])
# Esc routes into the cancel path instead of closing the window behind the
# running upload. The dialog stays open; it is closed by on_finished.
dlg2 = UploadProgressDialog(2)
esc = []
dlg2.cancel_requested.connect(lambda: esc.append(True))
dlg2.show()
dlg2.reject()
check('Esc triggers cancel, not a silent close', esc == [True])
check('Esc leaves the dialog open', dlg2.isVisible())
# 0.9.11 bug: close() went through closeEvent -> reject() -> cancel, so the
# window stayed on screen after the run had finished. Only force_close() closes.
dlg2.close()
check('close() alone does not close it either', dlg2.isVisible())
dlg2.force_close()
check('force_close() actually closes the window', not dlg2.isVisible())

# set_current must not overwrite the "cancelling" message.
before = dlg.detail.text()
dlg.set_current(3, 'Other.jpg')
check('cancelling message survives set_current', dlg.detail.text() == before)


# ── Worker cancel ─────────────────────────────────────────────────────────────
class FakeApi:
    log = logger
    timeout = 5

    def __init__(self):
        self.uploaded = []

    def upload(self, filename, filepath, wikitext, comment, ignore_warnings=False):
        self.uploaded.append(filename)
        time.sleep(0.25)          # long enough for cancel() to land

    def clear_token(self):
        pass

    def get_page_id(self, filename):
        return None               # skips SDC, keeps the fake small

    def update_gallery(self, page, entries):
        pass


rows = [{'filepath': f'/tmp/f{i}.jpg', 'target_name': f'F{i}.jpg',
         'source_name': f'f{i}.jpg', 'date': '', 'description_all': '',
         'author': '', 'source': '', 'permission': '', 'license_text': '',
         'other_templates': '', 'other_fields': '', 'template': 'Information'}
        for i in range(5)]

api = FakeApi()
w = UploadWorker(api, rows, '', False)
started = []
summary = {}
loop = QEventLoop()
w.file_started.connect(lambda i, n: started.append(n))
w.finished.connect(lambda s: (summary.update(s=s), loop.quit()))
# Cancel shortly after the run begins: file 1 is in flight, the rest must not start.
QTimer.singleShot(100, w.cancel)
QTimer.singleShot(15000, loop.quit)
w.start()
loop.exec_()
w.wait(3000)

print('   started:', started, '| uploaded:', api.uploaded)
print('   summary:', summary.get('s'))
check('the file in flight was finished, not torn down',
      len(api.uploaded) >= 1)
check('the run stopped early', len(api.uploaded) < 5,
      f'{len(api.uploaded)} of 5 uploaded')
check('summary reports the cancel',
      summary.get('s', '').startswith('Cancelled'), summary.get('s', ''))
check('summary counts the files not started',
      'not started' in summary.get('s', ''))

# Without a cancel, all files go up and the summary says Done.
api2 = FakeApi()
w2 = UploadWorker(api2, rows[:2], '', False)
summary2 = {}
loop2 = QEventLoop()
w2.finished.connect(lambda s: (summary2.update(s=s), loop2.quit()))
QTimer.singleShot(15000, loop2.quit)
w2.start()
loop2.exec_()
w2.wait(3000)
check('uncancelled run uploads everything', len(api2.uploaded) == 2)
check('uncancelled summary says Done',
      summary2.get('s', '').startswith('Done'), summary2.get('s', ''))


# ── Upload succeeded, post-processing (SDC) failed ────────────────────────────
# The file is on Commons; it must NOT be reported as "0/1 uploaded".
class SdcBrokenApi(FakeApi):
    def get_page_id(self, filename):
        raise RuntimeError('boom: no page id')


rows_sdc = [dict(rows[0], description_all='caption_en=Test\ndepicts=Q640')]
api3 = SdcBrokenApi()
w3 = UploadWorker(api3, rows_sdc, '', False)
summary3, statuses, errors = {}, [], []
loop3 = QEventLoop()
w3.progress.connect(lambda i, st: statuses.append(st))
w3.error.connect(lambda i, m: errors.append(m))
w3.finished.connect(lambda s: (summary3.update(s=s), loop3.quit()))
QTimer.singleShot(15000, loop3.quit)
w3.start()
loop3.exec_()
w3.wait(3000)

print('   statuses:', statuses, '| summary:', summary3.get('s'))
check('the file was uploaded', api3.uploaded == ['F0.jpg'], str(api3.uploaded))
check('an SDC failure still counts the upload',
      summary3.get('s', '').startswith('Done: 1/1'), summary3.get('s', ''))
check('the summary mentions the missing structured data',
      'without structured data' in summary3.get('s', ''), summary3.get('s', ''))
check('the row status flags it',
      statuses[-1] == '✓ Uploaded (SDC failed)', str(statuses[-1]))
check('the error message says the file did go up',
      errors and errors[0].startswith('Uploaded, but structured data failed'),
      str(errors))


# ── Upload itself failed ──────────────────────────────────────────────────────
class UploadBrokenApi(FakeApi):
    def upload(self, *a, **kw):
        raise RuntimeError('boom: upload refused')


api4 = UploadBrokenApi()
w4 = UploadWorker(api4, rows[:1], '', False)
summary4, statuses4 = {}, []
loop4 = QEventLoop()
w4.progress.connect(lambda i, st: statuses4.append(st))
w4.finished.connect(lambda s: (summary4.update(s=s), loop4.quit()))
QTimer.singleShot(15000, loop4.quit)
w4.start()
loop4.exec_()
w4.wait(3000)
check('a real upload failure is still counted as a failure',
      summary4.get('s', '').startswith('Done: 0/1'), summary4.get('s', ''))
check('the row status says Error', statuses4[-1] == '✗ Error', str(statuses4))

print('\nFAILURES (2):', fails if fails else 'none')
sys.exit(1 if fails else 0)
