"""OAuth 2.0 (PKCE) sign-in against Wikimedia (0.17.0).

The second, simpler authorization path next to mw_oauth (OAuth 1.0a).
No request signing: one authorization-code exchange, then a Bearer header
on every API call. The client is registered as NON-CONFIDENTIAL, so there
is NO client secret anywhere in this module - the client id below is
public by design (it appears in every user's address bar during
authorization). PKCE replaces the secret.

Pitfalls this module is built around (researched before building, all
verified against the OAuth extension's source or its documentation):

  * Access tokens EXPIRE after four hours. The refresh token gets them
    renewed without bothering the user; api.py retries one failed request
    after a refresh.
  * The server ROTATES the refresh token on every renewal (league
    oauth2-server behaviour): the response carries a NEW refresh token and
    the old one dies. Whoever calls refresh_tokens() must persist the pair
    from the response, not keep the old one.
  * The authorize and token endpoints live on META (the central OAuth
    wiki) even for a consumer restricted to Commons - same as the OAuth
    1.0a handshake. But any AUTHENTICATED call to meta would fail with
    mwoauth-invalid-authorization-wrong-wiki (the 0.12.2 lesson), so the
    who-am-I check goes against the COMMONS action API with the Bearer
    header, never against meta's profile endpoint.
  * redirect_uri must be IDENTICAL in the authorize step and the token
    exchange, and both must match the registered URL exactly - OAuth 2
    compares the full string, there is no prefix rule.
"""

import base64
import hashlib
import secrets
import string
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests
from PyQt5.QtCore import QThread, pyqtSignal

from .constants import APP_NAME, __version__
from .i18n import tr
from .mw_oauth import LOOPBACK_PORT, MWOAuthError

# The public client id of the registered non-confidential OAuth 2.0 client
# ("Cammello", proposed 06.08.2026). Public by design - do NOT add a client
# secret here; the whole point of the PKCE client is that none is needed.
CLIENT_ID = '51a96b0f9f224d2408d4ccba1d44d2f7'

# Central OAuth endpoints. The consumer itself is restricted to Commons;
# that restriction applies to authenticated API requests, not to the
# handshake, which is central on meta for every Wikimedia consumer.
AUTHORIZE_URL = 'https://meta.wikimedia.org/w/rest.php/oauth2/authorize'
TOKEN_URL = 'https://meta.wikimedia.org/w/rest.php/oauth2/access_token'

# Must match the registered callback EXACTLY (exact string compare in
# OAuth 2 - the prefix rule of OAuth 1.0a does not exist here). Same fixed
# port the 1.0a loopback already owns; both flows never run at once.
REDIRECT_URI = f'http://127.0.0.1:{LOOPBACK_PORT}/cammello/'

# The Commons action API answers the who-am-I check (wrong-wiki lesson).
USERINFO_API = 'https://commons.wikimedia.org/w/api.php'

_USER_AGENT = f'{APP_NAME}/{__version__} (OAuth2)'

# RFC 7636: the verifier alphabet is [A-Za-z0-9._~-], length 43..128.
_PKCE_ALPHABET = string.ascii_letters + string.digits + '.-_~'


def is_configured():
    """Whether this build carries an OAuth 2 client id."""
    return bool(CLIENT_ID)


def make_pkce():
    """-> (code_verifier, code_challenge) per RFC 7636, S256.

    128 characters - the maximum the RFC allows, and entropy is free.
    The challenge is base64url WITHOUT padding; a trailing '=' would be
    rejected by the server.
    """
    verifier = ''.join(secrets.choice(_PKCE_ALPHABET) for _ in range(128))
    digest = hashlib.sha256(verifier.encode('ascii')).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b'=').decode('ascii')
    return verifier, challenge


def build_authorize_url(state, challenge):
    """The URL the user's browser opens."""
    return AUTHORIZE_URL + '?' + urllib.parse.urlencode({
        'response_type': 'code',
        'client_id': CLIENT_ID,
        'redirect_uri': REDIRECT_URI,
        'state': state,
        'code_challenge': challenge,
        'code_challenge_method': 'S256',
    })


def _token_request(data, timeout):
    """POST to the token endpoint, surface the server's error text."""
    try:
        r = requests.post(TOKEN_URL, data=data, timeout=timeout,
                          headers={'User-Agent': _USER_AGENT})
    except requests.exceptions.RequestException as e:
        raise MWOAuthError(tr('Network error during the token exchange: '
                              '{error}').format(error=e)) from e
    try:
        payload = r.json()
    except ValueError:
        payload = {}
    if r.status_code != 200 or 'access_token' not in payload:
        detail = payload.get('message') or payload.get('error') \
            or f'HTTP {r.status_code}'
        hint = payload.get('hint')
        if hint:
            detail = f'{detail} ({hint})'
        raise MWOAuthError(tr('The token exchange failed: {error}')
                           .format(error=detail))
    return payload


def exchange_code(code, verifier, timeout=30):
    """Authorization code -> token payload.

    Returns the server's dict: access_token, refresh_token, expires_in.
    redirect_uri is sent again here and must equal the authorize step's -
    the server verifies the pair.
    """
    return _token_request({
        'grant_type': 'authorization_code',
        'code': code,
        'client_id': CLIENT_ID,
        'redirect_uri': REDIRECT_URI,
        'code_verifier': verifier,
    }, timeout)


def refresh_tokens(refresh_token, timeout=30):
    """Refresh token -> NEW token payload.

    The response contains a ROTATED refresh token; the caller must persist
    the returned pair and forget the one passed in. No client secret: the
    client is non-confidential, and the server (league 9.x) only demands a
    secret from confidential clients - verified in its validateClient().
    """
    return _token_request({
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
        'client_id': CLIENT_ID,
    }, timeout)


def whoami_bearer(access_token, timeout=30):
    """The username the token belongs to, asked of COMMONS.

    Deliberately the action API of the wiki the consumer is restricted to,
    NOT meta's oauth2/resource/profile: a Commons-restricted token is
    rejected by meta with wrong-wiki (the exact 0.12.2 failure, relearned
    once already).
    """
    try:
        r = requests.get(USERINFO_API, params={
            'action': 'query', 'meta': 'userinfo', 'format': 'json',
        }, headers={
            'Authorization': f'Bearer {access_token}',
            'User-Agent': _USER_AGENT,
        }, timeout=timeout)
        data = r.json()
    except requests.exceptions.RequestException as e:
        raise MWOAuthError(tr('Network error during the sign-in check: '
                              '{error}').format(error=e)) from e
    except ValueError as e:
        raise MWOAuthError(tr('The sign-in check returned no usable '
                              'answer.')) from e
    info = (data.get('query') or {}).get('userinfo') or {}
    if 'error' in data:
        raise MWOAuthError(str(data['error'].get('info', data['error'])))
    if not info.get('name') or 'anon' in info:
        # A valid HTTP answer that does not carry a signed-in user means
        # the token did not authenticate us - say so, do not guess.
        raise MWOAuthError(tr('The server did not recognise the sign-in.'))
    return info['name']


def code_from_input(text):
    """Extract the authorization code from pasted text.

    Accepts the bare code or a full redirect URL out of the address bar -
    the same courtesy verifier_from_input() taught the 1.0a flow: when the
    loopback catch fails (firewall), the code sits in the URL and pasting
    the whole line must work.
    """
    text = (text or '').strip()
    if not text:
        return ''
    if '://' in text or 'code=' in text:
        try:
            query = urllib.parse.urlsplit(text).query or \
                text.split('?', 1)[-1]
            params = urllib.parse.parse_qs(query)
            if params.get('code'):
                return params['code'][0].strip()
        except ValueError:
            pass
        return ''
    return text


class _CodeCatcher(BaseHTTPRequestHandler):
    """Catches the redirect carrying ?code=...&state=...

    Defensive about the path, exactly like the 1.0a handler: whatever path
    the redirect lands on, if it carries a code it is ours - but ONLY when
    the state matches, otherwise a stray or forged redirect could inject a
    foreign code (that is what state is for).
    """

    def do_GET(self):
        params = urllib.parse.parse_qs(
            urllib.parse.urlsplit(self.path).query)
        code = (params.get('code') or [''])[0]
        state = (params.get('state') or [''])[0]
        srv = self.server
        if code and state == srv.expected_state:
            srv.caught_code = code
            body = tr('Cammello is authorized. You can close this '
                      'window.')
        elif code:
            srv.state_mismatch = True
            body = tr('This authorization answer does not belong to the '
                      'running Cammello session and was ignored.')
        else:
            body = tr('Waiting for the authorization…')
        payload = ('<html><body><h2>Cammello</h2><p>%s</p></body></html>'
                   % body).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass                                    # quiet, like the 1.0a server


class LoopbackServer:
    """The local catcher on the FIXED port the callback is registered for."""

    def __init__(self, expected_state):
        try:
            self.httpd = HTTPServer(('127.0.0.1', LOOPBACK_PORT),
                                    _CodeCatcher)
        except OSError as e:
            raise MWOAuthError(tr(
                'Port {port} is already in use, so the sign-in answer '
                'cannot be received. Close the other program or paste the '
                'code manually.').format(port=LOOPBACK_PORT)) from e
        self.httpd.expected_state = expected_state
        self.httpd.caught_code = None
        self.httpd.state_mismatch = False
        self._thread = threading.Thread(target=self.httpd.serve_forever,
                                        daemon=True)
        self._thread.start()

    @property
    def caught_code(self):
        return self.httpd.caught_code

    def close(self):
        try:
            self.httpd.shutdown()
            self.httpd.server_close()
        except Exception:
            pass


class OAuth2AuthorizeWorker(QThread):
    """Begin the flow: PKCE, loopback, browser URL; then wait for the code.

    ready(url) fires once the browser can be opened; succeeded(access,
    refresh, username) after the exchange and the Commons who-am-I;
    failed(msg) on any error. finish_with_code() feeds a manually pasted
    code into the same exchange.
    """

    ready = pyqtSignal(str)
    succeeded = pyqtSignal(str, str, str)
    failed = pyqtSignal(str)

    POLL_MS = 250

    def __init__(self, parent=None, timeout_s=600):
        super().__init__(parent)
        self.timeout_s = timeout_s
        self.verifier, self._challenge = make_pkce()
        self.state = secrets.token_urlsafe(24)
        self.server = None
        self._manual_code = None
        self._stopped = False

    def run(self):
        try:
            try:
                self.server = LoopbackServer(self.state)
            except MWOAuthError as e:
                # No port, no automatic catch - the manual paste still
                # works, so this is a downgrade, not a failure.
                self.server = None
                self.failed.emit(str(e))
            self.ready.emit(build_authorize_url(self.state,
                                                self._challenge))
            waited = 0.0
            code = None
            while waited < self.timeout_s and not self._stopped:
                if self._manual_code:
                    code = self._manual_code
                    break
                if self.server is not None and self.server.caught_code:
                    code = self.server.caught_code
                    break
                self.msleep(self.POLL_MS)
                waited += self.POLL_MS / 1000.0
            if self._stopped:
                return
            if not code:
                self.failed.emit(tr('The authorization timed out. Start '
                                    'it again when you are ready.'))
                return
            payload = exchange_code(code, self.verifier)
            username = whoami_bearer(payload['access_token'])
            self.succeeded.emit(payload['access_token'],
                                payload.get('refresh_token', ''), username)
        except MWOAuthError as e:
            self.failed.emit(str(e))
        except Exception as e:                  # never die silently
            self.failed.emit(f'{type(e).__name__}: {e}')
        finally:
            if self.server is not None:
                self.server.close()
                self.server = None

    def finish_with_code(self, text):
        """Feed a pasted code (or full URL) into the running wait loop."""
        code = code_from_input(text)
        if code:
            self._manual_code = code
        return bool(code)

    def stop(self):
        self._stopped = True
