"""MainWindow mixin: the IPTC tab.

Strictly additive: nothing in here is called by the MediaWiki code paths. The
tab shares the file list with the Files tab (same underlying table); IPTC
values live in self._iptc_store, keyed by normalized file path, so removing or
re-sorting table rows cannot mix files up.

Provisional defaults (marked in the UI, easy to change):
  * "Write into the original files" is OFF - IPTC goes into copies inside an
    export folder, which is also what the FTP upload sends.
  * Credentials: password is asked per session; storing it in the settings is
    opt-in and stored in PLAIN TEXT (QSettings has no encryption).
"""
import os

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QPushButton, QListWidget, QListWidgetItem, QSplitter, QComboBox,
    QCheckBox, QGroupBox, QMessageBox, QFileDialog, QTextEdit, QScrollArea,
    QAbstractItemView)
from PyQt5.QtCore import Qt, QSize

from .constants import *
from . import iptc
from .ftp_workers import (FtpUploadWorker, PROTOCOLS, DEFAULT_PORTS,
                          sftp_available, sftp_unavailable_reason)
from .widgets import (UploadProgressDialog, CollapsibleGroupBox,
                      apply_form_ratio)
from .i18n import tr


class MWIptcMixin:

    # ── Tab construction ──────────────────────────────────────────────────────

    def _build_iptc_tab(self):
        self._iptc_store = {}          # normpath -> {field_key: str}
        self._iptc_current = None      # normpath loaded in the editor
        self._iptc_loading = False

        w = QWidget()
        outer = QVBoxLayout(w)

        split = QSplitter(Qt.Horizontal)
        outer.addWidget(split, 1)

        # Left: the same files as in the Files tab.
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(QLabel(tr('Files (shared with the MediaWiki tab):')))
        self.iptc_list = QListWidget()
        # Looks like the MediaWiki tab: thumbnail + name per row. The icons
        # are COPIED from the main table (zero decoding), which also removes
        # the delay when opening the tab.
        self.iptc_list.setIconSize(QSize(96, 64))
        self.iptc_list.setUniformItemSizes(True)
        self.iptc_list.currentItemChanged.connect(self._iptc_on_select)
        lv.addWidget(self.iptc_list)
        self.iptc_count_lbl = QLabel('')
        lv.addWidget(self.iptc_count_lbl)
        refresh_btn = QPushButton(tr('Refresh list'))
        refresh_btn.clicked.connect(self._iptc_refresh_list)
        lv.addWidget(refresh_btn)
        split.addWidget(left)

        # Right: field editor + actions, inside a scroll area. Without it the
        # sections competed for height and squeezed the field rows into
        # unreadable slivers on smaller windows.
        right = QWidget()
        rv = QVBoxLayout(right)

        form_box = QGroupBox(tr('IPTC fields of the selected file'))
        form = QFormLayout(form_box)
        self._iptc_edits = {}
        for key, _exiv, label, multi in iptc.IPTC_FIELDS:
            edit = QLineEdit()
            edit.setMinimumHeight(26)      # never squeezed below readability
            if multi:
                edit.setPlaceholderText(tr('separated by ;'))
            edit.textChanged.connect(self._iptc_commit_current)
            self._iptc_edits[key] = edit
            form.addRow(tr(label) + ':', edit)
        rv.addWidget(form_box)

        btn_row = QHBoxLayout()
        self.iptc_read_btn = QPushButton(tr('Read IPTC from file'))
        self.iptc_read_btn.clicked.connect(self._iptc_read_selected)
        btn_row.addWidget(self.iptc_read_btn)
        self.iptc_from_mw_btn = QPushButton(tr('Fill from MediaWiki data'))
        self.iptc_from_mw_btn.setToolTip(
            tr('caption -> Caption/Headline, categories -> Keywords, author -> '
            'Creator, date -> Date created, target filename -> Title. QIDs '
            'are not resolved to names (that would need a Wikidata lookup).'))
        self.iptc_from_mw_btn.clicked.connect(self._iptc_fill_from_mw)
        btn_row.addWidget(self.iptc_from_mw_btn)
        self.iptc_to_mw_btn = QPushButton(tr('Caption -> Wikitext as'))
        self.iptc_to_mw_btn.setToolTip(
            tr("Copies the IPTC caption into the file's description as "
            'caption_<language>.'))
        self.iptc_to_mw_btn.clicked.connect(self._iptc_caption_to_mw)
        btn_row.addWidget(self.iptc_to_mw_btn)
        self.iptc_lang_combo = QComboBox()
        self.iptc_lang_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.iptc_lang_combo.addItems(['de', 'en', 'es', 'fr', 'it', 'pt'])
        # A fixed 60 px clipped the two letters behind the drop-down
        # indicator (the stylesheet reserves 24 px on the right and disables
        # the native width logic): minimum width instead of a fixed one.
        self.iptc_lang_combo.setMinimumWidth(78)
        self.iptc_lang_combo.setMaximumWidth(96)
        btn_row.addWidget(self.iptc_lang_combo)
        btn_row.addStretch()
        rv.addLayout(btn_row)

        write_box = QGroupBox(tr('IPTC writing'))
        wv = QVBoxLayout(write_box)
        self.iptc_inplace_cb = QCheckBox(
            tr('Write into the ORIGINAL files (default: copies in the export '
            'folder below)'))
        wv.addWidget(self.iptc_inplace_cb)
        dir_row = QHBoxLayout()
        self.iptc_export_dir_edit = QLineEdit()
        self.iptc_export_dir_edit.setPlaceholderText(tr('Export folder for copies'))
        dir_row.addWidget(self.iptc_export_dir_edit)
        browse = QPushButton('…')
        browse.setFixedWidth(30)
        browse.clicked.connect(self._iptc_pick_export_dir)
        dir_row.addWidget(browse)
        wv.addLayout(dir_row)
        self.iptc_write_btn = QPushButton(tr('Write IPTC (all files with data)'))
        self.iptc_write_btn.clicked.connect(self._iptc_write_all)
        wv.addWidget(self.iptc_write_btn)
        rv.addWidget(write_box)
        self._iptc_write_box = write_box

        self.iptc_status = QTextEdit()
        self.iptc_status.setReadOnly(True)
        self.iptc_status.setMaximumHeight(90)
        rv.addWidget(self.iptc_status)
        rv.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(right)
        split.addWidget(scroll)
        split.setSizes([340, 760])

        return w

    def _build_ftp_tab(self):
        """The merged FTP / Flickr tab (0.10.0). One shared file list on the
        left and one status area at the bottom right serve BOTH services; the
        FTP server/upload groups appear when the ftp feature is on, the
        Flickr account/upload groups when the flickr feature is on (the tab
        is built when either is). Upload buttons follow the SELECTION in the
        list: selected files, or all files when nothing is selected."""
        w = QWidget()
        outer = QVBoxLayout(w)
        split = QSplitter(Qt.Horizontal)
        outer.addWidget(split, 1)

        # Left: the same files as in the MediaWiki tab (multi-select).
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(QLabel(tr('Files (shared with the MediaWiki tab):')))
        self.ftp_list = QListWidget()
        self.ftp_list.setIconSize(QSize(96, 64))
        self.ftp_list.setUniformItemSizes(True)
        self.ftp_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.ftp_list.itemSelectionChanged.connect(self._ftp_update_count)
        lv.addWidget(self.ftp_list)
        self.ftp_count_lbl = QLabel('')
        lv.addWidget(self.ftp_count_lbl)
        refresh_btn = QPushButton(tr('Refresh list'))
        refresh_btn.clicked.connect(self._ftp_refresh_list)
        lv.addWidget(refresh_btn)
        split.addWidget(left)

        # Right: FTP and/or Flickr groups + one shared status area.
        right = QWidget()
        rv = QVBoxLayout(right)
        # The shared status box is created FIRST (the Flickr groups alias
        # it), but added to the layout LAST so it sits at the bottom.
        self.ftp_status = QTextEdit()
        self.ftp_status.setReadOnly(True)
        self.ftp_status.setMaximumHeight(120)

        if getattr(self, '_feat_ftp', True):
            box = QGroupBox(tr('FTP server'))
            fv = QFormLayout(box)
            self.ftp_protocol_combo = QComboBox()
            self.ftp_protocol_combo.setSizeAdjustPolicy(
                QComboBox.AdjustToContents)
            self.ftp_protocol_combo.addItems(PROTOCOLS)
            fv.addRow(tr('Protocol:'), self.ftp_protocol_combo)
            self.ftp_host_edit = QLineEdit()
            fv.addRow(tr('Host:'), self.ftp_host_edit)
            self.ftp_port_edit = QLineEdit()
            self.ftp_port_edit.setPlaceholderText(tr('empty = default port'))
            fv.addRow(tr('Port:'), self.ftp_port_edit)
            self.ftp_user_edit = QLineEdit()
            fv.addRow(tr('User:'), self.ftp_user_edit)
            self.ftp_password_edit = QLineEdit()
            self.ftp_password_edit.setEchoMode(QLineEdit.Password)
            fv.addRow(tr('Password:'), self.ftp_password_edit)
            self.ftp_store_pw_cb = QCheckBox(
                tr('Store password in settings (PLAIN TEXT - unsafe)'))
            fv.addRow('', self.ftp_store_pw_cb)
            self.ftp_dir_edit = QLineEdit()
            self.ftp_dir_edit.setPlaceholderText(tr('e.g.') + ' /upload')
            fv.addRow(tr('Remote directory:'), self.ftp_dir_edit)
            apply_form_ratio(fv)
            self._ftp_server_box = box
            rv.addWidget(box)

            if getattr(self, '_feat_iptc', True):
                note = QLabel(tr('Uploads the SELECTED files (or all, when '
                              'nothing is selected). IPTC data is written first; '
                              'files without IPTC data are skipped. Write '
                              'settings (export folder) are in the IPTC tab.'))
                note.setWordWrap(True)
                rv.addWidget(note)
                self.ftp_upload_btn = QPushButton(tr('Write IPTC + upload'))
                self.ftp_upload_btn.clicked.connect(self._iptc_start_ftp_upload)
                rv.addWidget(self.ftp_upload_btn)
            else:
                # IPTC hidden: no IPTC writing, the selection is uploaded
                # as it is.
                note = QLabel(tr('The IPTC tab is disabled: the selected files '
                              '(or all, when nothing is selected) are uploaded '
                              'AS THEY ARE, without IPTC writing.'))
                note.setWordWrap(True)
                rv.addWidget(note)
                self.ftp_upload_btn = QPushButton(tr('Upload'))
                self.ftp_upload_btn.clicked.connect(self._ftp_upload_asis)
                rv.addWidget(self.ftp_upload_btn)

        if getattr(self, '_feat_flickr', False):
            self._build_flickr_groups(rv)

        rv.addWidget(self.ftp_status)
        rv.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(right)
        split.addWidget(scroll)
        split.setSizes([340, 760])

        if getattr(self, '_feat_ftp', True) and not sftp_available():
            # ftp/ftps keep working; only sftp is unavailable.
            idx = self.ftp_protocol_combo.findText('sftp')
            if idx >= 0:
                self.ftp_protocol_combo.model().item(idx).setEnabled(False)
            self._ftp_log(f'SFTP disabled: {sftp_unavailable_reason()}')
        return w

    def _ftp_refresh_list(self):
        self._populate_shared_list(self.ftp_list)
        self._ftp_update_count()

    def _ftp_update_count(self):
        self.ftp_count_lbl.setText(self._selection_count_text(
            len(self.ftp_list.selectedItems()), self.ftp_list.count()))

    def _ftp_selected_paths(self):
        """Paths of the selection in the FTP list, or None for 'all files'
        (nothing selected = everything, the app-wide convention)."""
        items = self.ftp_list.selectedItems()
        if not items:
            return None
        return {it.data(Qt.UserRole) for it in items}

    def _ftp_upload_asis(self):
        """Upload without IPTC writing (used when the IPTC tab is off)."""
        selected = self._ftp_selected_paths()
        files = []
        for path, _name, target, _r in self._iptc_paths():
            if selected is not None and path not in selected:
                continue
            remote = target if os.path.splitext(target)[1] else (
                target + os.path.splitext(path)[1])
            files.append((path, remote))
        if not files:
            QMessageBox.information(self, 'FTP', tr('No files'))
            return
        self._ftp_start_upload(files)

    def _ftp_log(self, msg):
        self.logger.info('[FTP] %s', msg)
        self.ftp_status.append(msg)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _iptc_log(self, msg):
        self.logger.info('[IPTC] %s', msg)
        self.iptc_status.append(msg)

    def _iptc_paths(self):
        """(normpath, source_name, target_name, row) for every table row."""
        # (row index is carried along so the list can copy the row's icon)
        out = []
        for r in range(self.table.rowCount()):
            item = self.table.item(r, self.COL_FILENAME)
            if not item:
                continue
            path = item.data(Qt.UserRole)
            if not path:
                continue
            target_item = self.table.item(r, self.COL_TITLE)
            target = target_item.text() if target_item else os.path.basename(path)
            out.append((os.path.normpath(path), item.text(), target, r))
        return out

    def _iptc_refresh_list(self):
        self._iptc_commit_current()
        restored = self._populate_shared_list(self.iptc_list,
                                              keep_path=self._iptc_current)
        if restored is not None:
            self.iptc_list.setCurrentItem(restored)
        elif self.iptc_list.count():
            self.iptc_list.setCurrentRow(0)
        self.iptc_count_lbl.setText(self._selection_count_text(
            0, self.iptc_list.count()))

    def _iptc_on_select(self, current, _previous):
        self._iptc_commit_current()
        if current is None:
            self._iptc_current = None
            return
        path = current.data(Qt.UserRole)
        self._iptc_current = path
        data = self._iptc_store.get(path)
        if data is None:
            # First selection: read what is in the file, once.
            try:
                data = iptc.read_iptc(path)
                self._iptc_log(f'Read IPTC from "{os.path.basename(path)}" '
                               f'({len(data)} field(s)).')
            except Exception as e:
                data = {}
                self._iptc_log(f'Could not read IPTC from '
                               f'"{os.path.basename(path)}": {e}')
            self._iptc_store[path] = data
        self._iptc_loading = True
        try:
            for key, edit in self._iptc_edits.items():
                edit.setText(data.get(key, ''))
        finally:
            self._iptc_loading = False

    def _iptc_commit_current(self):
        if self._iptc_loading or not self._iptc_current:
            return
        data = self._iptc_store.setdefault(self._iptc_current, {})
        for key, edit in self._iptc_edits.items():
            data[key] = edit.text()

    def _iptc_read_selected(self):
        if not self._iptc_current:
            return
        try:
            data = iptc.read_iptc(self._iptc_current)
        except Exception as e:
            QMessageBox.warning(self, 'IPTC', f'Could not read IPTC: {e}')
            return
        self._iptc_store[self._iptc_current] = data
        self._iptc_loading = True
        try:
            for key, edit in self._iptc_edits.items():
                edit.setText(data.get(key, ''))
        finally:
            self._iptc_loading = False
        self._iptc_log(f'Re-read IPTC from '
                       f'"{os.path.basename(self._iptc_current)}".')

    def _iptc_fill_from_mw(self):
        """Derive IPTC fields from the MediaWiki data of the selected file.
        Only fills fields the mapping produced; hand-edited others survive."""
        if not self._iptc_current:
            return
        for path, _name, target, r in self._iptc_paths():
            if path != self._iptc_current:
                continue
            desc_item = self.table.item(r, self.COL_DESC)
            per_file = desc_item.text() if desc_item else ''
            merged = self._effective_text(per_file)
            date_item = self.table.item(r, self.COL_DATE)
            mapped = iptc.mw_to_iptc(
                merged,
                author=self.author_edit.text().strip(),
                date=date_item.text() if date_item else '',
                target_filename=target)
            data = self._iptc_store.setdefault(path, {})
            data.update(mapped)
            self._iptc_loading = True
            try:
                for key, edit in self._iptc_edits.items():
                    edit.setText(data.get(key, ''))
            finally:
                self._iptc_loading = False
            self._iptc_log(tr('Filled {n} field(s) from MediaWiki data '
                              'for "{name}".').format(
                n=len(mapped), name=os.path.basename(path)))
            return

    def _iptc_caption_to_mw(self):
        """IPTC caption -> caption_XX line in the file's description."""
        if not self._iptc_current:
            return
        self._iptc_commit_current()
        lang = self.iptc_lang_combo.currentText()
        line = iptc.iptc_to_caption_line(
            self._iptc_store.get(self._iptc_current, {}), lang)
        if not line:
            QMessageBox.information(self, 'IPTC', tr('The caption field is empty.'))
            return
        for path, _name, _target, r in self._iptc_paths():
            if path != self._iptc_current:
                continue
            item = self.table.item(r, self.COL_DESC)
            if item is None:
                return
            text = item.text()
            # Idempotent: replace an existing caption line for that language.
            lines = [l for l in text.split('\n')
                     if not l.strip().startswith(f'caption_{lang}=')]
            lines.insert(0, line)
            item.setText('\n'.join(l for l in lines if l.strip()))
            self._refresh_effective(r)
            self._iptc_log(tr('Caption copied to caption_{lang} for '
                              '"{name}".').format(
                lang=lang, name=os.path.basename(path)))
            return

    # ── Writing and uploading ─────────────────────────────────────────────────

    def _iptc_pick_export_dir(self):
        d = QFileDialog.getExistingDirectory(self, tr('Export folder'))
        if d:
            self.iptc_export_dir_edit.setText(d)

    def _iptc_write_targets(self, only_paths=None):
        """[(source_path, write_path, remote_name)] for all files with data,
        optionally restricted to `only_paths` (the FTP tab's selection).
        Returns None on a configuration error (already reported)."""
        self._iptc_commit_current()
        inplace = self.iptc_inplace_cb.isChecked()
        export_dir = self.iptc_export_dir_edit.text().strip()
        if not inplace and not export_dir:
            QMessageBox.warning(
                self, 'IPTC', tr('Choose an export folder, or enable writing '
                'into the original files.'))
            return None
        out = []
        for path, _name, target, _r in self._iptc_paths():
            if only_paths is not None and path not in only_paths:
                continue
            data = self._iptc_store.get(path)
            if not data or not any(v.strip() for v in data.values()):
                continue
            remote = target if os.path.splitext(target)[1] else (
                target + os.path.splitext(path)[1])
            write_path = path if inplace else os.path.join(export_dir, remote)
            out.append((path, write_path, remote))
        if not out:
            QMessageBox.information(
                self, 'IPTC', tr('No file has any IPTC data yet.'))
            return None
        return out

    def _iptc_write_all(self):
        targets = self._iptc_write_targets()
        if not targets:
            return
        written, failed = 0, 0
        for path, write_path, _remote in targets:
            try:
                iptc.write_iptc(path, self._iptc_store.get(path, {}),
                                target_path=write_path)
                written += 1
            except Exception as e:
                failed += 1
                self._iptc_log(f'✗ "{os.path.basename(path)}": {e}')
        _msg = tr('IPTC written: {written} file(s), {failed} failed.').format(
            written=written, failed=failed)
        self._iptc_log(_msg)
        QMessageBox.information(self, 'IPTC', _msg)

    def _ftp_credentials_ok(self):
        if not self.ftp_host_edit.text().strip():
            QMessageBox.warning(self, 'FTP', tr('Host is missing.'))
            return False
        if not self.ftp_password_edit.text():
            QMessageBox.warning(self, 'FTP', tr('Password is missing (it is asked '
                                'per session unless you chose to store it).'))
            return False
        return True

    def _iptc_start_ftp_upload(self):
        """FTP tab button with IPTC enabled: selection (or all) -> write
        IPTC -> upload the written files."""
        if not self._ftp_credentials_ok():
            return
        targets = self._iptc_write_targets(
            only_paths=self._ftp_selected_paths())
        if not targets:
            return

        # Write IPTC first; only successfully written files are uploaded.
        files = []
        for path, write_path, remote in targets:
            try:
                actual = iptc.write_iptc(path, self._iptc_store.get(path, {}),
                                         target_path=write_path)
                files.append((actual, remote))
            except Exception as e:
                self._ftp_log('✗ ' + tr('IPTC write failed, file skipped: '
                              '"{name}": {e}').format(
                    name=os.path.basename(path), e=e))
        if not files:
            QMessageBox.warning(self, 'FTP', tr('No file could be prepared.'))
            return
        self._ftp_start_upload(files)

    def _ftp_start_upload(self, files):
        """Shared FTP worker start for both button variants."""
        if not self._ftp_credentials_ok():
            return
        protocol = self.ftp_protocol_combo.currentText()
        self.ftp_upload_btn.setEnabled(False)
        self._ftp_dlg = UploadProgressDialog(len(files), self)
        self.ftp_worker = FtpUploadWorker(
            protocol, self.ftp_host_edit.text().strip(),
            self.ftp_port_edit.text().strip(),
            self.ftp_user_edit.text().strip(),
            self.ftp_password_edit.text(),
            self.ftp_dir_edit.text().strip(), files, self.logger)
        self.ftp_worker.file_started.connect(self._ftp_dlg.set_current)
        self.ftp_worker.progress.connect(self._iptc_on_ftp_progress)
        self.ftp_worker.error.connect(
            lambda i, m: self._ftp_log(f'✗ {m}'))
        self.ftp_worker.finished.connect(self._iptc_on_ftp_finished)
        self._ftp_dlg.cancel_requested.connect(self.ftp_worker.cancel)
        self._ftp_dlg.show()
        self._ftp_done = 0
        self.ftp_worker.start()

    def _iptc_on_ftp_progress(self, _index, status):
        if status.startswith(('✓', '✗')):
            self._ftp_done += 1
            self._ftp_dlg.set_done(self._ftp_done)

    def _iptc_on_ftp_finished(self, summary):
        self.ftp_upload_btn.setEnabled(True)
        self._ftp_dlg.force_close()
        self._ftp_log(summary)
        QMessageBox.information(self, tr('FTP upload'), summary)

    # ── Settings ──────────────────────────────────────────────────────────────
    # Split into an IPTC part and an FTP part (0.10.0): the two tabs can now
    # be switched off individually, so each part must only touch widgets that
    # exist when ITS tab was built.

    def _iptc_save_settings(self):
        s = self.settings
        s.setValue('iptc_export_dir', self.iptc_export_dir_edit.text())
        s.setValue('iptc_inplace', self.iptc_inplace_cb.isChecked())

    def _ftp_save_settings(self):
        s = self.settings
        s.setValue('ftp_protocol', self.ftp_protocol_combo.currentText())
        s.setValue('ftp_host', self.ftp_host_edit.text())
        s.setValue('ftp_port', self.ftp_port_edit.text())
        s.setValue('ftp_user', self.ftp_user_edit.text())
        s.setValue('ftp_dir', self.ftp_dir_edit.text())
        s.setValue('ftp_store_pw', self.ftp_store_pw_cb.isChecked())
        if self.ftp_store_pw_cb.isChecked():
            s.setValue('ftp_password', self.ftp_password_edit.text())
        else:
            s.remove('ftp_password')

    def _iptc_load_settings(self):
        s = self.settings
        self.iptc_export_dir_edit.setText(s.value('iptc_export_dir', ''))
        self.iptc_inplace_cb.setChecked(s.value('iptc_inplace', False, type=bool))

    def _ftp_load_settings(self):
        s = self.settings
        proto = s.value('ftp_protocol', 'ftp')
        idx = self.ftp_protocol_combo.findText(proto)
        if idx >= 0:
            self.ftp_protocol_combo.setCurrentIndex(idx)
        self.ftp_host_edit.setText(s.value('ftp_host', ''))
        self.ftp_port_edit.setText(s.value('ftp_port', ''))
        self.ftp_user_edit.setText(s.value('ftp_user', ''))
        self.ftp_dir_edit.setText(s.value('ftp_dir', ''))
        self.ftp_store_pw_cb.setChecked(s.value('ftp_store_pw', False, type=bool))
        if self.ftp_store_pw_cb.isChecked():
            self.ftp_password_edit.setText(s.value('ftp_password', ''))
