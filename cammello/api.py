"""MediaWiki / Wikimedia Commons API client."""
import json
import logging
import os
import requests
from .constants import *
from .constants import __version__
from .sdc import extract_name_from_caption
from .i18n import tr


REDACT_KEYS = {'password', 'lgpassword', 'token', 'lgtoken', 'logintoken'}


class LocalFileError(Exception):
    """The file could not be READ from the local disk (0.16.1).

    Kept apart from every other upload failure for two reasons, both learned
    from a user who lost 490 of 501 files to it:

      * The message has to name the LOCAL PATH. The old code let the bare
        OSError escape, and the surrounding log line names the COMMONS
        TARGET name - so the report pointed at a file that does not exist on
        the user's disk, and there was no way to tell which photo was
        actually unreadable.
      * It is worth RETRYING. A server rejection (bad filename, missing
        licence) will fail again on a resume, which is why the journal skips
        failed entries. A local read error is the opposite: it usually means
        the file was offline (a cloud placeholder), on a disconnected drive
        or on removed media, and once that is sorted out the very same file
        goes up fine.

    `path` is the local file, `reason` the original OSError text.
    """

    def __init__(self, path, reason):
        self.path = path
        self.reason = reason
        self.remote = is_remote_path(path)
        msg = tr('The file could not be read: {path} ({reason})').format(
            path=path, reason=reason)
        if self.remote:
            # 0.16.1 (Harald: "nur bei Problemen hinweisen"): the hint is
            # attached HERE, where a read has actually failed - not as a
            # warning when files are added. A network drive works fine most
            # of the time, so warning up front would cry wolf; at this point
            # it is the single most useful sentence we can offer, because a
            # dropped share is exactly what this failure looks like.
            msg += ' ' + tr('The file is on a network or removable drive. '
                            'Copy it to a local folder and try again.')
        super().__init__(msg)


def is_remote_path(path):
    """Whether `path` lives on a network share or removable drive.

    Windows: a UNC path (two leading backslashes) is remote by definition;
    for a drive letter GetDriveTypeW is asked - 4 is DRIVE_REMOTE, 2 is
    DRIVE_REMOVABLE. Other systems: anything under the usual mount points
    for mounted volumes.

    Best effort by design. Never raises and never blocks: this runs while an
    upload has already gone wrong, and a wrong guess must cost nothing more
    than a missing hint.
    """
    try:
        path = os.path.abspath(path)
        if sys.platform == 'win32':
            if path.startswith('\\\\'):
                return True
            drive = os.path.splitdrive(path)[0]
            if not drive:
                return False
            import ctypes
            kind = ctypes.windll.kernel32.GetDriveTypeW(f'{drive}\\')
            return kind in (2, 4)      # DRIVE_REMOVABLE, DRIVE_REMOTE
        if sys.platform == 'darwin':
            return path.startswith('/Volumes/')
        return path.startswith(('/media/', '/mnt/', '/run/media/'))
    except Exception:
        return False


class MediaWikiApi:
    def __init__(self, api_url, username, password, timeout=120, logger=None,
                 oauth_token=None, oauth_secret=None):
        self.api_url = api_url
        self.timeout = timeout
        self.log = logger or logging.getLogger(APP_NAME)
        self.session = requests.Session()
        self.session.headers['User-Agent'] = (
            f'{APP_NAME}/{__version__} '
            f'(Python {sys.version_info.major}.{sys.version_info.minor}; PyQt5)'
        )
        self.csrf_token = None
        self.username = username
        self.password = password
        # OAuth 1.0a access credentials (from mw_oauth / the OS keyring). When
        # both are present every request is signed with an Authorization header
        # and no BotPassword login handshake happens. Empty = BotPassword path.
        self._oauth_token = oauth_token or ''
        self._oauth_secret = oauth_secret or ''
        self._use_oauth = bool(self._oauth_token and self._oauth_secret)

    # ── central helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _redact(params):
        if not isinstance(params, dict):
            return params
        out = {}
        for k, v in params.items():
            out[k] = '***' if k in REDACT_KEYS else v
        return out

    @staticmethod
    def _explain_badfilename(requested, stored):
        """A human-readable message for the upload API's 'badfilename'
        warning: name the offending character(s) instead of echoing the
        server's bare corrected name."""
        illegal = {':': 'colon', '/': 'slash', '\\': 'backslash'}
        found = sorted({c for c in str(requested) if c in illegal})
        stored = str(stored).replace('_', ' ')
        if found:
            chars = ', '.join(f'{c!r} ({illegal[c]})' for c in found)
            return (f'badfilename: MediaWiki forbids {chars} in file names '
                    f'and would store "{stored}" instead of "{requested}". '
                    f'Please rename the file (e.g. ":" \u2192 " \u2013").')
        return (f'badfilename: MediaWiki would normalize the name to '
                f'"{stored}" (requested: "{requested}"). Please adjust the '
                f'target filename.')

    @staticmethod
    def _trunc(text, n=2000):
        if text is None:
            return ''
        text = str(text)
        return text if len(text) <= n else text[:n] + f'… [{len(text)} chars]'

    def _request(self, method, desc, **kwargs):
        """Perform an HTTP request and log it fully."""
        url = kwargs.pop('url', self.api_url)
        kwargs.setdefault('timeout', self.timeout)

        payload = kwargs.get('params') or kwargs.get('data') or {}
        file_note = ''
        files = kwargs.get('files')
        if files:
            try:
                names = [v[0] if isinstance(v, (tuple, list)) else 'file'
                         for v in files.values()]
                file_note = ' files=' + ','.join(names)
            except Exception:
                file_note = ' files=<...>'
        self.log.debug('→ %s [%s] params=%s%s',
                       method, desc, self._redact(payload), file_note)

        # OAuth 1.0a: sign every request with the stored access token instead
        # of relying on a login session cookie. Per RFC 5849 the multipart
        # body of a file upload is NOT signed, so when `files` is present only
        # the query parameters (plus the oauth_* parameters) go into the
        # signature base string; the form fields ride in the multipart body.
        if self._use_oauth:
            from . import mw_oauth
            sign_params = dict(kwargs.get('params') or {})
            if not kwargs.get('files'):
                body = kwargs.get('data')
                if isinstance(body, dict):
                    sign_params.update(body)
            headers = dict(kwargs.get('headers') or {})
            headers['Authorization'] = mw_oauth.authorization_header(
                method, url, sign_params,
                self._oauth_token, self._oauth_secret)
            kwargs['headers'] = headers

        try:
            r = self.session.request(method, url, **kwargs)
        except requests.exceptions.RequestException as e:
            self.log.error('✗ Network error during %s: %s', desc, e, exc_info=True)
            raise Exception(f'Network error during {desc}: {e}') from e

        self.log.debug('← [%s] HTTP %s, %s bytes',
                       desc, r.status_code, len(r.content or b''))
        return r

    def _json(self, r, desc):
        """Parse the response as JSON; otherwise raise a meaningful exception."""
        if r.status_code != 200:
            body = self._trunc(r.text)
            self.log.error('✗ HTTP %s during %s. Response: %s',
                           r.status_code, desc, body)
            raise Exception(f'HTTP {r.status_code} during {desc}. Response: {body}')
        try:
            return r.json()
        except ValueError:
            body = self._trunc(r.text)
            self.log.error('✗ Non-JSON response during %s. Response: %s', desc, body)
            raise Exception(
                f'Non-JSON response during {desc} (possibly rate limit, '
                f'maintenance or file too large). Response: {body}'
            )

    def _check_error(self, data, desc):
        """Return (code, info) if the response contains an API error."""
        if isinstance(data, dict) and 'error' in data:
            err = data['error']
            code = err.get('code', 'unknown')
            info = err.get('info') or json.dumps(err, ensure_ascii=False)
            self.log.error('✗ API error during %s: [%s] %s', desc, code, info)
            return code, info
        return None, None

    # ── Login / session ──────────────────────────────────────────────────────

    def _get_login_token(self):
        r = self._request('GET', 'login-token', params={
            'action': 'query', 'meta': 'tokens', 'type': 'login', 'format': 'json'
        })
        j = self._json(r, 'login-token')
        try:
            return j['query']['tokens']['logintoken']
        except (KeyError, TypeError):
            raise Exception('Login token not received. Response: '
                            + self._trunc(json.dumps(j, ensure_ascii=False)))

    def _client_login(self):
        """AuthManager-based login for normal accounts. Returns True on success."""
        token = self._get_login_token()
        r = self._request('POST', 'clientlogin', data={
            'action': 'clientlogin',
            'loginreturnurl': 'https://commons.wikimedia.org',
            'username': self.username, 'password': self.password,
            'logintoken': token, 'format': 'json'
        })
        result = self._json(r, 'clientlogin')
        cl = result.get('clientlogin', {})
        status = cl.get('status')
        if status == 'PASS':
            self.log.info('clientlogin succeeded.')
            return True
        cl_msg = cl.get('message') or cl.get('messagecode') or status
        if status in ('UI', 'REDIRECT'):
            self.log.warning(
                'clientlogin needs an extra step (status=%s) – usually 2FA, '
                'OAuth or email confirmation, so a normal-account login cannot '
                'complete through this form.', status)
        else:
            self.log.warning('clientlogin not successful (status=%s): %s',
                             status, cl_msg)
        self._last_login_msg = cl_msg
        return False

    def _bot_login(self):
        """action=login, the documented method for BotPasswords (User@bot)."""
        token = self._get_login_token()
        r = self._request('POST', 'bot-login', data={
            'action': 'login', 'lgname': self.username,
            'lgpassword': self.password, 'lgtoken': token, 'format': 'json'
        })
        result = self._json(r, 'bot-login')
        login = result.get('login', {})
        if login.get('result') == 'Success':
            self.log.info('Bot login succeeded.')
            return True
        self._last_login_msg = login.get('reason') or login.get('result') or 'unknown'
        self.log.warning('Bot login not successful: %s', self._last_login_msg)
        return False

    def login(self):
        if not self.api_url.startswith('https://'):
            raise Exception('Security error: API URL must use HTTPS, not HTTP.')

        # OAuth path: there is no login handshake and no session cookie - the
        # Authorization header on every request authenticates us. Just confirm
        # the server sees a real (non-anonymous) user before we start writing.
        if self._use_oauth:
            self.log.info('Authenticating via OAuth (no login call needed) …')
            self._verify_session()
            return True

        self.log.info('Logging in as "%s" …', self.username)
        self._last_login_msg = None

        # BotPassword usernames contain '@' (e.g. "Seewolf@Cammello"). For those,
        # action=login is the documented and reliable method, so try it first;
        # clientlogin/AuthManager can report success for a BotPassword without
        # actually establishing a write-capable session.
        if '@' in self.username:
            methods = [self._bot_login, self._client_login]
        else:
            methods = [self._client_login, self._bot_login]

        for method in methods:
            if method():
                self._verify_session()  # raises if the session is anonymous
                return True

        msg = self._last_login_msg or 'unknown'
        self.log.error('Login failed: %s', msg)
        raise Exception(
            f'Login failed: {msg}. For API uploads to Commons, use a BotPassword '
            f'(Special:BotPasswords) with the "Upload new files" and "Edit '
            f'existing pages" grants.'
        )

    def whoami(self):
        """Return the userinfo of the current session (for "Test connection")."""
        r = self._request('GET', 'userinfo', params={
            'action': 'query', 'meta': 'userinfo', 'format': 'json'
        })
        j = self._json(r, 'userinfo')
        return j.get('query', {}).get('userinfo', {})

    def get_csrf_token(self):
        if self.csrf_token:
            return self.csrf_token
        r = self._request('GET', 'csrf-token', params={
            'action': 'query', 'meta': 'tokens', 'format': 'json'
        })
        j = self._json(r, 'csrf-token')
        try:
            self.csrf_token = j['query']['tokens']['csrftoken']
        except (KeyError, TypeError):
            raise Exception('CSRF token not received. Response: '
                            + self._trunc(json.dumps(j, ensure_ascii=False)))
        return self.csrf_token

    def clear_token(self):
        self.csrf_token = None

    def _verify_session(self):
        """Confirm the session is actually authenticated after login.

        clientlogin/login can report success while the server still treats the
        request as anonymous (e.g. missing BotPassword grants). Catch that here
        instead of failing later with assertuserfailed during the upload.
        """
        info = self.whoami()
        if not info or 'anon' in info or not info.get('id'):
            raise Exception(
                'Login reported success, but the session is anonymous '
                '(server does not see a logged-in user). Check the account / '
                'password, or the grants of the BotPassword.'
            )
        self.log.info('Session verified as user "%s" (id %s).',
                      info.get('name'), info.get('id'))

    def _relogin(self):
        """Re-authenticate after a lost session (assertuserfailed)."""
        self.log.warning('Session lost – re-authenticating…')
        self.clear_token()
        self.login()

    # ── Upload ───────────────────────────────────────────────────────────────

    @staticmethod
    def check_readable(filepath):
        """Raise LocalFileError unless the file can actually be read.

        Opening is not enough to tell: Windows hands out a handle for a
        OneDrive placeholder or a file on a dropped network share and only
        fails when the data is asked for. So one byte is actually read.
        Cheap - one open and one byte - and it turns a traceback from deep
        inside requests into a sentence naming the file.
        """
        try:
            with open(filepath, 'rb') as fh:
                fh.read(1)
        except OSError as e:
            raise LocalFileError(filepath, e.strerror or str(e)) from e

    def upload(self, filename, filepath, wikitext, comment, ignore_warnings=False):
        # Before anything else: can this file be read at all? (0.16.1)
        self.check_readable(filepath)
        size = os.path.getsize(filepath) if os.path.exists(filepath) else -1
        self.log.info('Uploading "%s" (%.1f MB)…',
                      filename, size / 1e6 if size > 0 else 0.0)
        self.log.debug('Wikitext for "%s":\n%s', filename, wikitext)

        for attempt in (1, 2):  # one retry on badtoken or lost session
            token = self.get_csrf_token()
            with open(filepath, 'rb') as f:
                data = {
                    'action': 'upload', 'filename': filename,
                    'text': wikitext, 'comment': comment,
                    'token': token, 'format': 'json', 'assert': 'user',
                }
                if ignore_warnings:
                    data['ignorewarnings'] = '1'
                try:
                    r = self._request(
                        'POST', f'upload {filename}', data=data,
                        files={'file': (os.path.basename(filepath), f)})
                except OSError as e:
                    # requests reads the handle itself while building the
                    # multipart body, so a disk that goes away mid-run
                    # surfaces HERE, not at check_readable above. Same
                    # translation, so both look alike to the user.
                    raise LocalFileError(filepath,
                                         e.strerror or str(e)) from e
            result = self._json(r, f'upload {filename}')

            code, info = self._check_error(result, f'upload {filename}')
            if code:
                if code == 'badtoken' and attempt == 1:
                    self.log.warning('badtoken – fetching new token, retrying.')
                    self.clear_token()
                    continue
                if code in ('assertuserfailed', 'mustbeloggedin') and attempt == 1:
                    self._relogin()
                    continue
                raise Exception(f'[{code}] {info}')

            upload = result.get('upload', {})
            res = upload.get('result')
            self.log.debug('upload result=%s for "%s"', res, filename)

            if res == 'Success':
                self.log.info('✓ Uploaded: "%s"', filename)
                return True

            warnings = upload.get('warnings', {})
            if warnings:
                if 'exists' in warnings and ignore_warnings:
                    self.log.info('File exists – overwriting "%s".', filename)
                    return True
                if 'badfilename' in warnings:
                    # Translate the server's terse warning into what actually
                    # happened: which character(s) MediaWiki refused and what
                    # name it would store instead ($wgIllegalFileChars: each
                    # ':', '/' or '\' becomes '-'). normalize_commons_filename
                    # catches these before the request; this branch remains
                    # for names that MediaWiki normalizes for OTHER reasons.
                    raise Exception(self._explain_badfilename(
                        filename, warnings['badfilename']))
                detail = ', '.join(f'{k}={v}' for k, v in warnings.items())
                raise Exception(f'Warnings: {detail}')

            # Unexpected structure: do NOT treat as success.
            raise Exception(
                f'Upload failed (result={res!r}). Response: '
                + self._trunc(json.dumps(result, ensure_ascii=False))
            )

        raise Exception('Upload failed after retry (badtoken or lost session).')

    def get_page_id(self, filename):
        r = self._request('GET', 'page-id', params={
            'action': 'query', 'titles': f'File:{filename}', 'format': 'json'
        })
        j = self._json(r, 'page-id')
        pages = j.get('query', {}).get('pages', {})
        if not pages:
            self.log.warning('No page id found for "%s".', filename)
            return None
        page = next(iter(pages.values()))
        pid = page.get('pageid')
        self.log.debug('pageid for "%s" = %s', filename, pid)
        return pid

    def set_structured_data(self, page_id, labels, claims):
        """Set labels and claims in a single wbeditentity call."""
        labels_data = {lang: {'language': lang, 'value': val}
                       for lang, val in labels.items() if val}

        claims_data = []
        for prop, value in claims:
            # 0.12.15: a claim value is either a QID string (all the item
            # properties) or a ('coord', lat, lon) tuple for P1259. Two
            # datatypes, one list - the caller should not have to build
            # Wikibase JSON.
            if isinstance(value, (tuple, list)) and value and value[0] == 'coord':
                _tag, lat, lon = value
                claims_data.append({
                    'mainsnak': {
                        'snaktype': 'value',
                        'property': prop,
                        'datavalue': {
                            'type': 'globecoordinate',
                            'value': {
                                'latitude': float(lat),
                                'longitude': float(lon),
                                'altitude': None,
                                # 1e-6 deg is ~0.1 m; the value Commons uses
                                # for camera coordinates by default.
                                'precision': 1e-6,
                                'globe': 'http://www.wikidata.org/entity/Q2',
                            }
                        }
                    },
                    'type': 'statement',
                    'rank': 'normal'
                })
                continue
            # 0.15.0: ('quantity', amount, unit_qid_or_None) for the EXIF
            # capture settings (exposure time, f-number, ISO, focal
            # length). Wikibase wants the amount as a SIGNED STRING and the
            # unit as an entity URI - or the literal string '1' for a
            # dimensionless number, NOT None.
            # 0.15.0: ('time', 'YYYY-MM-DD') for inception (P571). Day
            # precision (11) on purpose - that is what the community sets,
            # and the camera clock's minutes add nothing but noise.
            if isinstance(value, (tuple, list)) and value \
                    and value[0] == 'time':
                _tag, iso_date = value
                claims_data.append({
                    'mainsnak': {
                        'snaktype': 'value',
                        'property': prop,
                        'datavalue': {
                            'type': 'time',
                            'value': {
                                'time': f'+{iso_date}T00:00:00Z',
                                'timezone': 0, 'before': 0, 'after': 0,
                                'precision': 11,
                                'calendarmodel':
                                    'http://www.wikidata.org/entity/Q1985727',
                            }
                        }
                    },
                    'type': 'statement',
                    'rank': 'normal'
                })
                continue
            # 0.15.2: ('monolingual', text, lang) for alt text (P11265).
            # Wikibase wants text and language in one value object.
            if isinstance(value, (tuple, list)) and value \
                    and value[0] == 'monolingual':
                _tag, text, lang = value
                claims_data.append({
                    'mainsnak': {
                        'snaktype': 'value',
                        'property': prop,
                        'datavalue': {
                            'type': 'monolingualtext',
                            'value': {'text': str(text),
                                      'language': str(lang)},
                        }
                    },
                    'type': 'statement',
                    'rank': 'normal'
                })
                continue
            # 0.15.0: ('string', text) for plain-string properties such as
            # the media type (P1163).
            if isinstance(value, (tuple, list)) and value \
                    and value[0] == 'string':
                claims_data.append({
                    'mainsnak': {
                        'snaktype': 'value',
                        'property': prop,
                        'datavalue': {'type': 'string',
                                      'value': str(value[1])},
                    },
                    'type': 'statement',
                    'rank': 'normal'
                })
                continue
            if isinstance(value, (tuple, list)) and value \
                    and value[0] == 'quantity':
                _tag, amount, unit_qid = value
                unit = ('http://www.wikidata.org/entity/' + unit_qid
                        if unit_qid else '1')
                amt = ('%+.10g' % float(amount))
                claims_data.append({
                    'mainsnak': {
                        'snaktype': 'value',
                        'property': prop,
                        'datavalue': {
                            'type': 'quantity',
                            'value': {'amount': amt, 'unit': unit},
                        }
                    },
                    'type': 'statement',
                    'rank': 'normal'
                })
                continue
            qid = (value or '').strip()
            m = re.match(r'^Q(\d+)$', qid, flags=re.IGNORECASE)
            if not m:
                self.log.warning('Invalid QID for %s skipped: %r', prop, qid)
                continue
            numeric_id = int(m.group(1))
            qid = f'Q{numeric_id}'  # normalize (e.g. "q123" -> "Q123")
            claims_data.append({
                'mainsnak': {
                    'snaktype': 'value',
                    'property': prop,
                    'datavalue': {
                        'type': 'wikibase-entityid',
                        'value': {'entity-type': 'item',
                                  'numeric-id': numeric_id, 'id': qid}
                    }
                },
                'type': 'statement',
                'rank': 'normal'
            })

        if not labels_data and not claims_data:
            self.log.debug('No SDC data for M%s.', page_id)
            return

        data = {}
        if labels_data:
            data['labels'] = labels_data
        if claims_data:
            data['claims'] = claims_data

        self.log.debug('SDC payload for M%s: %s',
                       page_id, self._trunc(json.dumps(data, ensure_ascii=False)))

        for attempt in (1, 2):
            token = self.get_csrf_token()
            r = self._request('POST', f'wbeditentity M{page_id}', data={
                'action': 'wbeditentity', 'id': f'M{page_id}',
                'data': json.dumps(data), 'token': token,
                'format': 'json', 'assert': 'user'
            })
            result = self._json(r, f'wbeditentity M{page_id}')
            code, info = self._check_error(result, f'wbeditentity M{page_id}')
            if code:
                if code in ('badtoken', 'invalid-csrf-token') and attempt == 1:
                    self.log.warning('SDC badtoken – new token, retrying.')
                    self.clear_token()
                    continue
                if code in ('assertuserfailed', 'mustbeloggedin') and attempt == 1:
                    self._relogin()
                    continue
                raise Exception(f'[{code}] {info}')
            self.log.info('✓ Structured data set for M%s.', page_id)
            return

        raise Exception('wbeditentity failed after badtoken retry.')

    def purge(self, page_title):
        """Purge a page and update its links tables.

        action=purge is POST-only and needs no CSRF token. forcelinkupdate=1
        is essential here: a plain purge only re-renders the page, while the
        links tables (which control category membership, e.g. the "missing
        SDC" maintenance categories) are only refreshed with forcelinkupdate.
        Returns True on success, False otherwise; never raises.
        """
        try:
            r = self._request('POST', f'purge {page_title}', data={
                'action': 'purge',
                'titles': page_title,
                'forcelinkupdate': 1,
                'format': 'json',
            })
            data = self._json(r, 'purge')
            code, info = self._check_error(data, 'purge')
            if code:
                self.log.warning('Purge failed for %s: [%s] %s',
                                 page_title, code, info)
                return False
            entries = data.get('purge', [])
            ok = any('purged' in e for e in entries)
            if ok:
                self.log.info('✓ Purged (with link update): %s', page_title)
            else:
                self.log.warning('Purge response without "purged" for %s: %s',
                                 page_title, entries)
            return ok
        except Exception as e:
            self.log.warning('Purge failed for %s: %s', page_title, e)
            return False

    # ── Gallery ──────────────────────────────────────────────────────────────

    def get_page_content(self, page_title):
        """Raw wikitext of a page, or None if the page DOES NOT EXIST.

        A failed fetch is NOT None - it raises. The distinction matters:
        update_gallery treats None as "create a fresh page", so silently
        turning a transient 503 into None would let it overwrite a grown
        gallery with just the current session's files.
        """
        index_url = self.api_url.replace('api.php', 'index.php')
        r = self._request('GET', f'raw {page_title}', url=index_url,
                          params={'action': 'raw', 'title': page_title})
        if r.status_code == 200:
            return r.text
        if r.status_code == 404:
            self.log.debug('Gallery page "%s" does not exist yet.', page_title)
            return None
        raise Exception(
            f'Could not read page "{page_title}": HTTP {r.status_code}. '
            f'Not editing it, to avoid overwriting existing content.')

    def set_page_content(self, page_title, content, comment):
        for attempt in (1, 2):
            token = self.get_csrf_token()
            r = self._request('POST', f'edit {page_title}', data={
                'action': 'edit', 'title': page_title,
                'text': content, 'summary': comment,
                'token': token, 'format': 'json', 'assert': 'user'
            })
            result = self._json(r, f'edit {page_title}')
            code, info = self._check_error(result, f'edit {page_title}')
            if code:
                if code in ('badtoken', 'invalid-csrf-token') and attempt == 1:
                    self.clear_token()
                    continue
                if code in ('assertuserfailed', 'mustbeloggedin') and attempt == 1:
                    self._relogin()
                    continue
                raise Exception(f'[{code}] {info}')
            self.log.info('✓ Gallery "%s" updated.', page_title)
            return

        raise Exception('Gallery edit failed after badtoken retry.')

    def update_gallery(self, gallery_page, file_entries):
        """Append file entries to gallery page."""
        gallery_open = '<gallery mode="packed-hover" heights="240">'
        gallery_close = '</gallery>'
        comment = f'Uploaded with {APP_NAME}'

        self.log.info('Updating gallery "%s" (%d entries)…',
                      gallery_page, len(file_entries))

        new_entries = ''
        for fname, caption in file_entries:
            name = extract_name_from_caption(caption)
            # Sanitize caption: remove newlines/pipes to prevent wikitext injection
            if name:
                name = name.replace('|', '-').replace('\n', ' ').replace('\r', '')
                new_entries += f'File:{fname}|{name}\n'
            else:
                new_entries += f'File:{fname}\n'

        existing = self.get_page_content(gallery_page)
        if existing and gallery_close in existing:
            # Normal case: slot the new lines in before the LAST closing tag,
            # so everything else on the page - intro text, other sections,
            # categories below the gallery - is preserved untouched.
            idx = existing.rfind(gallery_close)
            new_content = existing[:idx] + new_entries + existing[idx:]
        elif existing:
            # The page exists but has no gallery yet. Append a COMPLETE new
            # gallery block: the opening tag has to be written too, otherwise
            # the file lines end up as plain text followed by a stray closing
            # tag.
            new_content = (existing.rstrip() + '\n\n' + gallery_open + '\n'
                           + new_entries + gallery_close)
        else:
            new_content = gallery_open + '\n' + new_entries + gallery_close

        self.set_page_content(gallery_page, new_content, comment)


# ── Upload worker thread ───────────────────────────────────────────────────────
