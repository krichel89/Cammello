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
from .i18n import tr
from .sdc import extract_structured_data, DEPICTS_OVERRIDES
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
    def _upload_rows(self):
        """Table rows the Upload button acts on.

        Selected rows only; if nothing is selected, every row. Returns a sorted
        list of table row indices.
        """
        selected = sorted({idx.row() for idx in self.table.selectedIndexes()})
        if selected:
            return selected
        return list(range(self.table.rowCount()))

    def _update_upload_btn(self):
        """Keep the button label honest about what a click would do."""
        total = self.table.rowCount()
        selected = {idx.row() for idx in self.table.selectedIndexes()}
        if selected:
            self.upload_btn.setText(
                tr('Upload selected ({n})').format(n=len(selected)))
            self.upload_btn.setToolTip(
                tr('Uploads the selected rows. Deselect everything to upload all '
                'files.'))
        else:
            self.upload_btn.setText(
                tr('Upload all ({n})').format(n=total) if total
                else tr('Upload all'))
            self.upload_btn.setToolTip(
                tr('Nothing is selected, so all files are uploaded. Select rows '
                'to upload only those.'))

    def _qid_problems(self, rows=None):
        """Collect fields whose Wikidata value is not a valid QID.

        Covers the searchable fields (creator, depicts, created_during) plus
        the fixed copyright/license fields, in the upload settings, the base
        description and the per-file descriptions of the rows about to be
        uploaded (rows=None: all rows). Returns human-readable strings; empty
        list means everything is fine.
        """
        if rows is None:
            rows = range(self.table.rowCount())
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
        for r in rows:
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

    def _depicts_problems(self, upload_rows):
        """Rows without depicts AND without an override checkbox.

        depicts is mandatory (WikiPortraits QA): either the file has at
        least one P180 QID (its own or inherited from a depicts= line in the
        base description), or one of the per-file overrides ('No Wikidata
        item' / 'Not applicable' / 'Unidentified') is set."""
        base_sd, _ = extract_structured_data(self.base_text_edit.toPlainText())
        base_depicts = (base_sd.get('depicts') or '').strip()
        problems = []
        for r in upload_rows:
            item = self.table.item(r, self.COL_DESC)
            sd, _ = extract_structured_data(item.text() if item else '')
            has_depicts = bool((sd.get('depicts') or '').strip()
                               or base_depicts)
            override = (sd.get('depicts_override') or '').strip().lower()
            if has_depicts or override in DEPICTS_OVERRIDES:
                continue
            name_item = self.table.item(r, self.COL_FILENAME)
            problems.append(name_item.text() if name_item else f'#{r + 1}')
        return problems

    def start_upload(self):
        # These early exits used to be silent in the log, which made an
        # apparently dead Upload button impossible to diagnose from the Log tab.
        if not self.api:
            self.logger.info('Upload aborted: not logged in.')
            QMessageBox.warning(self, tr('Not logged in'), tr('Please log in first.'))
            return
        if self.table.rowCount() == 0:
            self.logger.info('Upload aborted: the file table is empty.')
            QMessageBox.warning(self, tr('No files'), tr('Please add files first.'))
            return

        # Flush any not-yet-committed edit in the per-file editor to the table
        # before reading the descriptions.
        self._commit_editor()

        # Selected rows only; nothing selected means all rows.
        upload_rows = self._upload_rows()
        selection_used = bool({idx.row() for idx in self.table.selectedIndexes()})
        self.logger.info('Upload requested for %d of %d row(s) (%s).',
                         len(upload_rows), self.table.rowCount(),
                         'selection' if selection_used else 'no selection: all')

        problems = self._qid_problems(upload_rows)
        if problems:
            self.logger.info('Upload aborted: %d invalid Wikidata ID(s).',
                             len(problems))
            shown = '\n'.join(problems[:15])
            if len(problems) > 15:
                shown += '\n' + tr('… (+{n} more)').format(n=len(problems) - 15)
            QMessageBox.warning(
                self, tr('Invalid Wikidata IDs'),
                tr('The following fields must contain Wikidata QIDs (e.g. Q640).\n'
                'Pick an entry from the suggestion list or enter a valid QID:')
                + '\n\n' + shown)
            return

        # depicts is mandatory: block files that have neither a P180 QID nor
        # one of the three override checkboxes.
        missing = self._depicts_problems(upload_rows)
        if missing:
            shown = '\n'.join(missing[:15])
            if len(missing) > 15:
                shown += '\n' + tr('… (+{n} more)').format(n=len(missing) - 15)
            self.logger.info('Upload aborted: %d file(s) without depicts or '
                             'override.', len(missing))
            QMessageBox.warning(
                self, tr('Depicts is missing'),
                tr('depicts (P180) is mandatory. Enter a QID, or check one '
                   'of the overrides ("No Wikidata item", "Not applicable", '
                   '"Unidentified") for these files:') + '\n\n' + shown)
            return

        self._save_settings()
        # Apply the timeout to the active session in case it was changed.
        self.api.timeout = self._get_timeout()

        rows = []
        # Maps a worker index (0..n-1) back to its table row, which is not the
        # same thing as soon as only a selection is uploaded.
        self.upload_row_map = list(upload_rows)
        for r in upload_rows:
            filepath = self.table.item(r, self.COL_FILENAME).data(Qt.UserRole)
            source_name = self.table.item(r, self.COL_FILENAME).text()
            date = self.table.item(r, self.COL_DATE).text() if self.table.item(r, self.COL_DATE) else ''
            per_file_desc = self.table.item(r, self.COL_DESC).text() if self.table.item(r, self.COL_DESC) else ''

            # Same function as the Wikitext preview column: what you see in the
            # table is byte-for-byte what gets uploaded.
            combined, merge_warnings = self._effective_text(per_file_desc,
                                                            with_warnings=True)
            for warn in merge_warnings:
                self.logger.warning('Row %d ("%s"): %s', r + 1, source_name, warn)

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

        # Progress window with a Cancel button. Modeless on purpose: the table
        # stays readable (per-row status keeps updating behind it) while the
        # run is going on.
        self._progress_dlg = UploadProgressDialog(len(rows), self)
        self._done_count = 0

        # No base_text argument any more: each row already carries the fully
        # merged description_all (settings SDC + base + per-file). The worker
        # used to take a base_text it never read.
        self.worker = UploadWorker(
            self.api, rows,
            self.gallery_prefix_edit.text(),
            self.ignore_warnings_cb.isChecked()
        )
        self.worker.progress.connect(self.on_progress)
        self.worker.error.connect(self.on_error)
        self.worker.finished.connect(self.on_finished)
        self.worker.file_started.connect(self._progress_dlg.set_current)
        # Queued across threads by Qt: the flag is set in the worker object,
        # the worker thread picks it up before the next file.
        self._progress_dlg.cancel_requested.connect(self.worker.cancel)
        self._progress_dlg.show()
        self.worker.start()

    def _table_row(self, worker_index):
        """Translate a worker index into a table row (see upload_row_map)."""
        mapping = getattr(self, 'upload_row_map', None)
        if mapping and 0 <= worker_index < len(mapping):
            return mapping[worker_index]
        return worker_index

    def on_progress(self, index, status):
        row = self._table_row(index)
        item = self.table.item(row, self.COL_STATUS)
        if item:
            item.setText(status)
        total = len(getattr(self, 'upload_row_map', []) or []) or self.table.rowCount()
        self.progress_bar.setValue(index + 1)
        self.status_bar.showMessage(
            tr('Uploading {i}/{total}…').format(i=index + 1, total=total))
        # The bar counts finished files, not started ones.
        if status.startswith(('✓', '✗')):
            self._done_count = getattr(self, '_done_count', 0) + 1
            dlg = getattr(self, '_progress_dlg', None)
            if dlg is not None:
                dlg.set_done(self._done_count)

    def on_error(self, index, msg):
        if index < 0:
            # Gallery/global errors are shown only in the log/status bar.
            self.status_bar.showMessage(msg, 8000)
            return
        row = self._table_row(index)
        item = self.table.item(row, self.COL_STATUS)
        if item:
            item.setText(f'✗ {msg[:60]}')
            item.setToolTip(msg)

    def on_finished(self, summary):
        self.progress_bar.setVisible(False)
        self.upload_btn.setEnabled(True)
        self._update_upload_btn()
        self.status_bar.showMessage(summary)
        dlg = getattr(self, '_progress_dlg', None)
        if dlg is not None:
            dlg.force_close()   # plain close() is swallowed by reject()
            self._progress_dlg = None
        cancelled = summary.startswith('Cancelled')
        QMessageBox.information(
            self, 'Upload cancelled' if cancelled else 'Upload complete',
            summary + '\n\nDetails in the Log tab.')
