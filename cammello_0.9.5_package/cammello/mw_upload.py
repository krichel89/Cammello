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
from .constants import __version__, _WD_SINGLE_RE, _WD_LIST_RE
from .logging_setup import *
from .sdc import *
from .sdc import _strip_sd_lines
from .exif import *
from .api import *
from .workers import *
from .wikidata import *
from .wikidata import _style_wd_field
from .widgets import *
from .editors import *


class MWUploadMixin:
    def _qid_problems(self):
        """Collect fields whose Wikidata value is not a valid QID.

        Covers the searchable fields (creator, depicts, created_during) plus
        the fixed copyright/license fields, in the upload settings, the base
        description and every per-file description. Returns human-readable
        strings; empty list means everything is fine.
        """
        problems = []
        problems += invalid_qid_problems('Creator (P170)',
                                         self.creator_edit.text())
        problems += invalid_qid_problems('Copyright (P6216)',
                                         self.copyright_sdc_edit.text())
        problems += invalid_qid_problems('License (P275)',
                                         self.license_sdc_edit.text())
        base_sd, _ = extract_structured_data(self.base_text_edit.toPlainText())
        problems += invalid_qid_problems('Base: created during (P10408)',
                                         base_sd.get('created_during', ''))
        problems += invalid_qid_problems('Base: depicts (P180)',
                                         base_sd.get('depicts', ''), multi=True)
        for r in range(self.table.rowCount()):
            item = self.table.item(r, self.COL_DESC)
            if not item:
                continue
            sd, _ = extract_structured_data(item.text())
            if 'depicts' in sd:
                problems += invalid_qid_problems(
                    f'Row {r + 1}: depicts (P180)', sd.get('depicts', ''),
                    multi=True)
            if 'created_during' in sd:
                problems += invalid_qid_problems(
                    f'Row {r + 1}: created during (P10408)',
                    sd.get('created_during', ''))
        return problems

    def start_upload(self):
        if not self.api:
            QMessageBox.warning(self, 'Not logged in', 'Please log in first.')
            return
        if self.table.rowCount() == 0:
            QMessageBox.warning(self, 'No files', 'Please add files first.')
            return

        # Flush any not-yet-committed edit in the per-file editor to the table
        # before reading the descriptions.
        self._commit_editor()

        problems = self._qid_problems()
        if problems:
            shown = '\n'.join(problems[:15])
            if len(problems) > 15:
                shown += f'\n… (+{len(problems) - 15} more)'
            QMessageBox.warning(
                self, 'Invalid Wikidata IDs',
                'The following fields must contain Wikidata QIDs (e.g. Q640).\n'
                'Pick an entry from the suggestion list or enter a valid QID:\n\n'
                + shown)
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

        # creator / copyright / license live in the upload settings; prepend
        # them to the base description so the worker's SDC extractor picks
        # them up alongside the user-authored base text.
        base_lines = []
        for key, val in (('creator',   self.creator_edit.text().strip()),
                         ('copyright', self.copyright_sdc_edit.text().strip()),
                         ('license',   self.license_sdc_edit.text().strip())):
            if val:
                base_lines.append(f'{key}={val}')
        base_text = self.base_text_edit.toPlainText()
        if base_lines:
            base_text = '\n'.join(base_lines) + '\n' + base_text

        self.worker = UploadWorker(
            self.api, rows,
            base_text,
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
