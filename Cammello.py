#!/usr/bin/env python3
"""
Cammello v0.5.1 - Batch upload tool for Wikimedia Commons

Replaces VicunaUploader with structured data (SDC) support (caption_*, creator,
depicts, etc.).

New in 0.5.1:
  * BotPassword-first login (action=login for "User@bot" names), post-login
    session verification, and automatic re-login on a lost session.
  * Fixed EXIF capture-date reading (DateTimeOriginal lives in the EXIF sub-IFD).
  * Automatic maintenance category [[Category:Uploaded with Cammello]].
  * Save upload settings and the base description (button + on close); both are
    restored on the next start.

New in 0.5.0:
  * Renamed from CommonsSDC to Cammello.
  * Fully English user interface, comments and log messages.

From 0.4.0 (table UI):
  * Per-file thumbnail preview (left column), loaded efficiently downscaled
    (QImageReader) with EXIF orientation applied.
  * Wider source-file column; column widths freely adjustable.
  * The extension in the target filename is fixed (taken from the source file)
    and cannot be changed.

From 0.3.0:
  * Freely chosen target filename on Commons ("Target filename" column), with
    automatic extension handling and rejection of invalid characters.

From 0.2.0 (debugging focus):
  * Consistent logging (file + live log tab + console); credentials/tokens are
    masked in the log.
  * Every API call goes through central helpers that cleanly handle HTTP status,
    non-JSON responses and network errors -- there are no more "empty" errors.
  * The full wikitext and SDC payload are written to the log per file.
  * badtoken retry (one more attempt with a fresh CSRF token).
  * Configurable HTTP timeout.
  * "Test connection" (whoami) to verify the login state.

Requirements: pip install PyQt5 requests Pillow
License: CC0
"""

import sys
import os
import re
import json
import logging
import tempfile
import traceback
from logging.handlers import RotatingFileHandler
from datetime import datetime

import requests

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QPushButton, QLabel, QLineEdit,
    QTextEdit, QFileDialog, QMessageBox, QProgressBar, QSplitter,
    QGroupBox, QFormLayout, QHeaderView, QAbstractItemView, QDialog,
    QDialogButtonBox, QCheckBox, QStatusBar, QTabWidget, QPlainTextEdit,
    QStyledItemDelegate
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSettings, QObject, QUrl, QSize
from PyQt5.QtGui import QPixmap, QFont, QDesktopServices, QIcon, QImageReader

try:
    from PIL import Image
    from PIL.ExifTags import TAGS
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

__version__ = '0.5.1'
APP_NAME = 'Cammello'

# Maintenance category added to every uploaded file.
TRACKING_CATEGORY = f'Uploaded with {APP_NAME}'
TRACKING_CATEGORY_WIKITEXT = f'[[Category:{TRACKING_CATEGORY}]]'

# ── Logging infrastructure ──────────────────────────────────────────────────────

REDACT_KEYS = {'password', 'lgpassword', 'token', 'lgtoken', 'logintoken'}


def get_log_path():
    """Return a writable path for the log file."""
    base = os.path.join(os.path.expanduser('~'), APP_NAME)
    try:
        os.makedirs(base, exist_ok=True)
        return os.path.join(base, 'cammello_debug.log')
    except Exception:
        return os.path.join(tempfile.gettempdir(), 'cammello_debug.log')


class LogEmitter(QObject):
    """Bridge between the (thread-foreign) logging and the GUI.

    pyqtSignal provides a queued connection when emitted from the worker
    thread -- therefore thread-safe for updating the log view.
    """
    log_record = pyqtSignal(str)


class QtLogHandler(logging.Handler):
    def __init__(self, emitter):
        super().__init__()
        self.emitter = emitter

    def emit(self, record):
        try:
            self.emitter.log_record.emit(self.format(record))
        except Exception:
            pass


def setup_logging():
    """Set up file, GUI and console logging.

    Returns: (logger, emitter, gui_handler, log_path)
    """
    log_path = get_log_path()
    logger = logging.getLogger(APP_NAME)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    fmt = logging.Formatter('%(asctime)s %(levelname)-7s %(message)s',
                            '%Y-%m-%d %H:%M:%S')

    # File handler: always full detail (DEBUG) so nothing is lost.
    try:
        fh = RotatingFileHandler(log_path, maxBytes=2_000_000,
                                 backupCount=3, encoding='utf-8')
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except Exception:
        pass  # Continue without a file log if necessary.

    # GUI handler: INFO by default, DEBUG via the verbose checkbox.
    emitter = LogEmitter()
    gui_handler = QtLogHandler(emitter)
    gui_handler.setLevel(logging.INFO)
    gui_handler.setFormatter(fmt)
    logger.addHandler(gui_handler)

    # Console handler (e.g. when started from a terminal).
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    logger.info('%s %s started. Log file: %s', APP_NAME, __version__, log_path)
    return logger, emitter, gui_handler, log_path


# ── Structured data extraction (logic unchanged since v0.1.1) ───────────────────

SD_KEYS = [
    'creator', 'copyright', 'license', 'depicts', 'gallery_suffix',
]

PROPERTY_MAP = {
    'creator': 'P170',
    'copyright': 'P6216',
    'license': 'P275',
    'depicts': 'P180',
}

NAME_SEPARATORS = [' at ', ' bei ', ' à ', ' al ', ' auf ', ' sur ', ' on ', ' sul ']


def extract_structured_data(text):
    """Extract key=value lines from description_all text.
    Lines starting with # are treated as comments and removed."""
    sd = {}
    # Remove comment lines (starting with #)
    text = re.sub(r'^#[^\n]*\n?', '', text, flags=re.MULTILINE)
    result = text

    # Dynamically extract all caption_XX= lines (any language code)
    for m in re.finditer(r'(?:^|\n)caption_([a-z]{2,3})=([^\n]+)', result):
        lang = m.group(1)
        val = m.group(2).strip()
        sd['caption_' + lang] = val
    # Remove all matched caption_XX= lines from result
    result = re.sub(r'\ncaption_[a-z]{2,3}=[^\n]+', '', result)
    result = re.sub(r'^caption_[a-z]{2,3}=[^\n]+\n?', '', result, flags=re.MULTILINE)

    for key in SD_KEYS:
        # Match at start of string
        m = re.match(rf'^{key}=([^\n]+)', result)
        if not m:
            # Match after newline
            m = re.search(rf'\n{key}=([^\n]+)', result)
        if m:
            sd[key] = m.group(1).strip()
            result = re.sub(rf'\n{key}=[^\n]+', '', result)
            result = re.sub(rf'^{key}=[^\n]+\n?', '', result, flags=re.MULTILINE)

    return sd, result.strip()


def extract_name_from_caption(caption):
    """Extract person name from caption (everything before 'at', 'bei', etc.)"""
    if not caption:
        return caption
    for sep in NAME_SEPARATORS:
        if sep in caption:
            return caption.split(sep)[0].strip()
    return caption


def read_exif_date(filepath, log=None):
    """Read the capture date from EXIF data.

    DateTimeOriginal (36867) and DateTimeDigitized (36868) live in the EXIF
    sub-IFD (0x8769); DateTime (306) is in the base IFD. img.getexif() only
    exposes the base IFD directly, so the sub-IFD must be read explicitly.
    """
    if not HAS_PIL:
        return ''
    try:
        img = Image.open(filepath)
        exif = img.getexif()
        if not exif:
            return ''

        candidates = []
        try:
            sub = exif.get_ifd(0x8769)  # EXIF sub-IFD
            candidates.append(sub.get(36867))  # DateTimeOriginal
            candidates.append(sub.get(36868))  # DateTimeDigitized
        except Exception:
            pass
        candidates.append(exif.get(306))       # DateTime (base IFD)

        for value in candidates:
            if value:
                # "2025:01:15 14:30:00" -> "2025-01-15 14:30:00"
                return str(value).replace(':', '-', 2).strip()
        return ''
    except Exception as e:
        if log:
            log.debug('Could not read EXIF date for %s: %s', filepath, e)
        return ''


# ── Target filename on Commons ──────────────────────────────────────────────────

# Extensions accepted as a valid file extension.
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.tif', '.tiff', '.svg', '.webp'}

# Characters that are not allowed in MediaWiki page titles.
FORBIDDEN_TITLE_CHARS = set('#<>[]|{}')


def normalize_commons_filename(target, source_path):
    """Build the target filename for the upload to Commons.

    - strips a leading 'File:'/'Datei:' prefix
    - ensures an (image) extension is present; if missing, the source file's
      extension is appended
    - rejects empty names, overly long names and invalid characters with a
      ValueError (reported by the worker as a meaningful error)

    Returns: the cleaned filename (without 'File:' prefix).
    """
    name = (target or '').strip()

    # Remove namespace prefix (case-insensitive).
    for prefix in ('file:', 'datei:'):
        if name.lower().startswith(prefix):
            name = name[len(prefix):].strip()
            break

    if not name:
        name = os.path.basename(source_path).strip()
    if not name:
        raise ValueError('Empty target filename.')

    # Ensure the extension.
    src_ext = os.path.splitext(source_path)[1]
    _, ext = os.path.splitext(name)
    if ext.lower() not in IMAGE_EXTS:
        if not src_ext:
            raise ValueError('Source file has no extension; please specify an '
                             'extension in the target filename.')
        name = name + src_ext

    bad = sorted({c for c in name if c in FORBIDDEN_TITLE_CHARS or ord(c) < 32})
    if bad:
        raise ValueError(
            'Invalid characters in target filename: '
            + ' '.join(repr(b) for b in bad)
            + ' (not allowed: # < > [ ] | { } and control characters).'
        )

    if len(name.encode('utf-8')) > 240:
        raise ValueError('Target filename too long (max. ~240 bytes).')

    return name


# ── MediaWiki API ──────────────────────────────────────────────────────────────

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
            m = re.match(r'^Q(\d+)$', qid)
            if not m:
                self.log.warning('Invalid QID for %s skipped: %r', prop, qid)
                continue
            numeric_id = int(m.group(1))
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

class UploadWorker(QThread):
    progress = pyqtSignal(int, str)   # row, status
    finished = pyqtSignal(str)        # summary message
    error = pyqtSignal(int, str)      # row, error message

    def __init__(self, api, rows, base_text, gallery_prefix, ignore_warnings):
        super().__init__()
        self.api = api
        self.log = api.log
        self.rows = rows
        self.base_text = base_text
        self.gallery_prefix = gallery_prefix
        self.ignore_warnings = ignore_warnings

    def run(self):
        gallery_entries = {}   # gallery_page -> list of (filename, caption)
        success_count = 0

        self.log.info('=== Upload run started: %d file(s) ===', len(self.rows))

        for i, row in enumerate(self.rows):
            fname = (row.get('target_name')
                     or os.path.basename(row.get('filepath', ''))
                     or f'#{i}')
            try:
                self.progress.emit(i, 'Uploading…')

                # Normalize the target filename: ensure extension, strip a
                # "File:" prefix, reject invalid characters.
                filename = normalize_commons_filename(
                    row.get('target_name', ''), row['filepath'])
                fname = filename
                if filename != row.get('source_name'):
                    self.log.info('Target filename: "%s" → "%s"',
                                  row.get('source_name'), filename)

                sd, clean_desc = extract_structured_data(row['description_all'])
                self.log.debug('File "%s": extracted SD=%s', fname, sd)

                other_templates = row.get('other_templates', '')
                license_text = row.get('license_text', '')

                # Collect categories (deduplicated) from the description.
                cats_seen = set()
                cats = []
                for cat in re.findall(r'\[\[Category:[^\]]+\]\]', clean_desc):
                    if cat not in cats_seen:
                        cats.append(cat)
                        cats_seen.add(cat)
                clean_desc = re.sub(r'\[\[Category:[^\]]+\]\]\n?', '',
                                    clean_desc).strip()

                # Always add the maintenance category (deduplicated).
                if TRACKING_CATEGORY_WIKITEXT not in cats_seen:
                    cats.append(TRACKING_CATEGORY_WIKITEXT)
                    cats_seen.add(TRACKING_CATEGORY_WIKITEXT)

                # {{Information}} block
                info = f"{{{{{row.get('template', 'Information')}\n"
                info += f"|description={clean_desc}\n"
                if row.get('date'):
                    info += f"|date={row['date']}\n"
                if row.get('author'):
                    info += f"|author={row['author']}\n"
                if row.get('source'):
                    info += f"|source={row['source']}\n"
                if row.get('permission'):
                    info += f"|permission={row['permission']}\n"
                if row.get('other_fields'):
                    info += f"|other fields={row['other_fields']}\n"
                info += '}}'

                cats_str = '\n'.join(cats)

                parts = [info]
                if other_templates:
                    parts.append(other_templates)
                if license_text:
                    parts.append(f'== {{{{int:license-header}}}} ==\n{license_text}')
                if cats_str:
                    parts.append(cats_str)
                wikitext = '\n'.join(parts)

                # Upload
                self.api.upload(
                    filename, row['filepath'], wikitext,
                    f'Uploaded with {APP_NAME}', self.ignore_warnings
                )

                # Structured data
                labels = {}
                claims = []
                for key, val in sd.items():
                    if key.startswith('caption_'):
                        lang = key[8:]
                        labels[lang] = val
                    elif key in PROPERTY_MAP:
                        prop = PROPERTY_MAP[key]
                        if key == 'depicts':
                            for qid in val.split(','):
                                qid = qid.strip()
                                if qid:
                                    claims.append((prop, qid))
                        else:
                            claims.append((prop, val))

                if labels or claims:
                    self.api.clear_token()
                    page_id = self.api.get_page_id(filename)
                    if page_id:
                        self.api.set_structured_data(page_id, labels, claims)
                    else:
                        self.log.warning('SDC skipped: no pageid for "%s".', fname)

                # Collect gallery entry
                gallery_suffix = sd.get('gallery_suffix', '').strip()
                if self.gallery_prefix:
                    if gallery_suffix:
                        gallery_page = self.gallery_prefix.rstrip('/') + '/' + gallery_suffix
                    else:
                        gallery_page = self.gallery_prefix
                elif gallery_suffix:
                    gallery_page = None  # no prefix set -> skip gallery
                    self.log.warning('gallery_suffix set but no gallery prefix '
                                     '-> gallery skipped for "%s".', fname)
                else:
                    gallery_page = self.gallery_prefix or None

                caption = sd.get('caption_en', '')
                gallery_entries.setdefault(gallery_page, []).append(
                    (filename, caption)
                )

                self.progress.emit(i, '✓ Done')
                success_count += 1

            except Exception as e:
                # Full text + traceback to the log, compact message to the table.
                self.log.error('✗ Error for "%s": %s', fname, e, exc_info=True)
                msg = str(e) or f'{type(e).__name__} (no message)'
                self.error.emit(i, msg)
                self.progress.emit(i, '✗ Error')

        # Update galleries
        for gallery_page, entries in gallery_entries.items():
            if not gallery_page:
                continue
            try:
                self.api.update_gallery(gallery_page, entries)
            except Exception as e:
                self.log.error('✗ Gallery error (%s): %s',
                               gallery_page, e, exc_info=True)
                self.error.emit(-1, f'Gallery error ({gallery_page}): {e}')

        self.log.info('=== Upload run finished: %d/%d succeeded ===',
                      success_count, len(self.rows))
        self.finished.emit(
            f'Done: {success_count}/{len(self.rows)} file(s) uploaded.'
        )


# ── Login / test worker ────────────────────────────────────────────────────────

class LoginWorker(QThread):
    success = pyqtSignal(object)   # MediaWikiApi instance
    failure = pyqtSignal(str)

    def __init__(self, api_url, username, password, timeout, logger):
        super().__init__()
        self.api_url = api_url
        self.username = username
        self.password = password
        self.timeout = timeout
        self.logger = logger

    def run(self):
        try:
            api = MediaWikiApi(self.api_url, self.username, self.password,
                               timeout=self.timeout, logger=self.logger)
            if api.login():
                self.success.emit(api)
            else:
                self.failure.emit('Invalid credentials.')
        except Exception as e:
            self.logger.error('Login error: %s', e, exc_info=True)
            self.failure.emit(str(e) or f'{type(e).__name__} (no message)')


class TestWorker(QThread):
    done = pyqtSignal(str)
    fail = pyqtSignal(str)

    def __init__(self, api):
        super().__init__()
        self.api = api

    def run(self):
        try:
            info = self.api.whoami()
            name = info.get('name', '?')
            uid = info.get('id', '?')
            groups = ', '.join(info.get('groups', [])) or '–'
            self.done.emit(f'{name} (id {uid}); groups: {groups}')
        except Exception as e:
            self.fail.emit(str(e) or f'{type(e).__name__} (no message)')


# ── Delegate: target filename with a fixed extension ────────────────────────────

class FilenameDelegate(QStyledItemDelegate):
    """Editor for the target-filename column.

    While editing, only the base name (without extension) is shown; the source
    file's extension is firmly re-appended on commit and therefore cannot be
    changed.
    """

    def __init__(self, ext_for_row, parent=None):
        super().__init__(parent)
        self.ext_for_row = ext_for_row  # callable(row) -> '.jpg'

    @staticmethod
    def _strip_image_ext(text):
        root, ext = os.path.splitext(text)
        return root if ext.lower() in IMAGE_EXTS else text

    def createEditor(self, parent, option, index):
        return QLineEdit(parent)

    def setEditorData(self, editor, index):
        editor.setText(self._strip_image_ext(index.data() or ''))

    def setModelData(self, editor, model, index):
        base = self._strip_image_ext(editor.text().strip())
        if not base:
            return  # empty name -> keep the previous value
        ext = self.ext_for_row(index.row()) or ''
        model.setData(index, base + ext)


# ── Login dialog ───────────────────────────────────────────────────────────────

class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Login – Wikimedia Commons')
        self.setMinimumWidth(420)
        self.settings = QSettings(APP_NAME, 'Login')

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.url_edit = QLineEdit(self.settings.value(
            'api_url', 'https://commons.wikimedia.org/w/api.php'))
        self.user_edit = QLineEdit(self.settings.value('username', ''))
        self.pass_edit = QLineEdit()
        self.pass_edit.setEchoMode(QLineEdit.Password)

        form.addRow('API URL:', self.url_edit)
        form.addRow('Username:', self.user_edit)
        form.addRow('Password:', self.pass_edit)
        layout.addLayout(form)

        hint = QLabel('Tip: For bot logins, use a BotPassword '
                      '(Special:BotPasswords).')
        hint.setStyleSheet('color: gray; font-size: 11px;')
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_credentials(self):
        self.settings.setValue('api_url', self.url_edit.text())
        self.settings.setValue('username', self.user_edit.text())
        return self.url_edit.text(), self.user_edit.text(), self.pass_edit.text()


# ── Main window ────────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    COLS = ['', 'Source file', 'Target filename (Commons)', 'Date',
            'Description (all)', 'Status']
    COL_THUMB = 0
    COL_FILENAME = 1
    COL_TITLE = 2
    COL_DATE = 3
    COL_DESC = 4
    COL_STATUS = 5

    def __init__(self, logger, emitter, gui_handler, log_path):
        super().__init__()
        self.logger = logger
        self.emitter = emitter
        self.gui_handler = gui_handler
        self.log_path = log_path

        self.setWindowTitle(f'{APP_NAME} v{__version__}')
        self.setMinimumSize(1150, 740)
        self.api = None
        self.settings = QSettings(APP_NAME, 'Main')

        self._build_ui()
        self._restore_settings()

        # Mirror the live log into the GUI.
        self.emitter.log_record.connect(self._append_log)

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.tabs.addTab(self._build_upload_tab(), '⬆ Upload')
        self.tabs.addTab(self._build_log_tab(), '🐞 Log')

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage('Ready. Please log in first.')

    def _build_upload_tab(self):
        page = QWidget()
        main_layout = QVBoxLayout(page)

        # ── Toolbar ──
        toolbar = QHBoxLayout()
        self.login_btn = QPushButton('🔐 Login')
        self.login_btn.clicked.connect(self.do_login)

        self.test_btn = QPushButton('🔎 Test connection')
        self.test_btn.clicked.connect(self.test_connection)
        self.test_btn.setEnabled(False)

        self.login_label = QLabel('Not logged in')
        self.login_label.setStyleSheet('color: red')

        add_btn = QPushButton('➕ Add files')
        add_btn.clicked.connect(self.add_files)
        remove_btn = QPushButton('➖ Remove selected')
        remove_btn.clicked.connect(self.remove_selected)
        clear_btn = QPushButton('🗑 Clear all')
        clear_btn.clicked.connect(self.clear_all)

        self.upload_btn = QPushButton('🚀 Upload all')
        self.upload_btn.clicked.connect(self.start_upload)
        self.upload_btn.setStyleSheet(
            'font-weight: bold; background: #2a7; color: white; padding: 4px 12px;')

        self.ignore_warnings_cb = QCheckBox('Ignore warnings (overwrite)')

        toolbar.addWidget(self.login_btn)
        toolbar.addWidget(self.test_btn)
        toolbar.addWidget(self.login_label)
        toolbar.addSpacing(20)
        toolbar.addWidget(add_btn)
        toolbar.addWidget(remove_btn)
        toolbar.addWidget(clear_btn)
        toolbar.addStretch()
        toolbar.addWidget(self.ignore_warnings_cb)
        toolbar.addWidget(self.upload_btn)
        main_layout.addLayout(toolbar)

        # ── Splitter ──
        splitter = QSplitter(Qt.Horizontal)

        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        # Thumbnails on the left: icon size and row height.
        self.table.setIconSize(QSize(96, 64))
        self.table.verticalHeader().setDefaultSectionSize(70)
        self.table.verticalHeader().setVisible(False)
        # Fixed extension in the target filename (via delegate).
        self.table.setItemDelegateForColumn(
            self.COL_TITLE, FilenameDelegate(self._ext_for_row, self.table))

        ht = self.table.horizontalHeaderItem(self.COL_TITLE)
        if ht:
            ht.setToolTip('Name under which the file is stored on Commons '
                          '(without "File:"). The extension is taken from the '
                          'source file and cannot be changed. Empty = source filename.')
        hs = self.table.horizontalHeaderItem(self.COL_FILENAME)
        if hs:
            hs.setToolTip('Local source file (not modified).')
        htb = self.table.horizontalHeaderItem(self.COL_THUMB)
        if htb:
            htb.setToolTip('Preview')

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(self.COL_THUMB, QHeaderView.Fixed)
        self.table.setColumnWidth(self.COL_THUMB, 104)
        header.setSectionResizeMode(self.COL_FILENAME, QHeaderView.Interactive)
        self.table.setColumnWidth(self.COL_FILENAME, 250)
        header.setSectionResizeMode(self.COL_TITLE, QHeaderView.Interactive)
        self.table.setColumnWidth(self.COL_TITLE, 240)
        header.setSectionResizeMode(self.COL_DESC, QHeaderView.Stretch)
        header.setSectionResizeMode(self.COL_STATUS, QHeaderView.Interactive)
        self.table.setColumnWidth(self.COL_STATUS, 150)

        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked)
        self.table.itemSelectionChanged.connect(self.on_row_selected)
        splitter.addWidget(self.table)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right.setMinimumWidth(330)

        settings_group = QGroupBox('Upload settings')
        settings_form = QFormLayout(settings_group)
        self.author_edit = QLineEdit()
        self.source_edit = QLineEdit('{{own}}')
        self.permission_edit = QLineEdit()
        self.license_edit = QLineEdit('{{Cc-by-sa-4.0}}')
        self.other_templates_edit = QLineEdit()
        self.other_fields_edit = QLineEdit()
        self.other_fields_edit.setPlaceholderText(
            'e.g. {{Credit line|Author=Harald Krichel|Other=WikiPortraits}}')
        self.gallery_prefix_edit = QLineEdit()
        self.gallery_prefix_edit.setPlaceholderText('e.g. User:Harald Krichel')
        self.timeout_edit = QLineEdit('120')
        self.timeout_edit.setMaximumWidth(80)

        settings_form.addRow('Author:', self.author_edit)
        settings_form.addRow('Source:', self.source_edit)
        settings_form.addRow('Permission:', self.permission_edit)
        settings_form.addRow('License:', self.license_edit)
        settings_form.addRow('Other templates:', self.other_templates_edit)
        settings_form.addRow('Other fields:', self.other_fields_edit)
        settings_form.addRow('Gallery prefix:', self.gallery_prefix_edit)
        settings_form.addRow('HTTP timeout (s):', self.timeout_edit)
        right_layout.addWidget(settings_group)

        base_group = QGroupBox('Base description_all (for all files)')
        base_layout = QVBoxLayout(base_group)
        self.base_text_edit = QTextEdit()
        self.base_text_edit.setPlaceholderText(
            'creator=Q640\ncopyright=Q73566113\nlicense=Q18199165\n'
            '{{Berlinale 2025|type=red carpet}}')
        self.base_text_edit.setMaximumHeight(150)
        base_layout.addWidget(self.base_text_edit)
        right_layout.addWidget(base_group)

        save_settings_btn = QPushButton('💾 Save settings')
        save_settings_btn.setToolTip('Save the upload settings and the base '
                                     'description so they are restored next time.')
        save_settings_btn.clicked.connect(self._on_save_settings)
        right_layout.addWidget(save_settings_btn)

        file_group = QGroupBox('Selected file – description_all')
        file_layout = QVBoxLayout(file_group)
        self.file_desc_edit = QTextEdit()
        self.file_desc_edit.setPlaceholderText(
            'caption_en=Name at the Event\ncaption_de=Name beim Event\n'
            'depicts=Q12345\n\n{{en|1=Description}}')
        self.file_desc_edit.textChanged.connect(self.on_file_desc_changed)
        file_layout.addWidget(self.file_desc_edit)
        right_layout.addWidget(file_group)

        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumHeight(120)
        self.preview_label.setStyleSheet('background: #111; border-radius: 4px;')
        right_layout.addWidget(self.preview_label)

        splitter.addWidget(right)
        splitter.setSizes([720, 400])
        main_layout.addWidget(splitter)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        return page

    def _build_log_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        top = QHBoxLayout()
        self.verbose_cb = QCheckBox('Verbose logging')
        self.verbose_cb.stateChanged.connect(self._toggle_verbose)
        clear_log_btn = QPushButton('Clear')
        clear_log_btn.clicked.connect(lambda: self.log_view.clear())
        copy_log_btn = QPushButton('Copy')
        copy_log_btn.clicked.connect(self._copy_log)
        open_file_btn = QPushButton('Open log file')
        open_file_btn.clicked.connect(self._open_log_file)
        open_dir_btn = QPushButton('Open folder')
        open_dir_btn.clicked.connect(self._open_log_folder)

        top.addWidget(self.verbose_cb)
        top.addStretch()
        top.addWidget(clear_log_btn)
        top.addWidget(copy_log_btn)
        top.addWidget(open_file_btn)
        top.addWidget(open_dir_btn)
        layout.addLayout(top)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFont('Consolas' if sys.platform == 'win32'
                                    else 'Monospace', 9))
        self.log_view.document().setMaximumBlockCount(5000)
        layout.addWidget(self.log_view)

        path_label = QLabel(f'Log file: {self.log_path}')
        path_label.setStyleSheet('color: gray; font-size: 11px;')
        path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(path_label)

        return page

    # ── Log helpers ──────────────────────────────────────────────────────────

    def _append_log(self, msg):
        self.log_view.appendPlainText(msg)
        sb = self.log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _toggle_verbose(self, state):
        verbose = bool(state)
        self.gui_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
        self.logger.info('Verbose logging %s.', 'enabled' if verbose else 'disabled')

    def _copy_log(self):
        QApplication.clipboard().setText(self.log_view.toPlainText())
        self.status_bar.showMessage('Log copied to clipboard.', 3000)

    def _open_log_file(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.log_path))

    def _open_log_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(self.log_path)))

    # ── Settings ─────────────────────────────────────────────────────────────

    def _restore_settings(self):
        self.author_edit.setText(self.settings.value('author', ''))
        self.source_edit.setText(self.settings.value('source', '{{own}}'))
        self.permission_edit.setText(self.settings.value('permission', ''))
        self.license_edit.setText(self.settings.value('license', '{{Cc-by-sa-4.0}}'))
        self.other_templates_edit.setText(self.settings.value('other_templates', ''))
        self.other_fields_edit.setText(self.settings.value('other_fields', ''))
        self.gallery_prefix_edit.setText(self.settings.value('gallery_prefix', ''))
        self.timeout_edit.setText(self.settings.value('timeout', '120'))
        self.base_text_edit.setPlainText(self.settings.value('base_description', ''))

    def _save_settings(self):
        self.settings.setValue('author', self.author_edit.text())
        self.settings.setValue('source', self.source_edit.text())
        self.settings.setValue('permission', self.permission_edit.text())
        self.settings.setValue('license', self.license_edit.text())
        self.settings.setValue('other_templates', self.other_templates_edit.text())
        self.settings.setValue('other_fields', self.other_fields_edit.text())
        self.settings.setValue('gallery_prefix', self.gallery_prefix_edit.text())
        self.settings.setValue('timeout', self.timeout_edit.text())
        self.settings.setValue('base_description', self.base_text_edit.toPlainText())

    def _on_save_settings(self):
        """Explicitly persist the current settings (button + on close)."""
        self._save_settings()
        self.settings.sync()
        self.status_bar.showMessage('Settings saved.', 3000)

    def closeEvent(self, event):
        # Persist settings when the window is closed.
        self._save_settings()
        super().closeEvent(event)

    def _get_timeout(self):
        try:
            t = int(self.timeout_edit.text())
            return t if t > 0 else 120
        except (ValueError, TypeError):
            return 120

    # ── Login / test ─────────────────────────────────────────────────────────

    def do_login(self):
        dlg = LoginDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        api_url, username, password = dlg.get_credentials()

        self.login_btn.setEnabled(False)
        self.login_label.setText('Logging in…')
        self.login_label.setStyleSheet('color: orange')

        self._login_worker = LoginWorker(
            api_url, username, password, self._get_timeout(), self.logger)
        self._login_worker.success.connect(
            lambda api: self._on_login_success(api, username))
        self._login_worker.failure.connect(self._on_login_failure)
        self._login_worker.start()

    def _on_login_success(self, api, username):
        self.api = api
        self.login_btn.setEnabled(True)
        self.test_btn.setEnabled(True)
        self.login_label.setText(f'✓ Logged in as {username}')
        self.login_label.setStyleSheet('color: green')
        self.status_bar.showMessage(f'Logged in as {username}')

    def _on_login_failure(self, error_msg):
        self.login_btn.setEnabled(True)
        self.login_label.setText('Not logged in')
        self.login_label.setStyleSheet('color: red')
        QMessageBox.critical(self, 'Login error', error_msg)

    def test_connection(self):
        if not self.api:
            return
        self.test_btn.setEnabled(False)
        self.status_bar.showMessage('Testing connection…')
        self._test_worker = TestWorker(self.api)
        self._test_worker.done.connect(self._on_test_done)
        self._test_worker.fail.connect(self._on_test_fail)
        self._test_worker.start()

    def _on_test_done(self, info):
        self.test_btn.setEnabled(True)
        self.logger.info('Connection OK: %s', info)
        self.status_bar.showMessage(f'Connection OK: {info}', 8000)
        QMessageBox.information(self, 'Connection OK', f'Logged in as:\n{info}')

    def _on_test_fail(self, msg):
        self.test_btn.setEnabled(True)
        self.logger.error('Connection test failed: %s', msg)
        QMessageBox.warning(self, 'Connection problem', msg)

    # ── Table ────────────────────────────────────────────────────────────────

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, 'Select image files', '',
            'Images (*.jpg *.jpeg *.png *.gif *.tif *.tiff *.svg *.webp)'
        )
        for filepath in files:
            self._add_row(filepath)
        if files:
            self.logger.debug('%d file(s) added to the table.', len(files))

    def _ext_for_row(self, row):
        """Return the (fixed) extension of a row's source file, e.g. '.jpg'."""
        item = self.table.item(row, self.COL_FILENAME)
        fp = item.data(Qt.UserRole) if item else None
        return os.path.splitext(fp)[1] if fp else ''

    def _make_thumbnail(self, filepath, w=96, h=64):
        """Create a downscaled preview efficiently (without full resolution)."""
        try:
            reader = QImageReader(filepath)
            reader.setAutoTransform(True)  # apply EXIF orientation
            size = reader.size()
            if size.isValid() and (size.width() > w or size.height() > h):
                reader.setScaledSize(size.scaled(w, h, Qt.KeepAspectRatio))
            img = reader.read()
            if not img.isNull():
                return QPixmap.fromImage(img)
        except Exception as e:
            self.logger.debug('Thumbnail failed for %s: %s', filepath, e)
        return None

    def _add_row(self, filepath):
        row = self.table.rowCount()
        self.table.insertRow(row)
        filename = os.path.basename(filepath)
        date = read_exif_date(filepath, self.logger)

        # Thumbnail (left column)
        thumb_item = QTableWidgetItem()
        thumb_item.setFlags(thumb_item.flags() & ~Qt.ItemIsEditable)
        thumb_item.setTextAlignment(Qt.AlignCenter)
        pix = self._make_thumbnail(filepath)
        if pix is not None:
            thumb_item.setIcon(QIcon(pix))
        else:
            thumb_item.setText('—')
        self.table.setItem(row, self.COL_THUMB, thumb_item)

        # Source file (not editable)
        src_item = QTableWidgetItem(filename)
        src_item.setFlags(src_item.flags() & ~Qt.ItemIsEditable)
        src_item.setData(Qt.UserRole, filepath)
        self.table.setItem(row, self.COL_FILENAME, src_item)

        # Target filename on Commons; default = source filename incl. extension.
        self.table.setItem(row, self.COL_TITLE, QTableWidgetItem(filename))
        self.table.setItem(row, self.COL_DATE, QTableWidgetItem(date))
        self.table.setItem(row, self.COL_DESC, QTableWidgetItem(''))
        status_item = QTableWidgetItem('—')
        status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row, self.COL_STATUS, status_item)

    def remove_selected(self):
        rows = sorted(set(i.row() for i in self.table.selectedItems()), reverse=True)
        for row in rows:
            self.table.removeRow(row)

    def clear_all(self):
        self.table.setRowCount(0)

    def on_row_selected(self):
        rows = list(set(i.row() for i in self.table.selectedItems()))
        if len(rows) != 1:
            self.file_desc_edit.setPlaceholderText(
                'Select a single file to edit its description.')
            return
        row = rows[0]
        desc = self.table.item(row, self.COL_DESC)
        self.file_desc_edit.blockSignals(True)
        self.file_desc_edit.setPlainText(desc.text() if desc else '')
        self.file_desc_edit.blockSignals(False)

        filepath = self.table.item(row, self.COL_FILENAME).data(Qt.UserRole)
        if filepath and os.path.exists(filepath):
            pix = QPixmap(filepath)
            if not pix.isNull():
                self.preview_label.setPixmap(
                    pix.scaled(300, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def on_file_desc_changed(self):
        rows = list(set(i.row() for i in self.table.selectedItems()))
        if len(rows) != 1:
            return
        row = rows[0]
        self.table.item(row, self.COL_DESC).setText(self.file_desc_edit.toPlainText())

    # ── Upload ───────────────────────────────────────────────────────────────

    def start_upload(self):
        if not self.api:
            QMessageBox.warning(self, 'Not logged in', 'Please log in first.')
            return
        if self.table.rowCount() == 0:
            QMessageBox.warning(self, 'No files', 'Please add files first.')
            return

        self._save_settings()
        # Apply the timeout to the active session in case it was changed.
        self.api.timeout = self._get_timeout()

        rows = []
        for r in range(self.table.rowCount()):
            filepath = self.table.item(r, self.COL_FILENAME).data(Qt.UserRole)
            source_name = self.table.item(r, self.COL_FILENAME).text()
            date = self.table.item(r, self.COL_DATE).text() if self.table.item(r, self.COL_DATE) else ''
            per_file_desc = self.table.item(r, self.COL_DESC).text() if self.table.item(r, self.COL_DESC) else ''

            base = self.base_text_edit.toPlainText().strip()
            combined = (base + '\n' + per_file_desc).strip() if base else per_file_desc

            # Target filename on Commons (may differ from the source name);
            # empty -> source filename. The extension is ensured in the worker.
            target_item = self.table.item(r, self.COL_TITLE)
            target_name = target_item.text().strip() if target_item else ''
            if not target_name:
                target_name = source_name

            rows.append({
                'filepath': filepath,
                'target_name': target_name,
                'source_name': source_name,
                'date': date,
                'description_all': combined,
                'author': self.author_edit.text(),
                'source': self.source_edit.text(),
                'permission': self.permission_edit.text(),
                'license_text': self.license_edit.text(),
                'other_templates': self.other_templates_edit.text(),
                'other_fields': self.other_fields_edit.text(),
                'template': 'Information',
            })

        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(rows))
        self.progress_bar.setValue(0)
        self.upload_btn.setEnabled(False)

        self.worker = UploadWorker(
            self.api, rows,
            self.base_text_edit.toPlainText(),
            self.gallery_prefix_edit.text(),
            self.ignore_warnings_cb.isChecked()
        )
        self.worker.progress.connect(self.on_progress)
        self.worker.error.connect(self.on_error)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

    def on_progress(self, row, status):
        item = self.table.item(row, self.COL_STATUS)
        if item:
            item.setText(status)
        self.progress_bar.setValue(row + 1)
        self.status_bar.showMessage(f'Uploading {row + 1}/{self.table.rowCount()}…')

    def on_error(self, row, msg):
        if row < 0:
            # Gallery/global errors are shown only in the log/status bar.
            self.status_bar.showMessage(msg, 8000)
            return
        item = self.table.item(row, self.COL_STATUS)
        if item:
            item.setText(f'✗ {msg[:60]}')
            item.setToolTip(msg)

    def on_finished(self, summary):
        self.progress_bar.setVisible(False)
        self.upload_btn.setEnabled(True)
        self.status_bar.showMessage(summary)
        QMessageBox.information(self, 'Upload complete',
                                summary + '\n\nDetails in the Log tab.')


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)

    logger, emitter, gui_handler, log_path = setup_logging()

    # Write unhandled exceptions to the log as well.
    def excepthook(exc_type, exc_value, exc_tb):
        logger.critical('Unhandled exception:\n%s',
                        ''.join(traceback.format_exception(exc_type, exc_value, exc_tb)))
        sys.__excepthook__(exc_type, exc_value, exc_tb)
    sys.excepthook = excepthook

    window = MainWindow(logger, emitter, gui_handler, log_path)
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
