"""Flickr tab (0.10.0): account/authorization, shared file list, upload.

Independent of pyexiv2 (needs only the main table), so the tab has its own
feature switch (feature_flickr) and works even when IPTC/FTP/Culling are off.
Files are uploaded AS THEY ARE; the photo title on Flickr is the target
filename without extension. Privacy follows the account's upload defaults
(changing it per upload would be a separate feature).
"""
import os

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QListWidget, QListWidgetItem, QGroupBox, QFormLayout, QSplitter,
    QScrollArea, QTextEdit, QMessageBox, QAbstractItemView, QComboBox)
from PyQt5.QtCore import Qt, QSize, QUrl
from PyQt5.QtGui import QDesktopServices

from .constants import *
from .i18n import tr
from . import flickr
from . import channels
from . import credentials
from .widgets import (UploadProgressDialog, apply_form_ratio,
                      CollapsibleGroupBox, NoWheelComboBox)


class FlickrMixin:

    # ── Tab construction ─────────────────────────────────────────────────────

    def _build_flickr_groups(self, parent_layout):
        """Appends the Flickr account/upload groups to the merged
        FTP / Flickr tab (0.10.0: one shared file list and status area for
        both services). The Flickr list/status/count attributes are ALIASES
        of the FTP widgets, so all existing logic keeps working."""
        self._flickr_request = None      # (token, secret) during authorization
        # Shared widgets (created by the FTP part of the merged tab).
        self.flickr_list = self.ftp_list
        self.flickr_count_lbl = self.ftp_count_lbl
        self.flickr_status = self.ftp_status

        # Collapsible like every other section (0.12.8); open on first use.
        acc = CollapsibleGroupBox(tr('Flickr account'))
        form = QFormLayout(acc.content)
        self.flickr_api_key_edit = QLineEdit()
        form.addRow(tr('API key:'), self.flickr_api_key_edit)
        self.flickr_api_secret_edit = QLineEdit()
        self.flickr_api_secret_edit.setEchoMode(QLineEdit.Password)
        self.flickr_api_secret_edit.setToolTip(
            tr('Create a key/secret pair at flickr.com/services/apps/create. '
               'Both are stored in the settings.'))
        form.addRow(tr('API secret:'), self.flickr_api_secret_edit)
        self.flickr_auth_lbl = QLabel(tr('Not authorized.'))
        form.addRow('', self.flickr_auth_lbl)
        auth1 = QPushButton(tr('1. Open authorization page'))
        auth1.clicked.connect(self._flickr_auth_step1)
        form.addRow('', auth1)
        vrow = QHBoxLayout()
        self.flickr_verifier_edit = QLineEdit()
        self.flickr_verifier_edit.setPlaceholderText(
            tr('Verification code from the browser (nnn-nnn-nnn)'))
        vrow.addWidget(self.flickr_verifier_edit)
        auth2 = QPushButton(tr('2. Complete authorization'))
        auth2.clicked.connect(self._flickr_auth_step2)
        vrow.addWidget(auth2)
        form.addRow('', vrow)
        test_btn = QPushButton(tr('Test connection'))
        test_btn.clicked.connect(self._flickr_test)
        form.addRow('', test_btn)
        apply_form_ratio(form)
        parent_layout.addWidget(acc)

        up = CollapsibleGroupBox(tr('Flickr upload'))
        uform = QFormLayout(up.content)
        note = QLabel(tr('Files are uploaded as they are; the Flickr title is '
                         'the target filename. Privacy follows your account '
                         'upload defaults.'))
        note.setWordWrap(True)
        uform.addRow(note)
        self.flickr_license_combo = NoWheelComboBox()
        self.flickr_license_combo.setSizeAdjustPolicy(
            QComboBox.AdjustToContents)
        # itemData: None = leave the account default; else the license id
        # applied via flickr.photos.licenses.setLicense after the upload.
        self.flickr_license_combo.addItem(tr('Account default'), None)
        for lic_id, lic_name in flickr.LICENSES:
            self.flickr_license_combo.addItem(
                tr(lic_name) if lic_id == '0' else lic_name, lic_id)
        uform.addRow(tr('License:'), self.flickr_license_combo)
        self.flickr_upload_btn = QPushButton(tr('Upload to Flickr'))
        self.flickr_upload_btn.clicked.connect(self._flickr_upload)
        uform.addRow(self.flickr_upload_btn)
        apply_form_ratio(uform)
        parent_layout.addWidget(up)

    def _flickr_log(self, msg):
        self.logger.info('[Flickr] %s', msg)
        self.flickr_status.append('Flickr: ' + msg)

    # ── Shared file list ─────────────────────────────────────────────────────

    def _flickr_refresh_list(self):
        self._ftp_refresh_list()

    def _flickr_selected(self):
        """[(path, title)] for the selection, or ALL files when nothing is
        selected (the convention used everywhere else). Commons-marked files
        are excluded (channel marks, 0.12.1) - they are disabled in the list,
        so a selection cannot contain them, but the all-files fallback is
        filtered here."""
        items = self.flickr_list.selectedItems()
        if not items:
            items = [self.flickr_list.item(i)
                     for i in range(self.flickr_list.count())]
        out = []
        for it in items:
            path = it.data(Qt.UserRole)
            if self._channel_mark(path) == channels.MARK_COMMONS:
                continue
            title = os.path.splitext(it.data(Qt.UserRole + 1) or
                                     os.path.basename(path))[0]
            out.append((path, title))
        return out

    # ── Account / authorization ─────────────────────────────────────────────

    def _flickr_credentials_ok(self, need_token=False):
        if not (self.flickr_api_key_edit.text().strip()
                and (self.flickr_api_secret_edit.text().strip()
                     or self._flickr_secret('api_secret'))):
            QMessageBox.warning(self, 'Flickr',
                                tr('API key and secret are missing (create '
                                   'them at flickr.com/services/apps/create).'))
            return False
        if need_token and not self._flickr_secret('token'):
            QMessageBox.warning(self, 'Flickr',
                               tr('Not authorized yet - run the two '
                                  'authorization steps first.'))
            return False
        return True

    def _flickr_secret(self, kind):
        """One Flickr secret (token / token_secret / api_secret), keyring
        first, QSettings plaintext as the no-backend fallback (0.16.1)."""
        return credentials.migrate_qsettings_value(
            self.settings, 'flickr_' + kind, credentials.flickr_slot(kind))

    def _flickr_client(self):
        api_secret = (self.flickr_api_secret_edit.text().strip()
                      or self._flickr_secret('api_secret'))
        if api_secret and not self.flickr_api_secret_edit.text().strip():
            self.flickr_api_secret_edit.setText(api_secret)
        return flickr.FlickrClient(
            self.flickr_api_key_edit.text().strip(),
            api_secret,
            self._flickr_secret('token'),
            self._flickr_secret('token_secret'),
            logger=self.logger)

    def _flickr_auth_step1(self):
        if not self._flickr_credentials_ok():
            return
        try:
            token, secret = self._flickr_client().get_request_token()
        except Exception as e:
            QMessageBox.critical(self, 'Flickr', str(e))
            return
        self._flickr_request = (token, secret)
        url = flickr.FlickrClient.authorize_url(token)
        QDesktopServices.openUrl(QUrl(url))
        self._flickr_log(tr('Authorization page opened in the browser. '
                            'Grant access, then paste the code below.'))

    def _flickr_auth_step2(self):
        if self._flickr_request is None:
            QMessageBox.warning(self, 'Flickr',
                                tr('Run step 1 first (the code belongs to '
                                   'that request).'))
            return
        verifier = self.flickr_verifier_edit.text().strip()
        if not verifier:
            QMessageBox.warning(self, 'Flickr',
                                tr('The verification code is missing.'))
            return
        token, secret = self._flickr_request
        try:
            atoken, asecret, username = self._flickr_client(
                ).get_access_token(token, secret, verifier)
        except Exception as e:
            QMessageBox.critical(self, 'Flickr', str(e))
            return
        # 0.16.1: the OAuth token pair identifies the account and signs
        # every request - keyring material, not settings material. Plaintext
        # only when no backend is there.
        if not (credentials.store(credentials.flickr_slot('token'), atoken)
                and credentials.store(credentials.flickr_slot('token_secret'),
                                      asecret)):
            self.settings.setValue('flickr_token', atoken)
            self.settings.setValue('flickr_token_secret', asecret)
        else:
            self.settings.remove('flickr_token')
            self.settings.remove('flickr_token_secret')
        # Non-secret marker so the status line can say "authorized" without
        # reading the keyring during the window build.
        self.settings.setValue('flickr_authorized', True)
        self.settings.setValue('flickr_username', username)
        self.settings.sync()
        self._flickr_request = None
        self.flickr_verifier_edit.clear()
        self._flickr_show_auth_state()
        self._flickr_log(tr('Authorized as {username}.').format(
            username=username or '?'))

    def _flickr_show_auth_state(self):
        username = self.settings.value('flickr_username', '')
        if (self.settings.value('flickr_authorized', False, type=bool)
                or self.settings.value('flickr_token', '')):
            self.flickr_auth_lbl.setText(
                tr('Authorized as {username}.').format(
                    username=username or '?'))
        else:
            self.flickr_auth_lbl.setText(tr('Not authorized.'))

    def _flickr_test(self):
        if not self._flickr_credentials_ok(need_token=True):
            return
        try:
            username = self._flickr_client().test_login()
        except Exception as e:
            QMessageBox.critical(self, 'Flickr', str(e))
            return
        self.settings.setValue('flickr_username', username)
        self._flickr_show_auth_state()
        self._flickr_log(tr('Connection OK: {info}').format(info=username))

    # ── Upload ───────────────────────────────────────────────────────────────

    def _flickr_upload(self):
        if not self._flickr_credentials_ok(need_token=True):
            return
        files = self._flickr_selected()
        if not files:
            QMessageBox.information(self, 'Flickr', tr('No files'))
            return
        self._flickr_start_upload(files, self.flickr_upload_btn)

    def _flickr_start_upload(self, files, button=None):
        """Shared by the Flickr tab and the Culling '-> Flickr' target."""
        # Flickr is the commercial channel too: record the decision (0.12.4).
        self._mark_uploaded_channel([p for p, _title in files],
                                    channels.MARK_COMMERCIAL)
        self._flickr_btn = button
        if button is not None:
            button.setEnabled(False)
        self._flickr_dlg = UploadProgressDialog(len(files), self)
        self._flickr_done = 0
        license_id = (self.flickr_license_combo.currentData()
                      if hasattr(self, 'flickr_license_combo') else None)
        self._flickr_worker = flickr.FlickrUploadWorker(
            self._flickr_client(), files, self.logger,
            license_id=license_id)
        self._flickr_worker.file_started.connect(self._flickr_dlg.set_current)
        self._flickr_worker.progress.connect(self._flickr_on_progress)
        self._flickr_worker.error.connect(
            lambda i, m: self._flickr_log(f'✗ {m}'))
        self._flickr_worker.finished.connect(self._flickr_on_finished)
        self._flickr_dlg.cancel_requested.connect(self._flickr_worker.cancel)
        self._flickr_dlg.show()
        self._flickr_worker.start()

    def _flickr_on_progress(self, _index, status):
        if status.startswith(('✓', '✗')):
            self._flickr_done += 1
            self._flickr_dlg.set_done(self._flickr_done)

    def _flickr_on_finished(self, summary):
        if self._flickr_btn is not None:
            self._flickr_btn.setEnabled(True)
        self._flickr_dlg.force_close()
        self._flickr_log(summary)
        QMessageBox.information(self, tr('Flickr upload'), summary)

    # ── Settings ─────────────────────────────────────────────────────────────

    def _flickr_save_settings(self):
        s = self.settings
        s.setValue('flickr_api_key', self.flickr_api_key_edit.text().strip())
        secret_text = self.flickr_api_secret_edit.text().strip()
        if secret_text:
            if credentials.store(credentials.flickr_slot('api_secret'),
                                 secret_text):
                s.remove('flickr_api_secret')
            else:
                s.setValue('flickr_api_secret', secret_text)
        s.setValue('flickr_license',
                   self.flickr_license_combo.currentData() or '')

    def _flickr_load_settings(self):
        s = self.settings
        self.flickr_api_key_edit.setText(s.value('flickr_api_key', ''))
        # Build time: plaintext only - _flickr_secret() (keyring) runs
        # lazily at first USE, never while the window is being built.
        self.flickr_api_secret_edit.setText(s.value('flickr_api_secret', ''))
        saved_lic = s.value('flickr_license', '') or None
        idx = self.flickr_license_combo.findData(saved_lic)
        if idx >= 0:
            self.flickr_license_combo.setCurrentIndex(idx)
        self._flickr_show_auth_state()
