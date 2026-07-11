"""Functional guard for the login path (0.9.9 regression fix).

Covers the exact chain that crashed: MainWindow.do_login -> LoginDialog
(QSettings) -> LoginWorker.run -> MediaWikiApi. The network is unreachable in
the sandbox, so the worker is expected to FAIL - but with a network error, not
with a NameError.
"""
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QEventLoop, QTimer

from cammello.widgets import LoginDialog
from cammello.workers import LoginWorker
from cammello.api import MediaWikiApi
from cammello.logging_setup import setup_logging

app = QApplication(sys.argv)
logger, emitter, gui_handler, log_path = setup_logging()

fails = []


def check(name, cond, detail=''):
    print(('PASS' if cond else 'FAIL'), name, detail)
    if not cond:
        fails.append(name)


# 1) The dialog constructs (this is what raised NameError: QSettings).
dlg = LoginDialog()
url, user, pw = dlg.get_credentials()
check('LoginDialog constructs and returns credentials',
      url.endswith('/w/api.php'), url)

# 2) MediaWikiApi is reachable from workers (was NameError: MediaWikiApi).
check('workers can see MediaWikiApi',
      LoginWorker.__module__ == 'cammello.workers'
      and 'MediaWikiApi' in vars(sys.modules['cammello.workers']))

# 3) api.upload uses os.path -> os must be imported in cammello.api.
check('cammello.api has os imported', 'os' in vars(sys.modules['cammello.api']))
check('cammello.api has extract_name_from_caption',
      'extract_name_from_caption' in vars(sys.modules['cammello.api']))

# 4) Run the worker. The sandbox has no route to wikimedia.org, so this must
#    end in failure - but the message must be a network error, NOT a NameError.
result = {}
w = LoginWorker('https://commons.wikimedia.org/w/api.php', 'X@Cammello', 'pw',
                5, logger)
loop = QEventLoop()
w.success.connect(lambda api: (result.update(ok=True), loop.quit()))
w.failure.connect(lambda msg: (result.update(err=msg), loop.quit()))
QTimer.singleShot(30000, loop.quit)
w.start()
loop.exec_()
w.wait(2000)

err = result.get('err', '')
print('   worker failure message:', repr(err)[:120])
check('worker did not die with a NameError',
      'is not defined' not in err and 'NameError' not in err)
check('worker reported something (network error expected here)',
      bool(err) or result.get('ok'))

# 5) os.path.getsize path in upload() must not raise NameError.
api = MediaWikiApi('https://commons.wikimedia.org/w/api.php', 'u', 'p',
                   timeout=1, logger=logger)
try:
    api.upload('X.jpg', '/does/not/exist.jpg', 'text', 'comment')
    msg = ''
except NameError as e:
    msg = f'NameError: {e}'
except Exception as e:
    msg = ''  # any other error (network / missing file) is fine here
check('upload() reaches past os.path without NameError', msg == '', msg)

print('\nFAILURES:', fails if fails else 'none')
sys.exit(1 if fails else 0)
