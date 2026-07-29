"""Part of MainWindow, split out as a mixin. See main_window.py for the class
that combines these mixins. Mixins are plain classes holding grouped methods;
they rely on attributes created in MainWindow.__init__ / _build_* and on the
COL_* / COLS class attributes defined on MainWindow."""
import os
import sys
import traceback
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QPushButton, QLabel, QLineEdit,
    QTextEdit, QFileDialog, QMessageBox, QProgressBar, QSplitter,
    QGroupBox, QFormLayout, QHeaderView, QAbstractItemView, QDialog,
    QDialogButtonBox, QCheckBox, QStatusBar, QTabWidget, QPlainTextEdit,
    QStyledItemDelegate, QComboBox, QScrollArea, QCompleter)
from PyQt5.QtCore import (Qt, QThread, pyqtSignal, QSettings, QObject, QUrl,
                          QSize, QRegExp, QTimer, QStringListModel, QEvent,
                          QItemSelectionModel)
from PyQt5.QtGui import (QPixmap, QFont, QDesktopServices, QIcon, QImageReader,
                         QRegExpValidator)
from .constants import *
from . import workflows
from . import native_exec
from .constants import __version__, _WD_SINGLE_RE, _WD_LIST_RE
from .logging_setup import *
from .sdc import *
from . import credentials
from .sdc import _strip_sd_lines
from .exif import *
from .api import *
from .workers import *
from .wikidata import *
from .wikidata import _style_wd_field
from .widgets import *
from .editors import *
from .i18n import tr


class MWSettingsMixin:
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
        self.status_bar.showMessage(tr('Log copied to clipboard.'), 3000)

    def _open_log_file(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.log_path))

    def _open_log_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(self.log_path)))

    # ── Settings ─────────────────────────────────────────────────────────────


    def _restore_settings(self):
        # 0.15.0: the selected workflow survives a restart. Signals are
        # blocked so restoring does not count as a switch (which would
        # re-apply presets over restored field values).
        wf_cb = getattr(self, 'workflow_combo', None)
        if wf_cb is not None:
            saved_wf = workflows.by_key(
                self.settings.value('workflow', workflows.DEFAULT_KEY))['key']
            idx = wf_cb.findData(saved_wf)
            if idx >= 0:
                wf_cb.blockSignals(True)
                wf_cb.setCurrentIndex(idx)
                wf_cb.blockSignals(False)
        # Visibility follows the restored workflow (0.15.0). Signals were
        # blocked above, so this has to run explicitly.
        if hasattr(self, '_apply_workflow_visibility'):
            self._apply_workflow_visibility()
        # 0.15.0: the required-field dots reflect the RESTORED values, so
        # they must run after the restore, not only on textChanged.
        if hasattr(self, '_refresh_required_marks'):
            self._refresh_required_marks()

        self.author_edit.setText(self.settings.value('author', ''))
        self.source_edit.setText(self.settings.value('source', '{{own}}'))
        self.permission_edit.setText(self.settings.value('permission', ''))
        self.license_edit.setText(self.settings.value('license', '{{Cc-by-sa-4.0}}'))
        self.other_templates_edit.setText(self.settings.value('other_templates', ''))
        self.other_fields_edit.setText(self.settings.value('other_fields', ''))
        self.gallery_prefix_edit.setText(self.settings.value('gallery_prefix', ''))
        self.timeout_edit.setText(self.settings.value('timeout', '120'))

        # SDC fields moved out of base_description into upload settings in 0.7.3.
        # If they were never saved but the old base_description carries them,
        # migrate the values across on this first run.
        creator = self.settings.value('creator_sdc', None)
        copyright_ = self.settings.value('copyright_sdc', None)
        license_ = self.settings.value('license_sdc', None)
        base_default = ''  # empty by default; previous default was copyright+license lines
        base_txt = self.settings.value('base_description', base_default)
        if creator is None or copyright_ is None or license_ is None:
            sd, _ = extract_structured_data(base_txt)
            if creator is None:
                creator = sd.get('creator', '')
            if copyright_ is None:
                copyright_ = sd.get('copyright', 'Q73566113')
            if license_ is None:
                license_ = sd.get('license', 'Q18199165')
            base_txt = _strip_sd_lines(base_txt,
                                       ('creator', 'copyright', 'license'))
        self.creator_edit.setText(creator or '')
        self.copyright_sdc_edit.setText(copyright_ or 'Q73566113')
        self.license_sdc_edit.setText(license_ or 'Q18199165')
        self.base_text_edit.setPlainText(base_txt)
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
        self.settings.setValue('creator_sdc', self.creator_edit.text())
        self.settings.setValue('source', self.source_edit.text())
        self.settings.setValue('permission', self.permission_edit.text())
        self.settings.setValue('license', self.license_edit.text())
        self.settings.setValue('license_sdc', self.license_sdc_edit.text())
        self.settings.setValue('copyright_sdc', self.copyright_sdc_edit.text())
        self.settings.setValue('other_templates', self.other_templates_edit.text())
        self.settings.setValue('other_fields', self.other_fields_edit.text())
        self.settings.setValue('gallery_prefix', self.gallery_prefix_edit.text())
        self.settings.setValue('timeout', self.timeout_edit.text())
        self.settings.setValue('base_description', self.base_text_edit.toPlainText())
        self.settings.setValue('expert_mode', self.expert_cb.isChecked())
        if hasattr(self, 'iptc_export_dir_edit'):
            self._iptc_save_settings()
        if hasattr(self, 'mw_user_edit'):
            self._login_settings.setValue('username',
                                          self.mw_user_edit.text().strip())
            # 0.12.12: the password field is loaded LAZILY (first BotPassword
            # dialog open). Saving an untouched, never-loaded field would
            # pass '' to save_mediawiki_password - which DELETES the stored
            # secret. Only a loaded (and thus possibly edited) field is
            # authoritative.
            if getattr(self, '_mw_password_loaded', True):
                credentials.save_mediawiki_password(
                    self._login_settings, self.mw_user_edit.text(),
                    self.mw_password_edit.text())
            self._login_settings.sync()
        if hasattr(self, 'ftp_host_edit'):
            self._ftp_save_settings()
        if hasattr(self, 'flickr_api_key_edit'):
            self._flickr_save_settings()
        if hasattr(self, 'cull_advance_cb'):
            self._cull_save_settings()
        if hasattr(self, 'scheme_combo'):
            self.settings.setValue('color_scheme',
                                   self.scheme_combo.currentData())

    def _on_save_settings(self):
        """Explicitly persist the current settings (button + on close)."""
        self._save_settings()
        self.settings.sync()
        self.status_bar.showMessage(tr('Settings saved.'), 3000)

    # ── Settings import/export as a plain text file ──────────────────────────

    # Section markers used in the exported text file.
    _BLOCK_BASE_BEGIN = '=== base_description ==='
    _BLOCK_BASE_END = '=== end base_description ==='
    _BLOCK_FILE_BEGIN = '=== file_description ==='
    _BLOCK_FILE_END = '=== end file_description ==='
    # Single-line keys written as "key = value".
    _FILE_KEYS = ('author', 'creator_sdc', 'source', 'permission', 'license',
                  'license_sdc', 'copyright_sdc', 'other_templates',
                  'other_fields', 'gallery_prefix', 'timeout', 'expert_mode')

    def _save_settings_to_file(self):
        default = os.path.join(os.path.expanduser('~'), 'cammello_settings.txt')
        path, _ = QFileDialog.getSaveFileName(
            self, tr('Save settings to file'), default,
            tr('Text files') + ' (*.txt);;' + tr('All files') + ' (*)')
        if not path:
            return

        # Make sure the selected file's description is up to date in the table.
        self._commit_editor()
        values = {
            'author': self.author_edit.text(),
            'creator_sdc': self.creator_edit.text(),
            'source': self.source_edit.text(),
            'permission': self.permission_edit.text(),
            'license': self.license_edit.text(),
            'license_sdc': self.license_sdc_edit.text(),
            'copyright_sdc': self.copyright_sdc_edit.text(),
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
            QMessageBox.critical(self, tr('Save error'),
                                 tr('Could not write the file:') + f'\n{e}')
            return

        self.logger.info('Settings written to %s (file description incl.: %s)',
                         path, included_file)
        if self.export_file_desc_cb.isChecked() and not included_file:
            self.status_bar.showMessage(
                tr('Saved. No single file selected, so no file description was '
                'included.'), 6000)
        else:
            self.status_bar.showMessage(
                tr('Settings saved to {path}').format(path=path), 5000)

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
            self, tr('Load settings from file'), os.path.expanduser('~'),
            tr('Text files') + ' (*.txt);;' + tr('All files') + ' (*)')
        if not path:
            return
        try:
            with open(path, encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            QMessageBox.critical(self, tr('Load error'),
                                 tr('Could not read the file:') + f'\n{e}')
            return

        singles, base_desc, file_desc = self._parse_settings_file(content)

        setters = {
            'author': self.author_edit.setText,
            'creator_sdc': self.creator_edit.setText,
            'source': self.source_edit.setText,
            'permission': self.permission_edit.setText,
            'license': self.license_edit.setText,
            'license_sdc': self.license_sdc_edit.setText,
            'copyright_sdc': self.copyright_sdc_edit.setText,
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
                note = ' ' + tr('(file description in the file was ignored: '
                                'no single file selected)')

        self.logger.info('Settings loaded from %s%s', path, note)
        self.status_bar.showMessage(
            tr('Settings loaded from {path}.').format(path=path) + note, 6000)

    def closeEvent(self, event):
        # Persist settings when the window is closed; flush pending XMP
        # writes of the culling tab (write-behind) before the process dies.
        self._save_settings()
        if hasattr(self, '_cull_wb'):
            self._cull_shutdown()
        # Stop the metadata helper process AFTER the flush (the flush may
        # still need it for the last queued writes).
        native_exec.shutdown()
        super().closeEvent(event)

    def _get_timeout(self):
        try:
            t = int(self.timeout_edit.text())
            return t if t > 0 else 120
        except (ValueError, TypeError):
            return 120

    # ── Login / test ─────────────────────────────────────────────────────────
