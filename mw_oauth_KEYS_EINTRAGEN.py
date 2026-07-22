"""Wikimedia OAuth 1.0a for Cammello: one-click login, Commons-only rights.

Flow (all against meta.wikimedia.org, where WMF's central OAuth lives; the
signed API calls afterwards go to commons.wikimedia.org):

    1. start a loopback HTTP server on 127.0.0.1:<random port>
    2. Special:OAuth/initiate  (oauth_callback = the loopback URL)
    3. open Special:OAuth/authorize in the user's browser
    4. user clicks "Allow" -> browser is redirected to the loopback server,
       which captures oauth_verifier (and checks the token matches)
    5. Special:OAuth/token    -> access token + access secret
    6. action=query&meta=userinfo on the consumer's wiki (Commons) -> the
       authorizing user's name.  (NOT Special:OAuth/identify on meta: a
       Commons-restricted consumer's token is not valid there.  The old JWT
       identify() helper is kept below for reference but unused.)

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
    applicable project: commons.wikimedia.org, grants: edit + upload.
    Callback URL: http://127.0.0.1:8127/cammello/  (the FIXED loopback port,
    LOOPBACK_PORT), with "Allow consumer to specify a callback in requests
    ... as a required prefix" CHECKED.

    Why a fixed port with the full path: after "Allow", Wikimedia redirects
    the browser to the callback, and in practice it uses the REGISTERED
    callback URL as the redirect target.  So the port Cammello listens on
    must equal the registered port, and the registered path must be the one
    Cammello's little server answers on - otherwise the browser lands on a
    port/path where nothing is listening ("cannot connect to 127.0.0.1").
    A fixed port makes the redirect land on the running server every time,
    so the verifier is captured automatically (no manual code entry).

    Special:OAuth checks the callback with a PLAIN STRING PREFIX (a substr
    compare - no port wildcard).  With the box checked, the request callback
    http://127.0.0.1:8127/cammello/ must start with the registered one; keep
    them identical.

    For OTHER users (not the proposer) to sign in, the consumer must be
    APPROVED by OAuth admins - submit it and wait.  As the proposer you can
    use it immediately.  Paste the resulting key/secret into
    CONSUMER_KEY / CONSUMER_SECRET; both ship in the binary by design.

    Fallback - out-of-band (oob) flow (begin_oob / finish_oob): if the fixed
    loopback port is busy or blocked, authorize with oauth_callback='oob'
    instead (the dialog's "Enter the confirmation code manually" box).  'oob'
    is always accepted; the user pastes a verifier code by hand.

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
import logging
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
# The username is fetched from the consumer's own wiki (Commons), NOT from
# meta: a consumer restricted to commons.wikimedia.org gets an access token
# that is only valid on Commons, so Special:OAuth/identify on meta fails with
# mwoauth-invalid-authorization-wrong-wiki.  A signed userinfo call to the
# Commons API uses the token where it IS valid (the same place uploads go).
USERINFO_API = 'https://commons.wikimedia.org/w/api.php'
CALLBACK_PATH = '/cammello/'                  # must match registered prefix
LOOPBACK_HOST = '127.0.0.1'
# A FIXED loopback port (not a random one): Wikimedia redirects the browser
# to the registered callback URL, so the port Cammello listens on must be the
# exact port that was registered.  A random port would leave the redirect
# pointing at a port where nothing is listening ("cannot connect to
# 127.0.0.1").  The registered consumer callback must therefore be exactly
# http://127.0.0.1:8127/cammello/ (with the prefix box checked).  If the port
# is busy, the sign-in dialog falls back to the manual (oob) code entry.
LOOPBACK_PORT = 8127

# 0.12.7: this module used to log NOTHING. A sign-in that failed left no
# trace at all in cammello_debug.log - not the bind result, not the callback
# that was requested, not a timeout - so the cause could not be told apart
# from the outside (Harald's failed manual sign-in, 18.07.2026). Every
# station below now logs. No secrets: tokens and verifiers are never
# written, only whether they arrived.
_log = logging.getLogger('Cammello')

# How long the loopback server waits for the browser round-trip. Generous on
# purpose: the user may have to sign in to the wiki first, pick an account,
# or move to another browser. Being slow must never be the reason a sign-in
# fails (Harald: "the manual way should not have to be faster").
DEFAULT_TIMEOUT_S = 600


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


# ── Who am I: username via the consumer's own wiki (Commons) ─────────────────

def whoami(access_token, access_secret, api_url=USERINFO_API, timeout=30):
    """Authorizing user's name, via a signed action=query&meta=userinfo call
    to the consumer's wiki (Commons by default).

    Used instead of the meta JWT identify endpoint: a Commons-restricted
    consumer's token is not valid on meta, so identify() there returns
    mwoauth-invalid-authorization-wrong-wiki.  This call signs a normal API
    request the same way api.py does, against the wiki where the token is
    valid, and reads the name straight out of the userinfo block.
    """
    params = {'action': 'query', 'meta': 'userinfo', 'format': 'json'}
    header = authorization_header('GET', api_url, params,
                                  access_token, access_secret)
    r = requests.get(api_url, params=params,
                     headers={'User-Agent': WD_USER_AGENT,
                              'Authorization': header}, timeout=timeout)
    try:
        data = r.json()
    except ValueError:
        raise MWOAuthError(f'userinfo: non-JSON reply (HTTP {r.status_code}): '
                           f'{r.text[:200]}')
    if 'error' in data:
        err = data['error']
        raise MWOAuthError(f'userinfo: {err.get("code")}: {err.get("info", "")}')
    name = data.get('query', {}).get('userinfo', {}).get('name', '')
    if not name:
        raise MWOAuthError(f'userinfo: no username in reply {data!r}')
    return name


# ── Loopback callback server ─────────────────────────────────────────────────

class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlsplit(self.path)
        query = dict(parse_qsl(parsed.query))
        # Capture as long as this looks like the OAuth redirect (carries a
        # verifier), whatever path Wikimedia sent it to - the redirect target
        # is the registered callback, whose path we do not fully control.
        if 'oauth_verifier' not in query and 'oauth_token' not in query:
            self.send_error(404)
            return
        self.server.captured = query
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
    """One-shot HTTP server bound to 127.0.0.1 on the FIXED LOOPBACK_PORT so
    it matches the registered consumer callback."""

    def __init__(self):
        try:
            self.httpd = HTTPServer((LOOPBACK_HOST, LOOPBACK_PORT),
                                    _CallbackHandler)
        except OSError as e:
            _log.warning('OAuth: could not listen on %s:%s (%s) - the '
                         'browser redirect will land nowhere.',
                         LOOPBACK_HOST, LOOPBACK_PORT, e)
            raise MWOAuthError(tr(
                'The local port {port} needed for sign-in is already in use. '
                'Close the program using it, or tick "Enter the confirmation '
                'code manually" to sign in without it.').format(
                    port=LOOPBACK_PORT)) from e
        self.httpd.timeout = 0.5        # poll interval for cancellation
        self.httpd.captured = None
        self.port = LOOPBACK_PORT
        self.callback = f'http://{LOOPBACK_HOST}:{LOOPBACK_PORT}{CALLBACK_PATH}'
        _log.info('OAuth: listening on %s for the callback.', self.callback)

    def wait(self, timeout_s, cancelled):
        """Block until one callback arrived, timeout, or cancelled()."""
        deadline = time.monotonic() + timeout_s
        _log.debug('OAuth: waiting up to %s s for the browser to come back.',
                   timeout_s)
        while self.httpd.captured is None:
            if cancelled():
                _log.info('OAuth: wait for the callback cancelled.')
                raise MWOAuthError(tr('Authorization cancelled.'))
            if time.monotonic() > deadline:
                # Explicit, because a silent expiry is indistinguishable
                # from "nothing ever arrived" in the log.
                _log.warning('OAuth: no callback within %s s - giving up on '
                             'the automatic return.', timeout_s)
                raise MWOAuthError(tr('Authorization timed out.'))
            self.httpd.handle_request()
        got = self.httpd.captured
        _log.info('OAuth: callback received (verifier present: %s).',
                  'yes' if got.get('oauth_verifier') else 'no')
        return got

    def close(self):
        try:
            self.httpd.server_close()
        except OSError:
            pass


# ── Full blocking flow + Qt worker ───────────────────────────────────────────

def run_authorization(timeout_s=DEFAULT_TIMEOUT_S, cancelled=lambda: False,
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
        _log.info('OAuth: requesting a request token (callback: %s).',
                  server.callback)
        req_token, req_secret = initiate(server.callback)
        _log.info('OAuth: request token received; opening the browser.')
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
    username = whoami(access_token, access_secret)
    return access_token, access_secret, username


# ── Out-of-band (oob) flow: no loopback, user pastes a verifier code ─────────
# Works with ANY consumer no matter its callback URL, its "callback is
# prefix" flag, or its approval status, because oauth_callback='oob' is
# always accepted by Special:OAuth/initiate.  The trade-off is manual: after
# clicking "Allow" the wiki shows a short verifier code that the user copies
# back into Cammello.  Split into two steps because the user acts in between.

def begin_oob(timeout=30, use_loopback=True):
    """Manual step 1: -> (request_token, request_secret, url, server).

    0.12.7 - why this no longer asks for 'oob' by default
    -----------------------------------------------------
    It used to call initiate('oob'), on the assumption that the wiki would
    then DISPLAY a verifier code. With this consumer it does not: the
    callback is registered "as a required prefix", 'oob' does not match that
    prefix, and Special:OAuth redirects the browser to the REGISTERED
    callback anyway. With no loopback server running, the browser hit
    127.0.0.1 and showed ERR_CONNECTION_REFUSED - exactly what Harald saw on
    18.07.2026. The verifier was in the address bar all along and nobody was
    there to take it.

    So the manual mode now starts the loopback server TOO and asks for the
    same callback as the automatic flow. Effect:
      * if the redirect arrives, the caller's watcher completes the sign-in
        without the user pasting anything;
      * if it does not (server on another machine, browser blocked), the
        user pastes the address from the browser, which works whether or
        not the page loaded.
    Only when the port cannot be bound does it fall back to a true 'oob'
    request - the one situation where that is the honest thing to ask for.

    `server` is None in the fallback case; the caller must close it.
    """
    if not is_configured():
        raise MWOAuthError('OAuth consumer key/secret not configured '
                           '(mw_oauth.CONSUMER_KEY).')
    server = None
    callback = 'oob'
    if use_loopback:
        try:
            server = _LoopbackServer()
            callback = server.callback
        except MWOAuthError as exc:
            # Not fatal here: the manual path exists precisely for this.
            _log.warning('OAuth manual: no loopback server (%s) - falling '
                         'back to a true oob request.', exc)
    _log.info('OAuth manual: requesting a request token (callback: %s).',
              callback)
    try:
        req_token, req_secret = initiate(callback, timeout)
    except Exception:
        if server is not None:
            server.close()
        raise
    return req_token, req_secret, authorize_url(req_token), server


def finish_oob(request_token, request_secret, verifier, timeout=30):
    """oob step 2: the pasted verifier code ->
    (access_token, access_secret, username)."""
    verifier = (verifier or '').strip()
    if not verifier:
        raise MWOAuthError(tr('Please paste the confirmation code first.'))
    _log.info('OAuth manual: exchanging the pasted confirmation.')
    access_token, access_secret = complete(
        request_token, request_secret, verifier, timeout)
    username = whoami(access_token, access_secret)
    _log.info('OAuth manual: sign-in completed for user "%s".', username)
    return access_token, access_secret, username


class OAuthOOBBeginWorker(QThread):
    """Manual phase 1 off the GUI thread -> authorize URL.

    Since 0.12.7 this also starts the loopback server (see begin_oob); the
    server object is left on `.server` for the caller, which starts an
    OAuthCallbackWatchWorker on it and is responsible for closing it.

    Signals:
        ready(request_token, request_secret, url, loopback_active)
        failed(message)
    """

    ready = pyqtSignal(str, str, str, bool)
    failed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.server = None

    def run(self):
        try:
            req_token, req_secret, url, server = begin_oob()
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.server = server
        self.ready.emit(req_token, req_secret, url, server is not None)


class OAuthCallbackWatchWorker(QThread):
    """Waits on an ALREADY RUNNING loopback server during the manual flow.

    Runs in parallel with the user pasting something by hand: whichever
    completes first wins. A timeout is NOT a failure here - the manual path
    is still open - so it gets its own quiet signal instead of failed().

    Signals:
        succeeded(access_token, access_secret, username)
        expired(message)   - timed out or cancelled; the dialog stays open
    """

    succeeded = pyqtSignal(str, str, str)
    expired = pyqtSignal(str)

    def __init__(self, server, request_token, request_secret,
                 timeout_s=DEFAULT_TIMEOUT_S, parent=None):
        super().__init__(parent)
        self._server = server
        self._rt = request_token
        self._rs = request_secret
        self._timeout_s = timeout_s
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            captured = self._server.wait(self._timeout_s,
                                         lambda: self._cancelled)
        except Exception as exc:
            self.expired.emit(str(exc))
            return
        try:
            if captured.get('oauth_token') != self._rt:
                raise MWOAuthError('callback token mismatch')
            verifier = captured.get('oauth_verifier', '')
            if not verifier:
                raise MWOAuthError('callback carried no oauth_verifier')
            token, secret, username = finish_oob(self._rt, self._rs, verifier)
        except Exception as exc:
            self.expired.emit(str(exc))
            return
        self.succeeded.emit(token, secret, username)


class OAuthOOBFinishWorker(QThread):
    """oob phase 2 off the GUI thread: verifier -> access token + identify.

    Signals:
        succeeded(access_token, access_secret, username)
        failed(message)
    """

    succeeded = pyqtSignal(str, str, str)
    failed = pyqtSignal(str)

    def __init__(self, request_token, request_secret, verifier, parent=None):
        super().__init__(parent)
        self._rt = request_token
        self._rs = request_secret
        self._verifier = verifier

    def run(self):
        try:
            token, secret, username = finish_oob(
                self._rt, self._rs, self._verifier)
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.succeeded.emit(token, secret, username)


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
