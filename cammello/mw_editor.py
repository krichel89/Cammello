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


class MWEditorMixin:
    def _base_sdc_lines(self):
        """The creator/copyright/license SDC lines from Upload settings that are
        prepended to every file's base description at upload time."""
        lines = []
        for key, edit in (('creator', self.creator_edit),
                          ('copyright', self.copyright_sdc_edit),
                          ('license', self.license_sdc_edit)):
            val = edit.text().strip()
            if val:
                lines.append(f'{key}={val}')
        return lines

    def _effective_text(self, per_file_text):
        """The combined description_all for one file, as it will be uploaded:
        creator/copyright/license (from Upload settings) + base description +
        the per-file description."""
        parts = []
        sdc = self._base_sdc_lines()
        if sdc:
            parts.append('\n'.join(sdc))
        base = self.base_text_edit.toPlainText().strip()
        if base:
            parts.append(base)
        pf = (per_file_text or '').strip()
        if pf:
            parts.append(pf)
        return '\n'.join(parts)

    def _refresh_effective(self, row):
        if row < 0 or row >= self.table.rowCount():
            return
        eff = self.table.item(row, self.COL_EFFECTIVE)
        if eff is None:
            return
        desc_item = self.table.item(row, self.COL_DESC)
        per_file = desc_item.text() if desc_item else ''
        text = self._effective_text(per_file)
        if eff.text() == text:
            return  # unchanged: skip setText and the row-height relayout
        eff.setText(text)
        eff.setToolTip(text)  # full text on hover, even if the cell is small

    def _refresh_all_effective(self):
        """Debounced full refresh: typing in a base/QID field schedules ONE
        refresh instead of relayouting every row on every keystroke."""
        if not hasattr(self, '_eff_timer'):
            self._eff_timer = QTimer(self)
            self._eff_timer.setSingleShot(True)
            self._eff_timer.setInterval(250)
            self._eff_timer.timeout.connect(self._do_refresh_all_effective)
        self._eff_timer.start()

    def _do_refresh_all_effective(self):
        # Batch the relayout: suspend painting while all rows are updated.
        self.table.setUpdatesEnabled(False)
        try:
            for r in range(self.table.rowCount()):
                self._refresh_effective(r)
        finally:
            self.table.setUpdatesEnabled(True)

    def remove_selected(self):
        rows = sorted(set(i.row() for i in self.table.selectedItems()), reverse=True)
        for row in rows:
            self.table.removeRow(row)

    def bulk_edit_selected(self):
        # Commit any pending per-file edit before touching the rows.
        self._commit_editor()
        rows = sorted(set(i.row() for i in self.table.selectedItems()))
        if not rows:
            QMessageBox.information(
                self, 'No selection',
                'Please select one or more rows first '
                '(Ctrl/Shift-click to select several).')
            return
        dlg = BulkEditDialog(len(rows), self)
        if dlg.exec_() != QDialog.Accepted:
            return
        key, value = dlg.result_field_value()

        # Disable sorting so row indices stay valid while we write cells.
        was_sorting = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)
        try:
            for row in rows:
                self._apply_bulk_field(row, key, value)
                self._refresh_effective(row)
        finally:
            self.table.setSortingEnabled(was_sorting)

        # Refresh the per-file editor from the (now-updated) table. Clear the
        # tracked editor row first so the reload does not flush the stale
        # editor content back over the bulk change.
        self._editor_item = None
        self.on_row_selected()
        self.status_bar.showMessage(
            f'Applied "{key}" to {len(rows)} file(s).', 6000)

    def _apply_bulk_field(self, row, key, value):
        """Apply one (key, value) to a single row."""
        if key == 'date':
            item = self.table.item(row, self.COL_DATE)
            if item is None:
                item = QTableWidgetItem()
                self.table.setItem(row, self.COL_DATE, item)
            item.setText(value)
            return

        # Description-based fields: round-trip through a scratch editor so the
        # existing load/assemble logic (captions, depicts, categories, extra)
        # is reused and other fields on the row are preserved.
        if not hasattr(self, '_scratch_editor'):
            self._scratch_editor = StructuredDescriptionEditor(is_base=False)
        ed = self._scratch_editor
        desc_item = self.table.item(row, self.COL_DESC)
        if desc_item is None:
            desc_item = QTableWidgetItem('')
            self.table.setItem(row, self.COL_DESC, desc_item)
        ed.load(desc_item.text())

        if key == 'depicts':
            ed.depicts.setText(value)
        elif key == 'categories':
            ed.categories.setText(value)
        elif key.startswith('caption:'):
            lang = key.split(':', 1)[1]
            caps = ed.captions_editor.get_captions()
            if value:
                caps[lang] = value
            else:
                caps.pop(lang, None)
            # Keep the per-language information wikitext intact.
            ed.captions_editor.set_language_data(
                caps, ed.captions_editor.get_infos())

        desc_item.setText(ed.assemble())

    def clear_all(self):
        self.table.setRowCount(0)


    def _selected_row(self):
        rows = list(set(i.row() for i in self.table.selectedItems()))
        return rows[0] if len(rows) == 1 else None

    def on_row_selected(self):
        # Flush the row currently in the editor before switching away from it.
        self._commit_editor()

        row = self._selected_row()
        if row is None:
            self._editor_item = None
            self.file_desc_edit.setPlaceholderText(
                'Select a single file to edit its description.')
            return

        self._load_selected_desc()

        filepath = self.table.item(row, self.COL_FILENAME).data(Qt.UserRole)
        if filepath and os.path.exists(filepath):
            # Scaled read via QImageReader (see _make_thumbnail) instead of a
            # full-resolution QPixmap decode: ~30x faster on 45MP images.
            pix = self._make_thumbnail(filepath, w=300, h=200)
            if pix is not None and not pix.isNull():
                self.preview_label.setPixmap(pix)

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
        # Bind to the file item (not a fixed index) so the commit target stays
        # correct after sorting or row removal.
        self._editor_item = (self.table.item(row, self.COL_FILENAME)
                             if row is not None else None)

    def _commit_editor(self, expert=None):
        """Write the per-file editor's current content to the row it was loaded
        from.

        Called on field switch (a field losing focus / editing finished), on
        row change, and as a safety flush before reads (upload, bulk edit,
        save-to-file). The target row is resolved live from the loaded file
        item (self._editor_item.row()), so it stays correct after sorting or
        row removal; a removed item reports row() == -1 and is skipped.

        expert: which editor to read; defaults to the current mode. The mode
        switch passes the OLD mode explicitly (the checkbox is already flipped
        when its handler runs).
        """
        if self._loading_desc:
            return
        if self._editor_item is None:
            return
        row = self._editor_item.row()
        if row < 0:
            return  # the row was removed from the table
        item = self.table.item(row, self.COL_DESC)
        if item is None:
            return
        if expert is None:
            expert = self.expert_cb.isChecked()
        if expert:
            item.setText(self.file_desc_edit.toPlainText())
        else:
            item.setText(self.file_struct.assemble())
        self._refresh_effective(row)

    # ── Expert mode ──────────────────────────────────────────────────────────

    def _toggle_expert(self, state):
        new_expert = bool(state)
        # Flush the currently visible (old-mode) editor before switching, so
        # edits not yet committed by a field switch are not lost on reload.
        self._commit_editor(expert=not new_expert)
        self.settings.setValue('expert_mode', new_expert)
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
            # base_struct -> base_text write; _on_base_struct_changed refreshes.
            return
        # User edited the raw base text directly (expert mode).
        self._refresh_all_effective()

    def _on_base_struct_changed(self):
        if self._loading_desc:
            return
        self._loading_desc = True
        try:
            self.base_text_edit.setPlainText(self.base_struct.assemble())
        finally:
            self._loading_desc = False
        self._refresh_all_effective()

    # ── Upload ───────────────────────────────────────────────────────────────
