"""OAuth flow test (0.12.7) - runs a REAL loopback round-trip.

Only the Wikimedia calls are faked (initiate/complete/whoami); the HTTP
server, the redirect and the capture are the real thing. Run as a file.
"""
import os
import sys
import threading
import time
import urllib.request

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

FAILURES = []


def check(name, cond, detail=''):
    print(('PASS ' if cond else 'FAIL ') + name, detail)
    if not cond:
        FAILURES.append(name)


def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import logging
    logging.basicConfig(level=logging.DEBUG, format='%(levelname)s %(message)s')
    from cammello import mw_oauth
    from cammello.widgets import verifier_from_input

    # Fake the three network calls; everything else is real.
    mw_oauth.CONSUMER_KEY = 'k' * 8
    mw_oauth.CONSUMER_SECRET = 's' * 8
    mw_oauth.initiate = lambda callback, timeout=30: ('reqtok', 'reqsec')
    mw_oauth.authorize_url = lambda t: f'https://example.invalid/auth?{t}'
    mw_oauth.complete = lambda rt, rs, v, timeout=30: (f'acc-{v}', 'accsec')
    mw_oauth.whoami = lambda t, s, **kw: 'Seewolf'

    # ── 1. Manual mode starts a loopback server ─────────────────────────
    rt, rs, url, server = mw_oauth.begin_oob()
    check('manual mode returns a request token', rt == 'reqtok')
    check('manual mode DID start a loopback server', server is not None)
    if server is None:
        print('cannot continue without a server')
        return 1
    check('callback points at the fixed port',
          server.callback ==
          f'http://127.0.0.1:{mw_oauth.LOOPBACK_PORT}/cammello/',
          server.callback)

    # ── 2. A real browser-style redirect is captured ────────────────────
    captured = {}

    def wait_in_thread():
        try:
            captured.update(server.wait(20, lambda: False))
        except Exception as exc:                     # noqa: BLE001
            captured['error'] = str(exc)

    t = threading.Thread(target=wait_in_thread)
    t.start()
    time.sleep(0.3)
    target = f'{server.callback}?oauth_token=reqtok&oauth_verifier=VER123'
    with urllib.request.urlopen(target, timeout=10) as resp:
        page = resp.read().decode('utf-8')
        check('browser gets a real confirmation page', resp.status == 200)
        check('page mentions Cammello', 'Cammello' in page)
    t.join(timeout=10)
    check('verifier captured from the redirect',
          captured.get('oauth_verifier') == 'VER123', str(captured))
    server.close()

    # ── 3. The port is free again afterwards ────────────────────────────
    second = mw_oauth._LoopbackServer()
    check('port released after close', second.port == mw_oauth.LOOPBACK_PORT)
    second.close()

    # ── 4. Fallback when the port is taken ──────────────────────────────
    blocker = mw_oauth._LoopbackServer()
    rt2, rs2, url2, server2 = mw_oauth.begin_oob()
    check('no second server on a busy port', server2 is None)
    check('a request token is still issued', rt2 == 'reqtok')
    blocker.close()

    # ── 5. The watcher completes a sign-in on its own ───────────────────
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    rt3, rs3, url3, server3 = mw_oauth.begin_oob()
    check('third run got a server', server3 is not None)
    result = {}
    watcher = mw_oauth.OAuthCallbackWatchWorker(server3, rt3, rs3,
                                                timeout_s=20)
    watcher.succeeded.connect(
        lambda tok, sec, user: result.update(tok=tok, user=user))
    watcher.expired.connect(lambda msg: result.update(expired=msg))
    watcher.start()
    time.sleep(0.3)
    with urllib.request.urlopen(
            f'{server3.callback}?oauth_token={rt3}&oauth_verifier=W9',
            timeout=10):
        pass
    deadline = time.time() + 10
    while not result and time.time() < deadline:
        app.processEvents()
        time.sleep(0.05)
    watcher.wait(5000)
    app.processEvents()
    check('watcher signed in without any pasting',
          result.get('user') == 'Seewolf', str(result))
    check('watcher used the verifier from the callback',
          result.get('tok') == 'acc-W9', str(result))
    server3.close()

    # ── 6. A stale token is rejected ────────────────────────────────────
    rt4, rs4, url4, server4 = mw_oauth.begin_oob()
    res4 = {}
    w4 = mw_oauth.OAuthCallbackWatchWorker(server4, 'DIFFERENT-TOKEN', rs4,
                                           timeout_s=20)
    w4.succeeded.connect(lambda *a: res4.update(ok=True))
    w4.expired.connect(lambda msg: res4.update(expired=msg))
    w4.start()
    time.sleep(0.3)
    try:
        urllib.request.urlopen(
            f'{server4.callback}?oauth_token={rt4}&oauth_verifier=X',
            timeout=10).close()
    except Exception:                                # noqa: BLE001
        pass
    deadline = time.time() + 10
    while not res4 and time.time() < deadline:
        app.processEvents()
        time.sleep(0.05)
    w4.wait(5000)
    check('mismatched callback token refused',
          'mismatch' in res4.get('expired', ''), str(res4))
    server4.close()

    # ── 7. The address from a FAILED browser page still works ───────────
    failed_page_url = (f'http://127.0.0.1:{mw_oauth.LOOPBACK_PORT}/cammello/'
                       f'?oauth_verifier=FROMBAR&oauth_token=reqtok')
    check('verifier read from the address bar',
          verifier_from_input(failed_page_url) == 'FROMBAR')

    print('\n' + ('ALL OAUTH CHECKS PASSED' if not FAILURES
                  else f'FAILURES: {FAILURES}'))
    return 1 if FAILURES else 0


if __name__ == '__main__':
    sys.exit(main())
