#!/usr/bin/env python3
"""0.18.22/0.18.23: OAuth 1.0a is gone, and a dialog can no longer be
torn down with its authorize thread still running.

Run headless:  QT_QPA_PLATFORM=offscreen python3 test_signin_01822.py
"""
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QSettings

app = QApplication.instance() or QApplication([])

import Cammello                                            # noqa: E402,F401
from cammello import mw_oauth2, widgets                    # noqa: E402
from cammello.constants import APP_NAME                    # noqa: E402

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


URL = 'https://meta.wikimedia.org/w/rest.php/oauth2/authorize?client_id=x'

# ── 1. OAuth 1.0a really is gone ─────────────────────────────────────────
import importlib                                           # noqa: E402
try:
    importlib.import_module('cammello.mw_oauth')
    check('the 1.0a module is gone', False, 'it still imports')
except ImportError:
    check('the 1.0a module is gone', True)

pkg = os.path.dirname(os.path.abspath(widgets.__file__))
offenders = []
for name in sorted(os.listdir(pkg)):
    if not name.endswith('.py'):
        continue
    body = open(os.path.join(pkg, name), encoding='utf-8').read()
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith('#'):
            continue
        if ('from .mw_oauth import' in stripped
                or 'from . import mw_oauth\n' in stripped + '\n'
                or stripped == 'import mw_oauth'):
            offenders.append(f'{name}: {stripped}')
check('no module imports it any more', not offenders, str(offenders))

check('the loopback port moved along', mw_oauth2.LOOPBACK_PORT == 8127,
      str(mw_oauth2.LOOPBACK_PORT))
eq('and the registered callback is unchanged', mw_oauth2.REDIRECT_URI,
   'http://127.0.0.1:8127/cammello/')
check('the error class moved along',
      issubclass(mw_oauth2.MWOAuthError, Exception))

# api.py must not sign anything even when handed 1.0a credentials.
from cammello.api import MediaWikiApi                      # noqa: E402
api = MediaWikiApi('https://commons.wikimedia.org/w/api.php', '', '',
                   oauth_token='tok', oauth_secret='sec')
check('api.py ignores 1.0a credentials', not api._use_oauth)
src = open(os.path.join(pkg, 'api.py'), encoding='utf-8').read()
check('and has no signing code left',
      'authorization_header' not in src)

# ── 2. the browser choice is gone again ─────────────────────────────────
# It did not work on Harald's Mac (0.18.23). The default browser is the
# only way now; a second browser gets the link by copy.
for gone in ('LOGIN_BROWSERS', 'browser_command', 'open_authorize_url'):
    check(f'{gone} is gone from mw_oauth2', not hasattr(mw_oauth2, gone))

# ── 3. the dialog ────────────────────────────────────────────────────────
QSettings(APP_NAME, 'Login').remove('login_browser')
dlg = widgets.OAuthLoginDialog()
check('no 1.0a switch in the dialog', not hasattr(dlg, 'oauth1_cb'))
check('no manual-code switch either', not hasattr(dlg, 'oob_cb'))
# 0.18.22 (Harald): one way in, nothing to choose. The link row, the
# Copy/Open buttons, the "show the link only" switch and the browser
# chooser are all gone - "das Programm soll ja moeglichst einfach fuer
# Benutzer sein".
for gone in ('url_edit', 'copy_btn', 'open_btn', 'show_only_cb',
             'browser_combo'):
    check(f'the dialog has no {gone} any more', not hasattr(dlg, gone))
check('the paste fallback is still there', hasattr(dlg, 'verifier_edit'))
check('and the bot password', hasattr(dlg, 'botpassword_btn'))
check('and the one start button', hasattr(dlg, 'start_btn'))

# ── 4. a failed attempt does not leave a worker behind ───────────────────
class FakeSignal:
    def __init__(self):
        self.connected = 0

    def connect(self, _fn):
        self.connected += 1

    def disconnect(self):
        if not self.connected:
            raise TypeError('nothing connected')
        self.connected = 0


class FakeWorker:
    def __init__(self):
        self.ready = FakeSignal()
        self.succeeded = FakeSignal()
        self.failed = FakeSignal()
        self.stopped = 0
        self.waited = 0
        self._running = True
        for sig in (self.ready, self.succeeded, self.failed):
            sig.connect(None)

    def stop(self):
        self.stopped += 1
        self._running = False

    def isRunning(self):
        return self._running

    def wait(self, _ms=0):
        self.waited += 1
        return True

    def start(self):
        pass


d = widgets.OAuthLoginDialog()
worker = FakeWorker()
d._worker = worker
d._on_failure('The token exchange failed: HTTP 403')
check('a failed authorization stops its worker', worker.stopped == 1,
      str(worker.stopped))
check('and disconnects it first, so no late result arrives',
      worker.ready.connected == 0 and worker.succeeded.connected == 0
      and worker.failed.connected == 0)
check('the dialog forgets it', d._worker is None)
check('and the start button is usable again', d.start_btn.isEnabled())

# A second attempt must stop a worker that is somehow still around.
stale = FakeWorker()
d._worker = stale
started_workers = []
d._start_oauth2 = lambda: started_workers.append('new')
d._start()
check('starting again stops the stale worker first', stale.stopped == 1,
      str(stale.stopped))
eq('and then starts a new one', started_workers, ['new'])

# Cancelling stops it too, and it is idempotent.
third = FakeWorker()
d._worker = third
d._stop_worker()
d._stop_worker()
check('cancelling stops the worker exactly once', third.stopped == 1,
      str(third.stopped))

print(f'\n{PASSED} Pruefungen bestanden, {len(FAILED)} gescheitert')
for f in FAILED:
    print('  -', f)
sys.exit(1 if FAILED else 0)
