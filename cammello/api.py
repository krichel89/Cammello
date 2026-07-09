"""MediaWiki / Wikimedia Commons API client."""
import json
import logging
import requests
from .constants import *
from .constants import __version__


REDACT_KEYS = {'password', 'lgpassword', 'token', 'lgtoken', 'logintoken'}

class MediaWikiApi:
    def __init__(self, api_url, username, password, timeout=120, logger=None):
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

    def upload(self, filename, filepath, wikitext, comment, ignore_warnings=False):
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
                r = self._request('POST', f'upload {filename}', data=data,
                                  files={'file': (os.path.basename(filepath), f)})
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
        for prop, qid in claims:
            qid = (qid or '').strip()
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
        """Get raw wikitext of a page."""
        index_url = self.api_url.replace('api.php', 'index.php')
        r = self._request('GET', f'raw {page_title}', url=index_url,
                          params={'action': 'raw', 'title': page_title})
        if r.status_code == 200:
            return r.text
        if r.status_code == 404:
            self.log.debug('Gallery page "%s" does not exist yet.', page_title)
            return None
        self.log.warning('Gallery page "%s": HTTP %s', page_title, r.status_code)
        return None

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
            idx = existing.rfind(gallery_close)
            new_content = existing[:idx] + new_entries + existing[idx:]
        elif existing:
            new_content = existing.rstrip() + '\n' + new_entries + gallery_close
        else:
            new_content = gallery_open + '\n' + new_entries + gallery_close

        self.set_page_content(gallery_page, new_content, comment)


# ── Upload worker thread ───────────────────────────────────────────────────────
