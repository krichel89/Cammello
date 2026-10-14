#!/usr/bin/env python3
"""0.18.32: a stored OAuth token that is rejected (401, 'Jwt is expired') and
cannot be renewed clears the stored pair and opens the authorization window
instead of showing the raw HTTP error; a second failure shows the error.

Run headless:  QT_QPA_PLATFORM=offscreen python3 test_oauthexpired_01832.py
"""
import os
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
_HOME = tempfile.mkdtemp()
os.environ['HOME'] = _HOME
os.environ['USERPROFILE'] = _HOME
os.environ['CAMMELLO_WORKFLOWS'] = os.path.join(_HOME, 'workflows.toml')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication, QMessageBox

import Cammello
from cammello import mw_files
from cammello.logging_setup import setup_logging

app = QApplication(sys.argv)
logger, emitter, gui_handler, log_path = setup_logging()
fails = []


def check(name, cond, detail=''):
    print(('PASS' if cond else 'FAIL'), name, detail)
    if not cond:
        fails.append(name)


shown = []
QMessageBox.critical = staticmethod(lambda *a, **k: shown.append(a[2]))
w = Cammello.MainWindow(logger, emitter, gui_handler, log_path)

cleared = []
opened = []
mw_files.clear_stored_oauth2 = lambda: cleared.append(1)
w.open_signin_dialog = lambda force=False: opened.append(force)

MSG = ('HTTP 401 during userinfo. Response: '
       '{"httpCode":401,"httpReason":"Jwt is expired"}')

w._login_used_bearer = True
w._on_login_failure(MSG)
check('token cleared', cleared == [1])
check('authorization window opened (forced)', opened == [True])
check('no raw error box', shown == [])

w._login_used_bearer = True          # the fresh token fails too
w._on_login_failure(MSG)
check('second failure shows the error', len(shown) == 1 and cleared == [1])

w._login_retrying = False
w._login_used_bearer = False         # bot password / other failure
w._on_login_failure('Invalid credentials.')
check('other errors unchanged', len(shown) == 2 and opened == [True])

print('FAILURES:', fails or 'none')
os._exit(1 if fails else 0)
