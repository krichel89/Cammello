#!/usr/bin/env python3
"""
Cammello v0.7.1 - Batch upload tool for Wikimedia Commons

Replaces VicunaUploader with structured data (SDC) support (caption_*, creator,
depicts, etc.).

New in 0.7.1:
  * New structured field "Created during (P10408)" for the event a file was
    created during (e.g. Q124692383, 81st Venice International Film Festival).
  * Image files can be dragged and dropped onto the file table; dropping a
    folder adds the image files directly inside it.
  * The single-value Wikidata QID fields (creator, copyright, license, created
    during) now use a standard width instead of stretching across the panel.

New in 0.7.0:
  * The mode toggle is now "Expert mode" (raw description_all text). Its default
    is OFF, i.e. the structured fields are shown by default (what used to be
    "Beginner mode").
  * Dedicated "Categories" field in the structured editor (semicolon-separated,
    names without the [[Category:]] wrapper).
  * The value separator for multi-value fields (depicts, categories) is ";".
  * The gallery-suffix field is only shown for the base description, not for the
    per-file (selected-file) editor.
  * The extra-wikitext box starts at two lines and is drag-resizable.
  * Copyright (Q73566113) and license (Q18199165) are preselected in the base
    (via the default base text) instead of being shown as greyed examples; each
    Wikidata field carries an explanatory hint, e.g. "Q73566113 (CC-licensed)"
    or "e.g. Q640 (Harald Krichel)".
  * Settings can be exported to / imported from a plain text file, optionally
    including the selected file's description.
  * Example placeholders use Harald Krichel / Q640.

New in 0.6.0:
  * Beginner mode (on by default) with structured single-line fields for both
    the per-file and the base description; multilingual captions via a language
    dropdown with "Add language".
  * Right panel scrolls, so input fields are never compressed; the extra-wikitext
    box is multi-line and accepts # comment lines (stripped at upload).
  * Copyright (Q73566113) and License (Q18199165) default into the base section.
  * Login dialog: API URL hidden, with a link to Special:BotPasswords and the
    list of required grants.

New in 0.5.1:
  * BotPassword-first login, session verification, automatic re-login.
  * Fixed EXIF capture-date reading; validation warnings for description typos.
  * Automatic maintenance category; saved settings and base description.

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
    QStyledItemDelegate, QComboBox, QScrollArea
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSettings, QObject, QUrl, QSize
from PyQt5.QtGui import QPixmap, QFont, QDesktopServices, QIcon, QImageReader

try:
    from PIL import Image
    from PIL.ExifTags import TAGS
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

__version__ = '0.7.1'
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
    'creator', 'copyright', 'license', 'depicts', 'created_during',
    'gallery_suffix',
]

PROPERTY_MAP = {
    'creator': 'P170',
    'copyright': 'P6216',
    'license': 'P275',
    'depicts': 'P180',
    'created_during': 'P10408',
}

# Standard width (px) for single-value Wikidata QID fields in the structured
# editor. Keeps QID inputs at a sensible length instead of stretching them
# across the whole panel.
WD_FIELD_WIDTH = 220

# Accepted image extensions (used by the file dialog and by drag-and-drop).
IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.gif', '.tif', '.tiff', '.svg', '.webp')

NAME_SEPARATORS = [' at ', ' bei ', ' à ', ' al ', ' auf ', ' sur ', ' on ', ' sul ']


def extract_structured_data(text):
    """Extract key=value lines from description_all text.
    Lines starting with # are treated as comments and removed.
    Keys are matched case-insensitively (license= and LICENSE= are equivalent)."""
    sd = {}
    # Remove comment lines (starting with #)
    text = re.sub(r'^#[^\n]*\n?', '', text, flags=re.MULTILINE)
    result = text

    # Dynamically extract all caption_XX= lines (any language code)
    for m in re.finditer(r'(?:^|\n)caption_([a-z]{2,3})=([^\n]+)',
                         result, flags=re.IGNORECASE):
        lang = m.group(1).lower()
        val = m.group(2).strip()
        sd['caption_' + lang] = val
    # Remove all matched caption_XX= lines from result
    result = re.sub(r'\ncaption_[a-z]{2,3}=[^\n]+', '', result, flags=re.IGNORECASE)
    result = re.sub(r'^caption_[a-z]{2,3}=[^\n]+\n?', '', result,
                    flags=re.MULTILINE | re.IGNORECASE)

    for key in SD_KEYS:
        # Match at start of string
        m = re.match(rf'^{key}=([^\n]+)', result, flags=re.IGNORECASE)
        if not m:
            # Match after newline
            m = re.search(rf'\n{key}=([^\n]+)', result, flags=re.IGNORECASE)
        if m:
            sd[key] = m.group(1).strip()
            result = re.sub(rf'\n{key}=[^\n]+', '', result, flags=re.IGNORECASE)
            result = re.sub(rf'^{key}=[^\n]+\n?', '', result,
                            flags=re.MULTILINE | re.IGNORECASE)

    return sd, result.strip()


# Keys that look like a structured-data tag when they appear at the start of a line.
_LINT_KEYS_RE = (r'(?:creator|copyright|license|depicts|created_during|'
                 r'gallery_suffix|caption_[a-z]{2,3})')


def find_description_issues(text):
    """Scan description_all for likely typos and return human-readable warnings.

    Catches things that would otherwise be silently turned into broken wikitext:
    a key with the wrong separator (creator_Q… instead of creator=Q…), a
    misspelled [[Category:]] link, or a duplicated "Category:" prefix. This only
    reports problems; it does not change the text.
    """
    issues = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        low = line.lower()
        # 1) known key followed by '_' or ':' instead of '='
        m = re.match(rf'^({_LINT_KEYS_RE})[_:]', low)
        if m:
            issues.append(
                f'"{line[:60]}" looks like a "{m.group(1)}=value" tag but uses '
                f'"_"/":" instead of "=". It will be treated as plain text, and '
                f'no structured data will be set for it.')
            continue
        # 2) misspelled category link ([[Cate… but not [[Category:)
        if re.match(r'^\[\[\s*cate', low) and not low.startswith('[[category:'):
            issues.append(
                f'"{line[:60]}" looks like a misspelled category ("[[Category:" '
                f'expected); it will NOT be added as a category.')
            continue
        # 3) duplicated Category: prefix
        if re.match(r'^\[\[\s*category:\s*category:', low):
            issues.append(
                f'"{line[:60]}" has a duplicated "Category:" prefix; the resulting '
                f'category name will be wrong.')
            continue
    return issues


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
                for issue in find_description_issues(row['description_all']):
                    self.log.warning('Possible issue in description for "%s": %s',
                                     fname, issue)

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
                            # Separator is ";"; "," is still tolerated so that
                            # older comma-separated values keep working.
                            for qid in re.split(r'[;,]', val):
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
        self.url_edit.setVisible(False)  # hidden; always Commons by default
        self.user_edit = QLineEdit(self.settings.value('username', ''))
        self.user_edit.setPlaceholderText('e.g. Seewolf@Cammello')
        self.pass_edit = QLineEdit()
        self.pass_edit.setEchoMode(QLineEdit.Password)

        form.addRow('Username:', self.user_edit)
        form.addRow('Password:', self.pass_edit)
        layout.addLayout(form)

        hint = QLabel(
            'Use a <b>BotPassword</b>: create one at '
            '<a href="https://commons.wikimedia.org/wiki/Special:BotPasswords">'
            'Special:BotPasswords</a> and log in with the name shown there '
            '(e.g. <i>YourName@Cammello</i>).<br><br>'
            'Required grants:'
            '<ul style="margin-top:2px;">'
            '<li>Edit existing pages</li>'
            '<li>Create, edit, and move pages</li>'
            '<li>Upload new files</li>'
            '<li>Upload, replace, and move files</li>'
            '</ul>')
        hint.setStyleSheet('color: gray; font-size: 11px;')
        hint.setWordWrap(True)
        hint.setOpenExternalLinks(True)
        hint.setTextInteractionFlags(Qt.TextBrowserInteraction)
        layout.addWidget(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_credentials(self):
        self.settings.setValue('api_url', self.url_edit.text())
        self.settings.setValue('username', self.user_edit.text())
        return self.url_edit.text(), self.user_edit.text(), self.pass_edit.text()


# ── Structured editor: language list, example, captions editor ──────────────────

# Curated language list for the caption dropdown (code, display name).
LANGUAGES = [
    ('en', 'English'), ('de', 'Deutsch'), ('es', 'Español'), ('fr', 'Français'),
    ('it', 'Italiano'), ('ca', 'Català'), ('pt', 'Português'), ('nl', 'Nederlands'),
    ('pl', 'Polski'), ('sv', 'Svenska'), ('ru', 'Русский'), ('uk', 'Українська'),
    ('ja', '日本語'), ('zh', '中文'), ('ar', 'العربية'),
]

# Worked example of a description_all with every option (used as a placeholder).
EXAMPLE_DESCRIPTION_ALL = (
    'caption_en=Harald Krichel at the Berlinale 2026\n'
    'caption_de=Harald Krichel auf der Berlinale 2026\n'
    'creator=Q640\n'
    'copyright=Q73566113\n'
    'license=Q18199165\n'
    'depicts=Q42; Q64\n'
    '# created_during=Q124692383  (e.g. 81st Venice Film Festival)\n'
    'gallery_suffix=Berlinale 2026\n'
    '\n'
    '{{en|1=Harald Krichel at the Berlinale 2026}}\n'
    '[[Category:Harald Krichel]]'
)


# Category links ([[Category:Name]]) that can be split out of / rebuilt for the
# structured "Categories" field. The tracking category is added only at upload.
_CATEGORY_RE = re.compile(r'\[\[\s*Category:\s*([^\]|]+?)\s*\]\]', re.IGNORECASE)


def normalize_category_name(name):
    """Turn a user-entered category into a bare name (no [[Category:]] wrapper)."""
    name = (name or '').strip()
    name = re.sub(r'^\[\[\s*', '', name)
    name = re.sub(r'\s*\]\]$', '', name)
    name = re.sub(r'^\s*Category:\s*', '', name, flags=re.IGNORECASE)
    return name.strip()


def split_categories(text):
    """Return (list_of_bare_category_names, text_without_category_links).

    Lines that consist only of category links are dropped entirely; lines that
    mix category links with other content keep the other content.
    """
    cats = [m.group(1).strip() for m in _CATEGORY_RE.finditer(text or '')]
    kept = []
    for line in (text or '').split('\n'):
        had_cat = bool(_CATEGORY_RE.search(line))
        cleaned = _CATEGORY_RE.sub('', line)
        if had_cat and not cleaned.strip():
            continue  # line was purely category link(s)
        kept.append(cleaned)
    rest = re.sub(r'\n{3,}', '\n\n', '\n'.join(kept)).strip()
    return cats, rest


class CaptionsEditor(QWidget):
    """A small editor for multilingual captions: one row per language with a
    language dropdown, a text field and a remove button, plus an "Add language"
    button. Always keeps at least one row."""

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows = []  # list of dicts: {widget, combo, edit}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        self._rows_box = QVBoxLayout()
        self._rows_box.setContentsMargins(0, 0, 0, 0)
        self._rows_box.setSpacing(4)
        outer.addLayout(self._rows_box)

        add_btn = QPushButton('➕ Add language')
        add_btn.clicked.connect(lambda: (self.add_row(), self.changed.emit()))
        outer.addWidget(add_btn)

        self.add_row()  # start with one empty row

    def add_row(self, lang='en', value=''):
        row_widget = QWidget()
        h = QHBoxLayout(row_widget)
        h.setContentsMargins(0, 0, 0, 0)

        combo = QComboBox()
        for code, name in LANGUAGES:
            combo.addItem(f'{code} – {name}', code)
        idx = combo.findData(lang)
        if idx < 0:                       # unknown code (e.g. from advanced mode)
            combo.addItem(lang, lang)
            idx = combo.findData(lang)
        combo.setCurrentIndex(idx)
        combo.setMaximumWidth(150)

        edit = QLineEdit(value)
        edit.setPlaceholderText('e.g. Harald Krichel at the Berlinale 2026')

        remove = QPushButton('✕')
        remove.setFixedWidth(28)
        remove.setToolTip('Remove this language')

        h.addWidget(combo)
        h.addWidget(edit, 1)
        h.addWidget(remove)
        self._rows_box.addWidget(row_widget)

        entry = {'widget': row_widget, 'combo': combo, 'edit': edit}
        self._rows.append(entry)
        combo.currentIndexChanged.connect(lambda *_: self.changed.emit())
        edit.textChanged.connect(lambda *_: self.changed.emit())
        remove.clicked.connect(lambda: self._remove(entry))

    def _remove(self, entry):
        entry['widget'].setParent(None)
        self._rows.remove(entry)
        if not self._rows:
            self.add_row()  # always keep at least one row
        self.changed.emit()

    def get_captions(self):
        """Return {lang: value} for all non-empty caption rows."""
        out = {}
        for e in self._rows:
            lang = e['combo'].currentData()
            val = e['edit'].text().strip()
            if val:
                out[lang] = val
        return out

    def set_captions(self, captions):
        for e in list(self._rows):
            e['widget'].setParent(None)
        self._rows = []
        if captions:
            for lang, val in captions.items():
                self.add_row(lang, val)
        else:
            self.add_row()


# Lines that are recognized key=value assignments (used to compute leftover text).
_ASSIGN_RE = re.compile(
    r'^\s*(?:caption_[a-z]{2,3}|creator|copyright|license|depicts|gallery_suffix)\s*=',
    re.IGNORECASE)


def leftover_text(text):
    """Return all lines that are NOT key=value assignments. Comment lines (#) and
    wikitext are kept, so comments survive a round-trip through the structured
    editor (they are only stripped at upload time)."""
    return '\n'.join(l for l in text.split('\n') if not _ASSIGN_RE.match(l)).strip()


class _VGrip(QWidget):
    """A thin horizontal grip strip that lets the user drag-resize the height of
    a target widget. Used to make the extra-wikitext box resizable."""

    def __init__(self, target, min_height, parent=None):
        super().__init__(parent)
        self._target = target
        self._min_height = min_height
        self.setFixedHeight(7)
        self.setCursor(Qt.SizeVerCursor)
        self.setToolTip('Drag to resize the field')
        self.setStyleSheet('background:#b0b0b0; border-radius:3px; margin:1px 0;')
        self._press_y = None
        self._start_h = 0

    def mousePressEvent(self, event):
        self._press_y = event.globalPos().y()
        self._start_h = self._target.height()

    def mouseMoveEvent(self, event):
        if self._press_y is None:
            return
        delta = event.globalPos().y() - self._press_y
        self._target.setFixedHeight(max(self._min_height, self._start_h + delta))

    def mouseReleaseEvent(self, event):
        self._press_y = None


class StructuredDescriptionEditor(QWidget):
    """Structured single-line editor for a description_all value: multilingual
    captions plus creator/copyright/license/depicts (and, for the base only, a
    gallery suffix), a dedicated categories field and a resizable free-text area
    for extra wikitext and comments. Used for both the per-file and the base
    description when expert mode is off.

    show_gallery_suffix: only the base editor offers the gallery suffix.
    """

    changed = pyqtSignal()

    def __init__(self, parent=None, show_gallery_suffix=True):
        super().__init__(parent)
        self.show_gallery_suffix = show_gallery_suffix
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(QLabel('Captions:'))
        self.captions_editor = CaptionsEditor()
        self.captions_editor.changed.connect(self.changed)
        layout.addWidget(self.captions_editor)

        form = QFormLayout()
        self.creator = QLineEdit()
        self.creator.setPlaceholderText('e.g. Q640')
        self.copyright = QLineEdit()
        self.license = QLineEdit()
        self.depicts = QLineEdit()
        self.depicts.setPlaceholderText('e.g. Q42; Q64')
        self.created_during = QLineEdit()
        self.created_during.setPlaceholderText('e.g. Q124692383')
        self.categories = QLineEdit()
        self.categories.setPlaceholderText('e.g. Berlinale 2026; Portraits')

        # Single-value Wikidata QID fields get a standard width instead of
        # stretching across the whole panel.
        for w in (self.creator, self.copyright, self.license,
                  self.created_during):
            w.setMaximumWidth(WD_FIELD_WIDTH)

        self.gallery_suffix = QLineEdit()
        self.gallery_suffix.setPlaceholderText('e.g. Berlinale 2026')

        fields = [self.creator, self.copyright, self.license,
                  self.depicts, self.created_during, self.categories]
        if self.show_gallery_suffix:
            fields.append(self.gallery_suffix)
        for w in fields:
            w.textChanged.connect(lambda *_: self.changed.emit())

        # Each Wikidata/category field carries a grey explanatory hint to its right.
        form.addRow('Creator (P170):',
                    self._with_hint(self.creator, 'e.g. Q640 (Harald Krichel)'))
        form.addRow('Copyright (P6216):',
                    self._with_hint(self.copyright, 'Q73566113 (CC-licensed)'))
        form.addRow('License (P275):',
                    self._with_hint(self.license, 'Q18199165 (CC BY-SA 4.0)'))
        form.addRow('Depicts (P180):',
                    self._with_hint(self.depicts, 'semicolon-separated', wide=True))
        form.addRow('Created during (P10408):',
                    self._with_hint(self.created_during,
                                    'e.g. Q124692383 (81st Venice Film Festival)'))
        form.addRow('Categories:',
                    self._with_hint(self.categories,
                                    'semicolon-separated, without [[Category:]]',
                                    wide=True))
        if self.show_gallery_suffix:
            form.addRow('Gallery suffix:', self.gallery_suffix)
        layout.addLayout(form)

        layout.addWidget(QLabel('Extra wikitext / comments:'))
        self.extra = QTextEdit()
        self.extra.setPlaceholderText(
            'e.g. {{en|1=…}}\n'
            '# lines starting with # are comments and are not uploaded')
        # Start at two text lines; the grip below makes it drag-resizable.
        two_lines = self.extra.fontMetrics().lineSpacing() * 2 + 12
        self.extra.setFixedHeight(two_lines)
        self.extra.textChanged.connect(lambda: self.changed.emit())
        layout.addWidget(self.extra)
        layout.addWidget(_VGrip(self.extra, two_lines))

    @staticmethod
    def _with_hint(edit, hint, wide=False):
        """Wrap a line edit and a grey hint label into one row widget.

        wide=True lets the edit stretch to fill the row (used for the
        semicolon-separated list fields). Otherwise the edit keeps its
        standard width and the row is left-aligned with the hint beside it.
        """
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        if wide:
            h.addWidget(edit, 1)
            h.addWidget(lbl := QLabel(hint))
        else:
            h.addWidget(edit)
            h.addWidget(lbl := QLabel(hint))
            h.addStretch(1)
        lbl.setStyleSheet('color:#888;')
        return w

    def load(self, text):
        sd, _ = extract_structured_data(text)
        caps = {k[len('caption_'):]: v for k, v in sd.items()
                if k.startswith('caption_')}
        self.captions_editor.set_captions(caps)
        self.creator.setText(sd.get('creator', ''))
        self.copyright.setText(sd.get('copyright', ''))
        self.license.setText(sd.get('license', ''))
        self.depicts.setText(sd.get('depicts', ''))
        self.created_during.setText(sd.get('created_during', ''))
        if self.show_gallery_suffix:
            self.gallery_suffix.setText(sd.get('gallery_suffix', ''))
        # Split category links out of the leftover text into the categories field.
        cats, extra = split_categories(leftover_text(text))
        self.categories.setText('; '.join(cats))
        self.extra.setPlainText(extra)

    def assemble(self):
        lines = [f'caption_{lang}={val}'
                 for lang, val in self.captions_editor.get_captions().items()]
        pairs = [('creator', self.creator), ('copyright', self.copyright),
                 ('license', self.license), ('depicts', self.depicts),
                 ('created_during', self.created_during)]
        if self.show_gallery_suffix:
            pairs.append(('gallery_suffix', self.gallery_suffix))
        for key, w in pairs:
            val = w.text().strip()
            if val:
                lines.append(f'{key}={val}')
        body = '\n'.join(lines)

        extra = self.extra.toPlainText().strip()
        if extra:
            body = (body + '\n\n' + extra).strip()

        cats = [normalize_category_name(c) for c in self.categories.text().split(';')]
        cat_lines = '\n'.join(f'[[Category:{c}]]' for c in cats if c)
        if cat_lines:
            body = (body + '\n' + cat_lines).strip()
        return body


# ── Main window ────────────────────────────────────────────────────────────────

class FileDropTableWidget(QTableWidget):
    """QTableWidget that accepts image files dropped onto it.

    Dropped files with a known image extension (and immediate image files
    inside a dropped folder) are passed to on_files_dropped as a list of
    absolute paths. Everything else is ignored.
    """

    def __init__(self, rows, cols, on_files_dropped=None, parent=None):
        super().__init__(rows, cols, parent)
        self._on_files_dropped = on_files_dropped
        self.setAcceptDrops(True)

    @staticmethod
    def _collect(urls):
        paths = []
        for url in urls:
            path = url.toLocalFile()
            if not path:
                continue
            if os.path.isdir(path):
                # Immediate image files inside a dropped folder (not recursive).
                for name in sorted(os.listdir(path)):
                    full = os.path.join(path, name)
                    if (os.path.isfile(full)
                            and os.path.splitext(name)[1].lower() in IMAGE_EXTS):
                        paths.append(full)
            elif os.path.splitext(path)[1].lower() in IMAGE_EXTS:
                paths.append(path)
        return paths

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            paths = self._collect(event.mimeData().urls())
            if paths and self._on_files_dropped:
                self._on_files_dropped(paths)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)


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
        self._loading_desc = False  # guard against feedback loops while loading

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

        self.table = FileDropTableWidget(
            0, len(self.COLS), on_files_dropped=self._add_dropped_files)
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
        right.setMinimumWidth(360)

        settings_group = QGroupBox('Upload settings')
        settings_form = QFormLayout(settings_group)
        self.author_edit = QLineEdit()
        self.author_edit.setPlaceholderText('e.g. [[User:Seewolf|Harald Krichel]]')
        self.source_edit = QLineEdit('{{own}}')
        self.source_edit.setPlaceholderText('e.g. {{own}}')
        self.permission_edit = QLineEdit()
        self.permission_edit.setPlaceholderText('e.g. (leave empty unless needed)')
        self.license_edit = QLineEdit('{{Cc-by-sa-4.0}}')
        self.license_edit.setPlaceholderText('e.g. {{Cc-by-sa-4.0}}')
        self.other_templates_edit = QLineEdit()
        self.other_templates_edit.setPlaceholderText(
            'e.g. {{WikiPortraits at Berlinale 2026}}')
        self.other_fields_edit = QLineEdit()
        self.other_fields_edit.setPlaceholderText(
            'e.g. {{Credit line|Author=Harald Krichel|Other=WikiPortraits}}')
        self.gallery_prefix_edit = QLineEdit()
        self.gallery_prefix_edit.setPlaceholderText('e.g. User:Seewolf')
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

        # Mode toggle: expert mode shows the raw description_all text; when it is
        # off (the default), the structured fields are shown.
        self.expert_cb = QCheckBox('🧑\u200d💻 Expert mode (raw description_all text)')
        self.expert_cb.setToolTip('Edit the raw description_all text directly '
                                  'instead of using the structured single-line '
                                  'fields.')
        self.expert_cb.stateChanged.connect(self._toggle_expert)
        right_layout.addWidget(self.expert_cb)

        # ── Base description (for all files) ──
        base_group = QGroupBox('Base description (for all files)')
        base_layout = QVBoxLayout(base_group)
        self.base_text_edit = QTextEdit()
        self.base_text_edit.setPlaceholderText(
            'Shared lines for every file, e.g.\n'
            'creator=Q640\ncopyright=Q73566113\nlicense=Q18199165')
        self.base_text_edit.setMinimumHeight(110)
        self.base_text_edit.textChanged.connect(self._on_base_text_changed)
        base_layout.addWidget(self.base_text_edit)
        self.base_struct = StructuredDescriptionEditor(show_gallery_suffix=True)
        self.base_struct.changed.connect(self._on_base_struct_changed)
        self.base_struct.setVisible(False)
        base_layout.addWidget(self.base_struct)
        right_layout.addWidget(base_group)

        save_settings_btn = QPushButton('💾 Save settings')
        save_settings_btn.setToolTip('Save the upload settings and the base '
                                     'description so they are restored next time.')
        save_settings_btn.clicked.connect(self._on_save_settings)
        right_layout.addWidget(save_settings_btn)

        # Settings import/export to a plain text file (optionally incl. the
        # selected file's description).
        file_io = QHBoxLayout()
        save_file_btn = QPushButton('📄 Save to file…')
        save_file_btn.setToolTip('Write settings + base description to a text file.')
        save_file_btn.clicked.connect(self._save_settings_to_file)
        load_file_btn = QPushButton('📂 Load from file…')
        load_file_btn.setToolTip('Read settings back from a text file.')
        load_file_btn.clicked.connect(self._load_settings_from_file)
        self.export_file_desc_cb = QCheckBox('incl. selected file')
        self.export_file_desc_cb.setToolTip(
            "Also write the selected file's description into the settings file.")
        file_io.addWidget(save_file_btn)
        file_io.addWidget(load_file_btn)
        file_io.addWidget(self.export_file_desc_cb)
        file_io.addStretch()
        right_layout.addLayout(file_io)

        # ── Selected file description ──
        file_group = QGroupBox('Selected file – description')
        file_layout = QVBoxLayout(file_group)
        self.file_desc_edit = QTextEdit()
        self.file_desc_edit.setPlaceholderText(EXAMPLE_DESCRIPTION_ALL)
        self.file_desc_edit.setMinimumHeight(150)
        self.file_desc_edit.textChanged.connect(self.on_file_desc_changed)
        file_layout.addWidget(self.file_desc_edit)
        self.file_struct = StructuredDescriptionEditor(show_gallery_suffix=False)
        self.file_struct.changed.connect(self._on_file_struct_changed)
        self.file_struct.setVisible(False)
        file_layout.addWidget(self.file_struct)
        right_layout.addWidget(file_group)

        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumHeight(140)
        self.preview_label.setStyleSheet('background: #111; border-radius: 4px;')
        right_layout.addWidget(self.preview_label)
        right_layout.addStretch()

        # Wrap the right panel in a scroll area so fields are never compressed.
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setWidget(right)
        right_scroll.setMinimumWidth(380)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        splitter.addWidget(right_scroll)
        splitter.setSizes([720, 420])
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
        self.base_text_edit.setPlainText(self.settings.value(
            'base_description', 'copyright=Q73566113\nlicense=Q18199165'))
        # Expert mode is OFF by default (structured fields shown); honour a saved
        # choice. (The old 'beginner_mode' key, if present, is the inverse.)
        expert = self.settings.value('expert_mode', None)
        if expert is None:
            beginner = self.settings.value('beginner_mode', 'true')
            expert = beginner not in (True, 'true')
        else:
            expert = expert in (True, 'true')
        self.expert_cb.blockSignals(True)
        self.expert_cb.setChecked(bool(expert))
        self.expert_cb.blockSignals(False)
        self._apply_mode()

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
        self.settings.setValue('expert_mode', self.expert_cb.isChecked())

    def _on_save_settings(self):
        """Explicitly persist the current settings (button + on close)."""
        self._save_settings()
        self.settings.sync()
        self.status_bar.showMessage('Settings saved.', 3000)

    # ── Settings import/export as a plain text file ──────────────────────────

    # Section markers used in the exported text file.
    _BLOCK_BASE_BEGIN = '=== base_description ==='
    _BLOCK_BASE_END = '=== end base_description ==='
    _BLOCK_FILE_BEGIN = '=== file_description ==='
    _BLOCK_FILE_END = '=== end file_description ==='
    # Single-line keys written as "key = value".
    _FILE_KEYS = ('author', 'source', 'permission', 'license', 'other_templates',
                  'other_fields', 'gallery_prefix', 'timeout', 'expert_mode')

    def _save_settings_to_file(self):
        default = os.path.join(os.path.expanduser('~'), 'cammello_settings.txt')
        path, _ = QFileDialog.getSaveFileName(
            self, 'Save settings to file', default,
            'Text files (*.txt);;All files (*)')
        if not path:
            return

        values = {
            'author': self.author_edit.text(),
            'source': self.source_edit.text(),
            'permission': self.permission_edit.text(),
            'license': self.license_edit.text(),
            'other_templates': self.other_templates_edit.text(),
            'other_fields': self.other_fields_edit.text(),
            'gallery_prefix': self.gallery_prefix_edit.text(),
            'timeout': self.timeout_edit.text(),
            'expert_mode': 'true' if self.expert_cb.isChecked() else 'false',
        }
        lines = ['# Cammello settings file', f'# version: {__version__}', '']
        for k in self._FILE_KEYS:
            lines.append(f'{k} = {values[k]}')
        lines += ['', self._BLOCK_BASE_BEGIN,
                  self.base_text_edit.toPlainText(), self._BLOCK_BASE_END]

        included_file = False
        if self.export_file_desc_cb.isChecked():
            row = self._selected_row()
            if row is not None:
                item = self.table.item(row, self.COL_DESC)
                file_desc = item.text() if item else ''
                lines += ['', self._BLOCK_FILE_BEGIN, file_desc,
                          self._BLOCK_FILE_END]
                included_file = True

        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines) + '\n')
        except Exception as e:
            QMessageBox.critical(self, 'Save error',
                                 f'Could not write the file:\n{e}')
            return

        self.logger.info('Settings written to %s (file description incl.: %s)',
                         path, included_file)
        if self.export_file_desc_cb.isChecked() and not included_file:
            self.status_bar.showMessage(
                'Saved. No single file selected, so no file description was '
                'included.', 6000)
        else:
            self.status_bar.showMessage(f'Settings saved to {path}', 5000)

    def _parse_settings_file(self, content):
        """Parse an exported settings file into (singles, base_desc, file_desc).

        base_desc/file_desc are None if the respective block is absent.
        """
        singles = {}
        base_lines = None
        file_lines = None
        mode = None  # None | 'base' | 'file'
        for line in content.split('\n'):
            s = line.strip()
            if s == self._BLOCK_BASE_BEGIN:
                mode, base_lines = 'base', []
                continue
            if s == self._BLOCK_BASE_END and mode == 'base':
                mode = None
                continue
            if s == self._BLOCK_FILE_BEGIN:
                mode, file_lines = 'file', []
                continue
            if s == self._BLOCK_FILE_END and mode == 'file':
                mode = None
                continue
            if mode == 'base':
                base_lines.append(line)
                continue
            if mode == 'file':
                file_lines.append(line)
                continue
            if not s or s.startswith('#'):
                continue
            if '=' in line:
                key, val = line.split('=', 1)
                singles[key.strip()] = val.strip()
        base = '\n'.join(base_lines) if base_lines is not None else None
        filed = '\n'.join(file_lines) if file_lines is not None else None
        return singles, base, filed

    def _load_settings_from_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Load settings from file', os.path.expanduser('~'),
            'Text files (*.txt);;All files (*)')
        if not path:
            return
        try:
            with open(path, encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            QMessageBox.critical(self, 'Load error',
                                 f'Could not read the file:\n{e}')
            return

        singles, base_desc, file_desc = self._parse_settings_file(content)

        setters = {
            'author': self.author_edit.setText,
            'source': self.source_edit.setText,
            'permission': self.permission_edit.setText,
            'license': self.license_edit.setText,
            'other_templates': self.other_templates_edit.setText,
            'other_fields': self.other_fields_edit.setText,
            'gallery_prefix': self.gallery_prefix_edit.setText,
            'timeout': self.timeout_edit.setText,
        }
        for key, setter in setters.items():
            if key in singles:
                setter(singles[key])

        if base_desc is not None:
            self.base_text_edit.setPlainText(base_desc)

        if 'expert_mode' in singles:
            expert = singles['expert_mode'].strip().lower() in ('1', 'true', 'yes')
            self.expert_cb.blockSignals(True)
            self.expert_cb.setChecked(expert)
            self.expert_cb.blockSignals(False)
        self._apply_mode()  # re-sync visibility and the structured base view

        note = ''
        if file_desc is not None:
            row = self._selected_row()
            if row is not None:
                self.table.item(row, self.COL_DESC).setText(file_desc)
                self._load_selected_desc()
            else:
                note = (' (file description in the file was ignored: no single '
                        'file selected)')

        self.logger.info('Settings loaded from %s%s', path, note)
        self.status_bar.showMessage(f'Settings loaded from {path}.{note}', 6000)

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
        pattern = ' '.join('*' + ext for ext in IMAGE_EXTS)
        files, _ = QFileDialog.getOpenFileNames(
            self, 'Select image files', '', f'Images ({pattern})'
        )
        for filepath in files:
            self._add_row(filepath)
        if files:
            self.logger.debug('%d file(s) added to the table.', len(files))

    def _add_dropped_files(self, paths):
        """Add image files dropped onto the table."""
        for filepath in paths:
            self._add_row(filepath)
        if paths:
            self.logger.debug('%d file(s) added via drag-and-drop.', len(paths))

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

    def _selected_row(self):
        rows = list(set(i.row() for i in self.table.selectedItems()))
        return rows[0] if len(rows) == 1 else None

    def on_row_selected(self):
        row = self._selected_row()
        if row is None:
            self.file_desc_edit.setPlaceholderText(
                'Select a single file to edit its description.')
            return

        self._load_selected_desc()

        filepath = self.table.item(row, self.COL_FILENAME).data(Qt.UserRole)
        if filepath and os.path.exists(filepath):
            pix = QPixmap(filepath)
            if not pix.isNull():
                self.preview_label.setPixmap(
                    pix.scaled(300, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _load_selected_desc(self):
        """Load the selected row's description into the active per-file editor."""
        row = self._selected_row()
        text = ''
        if row is not None:
            item = self.table.item(row, self.COL_DESC)
            text = item.text() if item else ''
        self._loading_desc = True
        try:
            if self.expert_cb.isChecked():
                self.file_desc_edit.setPlainText(text)
            else:
                self.file_struct.load(text)
        finally:
            self._loading_desc = False

    def on_file_desc_changed(self):
        if self._loading_desc:
            return
        row = self._selected_row()
        if row is None:
            return
        self.table.item(row, self.COL_DESC).setText(self.file_desc_edit.toPlainText())

    def _on_file_struct_changed(self):
        if self._loading_desc:
            return
        row = self._selected_row()
        if row is None:
            return
        self.table.item(row, self.COL_DESC).setText(self.file_struct.assemble())

    # ── Expert mode ──────────────────────────────────────────────────────────

    def _toggle_expert(self, state):
        self.settings.setValue('expert_mode', bool(state))
        self._apply_mode()

    def _apply_mode(self):
        """Show the raw editors in expert mode, the structured ones otherwise,
        and (re)load the current content into the now-active editors."""
        expert = self.expert_cb.isChecked()
        # Per-file editors
        self.file_struct.setVisible(not expert)
        self.file_desc_edit.setVisible(expert)
        # Base editors
        self.base_struct.setVisible(not expert)
        self.base_text_edit.setVisible(expert)
        # Reload current content into the now-active editors.
        self._loading_desc = True
        try:
            self.base_struct.load(self.base_text_edit.toPlainText())
        finally:
            self._loading_desc = False
        self._load_selected_desc()

    # base_text_edit is the single source of truth for the base description;
    # base_struct is a synced structured view of it.
    def _on_base_text_changed(self):
        if self._loading_desc:
            return
        # nothing else to mirror; base_struct is reloaded on toggle/start

    def _on_base_struct_changed(self):
        if self._loading_desc:
            return
        self._loading_desc = True
        try:
            self.base_text_edit.setPlainText(self.base_struct.assemble())
        finally:
            self._loading_desc = False

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
