"""OAuth 2.0 mit PKCE (0.17.0).

Prueft PKCE nach RFC 7636, den State-Schutz des Loopback-Faengers per
ECHTEM HTTP-Roundtrip auf 127.0.0.1:8127, den Token-Tausch und die
Erneuerung gegen einen lokalen Schein-Tokenserver, die Rotation des
Refresh-Tokens, den Bearer-Header samt Einmal-Retry in api.py und den
Einfuege-Rueckweg fuer den Code.
"""
import base64
import hashlib
import json
import os
import re
import sys
import tempfile
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('CAMMELLO_WORKFLOWS',
                      os.path.join(tempfile.mkdtemp(), 'workflows.toml'))

from cammello import mw_oauth2
from cammello.api import MediaWikiApi
from cammello.mw_oauth import LOOPBACK_PORT, MWOAuthError

fails = []


def check(name, cond, detail=''):
    if cond:
        print('PASS', name, detail)
    else:
        print('FAIL', name, detail)
        fails.append(name)


# ── PKCE nach RFC 7636 ───────────────────────────────────────────────────
v1, c1 = mw_oauth2.make_pkce()
v2, c2 = mw_oauth2.make_pkce()
check('the verifier has the maximum RFC length', len(v1) == 128)
check('and stays inside the RFC alphabet',
      bool(re.fullmatch(r'[A-Za-z0-9._~-]+', v1)))
check('two calls never repeat', v1 != v2)
_soll = base64.urlsafe_b64encode(
    hashlib.sha256(v1.encode()).digest()).rstrip(b'=').decode()
check('the challenge is base64url(sha256) without padding',
      c1 == _soll and '=' not in c1)

_url = mw_oauth2.build_authorize_url('teststate', c1)
check('the authorize URL carries the PKCE pair',
      'code_challenge_method=S256' in _url and c1 in _url)
check('and the public client id', mw_oauth2.CLIENT_ID in _url)
check('and the exact registered redirect',
      f'127.0.0.1%3A{LOOPBACK_PORT}%2Fcammello%2F' in _url, _url[:120])
check('no client secret exists anywhere in the module',
      'CLIENT_SECRET' not in open('cammello/mw_oauth2.py').read())

# ── Einfuege-Rueckweg ────────────────────────────────────────────────────
check('a bare code passes through',
      mw_oauth2.code_from_input(' abc ') == 'abc')
check('a full redirect URL yields its code',
      mw_oauth2.code_from_input(
          f'http://127.0.0.1:{LOOPBACK_PORT}/cammello/?code=xy9&state=s')
      == 'xy9')
check('text without a code yields nothing',
      mw_oauth2.code_from_input('http://x/?state=only') == '')

# ── Loopback-Faenger: echter HTTP-Roundtrip, State-Schutz ────────────────
srv = mw_oauth2.LoopbackServer('richtig')
try:
    # Falscher State zuerst: MUSS verworfen werden (sonst koennte eine
    # untergeschobene Umleitung einen fremden Code einschleusen).
    urllib.request.urlopen(
        f'http://127.0.0.1:{LOOPBACK_PORT}/cammello/?code=BOESE&state=falsch',
        timeout=5).read()
    check('a redirect with a foreign state is ignored',
          srv.caught_code is None and srv.httpd.state_mismatch)
    urllib.request.urlopen(
        f'http://127.0.0.1:{LOOPBACK_PORT}/irgendwo?code=GUT&state=richtig',
        timeout=5).read()
    check('the matching redirect is caught on ANY path',
          srv.caught_code == 'GUT', repr(srv.caught_code))
finally:
    srv.close()
try:
    s2 = mw_oauth2.LoopbackServer('x')
    s2.close()
    check('the port is free again after close', True)
except MWOAuthError as e:
    check('the port is free again after close', False, str(e))

# Belegter Port: klare Meldung statt Absturz.
blocker = HTTPServer(('127.0.0.1', LOOPBACK_PORT), BaseHTTPRequestHandler)
try:
    try:
        mw_oauth2.LoopbackServer('x')
        check('a busy port raises the friendly error', False)
    except MWOAuthError as e:
        check('a busy port raises the friendly error',
              str(LOOPBACK_PORT) in str(e))
finally:
    blocker.server_close()

# ── Schein-Tokenserver: Tausch, Erneuerung, Rotation ─────────────────────
_seen = []


class _FakeToken(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        params = dict(p.split('=', 1) for p in
                      self.rfile.read(length).decode().split('&') if '=' in p)
        params = {k: urllib.request.unquote(v.replace('+', ' '))
                  for k, v in params.items()}
        _seen.append(params)
        if params.get('grant_type') == 'authorization_code':
            ok = (params.get('code') == 'GUT'
                  and params.get('code_verifier')
                  and params.get('client_id') == mw_oauth2.CLIENT_ID
                  and 'client_secret' not in params
                  and params.get('redirect_uri') == mw_oauth2.REDIRECT_URI)
            body = {'access_token': 'AT1', 'refresh_token': 'RT1',
                    'expires_in': 14400} if ok else {'error': 'bad'}
        elif params.get('grant_type') == 'refresh_token':
            ok = (params.get('refresh_token') == 'RT1'
                  and 'client_secret' not in params)
            # ROTATION: neues Refresh-Token in der Antwort.
            body = {'access_token': 'AT2', 'refresh_token': 'RT2',
                    'expires_in': 14400} if ok else {'error': 'bad'}
        else:
            body = {'error': 'bad'}
        payload = json.dumps(body).encode()
        self.send_response(200 if 'error' not in body else 400)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *a):
        pass


import urllib.parse
urllib.request.unquote = urllib.parse.unquote
_fake = HTTPServer(('127.0.0.1', 0), _FakeToken)
threading.Thread(target=_fake.serve_forever, daemon=True).start()
_alt = mw_oauth2.TOKEN_URL
mw_oauth2.TOKEN_URL = f'http://127.0.0.1:{_fake.server_address[1]}/token'
try:
    verifier, _ch = mw_oauth2.make_pkce()
    got = mw_oauth2.exchange_code('GUT', verifier)
    check('the exchange sends verifier + client id and NO secret',
          got.get('access_token') == 'AT1' and got.get('refresh_token') == 'RT1',
          str(got))
    got2 = mw_oauth2.refresh_tokens('RT1')
    check('the refresh works without a secret',
          got2.get('access_token') == 'AT2')
    check('and hands back a ROTATED refresh token',
          got2.get('refresh_token') == 'RT2')
    try:
        mw_oauth2.exchange_code('FALSCH', verifier)
        check('a rejected exchange raises with the server text', False)
    except MWOAuthError as e:
        check('a rejected exchange raises with the server text',
              'bad' in str(e), str(e))
finally:
    mw_oauth2.TOKEN_URL = _alt
    _fake.shutdown(); _fake.server_close()

# ── Bearer in api.py: Header und Einmal-Erneuerung ───────────────────────
_api_calls = []


class _FakeApiServer(BaseHTTPRequestHandler):
    def do_GET(self):
        auth = self.headers.get('Authorization', '')
        _api_calls.append(auth)
        if auth == 'Bearer FRISCH':
            body = {'query': {'userinfo': {'id': 1, 'name': 'Seewolf'}}}
        else:
            # So meldet die OAuth-Erweiterung ein totes Token: HTTP 200
            # mit mwoauth-invalid-authorization als Fehlercode.
            body = {'error': {'code': 'mwoauth-invalid-authorization',
                              'info': 'The authorization headers …'}}
        payload = json.dumps(body).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_POST = do_GET

    def log_message(self, *a):
        pass


_fake2 = HTTPServer(('127.0.0.1', 0), _FakeApiServer)
threading.Thread(target=_fake2.serve_forever, daemon=True).start()
_refreshed = []


def _refresher():
    _refreshed.append(True)
    return 'FRISCH'


api = MediaWikiApi(f'http://127.0.0.1:{_fake2.server_address[1]}/api.php',
                   'x', '', timeout=5,
                   bearer_token='ABGELAUFEN', bearer_refresher=_refresher)
r = api._request('GET', 'probe', params={'action': 'query'})
data = r.json()
check('an expired bearer token is refreshed ONCE and retried',
      len(_refreshed) == 1 and data.get('query', {})
      .get('userinfo', {}).get('name') == 'Seewolf',
      f'refreshes={len(_refreshed)} calls={_api_calls}')
check('the retry carries the fresh token',
      _api_calls[-1] == 'Bearer FRISCH', str(_api_calls))
check('the api afterwards keeps the fresh token',
      api._bearer_token == 'FRISCH')

_api_calls.clear(); _refreshed.clear()
api2 = MediaWikiApi(f'http://127.0.0.1:{_fake2.server_address[1]}/api.php',
                    'x', '', timeout=5,
                    bearer_token='ABGELAUFEN',
                    bearer_refresher=lambda: None)
r2 = api2._request('GET', 'probe', params={'action': 'query'})
check('a failed refresh does NOT loop - one request, one answer',
      len(_api_calls) == 1 and 'error' in r2.json(), str(_api_calls))
_fake2.shutdown(); _fake2.server_close()

# ── Speicher-Helfer: Rotation kommt im Keyring an ────────────────────────
from cammello import credentials
from cammello.widgets import (store_oauth2_tokens, stored_oauth2_tokens,
                              clear_stored_oauth2)
_fakekr = {}
credentials.clear_cache()
_orig = (credentials.backend_available, credentials.store,
         credentials.load, credentials.delete)
credentials.backend_available = lambda: True
credentials.store = lambda slot, sec: _fakekr.__setitem__(slot, sec) or True
credentials.load = lambda slot: _fakekr.get(slot)
credentials.delete = lambda slot: _fakekr.pop(slot, None) or True
try:
    store_oauth2_tokens('AT1', 'RT1')
    check('the pair lands as ONE keyring entry',
          list(_fakekr) == ['mw-oauth2:tokens'], str(list(_fakekr)))
    store_oauth2_tokens('AT2', 'RT2')
    check('a refresh overwrites with the rotated pair',
          stored_oauth2_tokens() == ('AT2', 'RT2'))
    clear_stored_oauth2()
    check('clearing removes the entry', stored_oauth2_tokens() == ('', ''))
finally:
    (credentials.backend_available, credentials.store,
     credentials.load, credentials.delete) = _orig
    credentials.clear_cache()

print('---')
print('FAILURES:', fails if fails else 'none')
print(f'{len(fails)} failure(s)')
sys.exit(1 if fails else 0)
