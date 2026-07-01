#!/usr/bin/env python3
"""
CommonsSDC v0.1.1 - Batch upload tool for Wikimedia Commons
Replaces VicunaUploader with structured data support (caption_*, creator, depicts, etc.)

Requirements: pip install PyQt5 requests Pillow
License: CC0
"""

import sys
import os
import re
import json
import requests
from datetime import datetime

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QPushButton, QLabel, QLineEdit,
    QTextEdit, QFileDialog, QMessageBox, QProgressBar, QSplitter,
    QGroupBox, QFormLayout, QHeaderView, QAbstractItemView, QDialog,
    QDialogButtonBox, QCheckBox, QStatusBar, QTabWidget
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSettings
from PyQt5.QtGui import QPixmap, QIcon, QFont

try:
    from PIL import Image
    from PIL.ExifTags import TAGS
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


__version__ = '0.1.1'

# ── Structured Data extraction ─────────────────────────────────────────────────

SD_KEYS = [
    'creator', 'copyright', 'license', 'depicts', 'gallery_suffix',
]

PROPERTY_MAP = {
    'creator':   'P170',
    'copyright': 'P6216',
    'license':   'P275',
    'depicts':   'P180',
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

def read_exif_date(filepath):
    """Read date from EXIF data."""
    if not HAS_PIL:
        return ''
    try:
        img = Image.open(filepath)
        # Use getexif() (public API); fall back to _getexif() for older Pillow
        exif_data = img.getexif() if hasattr(img, 'getexif') else img._getexif()
        if exif_data is None:
            return ''
        for tag_id, value in exif_data.items():
            tag = TAGS.get(tag_id, tag_id)
            if tag == 'DateTimeOriginal':
                # Format: "2025:01:15 14:30:00" -> "2025-01-15 14:30:00"
                return value.replace(':', '-', 2)
        return ''
    except Exception:
        return ''


# ── MediaWiki API ──────────────────────────────────────────────────────────────

class MediaWikiApi:
    def __init__(self, api_url, username, password):
        self.api_url = api_url
        self.session = requests.Session()
        self.session.headers['User-Agent'] = f'CommonsSDC/{__version__} (Python {sys.version_info.major}.{sys.version_info.minor}; PyQt5)'
        self.session.request = lambda method, url, **kwargs: requests.Session.request(
            self.session, method, url, timeout=kwargs.pop('timeout', 60), **kwargs
        )
        self.csrf_token = None
        self.username = username
        self.password = password

    def login(self):
        # Enforce HTTPS to prevent sending credentials over plain HTTP
        if not self.api_url.startswith('https://'):
            raise Exception('Security error: API URL must use HTTPS, not HTTP.')
        # Get login token
        r = self.session.get(self.api_url, params={
            'action': 'query', 'meta': 'tokens', 'type': 'login', 'format': 'json'
        })
        login_token = r.json()['query']['tokens']['logintoken']

        # Login
        r = self.session.post(self.api_url, data={
            'action': 'clientlogin', 'loginreturnurl': 'https://commons.wikimedia.org',
            'username': self.username, 'password': self.password,
            'logintoken': login_token, 'format': 'json'
        })
        result = r.json()
        if result.get('clientlogin', {}).get('status') == 'PASS':
            return True
        # Try bot login
        r = self.session.post(self.api_url, data={
            'action': 'login', 'lgname': self.username, 'lgpassword': self.password,
            'lgtoken': login_token, 'format': 'json'
        })
        return r.json().get('login', {}).get('result') == 'Success'

    def get_csrf_token(self):
        if self.csrf_token:
            return self.csrf_token
        r = self.session.get(self.api_url, params={
            'action': 'query', 'meta': 'tokens', 'format': 'json'
        })
        self.csrf_token = r.json()['query']['tokens']['csrftoken']
        return self.csrf_token

    def clear_token(self):
        self.csrf_token = None

    def upload(self, filename, filepath, wikitext, comment, ignore_warnings=False):
        token = self.get_csrf_token()
        with open(filepath, 'rb') as f:
            data = {
                'action': 'upload', 'filename': filename,
                'text': wikitext, 'comment': comment,
                'token': token, 'format': 'json'
            }
            if ignore_warnings:
                data['ignorewarnings'] = '1'
            r = self.session.post(self.api_url, data=data,
                                  files={'file': (os.path.basename(filepath), f)})
        result = r.json()
        if 'error' in result:
            if result['error']['code'] == 'badtoken':
                self.clear_token()
            raise Exception(result['error']['info'])
        upload = result.get('upload', {})
        if upload.get('result') == 'Success':
            return True
        warnings = upload.get('warnings', {})
        if 'exists' in warnings and ignore_warnings:
            return True
        if warnings:
            raise Exception('Warnings: ' + ', '.join(warnings.keys()))
        return True

    def get_page_id(self, filename):
        r = self.session.get(self.api_url, params={
            'action': 'query', 'titles': f'File:{filename}', 'format': 'json'
        })
        pages = r.json()['query']['pages']
        page = next(iter(pages.values()))
        return page.get('pageid')

    def set_structured_data(self, page_id, labels, claims):
        """Set labels and claims in a single wbeditentity call."""
        labels_data = {lang: {'language': lang, 'value': val}
                       for lang, val in labels.items() if val}
        claims_data = []
        for prop, qid in claims:
            m = re.match(r'^Q(\d+)$', qid)
            if not m:
                continue
            numeric_id = int(m.group(1))
            claims_data.append({
                'mainsnak': {
                    'snaktype': 'value',
                    'property': prop,
                    'datavalue': {
                        'type': 'wikibase-entityid',
                        'value': {'entity-type': 'item', 'numeric-id': numeric_id, 'id': qid}
                    }
                },
                'type': 'statement',
                'rank': 'normal'
            })

        if not labels_data and not claims_data:
            return

        data = {}
        if labels_data:
            data['labels'] = labels_data
        if claims_data:
            data['claims'] = claims_data

        token = self.get_csrf_token()
        r = self.session.post(self.api_url, data={
            'action': 'wbeditentity',
            'id': f'M{page_id}',
            'data': json.dumps(data),
            'token': token,
            'format': 'json'
        })
        result = r.json()
        if 'error' in result:
            if result['error']['code'] in ('badtoken', 'invalid-csrf-token'):
                self.clear_token()
            raise Exception(result['error']['info'])

    def get_page_content(self, page_title):
        """Get raw wikitext of a page."""
        index_url = self.api_url.replace('api.php', 'index.php')
        r = self.session.get(index_url, params={
            'action': 'raw', 'title': page_title
        })
        if r.status_code == 200:
            return r.text
        return None

    def set_page_content(self, page_title, content, comment):
        token = self.get_csrf_token()
        r = self.session.post(self.api_url, data={
            'action': 'edit', 'title': page_title,
            'text': content, 'summary': comment,
            'token': token, 'format': 'json'
        })
        if 'error' in r.json():
            raise Exception(r.json()['error']['info'])

    def update_gallery(self, gallery_page, file_entries):
        """Append file entries to gallery page."""
        gallery_open = '<gallery mode="packed-hover" heights="240">'
        gallery_close = '</gallery>'
        comment = 'Uploaded with CommonsSDC'

        new_entries = ''
        for fname, caption in file_entries:
            name = extract_name_from_caption(caption)
            # Sanitize caption: remove newlines and pipe characters to prevent wikitext injection
            if name:
                name = name.replace('|', '-').replace('\n', ' ').replace('\r', '')
                new_entries += f'File:{fname}|{name}\n'
            else:
                new_entries += f'File:{fname}\n'

        existing = self.get_page_content(gallery_page)
        if existing and gallery_close in existing:
            # Insert before last </gallery>
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
        self.rows = rows  # list of dicts: filepath, filename, title, date, description_all
        self.base_text = base_text
        self.gallery_prefix = gallery_prefix
        self.ignore_warnings = ignore_warnings

    def run(self):
        gallery_entries = {}  # gallery_page -> list of (filename, caption)
        success_count = 0

        for i, row in enumerate(self.rows):
            try:
                self.progress.emit(i, 'Uploading…')
                sd, clean_desc = extract_structured_data(row['description_all'])

                # Other templates
                other_templates = row.get('other_templates', '')
                license_text = row.get('license_text', '')

                # Extract categories from clean_desc (deduplicated), then remove from description
                cats_seen = set()
                cats = []
                for cat in re.findall(r'\[\[Category:[^\]]+\]\]', clean_desc):
                    if cat not in cats_seen:
                        cats.append(cat)
                        cats_seen.add(cat)
                # Remove [[Category:...]] from description field
                clean_desc = re.sub(r'\[\[Category:[^\]]+\]\]\n?', '', clean_desc).strip()
                # Re-set description in info block
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

                # Assemble wikitext
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
                    row['filename'], row['filepath'], wikitext,
                    'Uploaded with CommonsSDC', self.ignore_warnings
                )

                # Structured data
                labels = {}
                claims = []
                for key, val in sd.items():
                    if key.startswith('caption_'):
                        lang = key[8:]  # e.g. 'caption_zh' -> 'zh'
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
                    page_id = self.api.get_page_id(row['filename'])
                    if page_id:
                        self.api.set_structured_data(page_id, labels, claims)

                # Gallery
                gallery_suffix = sd.get('gallery_suffix', '').strip()
                if self.gallery_prefix:
                    if gallery_suffix:
                        gallery_page = self.gallery_prefix.rstrip('/') + '/' + gallery_suffix
                    else:
                        gallery_page = self.gallery_prefix
                elif gallery_suffix:
                    gallery_page = None  # no prefix set, skip gallery
                    caption = sd.get('caption_en', '')
                    gallery_entries.setdefault(gallery_page, []).append(
                        (row['filename'], caption)
                    )

                self.progress.emit(i, '✓ Done')
                success_count += 1

            except Exception as e:
                self.error.emit(i, str(e))
                self.progress.emit(i, f'✗ Error')

        # Update galleries
        for gallery_page, entries in gallery_entries.items():
            if not gallery_page:
                continue
            try:
                self.api.update_gallery(gallery_page, entries)
            except Exception as e:
                self.error.emit(-1, f'Gallery error ({gallery_page}): {str(e)}')

        self.finished.emit(f'Done: {success_count}/{len(self.rows)} files uploaded.')


# ── Login Dialog ───────────────────────────────────────────────────────────────

class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Login – Wikimedia Commons')
        self.setMinimumWidth(400)
        self.settings = QSettings('CommonsSDC', 'Login')

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.url_edit = QLineEdit(self.settings.value('api_url', 'https://commons.wikimedia.org/w/api.php'))
        self.user_edit = QLineEdit(self.settings.value('username', ''))
        self.pass_edit = QLineEdit()
        self.pass_edit.setEchoMode(QLineEdit.Password)

        form.addRow('API URL:', self.url_edit)
        form.addRow('Username:', self.user_edit)
        form.addRow('Password:', self.pass_edit)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_credentials(self):
        self.settings.setValue('api_url', self.url_edit.text())
        self.settings.setValue('username', self.user_edit.text())
        return self.url_edit.text(), self.user_edit.text(), self.pass_edit.text()


# ── Main Window ────────────────────────────────────────────────────────────────


# ── Login Worker Thread ────────────────────────────────────────────────────────

class LoginWorker(QThread):
    success = pyqtSignal(object)  # MediaWikiApi instance
    failure = pyqtSignal(str)     # error message

    def __init__(self, api_url, username, password):
        super().__init__()
        self.api_url = api_url
        self.username = username
        self.password = password

    def run(self):
        try:
            api = MediaWikiApi(self.api_url, self.username, self.password)
            if api.login():
                self.success.emit(api)
            else:
                self.failure.emit('Invalid credentials.')
        except Exception as e:
            self.failure.emit(str(e))

class MainWindow(QMainWindow):
    COLS = ['Filename', 'Title', 'Date', 'Description (all)', 'Status']
    COL_FILENAME = 0
    COL_TITLE = 1
    COL_DATE = 2
    COL_DESC = 3
    COL_STATUS = 4

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f'CommonsSDC v{__version__}')
        self.setMinimumSize(1100, 700)
        self.api = None
        self.settings = QSettings('CommonsSDC', 'Main')
        self._build_ui()
        self._restore_settings()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # ── Toolbar row ──
        toolbar = QHBoxLayout()
        self.login_btn = QPushButton('🔐 Login')
        self.login_btn.clicked.connect(self.do_login)
        self.login_label = QLabel('Not logged in')
        self.login_label.setStyleSheet('color: red')

        add_btn = QPushButton('➕ Add Files')
        add_btn.clicked.connect(self.add_files)
        remove_btn = QPushButton('➖ Remove Selected')
        remove_btn.clicked.connect(self.remove_selected)
        clear_btn = QPushButton('🗑 Clear All')
        clear_btn.clicked.connect(self.clear_all)

        self.upload_btn = QPushButton('🚀 Upload All')
        self.upload_btn.clicked.connect(self.start_upload)
        self.upload_btn.setStyleSheet('font-weight: bold; background: #2a7; color: white; padding: 4px 12px;')

        self.ignore_warnings_cb = QCheckBox('Ignore warnings (overwrite)')

        toolbar.addWidget(self.login_btn)
        toolbar.addWidget(self.login_label)
        toolbar.addSpacing(20)
        toolbar.addWidget(add_btn)
        toolbar.addWidget(remove_btn)
        toolbar.addWidget(clear_btn)
        toolbar.addStretch()
        toolbar.addWidget(self.ignore_warnings_cb)
        toolbar.addWidget(self.upload_btn)
        main_layout.addLayout(toolbar)

        # ── Splitter: table + right panel ──
        splitter = QSplitter(Qt.Horizontal)

        # File table
        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.horizontalHeader().setSectionResizeMode(self.COL_DESC, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(self.COL_FILENAME, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked)
        self.table.itemSelectionChanged.connect(self.on_row_selected)
        splitter.addWidget(self.table)

        # Right panel
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right.setMinimumWidth(320)

        # Settings group
        settings_group = QGroupBox('Upload Settings')
        settings_form = QFormLayout(settings_group)

        self.author_edit = QLineEdit()
        self.source_edit = QLineEdit('{{own}}')
        self.permission_edit = QLineEdit()
        self.license_edit = QLineEdit('{{Cc-by-sa-4.0}}')
        self.other_templates_edit = QLineEdit()
        self.other_fields_edit = QLineEdit()
        self.other_fields_edit.setPlaceholderText('e.g. {{Credit line|Author=Harald Krichel|Other=WikiPortraits}}')
        self.gallery_prefix_edit = QLineEdit()
        self.gallery_prefix_edit.setPlaceholderText('e.g. User:Harald Krichel')

        settings_form.addRow('Author:', self.author_edit)
        settings_form.addRow('Source:', self.source_edit)
        settings_form.addRow('Permission:', self.permission_edit)
        settings_form.addRow('License:', self.license_edit)
        settings_form.addRow('Other templates:', self.other_templates_edit)
        settings_form.addRow('Other fields:', self.other_fields_edit)
        settings_form.addRow('Gallery prefix:', self.gallery_prefix_edit)
        right_layout.addWidget(settings_group)

        # Base text
        base_group = QGroupBox('Base description_all (for all files)')
        base_layout = QVBoxLayout(base_group)
        self.base_text_edit = QTextEdit()
        self.base_text_edit.setPlaceholderText(
            'creator=Q640\ncopyright=Q73566113\nlicense=Q18199165\n{{Berlinale 2025|type=red carpet}}'
        )
        self.base_text_edit.setMaximumHeight(160)
        base_layout.addWidget(self.base_text_edit)
        right_layout.addWidget(base_group)

        # Per-file description
        file_group = QGroupBox('Selected file – description_all')
        file_layout = QVBoxLayout(file_group)
        self.file_desc_edit = QTextEdit()
        self.file_desc_edit.setPlaceholderText(
            'caption_en=Name at the Event\ncaption_de=Name beim Event\ndepicts=Q12345\n\n{{en|1=Description}}'
        )
        self.file_desc_edit.textChanged.connect(self.on_file_desc_changed)
        file_layout.addWidget(self.file_desc_edit)
        right_layout.addWidget(file_group)

        # Preview
        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumHeight(120)
        self.preview_label.setStyleSheet('background: #111; border-radius: 4px;')
        right_layout.addWidget(self.preview_label)

        splitter.addWidget(right)
        splitter.setSizes([700, 380])
        main_layout.addWidget(splitter)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage('Ready. Please login first.')

    def _restore_settings(self):
        self.author_edit.setText(self.settings.value('author', ''))
        self.source_edit.setText(self.settings.value('source', '{{own}}'))
        self.license_edit.setText(self.settings.value('license', '{{Cc-by-sa-4.0}}'))
        self.other_fields_edit.setText(self.settings.value('other_fields', ''))
        self.gallery_prefix_edit.setText(self.settings.value('gallery_prefix', ''))

    def _save_settings(self):
        self.settings.setValue('author', self.author_edit.text())
        self.settings.setValue('source', self.source_edit.text())
        self.settings.setValue('license', self.license_edit.text())
        self.settings.setValue('other_fields', self.other_fields_edit.text())
        self.settings.setValue('gallery_prefix', self.gallery_prefix_edit.text())

    def do_login(self):
        dlg = LoginDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        api_url, username, password = dlg.get_credentials()
        self.login_btn.setEnabled(False)
        self.login_label.setText('Logging in…')
        self.login_label.setStyleSheet('color: orange')
        # Run in background thread to avoid UI freeze
        self._login_worker = LoginWorker(api_url, username, password)
        self._login_worker.success.connect(lambda api: self._on_login_success(api, username))
        self._login_worker.failure.connect(self._on_login_failure)
        self._login_worker.start()

    def _on_login_success(self, api, username):
        self.api = api
        self.login_btn.setEnabled(True)
        self.login_label.setText(f'✓ Logged in as {username}')
        self.login_label.setStyleSheet('color: green')
        self.status_bar.showMessage(f'Logged in as {username}')

    def _on_login_failure(self, error_msg):
        self.login_btn.setEnabled(True)
        self.login_label.setText('Not logged in')
        self.login_label.setStyleSheet('color: red')
        QMessageBox.critical(self, 'Login error', error_msg)

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, 'Select image files', '',
            'Images (*.jpg *.jpeg *.png *.gif *.tif *.tiff *.svg *.webp)'
        )
        for filepath in files:
            self._add_row(filepath)

    def _add_row(self, filepath):
        row = self.table.rowCount()
        self.table.insertRow(row)
        filename = os.path.basename(filepath)
        date = read_exif_date(filepath)

        self.table.setItem(row, self.COL_FILENAME, QTableWidgetItem(filename))
        title_item = QTableWidgetItem(os.path.splitext(filename)[0])
        self.table.setItem(row, self.COL_TITLE, title_item)
        self.table.setItem(row, self.COL_DATE, QTableWidgetItem(date))
        self.table.setItem(row, self.COL_DESC, QTableWidgetItem(''))
        status_item = QTableWidgetItem('—')
        status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row, self.COL_STATUS, status_item)
        # Store filepath in item data
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
            self.file_desc_edit.setPlaceholderText('Select a single file to edit its description.')
            return
        row = rows[0]
        desc = self.table.item(row, self.COL_DESC)
        self.file_desc_edit.blockSignals(True)
        self.file_desc_edit.setPlainText(desc.text() if desc else '')
        self.file_desc_edit.blockSignals(False)

        # Show preview
        filepath = self.table.item(row, self.COL_FILENAME).data(Qt.UserRole)
        if filepath and os.path.exists(filepath):
            pix = QPixmap(filepath)
            if not pix.isNull():
                self.preview_label.setPixmap(
                    pix.scaled(300, 200, Qt.KeepAspectRatio,
                               Qt.SmoothTransformation)
                )

    def on_file_desc_changed(self):
        rows = list(set(i.row() for i in self.table.selectedItems()))
        if len(rows) != 1:
            return
        row = rows[0]
        self.table.item(row, self.COL_DESC).setText(self.file_desc_edit.toPlainText())

    def start_upload(self):
        if not self.api:
            QMessageBox.warning(self, 'Not logged in', 'Please login first.')
            return
        if self.table.rowCount() == 0:
            QMessageBox.warning(self, 'No files', 'Please add files first.')
            return

        self._save_settings()

        rows = []
        for r in range(self.table.rowCount()):
            filepath = self.table.item(r, self.COL_FILENAME).data(Qt.UserRole)
            filename = self.table.item(r, self.COL_FILENAME).text()
            date = self.table.item(r, self.COL_DATE).text() if self.table.item(r, self.COL_DATE) else ''
            per_file_desc = self.table.item(r, self.COL_DESC).text() if self.table.item(r, self.COL_DESC) else ''

            # Merge base text + per-file description
            base = self.base_text_edit.toPlainText().strip()
            combined = (base + '\n' + per_file_desc).strip() if base else per_file_desc

            title = self.table.item(r, self.COL_TITLE).text() if self.table.item(r, self.COL_TITLE) else filename
            rows.append({
                'filepath': filepath,
                'filename': title if title else filename,
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
        item = self.table.item(row, self.COL_STATUS)
        if item:
            item.setText(f'✗ {msg[:60]}')
            item.setToolTip(msg)

    def on_finished(self, summary):
        self.progress_bar.setVisible(False)
        self.upload_btn.setEnabled(True)
        self.status_bar.showMessage(summary)
        QMessageBox.information(self, 'Upload complete', summary)


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setApplicationName('CommonsSDC')
    app.setOrganizationName('CommonsSDC')
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
