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


class MWFilesMixin:
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
        added, dups, failed = self._add_paths(files)
        if added:
            self.logger.debug('%d file(s) added to the table.', added)
        self._report_add_result(added, dups, failed)

    def _add_dropped_files(self, paths):
        """Add image files dropped onto the table.

        Files already present in the table (matched by absolute source path)
        are skipped as duplicates. Each remaining file is processed
        independently: a failure on one file (bad image, permission error,
        unreadable EXIF) is logged and skipped so the rest of the drop still
        succeeds.
        """
        added, dups, failed = self._add_paths(paths)
        if added:
            self.logger.debug('%d file(s) added via drag-and-drop.', added)
        self._report_add_result(added, dups, failed)

    def _add_paths(self, paths):
        """Add the given files to the table, skipping duplicates.

        Returns (added, duplicates, failed). Sorting is disabled for the
        duration of the batch so setSortingEnabled does not reshuffle rows
        while they are only partially populated.
        """
        was_sorting = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)
        seen = self._current_filepaths()
        added = duplicates = failed = 0
        try:
            for filepath in paths:
                try:
                    if self._add_row(filepath, seen):
                        added += 1
                    else:
                        duplicates += 1
                        self.logger.debug('Skipping duplicate file: %r', filepath)
                except Exception as e:
                    failed += 1
                    self.logger.warning('Failed to add file %r: %s', filepath, e)
        finally:
            self.table.setSortingEnabled(was_sorting)
        return added, duplicates, failed

    def _report_add_result(self, added, duplicates, failed):
        parts = []
        if added:
            parts.append(f'{added} added')
        if duplicates:
            parts.append(f'{duplicates} duplicate(s) skipped')
        if failed:
            parts.append(f'{failed} skipped (see log)')
        if parts:
            self.status_bar.showMessage(', '.join(parts) + '.', 6000)

    @staticmethod
    def _norm_path(filepath):
        """Normalized absolute path for duplicate comparison.

        Uses os.path.normcase so the match is case-insensitive on Windows.
        Note: this compares path strings, so two different paths pointing at
        the same file (e.g. via symlink or hardlink) are NOT detected as
        duplicates.
        """
        return os.path.normcase(os.path.abspath(filepath))

    def _current_filepaths(self):
        """Set of normalized source paths currently in the table."""
        result = set()
        for r in range(self.table.rowCount()):
            item = self.table.item(r, self.COL_FILENAME)
            fp = item.data(Qt.UserRole) if item else None
            if fp:
                result.add(self._norm_path(fp))
        return result

    def _ext_for_row(self, row):
        """Return the (fixed) extension of a row's source file, e.g. '.jpg'."""
        item = self.table.item(row, self.COL_FILENAME)
        fp = item.data(Qt.UserRole) if item else None
        return os.path.splitext(fp)[1] if fp else ''

    def _make_thumbnail(self, filepath, w=THUMB_W, h=THUMB_H):
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

    def _add_row(self, filepath, seen=None):
        """Insert a row for filepath. Returns True if added, False if it was
        already present (duplicate, matched by normalized absolute path).

        seen: optional set of already-present normalized paths. When given it
        is used for the duplicate check and updated in place, so a batch add
        does not re-scan the whole table for every file.
        """
        norm = self._norm_path(filepath)
        existing = seen if seen is not None else self._current_filepaths()
        if norm in existing:
            return False

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

        # Effective (base + file) preview, read-only.
        eff_item = QTableWidgetItem('')
        eff_item.setFlags(eff_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row, self.COL_EFFECTIVE, eff_item)

        status_item = QTableWidgetItem('—')
        status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row, self.COL_STATUS, status_item)

        self._refresh_effective(row)

        if seen is not None:
            seen.add(norm)
        return True
