"""Flickr upload support (0.10.0).

OAuth 1.0a is implemented with the standard library only (hmac/hashlib/
base64/urllib.parse/secrets) - no new dependency; HTTP goes through the
already-present `requests`. The signing machinery is verified in
test_flickr.py against the canonical example vector from the OAuth Core 1.0
specification (consumer dpf43f3p2l4k3l03, expected signature
tR3+Ty81lMeYAr/Fid0kMTYa/WM=).

Design decision for the upload: the multipart body carries ONLY the photo.
RFC 5849 excludes multipart body parameters from the signature base string,
but Flickr's pre-OAuth upload documentation required signing all non-file
parameters - two readings that disagree. Sending no extra form fields makes
both readings identical, so the upload signature is unambiguous; the title is
set afterwards with a normal signed REST call (flickr.photos.setMeta), where
signing IS unambiguous. Costs one extra request per photo, removes a whole
class of 'invalid signature' failures.

The user needs an API key/secret from https://www.flickr.com/services/apps/create
and a one-time browser authorization (perms=write, out-of-band verifier).
"""
import base64
import hashlib
import hmac
import os
import secrets
import time
import xml.etree.ElementTree as ET
from urllib.parse import quote, urlencode, parse_qsl

import requests

from PyQt5.QtCore import QThread, pyqtSignal

from .i18n import tr

# Flickr license IDs (flickr.photos.licenses.getInfo; documented, stable).
# VERIFY: not re-checked against the live API from the build environment.
LICENSES = [
    ('0', 'All rights reserved'),
    ('4', 'CC BY 2.0'),
    ('5', 'CC BY-SA 2.0'),
    ('1', 'CC BY-NC-SA 2.0'),
    ('2', 'CC BY-NC 2.0'),
    ('3', 'CC BY-NC-ND 2.0'),
    ('6', 'CC BY-ND 2.0'),
    ('9', 'CC0 1.0'),
    ('10', 'Public Domain Mark 1.0'),
]

REQUEST_TOKEN_URL = 'https://www.flickr.com/services/oauth/request_token'
AUTHORIZE_URL = 'https://www.flickr.com/services/oauth/authorize'
ACCESS_TOKEN_URL = 'https://www.flickr.com/services/oauth/access_token'
REST_URL = 'https://api.flickr.com/services/rest/'
UPLOAD_URL = 'https://up.flickr.com/services/upload/'


def _enc(value):
    """Percent-encoding as required by OAuth 1.0 (RFC 3986 unreserved set)."""
    return quote(str(value), safe='-._~')


def oauth_signature(method, url, params, consumer_secret, token_secret=''):
    """HMAC-SHA1 signature over the OAuth base string.

    params: every oauth_* parameter plus any query/form-urlencoded parameters
    of the request (multipart body parameters are excluded per RFC 5849).
    """
    pairs = sorted((_enc(k), _enc(v)) for k, v in params.items())
    param_string = '&'.join(f'{k}={v}' for k, v in pairs)
    base = '&'.join((method.upper(), _enc(url), _enc(param_string)))
    key = f'{_enc(consumer_secret)}&{_enc(token_secret)}'
    digest = hmac.new(key.encode('ascii'), base.encode('ascii'),
                      hashlib.sha1).digest()
    return base64.b64encode(digest).decode('ascii')


def oauth_base_params(consumer_key, token=None):
    p = {
        'oauth_consumer_key': consumer_key,
        'oauth_nonce': secrets.token_hex(16),
        'oauth_signature_method': 'HMAC-SHA1',
        'oauth_timestamp': str(int(time.time())),
        'oauth_version': '1.0',
    }
    if token:
        p['oauth_token'] = token
    return p


class FlickrError(RuntimeError):
    pass


class FlickrClient:
    """Small OAuth 1.0a client for the handful of calls Cammello needs."""

    def __init__(self, api_key, api_secret, token='', token_secret='',
                 timeout=60, logger=None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.token = token
        self.token_secret = token_secret
        self.timeout = timeout
        self.log = logger

    # ── Authorization flow (out-of-band / 9-digit verifier) ─────────────────

    def get_request_token(self):
        """-> (token, token_secret). Step 1 of the authorization."""
        params = oauth_base_params(self.api_key)
        params['oauth_callback'] = 'oob'
        params['oauth_signature'] = oauth_signature(
            'GET', REQUEST_TOKEN_URL, params, self.api_secret, '')
        r = requests.get(REQUEST_TOKEN_URL, params=params,
                         timeout=self.timeout)
        data = dict(parse_qsl(r.text))
        if r.status_code != 200 or 'oauth_token' not in data:
            raise FlickrError(f'request_token failed (HTTP {r.status_code}): '
                              f'{r.text[:200]}')
        return data['oauth_token'], data['oauth_token_secret']

    @staticmethod
    def authorize_url(request_token):
        """Step 2: the user opens this in a browser and gets a verifier."""
        return (f'{AUTHORIZE_URL}?'
                + urlencode({'oauth_token': request_token, 'perms': 'write'}))

    def get_access_token(self, request_token, request_secret, verifier):
        """Step 3: -> (token, token_secret, username)."""
        params = oauth_base_params(self.api_key, request_token)
        params['oauth_verifier'] = verifier.strip()
        params['oauth_signature'] = oauth_signature(
            'GET', ACCESS_TOKEN_URL, params, self.api_secret, request_secret)
        r = requests.get(ACCESS_TOKEN_URL, params=params,
                         timeout=self.timeout)
        data = dict(parse_qsl(r.text))
        if r.status_code != 200 or 'oauth_token' not in data:
            raise FlickrError(f'access_token failed (HTTP {r.status_code}): '
                              f'{r.text[:200]}')
        return (data['oauth_token'], data['oauth_token_secret'],
                data.get('username', ''))

    # ── Signed REST calls ────────────────────────────────────────────────────

    def rest(self, method, **kwargs):
        """Signed POST to the REST endpoint; returns the parsed JSON."""
        params = oauth_base_params(self.api_key, self.token)
        params.update({'method': method, 'format': 'json',
                       'nojsoncallback': '1'})
        params.update({k: str(v) for k, v in kwargs.items()})
        params['oauth_signature'] = oauth_signature(
            'POST', REST_URL, params, self.api_secret, self.token_secret)
        r = requests.post(REST_URL, data=params, timeout=self.timeout)
        try:
            payload = r.json()
        except ValueError:
            raise FlickrError(f'{method}: non-JSON reply '
                              f'(HTTP {r.status_code}): {r.text[:200]}')
        if payload.get('stat') != 'ok':
            raise FlickrError(f'{method}: {payload.get("message", payload)}')
        return payload

    def test_login(self):
        """-> username of the authorized account."""
        payload = self.rest('flickr.test.login')
        return payload.get('user', {}).get('username', {}).get('_content', '')

    # ── Upload ───────────────────────────────────────────────────────────────

    def upload(self, path):
        """Uploads one file, returns the new photo id.

        The multipart body contains ONLY the photo (see module docstring), so
        the signature covers just the oauth_* parameters - unambiguous under
        both RFC 5849 and Flickr's own legacy signing rules.
        """
        params = oauth_base_params(self.api_key, self.token)
        params['oauth_signature'] = oauth_signature(
            'POST', UPLOAD_URL, params, self.api_secret, self.token_secret)
        with open(path, 'rb') as f:
            r = requests.post(
                UPLOAD_URL, data=params,
                files={'photo': (os.path.basename(path), f)},
                timeout=max(self.timeout, 300))
        root = ET.fromstring(r.text)
        if root.get('stat') != 'ok':
            err = root.find('err')
            msg = (err.get('msg') if err is not None else r.text[:200])
            raise FlickrError(f'upload: {msg}')
        photoid = root.findtext('photoid')
        if not photoid:
            raise FlickrError(f'upload: no photoid in reply: {r.text[:200]}')
        return photoid

    def set_title(self, photo_id, title, description=''):
        self.rest('flickr.photos.setMeta', photo_id=photo_id, title=title,
                  description=description)

    def set_license(self, photo_id, license_id):
        self.rest('flickr.photos.licenses.setLicense', photo_id=photo_id,
                  license_id=license_id)


class FlickrUploadWorker(QThread):
    """Batch upload, same interface as FtpUploadWorker: progress per file,
    cancel between files, summary at the end. files: [(path, title)]."""
    file_started = pyqtSignal(int, str)
    progress = pyqtSignal(int, str)
    error = pyqtSignal(int, str)
    finished = pyqtSignal(str)

    def __init__(self, client, files, logger, license_id=None):
        super().__init__()
        self.client = client
        self.files = files
        self.log = logger
        self.license_id = license_id      # None = account default
        self._cancelled = False

    def cancel(self):
        self._cancelled = True
        self.log.info('[Flickr] Cancel requested: stopping after the '
                      'current file.')

    def run(self):
        total = len(self.files)
        self.log.info('=== Flickr upload started: %d file(s) ===', total)
        ok = failed = 0
        cancelled_at = None
        for i, (path, title) in enumerate(self.files):
            if self._cancelled:
                cancelled_at = i
                self.progress.emit(i, tr('Cancelled'))
                break
            name = os.path.basename(path)
            self.file_started.emit(i, name)
            self.progress.emit(i, tr('Uploading…'))
            try:
                photo_id = self.client.upload(path)
                if title:
                    try:
                        self.client.set_title(photo_id, title)
                    except Exception as e:
                        # The photo IS on Flickr; only the title failed.
                        self.log.warning('[Flickr] setMeta failed for %s: %s',
                                         name, e)
                if self.license_id is not None:
                    try:
                        self.client.set_license(photo_id, self.license_id)
                    except Exception as e:
                        # The photo IS on Flickr; only the license failed.
                        self.log.warning('[Flickr] setLicense failed for '
                                         '%s: %s', name, e)
            except Exception as e:
                failed += 1
                self.log.error('✗ [Flickr] "%s": %s', name, e)
                self.error.emit(i, f'{name}: {e}')
                self.progress.emit(i, '✗ ' + tr('Error'))
                continue
            ok += 1
            self.log.info('✓ [Flickr] "%s" -> photo %s', name, photo_id)
            self.progress.emit(i, '✓ ' + tr('Sent'))
        if cancelled_at is not None:
            summary = tr('Cancelled: {ok}/{total} file(s) sent, '
                         '{skipped} not started.').format(
                ok=ok, total=total, skipped=total - cancelled_at)
        else:
            summary = tr('Done: {ok}/{total} file(s) sent.').format(
                ok=ok, total=total)
            if failed:
                summary += ' ' + tr('{n} failed').format(n=failed) + '.'
        self.log.info('=== Flickr upload finished: %s ===', summary)
        self.finished.emit(summary)
