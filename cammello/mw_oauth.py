"""Wikimedia OAuth 1.0a for Cammello: one-click login, Commons-only rights.

Flow (all against meta.wikimedia.org, where WMF's central OAuth lives; the
signed API calls afterwards go to commons.wikimedia.org):

    1. start a loopback HTTP server on 127.0.0.1:<random port>
    2. Special:OAuth/initiate  (oauth_callback = the loopback URL)
    3. open Special:OAuth/authorize in the user's browser
    4. user clicks "Allow" -> browser is redirected to the loopback server,
       which captures oauth_verifier (and checks the token matches)
    5. Special:OAuth/token    -> access token + access secret
    6. Special:OAuth/identify -> username (JWT, verified here)

The access token/secret pair never expires and belongs in the OS keyring
(credentials.mw_oauth_slot).  There is no login API call and no session
cookie: every request simply carries an Authorization header from
authorization_header().

Signing is reused from flickr.py - the HMAC-SHA1 machinery there is plain
RFC 5849 and already verified in test_flickr.py against the spec's example
vector.  (If a shared oauth_core module ever feels cleaner, move
oauth_signature/oauth_base_params/_enc there and import from both sides.)

Consumer registration (one-time, on Meta):
    Special:OAuthConsumerRegistration/propose, OAuth 1.0a, NOT owner-only,
    applicable project: commonswiki, grants: edit + upload,
    callback URL http://127.0.0.1/cammello/ with
    "Allow consumer to specify a callback in requests" CHECKED
    (that prefix option is what permits the random port below).
    Paste the resulting key/secret into CONSUMER_KEY / CONSUMER_SECRET.
    Until OAuth admins approve the consumer, only the proposer can
    authorize it - keep the BotPassword path as the default until then.

The consumer secret ships inside the binary by design.  It cannot be used
to access any account (every request needs the per-user access secret on
top); the callback prefix pins the verifier to the user's own machine.
Accepted desktop-app trade-off - do not bother obfuscating it.

Two signing pitfalls encoded below:
* The Special:OAuth endpoints are index.php?title=... - the `title` (and
  `format`) query parameters MUST be part of the signature base string.
* Multipart upload bodies are excluded from signatures (RFC 5849); only
  oauth_* and query parameters are signed.  api.py's upload call must pass
  its form fields accordingly (same reasoning as flickr.py's upload).
"""
import base64
import hashlib
import hmac
import json
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qsl, urlencode, urlsplit

import requests

from PyQt5.QtCore import QThread, pyqtSignal

from .constants import WD_USER_AGENT
from .flickr import oauth_base_params, oauth_signature
from .i18n import tr

# ── Consumer registration values (fill in after registering on Meta) ─────────
CONSUMER_KEY = ''       # from Special:OAuthConsumerRegistration
CONSUMER_SECRET = ''    # ships in the binary on purpose - see module docstring

OAUTH_INDEX = 'https://meta.wikimedia.org/w/index.php'
OAUTH_ISSUER = 'https://meta.wikimedia.org'   # `iss` claim in identify JWTs
CALLBACK_PATH = '/cammello/'                  # must match registered prefix
LOOPBACK_HOST = '127.0.0.1'


def is_configured():
    """False until CONSUMER_KEY/SECRET are filled in - lets the Settings tab
    hide the OAuth button in builds without a registered consumer."""
    return bool(CONSUMER_KEY and CONSUMER_SECRET)


class MWOAuthError(RuntimeError):
    pass


# ── Signed calls to the Special:OAuth endpoints ──────────────────────────────

def _special(page, oauth_params, token_secret, timeout):
    """GET index.php?title=Special:OAuth/<page> with a valid signature.

    `title` and `format` are ordinary query parameters and therefore part
    of the signature base string - forgetting them yields
    mwoauth-invalid-authorization, not a helpful message.
    """
    query = {'title': f'Special:OAuth/{page}', 'format': 'json'}
    signed = dict(query)
    signed.update(oauth_params)
    oauth_params['oauth_signature'] = oauth_signature(
        'GET', OAUTH_INDEX, signed, CONSUMER_SECRET, token_secret)
    r = requests.get(OAUTH_INDEX, params={**query, **oauth_params},
                     headers={'User-Agent': WD_USER_AGENT}, timeout=timeout)
    try:
        data = r.json()
    except ValueError:
        raise MWOAuthError(f'{page}: non-JSON reply (HTTP {r.status_code}): '
                           f'{r.text[:200]}')
    if 'error' in data:
        raise MWOAuthError(f'{page}: {data["error"]}: '
                           f'{data.get("message", "")}')
    return data


def initiate(callback, timeout=30):
    """Step 2: -> (request_token, request_secret)."""
    params = oauth_base_params(CONSUMER_KEY)
    params['oauth_callback'] = callback
    data = _special('initiate', params, '', timeout)
    if 'key' not in data or 'secret' not in data:
        raise MWOAuthError(f'initiate: unexpected reply {data!r}')
    return data['key'], data['secret']


def authorize_url(request_token):
    """Step 3: URL the user's browser opens."""
    return (f'{OAUTH_INDEX}?'
            + urlencode({'title': 'Special:OAuth/authorize',
                         'oauth_consumer_key': CONSUMER_KEY,
                         'oauth_token': request_token}))


def complete(request_token, request_secret, verifier, timeout=30):
    """Step 5: -> (access_token, access_secret)."""
    params = oauth_base_params(CONSUMER_KEY, request_token)
    params['oauth_verifier'] = verifier
    data = _special('token', params, request_secret, timeout)
    if 'key' not in data or 'secret' not in data:
        raise MWOAuthError(f'token: unexpected reply {data!r}')
    return data['key'], data['secret']


# ── identify: JWT with mandatory verification ────────────────────────────────

def _b64url_decode(part):
    pad = '=' * (-len(part) % 4)
    return base64.urlsafe_b64decode(part + pad)


def identify(access_token, access_secret, timeout=30, leeway=300):
    """Step 6: verified identity claims of the authorizing user (-> dict).

    The reply is a JWT signed with HS256 and OUR consumer secret; verifying
    it here (signature, issuer, audience, timestamps) is what makes the
    returned username trustworthy.  `leeway` absorbs client clock skew.
    """
    params = oauth_base_params(CONSUMER_KEY, access_token)
    query = {'title': 'Special:OAuth/identify'}
    signed = dict(query)
    signed.update(params)
    params['oauth_signature'] = oauth_signature(
        'GET', OAUTH_INDEX, signed, CONSUMER_SECRET, access_secret)
    r = requests.get(OAUTH_INDEX, params={**query, **params},
                     headers={'User-Agent': WD_USER_AGENT}, timeout=timeout)
    jwt = r.text.strip()
    try:
        header_b64, payload_b64, sig_b64 = jwt.split('.')
    except ValueError:
        raise MWOAuthError(f'identify: not a JWT (HTTP {r.status_code}): '
                           f'{jwt[:200]}')
    header = json.loads(_b64url_decode(header_b64))
    if header.get('alg') != 'HS256':            # refuse alg confusion attacks
        raise MWOAuthError(f'identify: unexpected alg {header.get("alg")!r}')
    expect = hmac.new(CONSUMER_SECRET.encode('ascii'),
                      f'{header_b64}.{payload_b64}'.encode('ascii'),
                      hashlib.sha256).digest()
    if not hmac.compare_digest(expect, _b64url_decode(sig_b64)):
        raise MWOAuthError('identify: JWT signature mismatch')
    claims = json.loads(_b64url_decode(payload_b64))
    now = time.time()
    if claims.get('iss') != OAUTH_ISSUER:
        raise MWOAuthError(f'identify: wrong issuer {claims.get("iss")!r}')
    if claims.get('aud') != CONSUMER_KEY:
        raise MWOAuthError('identify: wrong audience')
    if 'exp' in claims and now > float(claims['exp']) + leeway:
        raise MWOAuthError('identify: JWT expired')
    if 'iat' in claims and now < float(claims['iat']) - leeway:
        raise MWOAuthError('identify: JWT from the future (check clock)')
    return claims


# ── Authorization header for regular API requests (api.py) ───────────────────

def authorization_header(method, url, params, access_token, access_secret):
    """OAuth header for one request to any wiki the consumer covers.

    `params`: every query parameter AND every form-urlencoded body
    parameter of the request.  For multipart/form-data requests (file
    upload) pass ONLY the query parameters - multipart bodies are excluded
    from OAuth 1.0a signatures.
    """
    base_url = url.split('?', 1)[0]
    oauth_params = oauth_base_params(CONSUMER_KEY, access_token)
    signed = dict(params or {})
    signed.update(oauth_params)
    oauth_params['oauth_signature'] = oauth_signature(
        method, base_url, signed, CONSUMER_SECRET, access_secret)
    parts = ', '.join(
        f'{k}="{requests.utils.quote(str(v), safe="")}"'
        for k, v in sorted(oauth_params.items()))
    return f'OAuth realm="Cammello", {parts}'


# ── Loopback callback server ─────────────────────────────────────────────────

class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlsplit(self.path)
        if not parsed.path.startswith(CALLBACK_PATH):
            self.send_error(404)
            return
        self.server.captured = dict(parse_qsl(parsed.query))
        msg = tr("Authorization received. You can close this window "
                 "and return to Cammello.")
        body = ('<!doctype html><meta charset="utf-8"><title>Cammello</title>'
                f'<p>{msg}</p>').encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):       # keep the console quiet
        pass


class _LoopbackServer:
    """One-shot HTTP server bound to 127.0.0.1 on a random free port."""

    def __init__(self):
        self.httpd = HTTPServer((LOOPBACK_HOST, 0), _CallbackHandler)
        self.httpd.timeout = 0.5        # poll interval for cancellation
        self.httpd.captured = None
        self.port = self.httpd.server_address[1]
        self.callback = f'http://{LOOPBACK_HOST}:{self.port}{CALLBACK_PATH}'

    def wait(self, timeout_s, cancelled):
        """Block until one callback arrived, timeout, or cancelled()."""
        deadline = time.monotonic() + timeout_s
        while self.httpd.captured is None:
            if cancelled():
                raise MWOAuthError(tr('Authorization cancelled.'))
            if time.monotonic() > deadline:
                raise MWOAuthError(tr('Authorization timed out.'))
            self.httpd.handle_request()
        return self.httpd.captured

    def close(self):
        try:
            self.httpd.server_close()
        except OSError:
            pass


# ── Full blocking flow + Qt worker ───────────────────────────────────────────

def run_authorization(timeout_s=300, cancelled=lambda: False,
                      open_url=webbrowser.open):
    """Blocking end-to-end authorization.

    -> (access_token, access_secret, username).  Call from a worker thread,
    never from the GUI thread (it waits for the browser round-trip).
    """
    if not is_configured():
        raise MWOAuthError('OAuth consumer key/secret not configured '
                           '(mw_oauth.CONSUMER_KEY).')
    server = _LoopbackServer()
    try:
        req_token, req_secret = initiate(server.callback)
        open_url(authorize_url(req_token))
        captured = server.wait(timeout_s, cancelled)
    finally:
        server.close()
    if captured.get('oauth_token') != req_token:
        # a different/stale token means the redirect was not the answer to
        # OUR initiate - treat as an attack or a crossed wire, never accept
        raise MWOAuthError('callback token mismatch')
    verifier = captured.get('oauth_verifier', '')
    if not verifier:
        raise MWOAuthError('callback carried no oauth_verifier')
    access_token, access_secret = complete(req_token, req_secret, verifier)
    claims = identify(access_token, access_secret)
    return access_token, access_secret, claims.get('username', '')


class OAuthAuthorizeWorker(QThread):
    """Runs run_authorization() off the GUI thread (house style: flickr.py).

    Signals:
        authorize_url_ready(url) - emitted once the authorize URL exists.
            The UI shows it with a copy button; the loopback server keeps
            listening, so the user may open the URL in ANY browser on this
            machine (second browser with the wiki session, private window,
            ...) - the 127.0.0.1 redirect lands here regardless.
        succeeded(access_token, access_secret, username)
        failed(message)

    auto_open=True additionally launches the system default browser;
    auto_open=False emits only the signal (copy/paste workflow).
    cancel() aborts the wait within ~0.5 s.
    """

    authorize_url_ready = pyqtSignal(str)
    succeeded = pyqtSignal(str, str, str)
    failed = pyqtSignal(str)

    def __init__(self, timeout_s=600, auto_open=True, parent=None):
        super().__init__(parent)
        self._timeout_s = timeout_s
        self._auto_open = auto_open
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def _open(self, url):
        self.authorize_url_ready.emit(url)
        if self._auto_open:
            webbrowser.open(url)
        return True

    def run(self):
        try:
            token, secret, username = run_authorization(
                self._timeout_s, cancelled=lambda: self._cancelled,
                open_url=self._open)
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.succeeded.emit(token, secret, username)
