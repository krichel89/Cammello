#!/usr/bin/env python3
"""
CommonsSDC v0.2.0 - Batch upload tool for Wikimedia Commons (debugging build)

Ersetzt VicunaUploader mit Structured-Data-Unterstützung (caption_*, creator,
depicts, etc.). Diese Version legt den Schwerpunkt auf die FEHLERSUCHE:

  * Durchgaengiges Logging (Datei + Live-Log-Tab + Konsole), Zugangsdaten/Token
    werden im Log maskiert.
  * Jeder API-Aufruf laeuft ueber zentrale Helfer, die HTTP-Status, Nicht-JSON-
    Antworten und Netzwerkfehler sauber abfangen -- es gibt keine "leeren" Fehler
    mehr.
  * Vollstaendiger Wikitext und SDC-Payload werden pro Datei ins Log geschrieben.
  * badtoken-Retry (ein erneuter Versuch mit frischem CSRF-Token).
  * Konfigurierbarer HTTP-Timeout.
  * "Verbindung testen" (whoami), um den Login-Zustand zu pruefen.

Die Upload-/SDC-/Galerie-Logik ist gegenueber v0.1.1 funktional unveraendert;
alle Aenderungen sind additiv.

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
    QDialogButtonBox, QCheckBox, QStatusBar, QTabWidget, QPlainTextEdit
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSettings, QObject, QUrl
from PyQt5.QtGui import QPixmap, QFont, QDesktopServices

try:
    from PIL import Image
    from PIL.ExifTags import TAGS
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

__version__ = '0.3.0'

# ── Logging-Infrastruktur ───────────────────────────────────────────────────────

REDACT_KEYS = {'password', 'lgpassword', 'token', 'lgtoken', 'logintoken'}


def get_log_path():
    """Ermittelt einen beschreibbaren Pfad fuer die Logdatei."""
    base = os.path.join(os.path.expanduser('~'), 'CommonsSDC')
    try:
        os.makedirs(base, exist_ok=True)
        return os.path.join(base, 'commonssdc_debug.log')
    except Exception:
        return os.path.join(tempfile.gettempdir(), 'commonssdc_debug.log')


class LogEmitter(QObject):
    """Bruecke zwischen dem (thread-fremden) Logging und der GUI.

    pyqtSignal sorgt fuer eine queued connection, wenn aus dem Worker-Thread
    emittiert wird -- daher thread-sicher fuer die Aktualisierung des Log-Views.
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
    """Richtet Datei-, GUI- und Konsolen-Logging ein.

    Rueckgabe: (logger, emitter, gui_handler, log_path)
    """
    log_path = get_log_path()
    logger = logging.getLogger('CommonsSDC')
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    fmt = logging.Formatter('%(asctime)s %(levelname)-7s %(message)s',
                            '%Y-%m-%d %H:%M:%S')

    # Datei-Handler: immer volles Detail (DEBUG), damit nichts verloren geht.
    try:
        fh = RotatingFileHandler(log_path, maxBytes=2_000_000,
                                 backupCount=3, encoding='utf-8')
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except Exception:
        pass  # Notfalls ohne Datei-Log weiterarbeiten.

    # GUI-Handler: standardmaessig INFO, per Verbose-Checkbox auf DEBUG.
    emitter = LogEmitter()
    gui_handler = QtLogHandler(emitter)
    gui_handler.setLevel(logging.INFO)
    gui_handler.setFormatter(fmt)
    logger.addHandler(gui_handler)

    # Konsolen-Handler (z. B. beim Start aus dem Terminal).
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    logger.info('CommonsSDC %s gestartet. Logdatei: %s', __version__, log_path)
    return logger, emitter, gui_handler, log_path


# ── Structured Data extraction (unveraendert ggü. v0.1.1) ───────────────────────

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
    """Read date from EXIF data."""
    if not HAS_PIL:
        return ''
    try:
        img = Image.open(filepath)
        exif_data = img.getexif() if hasattr(img, 'getexif') else img._getexif()
        if exif_data is None:
            return ''
        for tag_id, value in exif_data.items():
            tag = TAGS.get(tag_id, tag_id)
            if tag == 'DateTimeOriginal':
                # "2025:01:15 14:30:00" -> "2025-01-15 14:30:00"
                return value.replace(':', '-', 2)
        return ''
    except Exception as e:
        if log:
            log.debug('EXIF-Datum konnte fuer %s nicht gelesen werden: %s',
                      filepath, e)
        return ''


# ── Ziel-Dateiname auf Commons ──────────────────────────────────────────────────

# Endungen, die als gueltige Datei-Endung akzeptiert werden.
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.tif', '.tiff', '.svg', '.webp'}

# In MediaWiki-Seitentiteln unzulaessige Zeichen.
FORBIDDEN_TITLE_CHARS = set('#<>[]|{}')


def normalize_commons_filename(target, source_path):
    """Bildet den Ziel-Dateinamen fuer den Upload auf Commons.

    - entfernt ein vorangestelltes 'File:'/'Datei:'
    - stellt sicher, dass eine (Bild-)Endung vorhanden ist; fehlt sie,
      wird die Endung der Quelldatei angehaengt
    - lehnt leere Namen, zu lange Namen und unzulaessige Zeichen mit
      ValueError ab (wird vom Worker als sprechender Fehler gemeldet)

    Rueckgabe: bereinigter Dateiname (ohne 'File:'-Praefix).
    """
    name = (target or '').strip()

    # Namespace-Praefix entfernen (case-insensitive).
    for prefix in ('file:', 'datei:'):
        if name.lower().startswith(prefix):
            name = name[len(prefix):].strip()
            break

    if not name:
        name = os.path.basename(source_path).strip()
    if not name:
        raise ValueError('Leerer Ziel-Dateiname.')

    # Endung sicherstellen.
    src_ext = os.path.splitext(source_path)[1]
    _, ext = os.path.splitext(name)
    if ext.lower() not in IMAGE_EXTS:
        if not src_ext:
            raise ValueError('Quelldatei hat keine Endung; bitte Endung '
                             'im Ziel-Dateinamen angeben.')
        name = name + src_ext

    bad = sorted({c for c in name if c in FORBIDDEN_TITLE_CHARS or ord(c) < 32})
    if bad:
        raise ValueError(
            'Unzulaessige Zeichen im Ziel-Dateinamen: '
            + ' '.join(repr(b) for b in bad)
            + ' (nicht erlaubt: # < > [ ] | { } sowie Steuerzeichen).'
        )

    if len(name.encode('utf-8')) > 240:
        raise ValueError('Ziel-Dateiname zu lang (max. ~240 Bytes).')

    return name


# ── MediaWiki API ──────────────────────────────────────────────────────────────

class MediaWikiApi:
    def __init__(self, api_url, username, password, timeout=120, logger=None):
        self.api_url = api_url
        self.timeout = timeout
        self.log = logger or logging.getLogger('CommonsSDC')
        self.session = requests.Session()
        self.session.headers['User-Agent'] = (
            f'CommonsSDC/{__version__} '
            f'(Python {sys.version_info.major}.{sys.version_info.minor}; PyQt5)'
        )
        self.csrf_token = None
        self.username = username
        self.password = password

    # ── zentrale Helfer ──────────────────────────────────────────────────────

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
        return text if len(text) <= n else text[:n] + f'… [{len(text)} Zeichen]'

    def _request(self, method, desc, **kwargs):
        """Fuehrt einen HTTP-Request aus und protokolliert ihn vollstaendig."""
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
            self.log.error('✗ Netzwerkfehler bei %s: %s', desc, e, exc_info=True)
            raise Exception(f'Netzwerkfehler bei {desc}: {e}') from e

        self.log.debug('← [%s] HTTP %s, %s Bytes',
                       desc, r.status_code, len(r.content or b''))
        return r

    def _json(self, r, desc):
        """Parst die Antwort als JSON; liefert sonst eine sprechende Exception."""
        if r.status_code != 200:
            body = self._trunc(r.text)
            self.log.error('✗ HTTP %s bei %s. Antwort: %s',
                           r.status_code, desc, body)
            raise Exception(f'HTTP {r.status_code} bei {desc}. Antwort: {body}')
        try:
            return r.json()
        except ValueError:
            body = self._trunc(r.text)
            self.log.error('✗ Keine JSON-Antwort bei %s. Antwort: %s', desc, body)
            raise Exception(
                f'Keine JSON-Antwort bei {desc} (evtl. Rate-Limit, Wartung oder '
                f'zu grosse Datei). Antwort: {body}'
            )

    def _check_error(self, data, desc):
        """Gibt (code, info) zurueck, falls die Antwort ein API-error enthaelt."""
        if isinstance(data, dict) and 'error' in data:
            err = data['error']
            code = err.get('code', 'unknown')
            info = err.get('info') or json.dumps(err, ensure_ascii=False)
            self.log.error('✗ API-Fehler bei %s: [%s] %s', desc, code, info)
            return code, info
        return None, None

    # ── Login / Session ──────────────────────────────────────────────────────

    def login(self):
        if not self.api_url.startswith('https://'):
            raise Exception('Sicherheitsfehler: API-URL muss HTTPS verwenden, nicht HTTP.')

        self.log.info('Login als „%s" …', self.username)

        r = self._request('GET', 'login-token', params={
            'action': 'query', 'meta': 'tokens', 'type': 'login', 'format': 'json'
        })
        j = self._json(r, 'login-token')
        try:
            login_token = j['query']['tokens']['logintoken']
        except (KeyError, TypeError):
            raise Exception('Login-Token nicht erhalten. Antwort: '
                            + self._trunc(json.dumps(j, ensure_ascii=False)))

        # 1) clientlogin (normales Benutzerkonto)
        r = self._request('POST', 'clientlogin', data={
            'action': 'clientlogin',
            'loginreturnurl': 'https://commons.wikimedia.org',
            'username': self.username, 'password': self.password,
            'logintoken': login_token, 'format': 'json'
        })
        result = self._json(r, 'clientlogin')
        cl = result.get('clientlogin', {})
        if cl.get('status') == 'PASS':
            self.log.info('clientlogin erfolgreich.')
            return True
        cl_msg = cl.get('message') or cl.get('messagecode') or cl.get('status')
        self.log.warning('clientlogin nicht erfolgreich: %s', cl_msg)

        # 2) Bot-Login (BotPasswords)
        r = self._request('POST', 'bot-login', data={
            'action': 'login', 'lgname': self.username,
            'lgpassword': self.password, 'lgtoken': login_token, 'format': 'json'
        })
        result = self._json(r, 'bot-login')
        login = result.get('login', {})
        if login.get('result') == 'Success':
            self.log.info('Bot-Login erfolgreich.')
            return True

        reason = login.get('reason') or login.get('result') or cl_msg or 'unbekannt'
        self.log.error('Login fehlgeschlagen: %s', reason)
        raise Exception(f'Login fehlgeschlagen: {reason}')

    def whoami(self):
        """Liefert die userinfo der aktuellen Session (fuer „Verbindung testen")."""
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
            raise Exception('CSRF-Token nicht erhalten. Antwort: '
                            + self._trunc(json.dumps(j, ensure_ascii=False)))
        return self.csrf_token

    def clear_token(self):
        self.csrf_token = None

    # ── Upload ───────────────────────────────────────────────────────────────

    def upload(self, filename, filepath, wikitext, comment, ignore_warnings=False):
        size = os.path.getsize(filepath) if os.path.exists(filepath) else -1
        self.log.info('Upload „%s" (%.1f MB)…',
                      filename, size / 1e6 if size > 0 else 0.0)
        self.log.debug('Wikitext fuer „%s":\n%s', filename, wikitext)

        for attempt in (1, 2):  # ein Retry bei badtoken
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
                    self.log.warning('badtoken – hole neuen Token, versuche erneut.')
                    self.clear_token()
                    continue
                raise Exception(f'[{code}] {info}')

            upload = result.get('upload', {})
            res = upload.get('result')
            self.log.debug('upload result=%s fuer „%s"', res, filename)

            if res == 'Success':
                self.log.info('✓ Hochgeladen: „%s"', filename)
                return True

            warnings = upload.get('warnings', {})
            if warnings:
                if 'exists' in warnings and ignore_warnings:
                    self.log.info('Datei existiert – ueberschreibe „%s".', filename)
                    return True
                detail = ', '.join(f'{k}={v}' for k, v in warnings.items())
                raise Exception(f'Warnungen: {detail}')

            # Unerwartete Struktur: NICHT als Erfolg durchwinken.
            raise Exception(
                f'Upload fehlgeschlagen (result={res!r}). Antwort: '
                + self._trunc(json.dumps(result, ensure_ascii=False))
            )

        raise Exception('Upload nach badtoken-Retry fehlgeschlagen.')

    def get_page_id(self, filename):
        r = self._request('GET', 'page-id', params={
            'action': 'query', 'titles': f'File:{filename}', 'format': 'json'
        })
        j = self._json(r, 'page-id')
        pages = j.get('query', {}).get('pages', {})
        if not pages:
            self.log.warning('Keine Seiten-ID fuer „%s" gefunden.', filename)
            return None
        page = next(iter(pages.values()))
        pid = page.get('pageid')
        self.log.debug('pageid fuer „%s" = %s', filename, pid)
        return pid

    def set_structured_data(self, page_id, labels, claims):
        """Set labels and claims in a single wbeditentity call."""
        labels_data = {lang: {'language': lang, 'value': val}
                       for lang, val in labels.items() if val}

        claims_data = []
        for prop, qid in claims:
            m = re.match(r'^Q(\d+)$', qid)
            if not m:
                self.log.warning('Ungueltige QID fuer %s uebersprungen: %r', prop, qid)
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
            self.log.debug('Keine SDC-Daten fuer M%s.', page_id)
            return

        data = {}
        if labels_data:
            data['labels'] = labels_data
        if claims_data:
            data['claims'] = claims_data

        self.log.debug('SDC-Payload fuer M%s: %s',
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
                    self.log.warning('SDC badtoken – neuer Token, erneuter Versuch.')
                    self.clear_token()
                    continue
                raise Exception(f'[{code}] {info}')
            self.log.info('✓ Structured Data gesetzt fuer M%s.', page_id)
            return

        raise Exception('wbeditentity nach badtoken-Retry fehlgeschlagen.')

    # ── Galerie ──────────────────────────────────────────────────────────────

    def get_page_content(self, page_title):
        """Get raw wikitext of a page."""
        index_url = self.api_url.replace('api.php', 'index.php')
        r = self._request('GET', f'raw {page_title}', url=index_url,
                          params={'action': 'raw', 'title': page_title})
        if r.status_code == 200:
            return r.text
        if r.status_code == 404:
            self.log.debug('Galerie-Seite „%s" existiert noch nicht.', page_title)
            return None
        self.log.warning('Galerie-Seite „%s": HTTP %s', page_title, r.status_code)
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
                raise Exception(f'[{code}] {info}')
            self.log.info('✓ Galerie „%s" aktualisiert.', page_title)
            return

        raise Exception('Galerie-Edit nach badtoken-Retry fehlgeschlagen.')

    def update_gallery(self, gallery_page, file_entries):
        """Append file entries to gallery page."""
        gallery_open = '<gallery mode="packed-hover" heights="240">'
        gallery_close = '</gallery>'
        comment = 'Uploaded with CommonsSDC'

        self.log.info('Aktualisiere Galerie „%s" (%d Eintraege)…',
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


# ── Upload Worker Thread ───────────────────────────────────────────────────────

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

        self.log.info('=== Upload-Lauf gestartet: %d Datei(en) ===', len(self.rows))

        for i, row in enumerate(self.rows):
            fname = (row.get('target_name')
                     or os.path.basename(row.get('filepath', ''))
                     or f'#{i}')
            try:
                self.progress.emit(i, 'Lade hoch…')

                # Ziel-Dateinamen normalisieren: Endung sicherstellen,
                # „File:"-Präfix entfernen, unzulässige Zeichen ablehnen.
                filename = normalize_commons_filename(
                    row.get('target_name', ''), row['filepath'])
                fname = filename
                if filename != row.get('source_name'):
                    self.log.info('Ziel-Dateiname: „%s" → „%s"',
                                  row.get('source_name'), filename)

                sd, clean_desc = extract_structured_data(row['description_all'])
                self.log.debug('Datei „%s": extrahierte SD=%s', fname, sd)

                other_templates = row.get('other_templates', '')
                license_text = row.get('license_text', '')

                # Kategorien (dedupliziert) aus Beschreibung ziehen
                cats_seen = set()
                cats = []
                for cat in re.findall(r'\[\[Category:[^\]]+\]\]', clean_desc):
                    if cat not in cats_seen:
                        cats.append(cat)
                        cats_seen.add(cat)
                clean_desc = re.sub(r'\[\[Category:[^\]]+\]\]\n?', '',
                                    clean_desc).strip()

                # {{Information}}-Block
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
                    'Uploaded with CommonsSDC', self.ignore_warnings
                )

                # Structured Data
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
                        self.log.warning('SDC uebersprungen: keine pageid fuer „%s".',
                                         fname)

                # Galerie sammeln
                gallery_suffix = sd.get('gallery_suffix', '').strip()
                if self.gallery_prefix:
                    if gallery_suffix:
                        gallery_page = self.gallery_prefix.rstrip('/') + '/' + gallery_suffix
                    else:
                        gallery_page = self.gallery_prefix
                elif gallery_suffix:
                    gallery_page = None  # kein Prefix gesetzt -> Galerie ueberspringen
                    self.log.warning('gallery_suffix gesetzt, aber kein Gallery-Prefix '
                                     '-> Galerie fuer „%s" uebersprungen.', fname)
                else:
                    gallery_page = self.gallery_prefix or None

                caption = sd.get('caption_en', '')
                gallery_entries.setdefault(gallery_page, []).append(
                    (filename, caption)
                )

                self.progress.emit(i, '✓ Fertig')
                success_count += 1

            except Exception as e:
                # Volltext + Traceback ins Log, kompakte Meldung in die Tabelle
                self.log.error('✗ Fehler bei „%s": %s', fname, e, exc_info=True)
                msg = str(e) or f'{type(e).__name__} (ohne Meldung)'
                self.error.emit(i, msg)
                self.progress.emit(i, '✗ Fehler')

        # Galerien aktualisieren
        for gallery_page, entries in gallery_entries.items():
            if not gallery_page:
                continue
            try:
                self.api.update_gallery(gallery_page, entries)
            except Exception as e:
                self.log.error('✗ Galerie-Fehler (%s): %s',
                               gallery_page, e, exc_info=True)
                self.error.emit(-1, f'Galerie-Fehler ({gallery_page}): {e}')

        self.log.info('=== Upload-Lauf beendet: %d/%d erfolgreich ===',
                      success_count, len(self.rows))
        self.finished.emit(
            f'Fertig: {success_count}/{len(self.rows)} Datei(en) hochgeladen.'
        )


# ── Login / Test Worker ────────────────────────────────────────────────────────

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
                self.failure.emit('Ungueltige Zugangsdaten.')
        except Exception as e:
            self.logger.error('Login-Fehler: %s', e, exc_info=True)
            self.failure.emit(str(e) or f'{type(e).__name__} (ohne Meldung)')


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
            self.done.emit(f'{name} (id {uid}); Gruppen: {groups}')
        except Exception as e:
            self.fail.emit(str(e) or f'{type(e).__name__} (ohne Meldung)')


# ── Login Dialog ───────────────────────────────────────────────────────────────

class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Login – Wikimedia Commons')
        self.setMinimumWidth(420)
        self.settings = QSettings('CommonsSDC', 'Login')

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.url_edit = QLineEdit(self.settings.value(
            'api_url', 'https://commons.wikimedia.org/w/api.php'))
        self.user_edit = QLineEdit(self.settings.value('username', ''))
        self.pass_edit = QLineEdit()
        self.pass_edit.setEchoMode(QLineEdit.Password)

        form.addRow('API URL:', self.url_edit)
        form.addRow('Benutzername:', self.user_edit)
        form.addRow('Passwort:', self.pass_edit)
        layout.addLayout(form)

        hint = QLabel('Tipp: Fuer Bot-Logins ein BotPassword '
                      '(Spezial:BotPasswords) verwenden.')
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


# ── Main Window ────────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    COLS = ['Quelldatei', 'Ziel-Dateiname (Commons)', 'Datum', 'Description (all)', 'Status']
    COL_FILENAME = 0
    COL_TITLE = 1
    COL_DATE = 2
    COL_DESC = 3
    COL_STATUS = 4

    def __init__(self, logger, emitter, gui_handler, log_path):
        super().__init__()
        self.logger = logger
        self.emitter = emitter
        self.gui_handler = gui_handler
        self.log_path = log_path

        self.setWindowTitle(f'CommonsSDC v{__version__}')
        self.setMinimumSize(1150, 740)
        self.api = None
        self.settings = QSettings('CommonsSDC', 'Main')

        self._build_ui()
        self._restore_settings()

        # Live-Log in die GUI spiegeln
        self.emitter.log_record.connect(self._append_log)

    # ── UI-Aufbau ────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.tabs.addTab(self._build_upload_tab(), '⬆ Upload')
        self.tabs.addTab(self._build_log_tab(), '🐞 Protokoll')

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage('Bereit. Bitte zuerst einloggen.')

    def _build_upload_tab(self):
        page = QWidget()
        main_layout = QVBoxLayout(page)

        # ── Toolbar ──
        toolbar = QHBoxLayout()
        self.login_btn = QPushButton('🔐 Login')
        self.login_btn.clicked.connect(self.do_login)

        self.test_btn = QPushButton('🔎 Verbindung testen')
        self.test_btn.clicked.connect(self.test_connection)
        self.test_btn.setEnabled(False)

        self.login_label = QLabel('Nicht eingeloggt')
        self.login_label.setStyleSheet('color: red')

        add_btn = QPushButton('➕ Dateien hinzufügen')
        add_btn.clicked.connect(self.add_files)
        remove_btn = QPushButton('➖ Auswahl entfernen')
        remove_btn.clicked.connect(self.remove_selected)
        clear_btn = QPushButton('🗑 Alle entfernen')
        clear_btn.clicked.connect(self.clear_all)

        self.upload_btn = QPushButton('🚀 Alle hochladen')
        self.upload_btn.clicked.connect(self.start_upload)
        self.upload_btn.setStyleSheet(
            'font-weight: bold; background: #2a7; color: white; padding: 4px 12px;')

        self.ignore_warnings_cb = QCheckBox('Warnungen ignorieren (überschreiben)')

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
        ht = self.table.horizontalHeaderItem(self.COL_TITLE)
        if ht:
            ht.setToolTip('Name, unter dem die Datei auf Commons gespeichert wird '
                          '(ohne „File:"). Endung wird automatisch ergänzt, falls '
                          'sie fehlt. Leer = Quell-Dateiname.')
        hs = self.table.horizontalHeaderItem(self.COL_FILENAME)
        if hs:
            hs.setToolTip('Lokale Quelldatei (wird nicht verändert).')
        self.table.horizontalHeader().setSectionResizeMode(
            self.COL_DESC, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(
            self.COL_FILENAME, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked)
        self.table.itemSelectionChanged.connect(self.on_row_selected)
        splitter.addWidget(self.table)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right.setMinimumWidth(330)

        settings_group = QGroupBox('Upload-Einstellungen')
        settings_form = QFormLayout(settings_group)
        self.author_edit = QLineEdit()
        self.source_edit = QLineEdit('{{own}}')
        self.permission_edit = QLineEdit()
        self.license_edit = QLineEdit('{{Cc-by-sa-4.0}}')
        self.other_templates_edit = QLineEdit()
        self.other_fields_edit = QLineEdit()
        self.other_fields_edit.setPlaceholderText(
            'z. B. {{Credit line|Author=Harald Krichel|Other=WikiPortraits}}')
        self.gallery_prefix_edit = QLineEdit()
        self.gallery_prefix_edit.setPlaceholderText('z. B. User:Harald Krichel')
        self.timeout_edit = QLineEdit('120')
        self.timeout_edit.setMaximumWidth(80)

        settings_form.addRow('Author:', self.author_edit)
        settings_form.addRow('Source:', self.source_edit)
        settings_form.addRow('Permission:', self.permission_edit)
        settings_form.addRow('License:', self.license_edit)
        settings_form.addRow('Other templates:', self.other_templates_edit)
        settings_form.addRow('Other fields:', self.other_fields_edit)
        settings_form.addRow('Gallery prefix:', self.gallery_prefix_edit)
        settings_form.addRow('HTTP-Timeout (s):', self.timeout_edit)
        right_layout.addWidget(settings_group)

        base_group = QGroupBox('Basis-description_all (für alle Dateien)')
        base_layout = QVBoxLayout(base_group)
        self.base_text_edit = QTextEdit()
        self.base_text_edit.setPlaceholderText(
            'creator=Q640\ncopyright=Q73566113\nlicense=Q18199165\n'
            '{{Berlinale 2025|type=red carpet}}')
        self.base_text_edit.setMaximumHeight(150)
        base_layout.addWidget(self.base_text_edit)
        right_layout.addWidget(base_group)

        file_group = QGroupBox('Ausgewählte Datei – description_all')
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
        self.verbose_cb = QCheckBox('Ausführliches Protokoll (verbose)')
        self.verbose_cb.stateChanged.connect(self._toggle_verbose)
        clear_log_btn = QPushButton('Leeren')
        clear_log_btn.clicked.connect(lambda: self.log_view.clear())
        copy_log_btn = QPushButton('Kopieren')
        copy_log_btn.clicked.connect(self._copy_log)
        open_file_btn = QPushButton('Logdatei öffnen')
        open_file_btn.clicked.connect(self._open_log_file)
        open_dir_btn = QPushButton('Ordner öffnen')
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

        path_label = QLabel(f'Logdatei: {self.log_path}')
        path_label.setStyleSheet('color: gray; font-size: 11px;')
        path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(path_label)

        return page

    # ── Log-Hilfsfunktionen ──────────────────────────────────────────────────

    def _append_log(self, msg):
        self.log_view.appendPlainText(msg)
        sb = self.log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _toggle_verbose(self, state):
        verbose = bool(state)
        self.gui_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
        self.logger.info('Verbose-Protokoll %s.', 'aktiviert' if verbose else 'deaktiviert')

    def _copy_log(self):
        QApplication.clipboard().setText(self.log_view.toPlainText())
        self.status_bar.showMessage('Protokoll in die Zwischenablage kopiert.', 3000)

    def _open_log_file(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.log_path))

    def _open_log_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(self.log_path)))

    # ── Settings ─────────────────────────────────────────────────────────────

    def _restore_settings(self):
        self.author_edit.setText(self.settings.value('author', ''))
        self.source_edit.setText(self.settings.value('source', '{{own}}'))
        self.license_edit.setText(self.settings.value('license', '{{Cc-by-sa-4.0}}'))
        self.other_templates_edit.setText(self.settings.value('other_templates', ''))
        self.other_fields_edit.setText(self.settings.value('other_fields', ''))
        self.gallery_prefix_edit.setText(self.settings.value('gallery_prefix', ''))
        self.timeout_edit.setText(self.settings.value('timeout', '120'))

    def _save_settings(self):
        self.settings.setValue('author', self.author_edit.text())
        self.settings.setValue('source', self.source_edit.text())
        self.settings.setValue('license', self.license_edit.text())
        self.settings.setValue('other_templates', self.other_templates_edit.text())
        self.settings.setValue('other_fields', self.other_fields_edit.text())
        self.settings.setValue('gallery_prefix', self.gallery_prefix_edit.text())
        self.settings.setValue('timeout', self.timeout_edit.text())

    def _get_timeout(self):
        try:
            t = int(self.timeout_edit.text())
            return t if t > 0 else 120
        except (ValueError, TypeError):
            return 120

    # ── Login / Test ─────────────────────────────────────────────────────────

    def do_login(self):
        dlg = LoginDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        api_url, username, password = dlg.get_credentials()

        self.login_btn.setEnabled(False)
        self.login_label.setText('Anmeldung läuft…')
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
        self.login_label.setText(f'✓ Eingeloggt als {username}')
        self.login_label.setStyleSheet('color: green')
        self.status_bar.showMessage(f'Eingeloggt als {username}')

    def _on_login_failure(self, error_msg):
        self.login_btn.setEnabled(True)
        self.login_label.setText('Nicht eingeloggt')
        self.login_label.setStyleSheet('color: red')
        QMessageBox.critical(self, 'Login-Fehler', error_msg)

    def test_connection(self):
        if not self.api:
            return
        self.test_btn.setEnabled(False)
        self.status_bar.showMessage('Teste Verbindung…')
        self._test_worker = TestWorker(self.api)
        self._test_worker.done.connect(self._on_test_done)
        self._test_worker.fail.connect(self._on_test_fail)
        self._test_worker.start()

    def _on_test_done(self, info):
        self.test_btn.setEnabled(True)
        self.logger.info('Verbindung OK: %s', info)
        self.status_bar.showMessage(f'Verbindung OK: {info}', 8000)
        QMessageBox.information(self, 'Verbindung OK',
                                f'Angemeldet als:\n{info}')

    def _on_test_fail(self, msg):
        self.test_btn.setEnabled(True)
        self.logger.error('Verbindungstest fehlgeschlagen: %s', msg)
        QMessageBox.warning(self, 'Verbindungsproblem', msg)

    # ── Tabelle ──────────────────────────────────────────────────────────────

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, 'Bilddateien auswählen', '',
            'Bilder (*.jpg *.jpeg *.png *.gif *.tif *.tiff *.svg *.webp)'
        )
        for filepath in files:
            self._add_row(filepath)
        if files:
            self.logger.debug('%d Datei(en) zur Tabelle hinzugefuegt.', len(files))

    def _add_row(self, filepath):
        row = self.table.rowCount()
        self.table.insertRow(row)
        filename = os.path.basename(filepath)
        date = read_exif_date(filepath, self.logger)

        self.table.setItem(row, self.COL_FILENAME, QTableWidgetItem(filename))
        # Ziel-Dateiname auf Commons; Standard = Quell-Dateiname inkl. Endung.
        self.table.setItem(row, self.COL_TITLE, QTableWidgetItem(filename))
        self.table.setItem(row, self.COL_DATE, QTableWidgetItem(date))
        self.table.setItem(row, self.COL_DESC, QTableWidgetItem(''))
        status_item = QTableWidgetItem('—')
        status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row, self.COL_STATUS, status_item)

        self.table.item(row, self.COL_FILENAME).setData(Qt.UserRole, filepath)

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
                'Einzelne Datei auswählen, um ihre Beschreibung zu bearbeiten.')
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
            QMessageBox.warning(self, 'Nicht eingeloggt', 'Bitte zuerst einloggen.')
            return
        if self.table.rowCount() == 0:
            QMessageBox.warning(self, 'Keine Dateien', 'Bitte zuerst Dateien hinzufügen.')
            return

        self._save_settings()
        # Timeout der aktiven Session anpassen, falls der Wert geaendert wurde.
        self.api.timeout = self._get_timeout()

        rows = []
        for r in range(self.table.rowCount()):
            filepath = self.table.item(r, self.COL_FILENAME).data(Qt.UserRole)
            source_name = self.table.item(r, self.COL_FILENAME).text()
            date = self.table.item(r, self.COL_DATE).text() if self.table.item(r, self.COL_DATE) else ''
            per_file_desc = self.table.item(r, self.COL_DESC).text() if self.table.item(r, self.COL_DESC) else ''

            base = self.base_text_edit.toPlainText().strip()
            combined = (base + '\n' + per_file_desc).strip() if base else per_file_desc

            # Ziel-Dateiname auf Commons (kann vom Quellnamen abweichen);
            # leer -> Quell-Dateiname. Endung wird im Worker sichergestellt.
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
        self.status_bar.showMessage(f'Lade hoch {row + 1}/{self.table.rowCount()}…')

    def on_error(self, row, msg):
        if row < 0:
            # Galerie-/globale Fehler nur im Log/Status anzeigen
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
        QMessageBox.information(self, 'Upload abgeschlossen',
                                summary + '\n\nDetails im Protokoll-Tab.')


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setApplicationName('CommonsSDC')
    app.setOrganizationName('CommonsSDC')

    logger, emitter, gui_handler, log_path = setup_logging()

    # Unbehandelte Ausnahmen ebenfalls ins Log schreiben.
    def excepthook(exc_type, exc_value, exc_tb):
        logger.critical('Unbehandelte Ausnahme:\n%s',
                        ''.join(traceback.format_exception(exc_type, exc_value, exc_tb)))
        sys.__excepthook__(exc_type, exc_value, exc_tb)
    sys.excepthook = excepthook

    window = MainWindow(logger, emitter, gui_handler, log_path)
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
