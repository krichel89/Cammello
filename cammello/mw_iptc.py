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
    QAbstractItemView, QDialog, QDialogButtonBox)
from PyQt5.QtCore import Qt, QSize

from .constants import *
from . import iptc
from . import channels
from .ftp_workers import (FtpUploadWorker, PROTOCOLS, DEFAULT_PORTS,
                          sftp_available, sftp_unavailable_reason)
from .widgets import (UploadProgressDialog, CollapsibleGroupBox, FlowLayout,
                      apply_form_ratio, NoWheelComboBox)
from .i18n import tr, current_language
from .wikidata import (WikidataSearchWorker, fetch_commons_categories,
                       fetch_in_background)


class _PersonResolveDialog(QDialog):
    """Resolve person names to Wikidata items. One row per name with a combo
    of matches (filled from a background wbsearchentities query). In 'category'
    mode each combo also offers "use the name as the category"; both modes
    offer "(skip)".

    result_choices() -> {name: value} where value is a QID string, the literal
    'literal' (category mode, use the name), or None (skip).
    """

    def __init__(self, names, mode='depicts', lang='en', parent=None):
        super().__init__(parent)
        self._mode = mode
        self._lang = lang or 'en'
        self.setWindowTitle(
            tr('Person shown -> depicts') if mode == 'depicts'
            else tr('Person shown -> categories'))
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(
            tr('Pick the matching Wikidata item for each person:')))
        form = QFormLayout()
        self._rows = []          # (name, combo)
        self._workers = []
        for name in names:
            combo = QComboBox()
            combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            combo.addItem(tr('Searching…'), None)
            form.addRow(name + ':', combo)
            self._rows.append((name, combo))
        lay.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        # Kick off one search per name (sequence numbers ignored - each combo
        # has its own worker).
        for i, (name, combo) in enumerate(self._rows):
            w = WikidataSearchWorker(name, self._lang, i, parent=self,
                                     fuzzy=True)
            w.results.connect(
                lambda _seq, items, c=combo, n=name: self._fill(c, n, items))
            self._workers.append(w)
            w.start()

    def _fill(self, combo, name, items):
        combo.clear()
        if self._mode == 'category':
            combo.addItem(tr('Use the name as the category'), 'literal')
        for qid, label, desc in items:
            text = f'{label} — {desc} ({qid})' if desc else f'{label} ({qid})'
            combo.addItem(text, qid)
        combo.addItem(tr('(skip)'), None)
        if items:                      # default to the top match
            combo.setCurrentIndex(0 if self._mode == 'category' else 0)
            if self._mode == 'category' and len(items):
                combo.setCurrentIndex(1)    # first real match, not 'literal'

    def result_choices(self):
        return {name: combo.currentData() for name, combo in self._rows}


class MWIptcMixin:

    # ── Tab construction ──────────────────────────────────────────────────────

    def _build_iptc_tab(self):
        self._iptc_store = {}          # normpath -> {field_key: str}
        self._iptc_current = None      # normpath loaded in the editor
        self._iptc_loading = False

        w = QWidget()
        outer = QVBoxLayout(w)

        # 0.12.8 (Harald): the constant creator / rights / contact block used
        # to sit ABOVE the splitter, spanning the full width - a full-width
        # band of fields on top of a two-column page, and it pushed the file
        # list and the editor down. It now lives in the RIGHT column next to
        # the file list, above the per-file fields, where it reads as what it
        # is: settings that apply to every image, next to the images.
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
        # Long file names must not widen the list (which would push the field
        # editor off-screen): elide in the middle and never scroll sideways.
        self.iptc_list.setTextElideMode(Qt.ElideMiddle)
        self.iptc_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.iptc_list.setWordWrap(True)
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

        # Constant creator / rights / contact block (primary widgets;
        # mirrored in Settings). Same for every image, hence above the
        # per-file fields. Collapsed by default - see the group itself.
        rv.addWidget(self._build_iptc_constants_group())

        form_box = QGroupBox(tr('IPTC fields of the selected file'))
        form = QFormLayout(form_box)
        self._iptc_edits = {}
        for key, _exiv, label, multi in iptc.EDITOR_FIELDS:
            edit = QLineEdit()
            edit.setMinimumHeight(26)      # never squeezed below readability
            if multi:
                edit.setPlaceholderText(tr('separated by ;'))
            edit.textChanged.connect(self._iptc_commit_current)
            self._iptc_edits[key] = edit
            form.addRow(tr(label) + ':', edit)
        rv.addWidget(form_box)

        btn_row = FlowLayout(spacing=6)   # wraps instead of forcing width
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
        self.iptc_persons_btn = QPushButton(tr('Person shown -> depicts + category'))
        self.iptc_persons_btn.setToolTip(
            tr('For each person shown: pick the Wikidata item, then add both a '
               'depicts (P180) statement and a category (Commons category '
               'P373, or the name).'))
        self.iptc_persons_btn.clicked.connect(self._iptc_persons_transfer)
        btn_row.addWidget(self.iptc_persons_btn)
        self.iptc_event_btn = QPushButton(tr('Event -> created during + category'))
        self.iptc_event_btn.setToolTip(
            tr('Pick the Wikidata item for the event, then set "created '
               'during" (P10408) and add a category (Commons category P373, '
               'or the name).'))
        self.iptc_event_btn.clicked.connect(self._iptc_event_transfer)
        btn_row.addWidget(self.iptc_event_btn)
        self.iptc_lang_combo = NoWheelComboBox()
        self.iptc_lang_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.iptc_lang_combo.addItems(['de', 'en', 'es', 'fr', 'it', 'pt'])
        # A fixed 60 px clipped the two letters behind the drop-down
        # indicator (the stylesheet reserves 24 px on the right and disables
        # the native width logic): minimum width instead of a fixed one.
        self.iptc_lang_combo.setMinimumWidth(78)
        self.iptc_lang_combo.setMaximumWidth(96)
        btn_row.addWidget(self.iptc_lang_combo)
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
        # The file list keeps its size; extra width goes to the field editor,
        # and the editor never shrinks below a usable width.
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        left.setMaximumWidth(460)
        scroll.setMinimumWidth(360)

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
        # Right-click menu: channel marks (Commons/CC vs. commercial, 0.12.1).
        self.ftp_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ftp_list.customContextMenuRequested.connect(self._ftp_context_menu)
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
            # 0.12.8 (Harald): the FTP/Flickr sections match the rest of the
            # app now - the same heading with the same arrow, and they fold
            # away. Open on first use, and the state is not persisted: this
            # tab is entered rarely, so a section someone folded weeks ago
            # would just look like a missing feature.
            box = CollapsibleGroupBox(tr('FTP server'))
            fv = QFormLayout(box.content)
            self.ftp_protocol_combo = NoWheelComboBox()
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

    def _commercial_allowed_paths(self):
        """The FTP/Flickr channel's effective file set: the selection (or all
        files) MINUS commons-marked files (0.12.1). Commons-marked items are
        disabled in the list so a selection cannot contain them, but the
        all-files fallback is filtered here. Logs the exclusion count."""
        selected = self._ftp_selected_paths()
        if selected is None:
            selected = {p for p, _n, _t, _r in self._iptc_paths()}
        allowed = {p for p in selected
                   if self._channel_mark(p) != channels.MARK_COMMONS}
        excluded = len(selected) - len(allowed)
        if excluded:
            self._ftp_log(tr('{n} file(s) excluded (marked for Commons).')
                          .format(n=excluded))
        return allowed

    def _ftp_upload_asis(self):
        """Upload without IPTC writing (used when the IPTC tab is off)."""
        allowed = self._commercial_allowed_paths()
        files = []
        for path, _name, target, _r in self._iptc_paths():
            if path not in allowed:
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

    # ── Person shown -> categories / depicts ─────────────────────────────────

    def _iptc_current_persons(self):
        """List of person names in the Person-shown field of the loaded file."""
        self._iptc_commit_current()
        if not self._iptc_current:
            return []
        raw = self._iptc_store.get(self._iptc_current, {}).get(
            iptc.PERSON_KEY, '')
        return iptc.split_multi(raw)

    def _iptc_apply_to_desc(self, transform):
        """Apply `transform(text) -> text` to the description (COL_DESC) of the
        currently loaded IPTC file, then refresh. Returns True on success."""
        for path, _name, _target, r in self._iptc_paths():
            if path != self._iptc_current:
                continue
            item = self.table.item(r, self.COL_DESC)
            if item is None:
                return False
            item.setText(transform(item.text()))
            self._refresh_effective(r)
            return True
        return False

    def _iptc_persons_transfer(self):
        """Combined: resolve each person shown once, then add BOTH a depicts
        (P180) statement (for picked QIDs) and a category (Commons category
        P373, the label, or the literal name)."""
        persons = self._iptc_current_persons()
        if not persons:
            QMessageBox.information(self, 'IPTC',
                                    tr('No person shown in this file.'))
            return
        qids, cats = self._iptc_resolve(persons)
        if qids is None:                   # cancelled
            return
        did = []
        if qids and self._iptc_apply_to_desc(
                lambda t: iptc.merge_depicts(t, qids)):
            did.append(tr('{n} depicts').format(n=len(qids)))
        if cats and self._iptc_apply_to_desc(
                lambda t: iptc.add_category_lines(t, cats)):
            did.append(tr('{n} categories').format(n=len(cats)))
        if did:
            self._iptc_log(tr('Person shown: added {what}.').format(
                what=', '.join(did)))

    def _iptc_resolve(self, names):
        """Resolve `names` via Wikidata (category mode: 'literal' allowed).
        Returns (qids, category_names) or (None, None) if cancelled.
        qids: the picked QIDs (for depicts / created during).
        category_names: Commons category (P373), label, or the literal name."""
        dlg = _PersonResolveDialog(names, mode='category',
                                   lang=current_language(), parent=self)
        if dlg.exec() != QDialog.Accepted:
            return None, None
        picks = dlg.result_choices()          # {name: 'literal' | qid | None}
        qids = [v for v in picks.values()
                if v and v != 'literal' and v.upper().startswith('Q')]
        cat_of_qid = {}
        if qids:
            # Off the GUI thread since 0.15.0 (security review): the
            # synchronous call froze the window for up to the timeout.
            # Errors keep their old meaning - an empty fetch, names fall
            # back to the label.
            fetched, _exc, _cancelled = fetch_in_background(
                self, tr('Asking Wikidata…'),
                fetch_commons_categories, qids)
            fetched = fetched or {}
            for q in qids:
                cat, label = fetched.get(q, (None, ''))
                cat_of_qid[q] = cat or label or ''
        cats = []
        for name, choice in picks.items():
            if not choice:
                continue
            cats.append(name if choice == 'literal'
                        else (cat_of_qid.get(choice) or name))
        return qids, [c for c in cats if c]

    # ── Constant creator / rights / contact block ────────────────────────────

    # (widget attr, storage key, label, is_contact) - primary widgets; the
    # storage key matches iptc.CONSTANT_FIELDS so _iptc_constants() maps 1:1.
    _CONSTANT_UI = [
        ('ci_byline_edit',    'byline',    'Creator (by-line)', False),
        ('ci_copyright_edit', 'copyright', 'Copyright notice',  False),
        ('ci_credit_edit',    'credit',    'Credit',            False),
        ('ci_email_edit',     'ci_email',  'E-mail',            True),
        ('ci_tel_edit',       'ci_tel',    'Phone',             True),
        ('ci_url_edit',       'ci_url',    'Website',           True),
        ('ci_street_edit',    'ci_street', 'Street',            True),
        ('ci_city_edit',      'ci_city',   'City',              True),
        ('ci_pcode_edit',     'ci_pcode',  'Postal code',       True),
        ('ci_ctry_edit',      'ci_ctry',   'Country',           True),
    ]

    def _build_iptc_constants_group(self):
        """Collapsible group with the creator / rights / contact fields that
        are written to EVERY processed image (persisted, not from MediaWiki)."""
        box = CollapsibleGroupBox(
            tr('Creator / rights / contact (same for all images)'))
        form = QFormLayout(box.content)
        for attr, _key, label, _contact in self._CONSTANT_UI:
            edit = QLineEdit()
            setattr(self, attr, edit)
            form.addRow(tr(label) + ':', edit)
        box.setChecked(False)          # collapsed by default
        return box

    def _iptc_constants(self):
        """The constant block as {storage_key: text} for iptc.write_iptc."""
        return {key: getattr(self, attr).text().strip()
                for attr, key, _l, _c in self._CONSTANT_UI}

    def _iptc_has_constants(self):
        return any(v for v in self._iptc_constants().values())

    # ── Event -> created during (P10408) / categories ────────────────────────

    def _iptc_current_event(self):
        self._iptc_commit_current()
        if not self._iptc_current:
            return ''
        return (self._iptc_store.get(self._iptc_current, {})
                .get(iptc.EVENT_KEY, '') or '').strip()

    def _iptc_event_transfer(self):
        """Combined: resolve the event once, then set "created during"
        (P10408) and add a category (Commons category P373, or the name)."""
        event = self._iptc_current_event()
        if not event:
            QMessageBox.information(self, 'IPTC',
                                    tr('No event in this file.'))
            return
        qids, cats = self._iptc_resolve([event])
        if qids is None:                   # cancelled
            return
        did = []
        if qids and self._iptc_apply_to_desc(
                lambda t: iptc.set_created_during(t, qids[0])):
            did.append(tr('created during {qid}').format(qid=qids[0]))
        if cats and self._iptc_apply_to_desc(
                lambda t: iptc.add_category_lines(t, cats)):
            did.append(tr('{n} categories').format(n=len(cats)))
        if did:
            self._iptc_log(tr('Event: added {what}.').format(
                what=', '.join(did)))

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
        has_const = self._iptc_has_constants()
        for path, _name, target, _r in self._iptc_paths():
            if only_paths is not None and path not in only_paths:
                continue
            data = self._iptc_store.get(path)
            has_data = bool(data and any(v.strip() for v in data.values()))
            # Write a file if it has its own IPTC data OR the constant block is
            # filled (the creator/rights block goes onto every processed image).
            if not has_data and not has_const:
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
                                constants=self._iptc_constants(),
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
        IPTC -> upload the written files. Commons-marked files are excluded
        (channel marks, 0.12.1)."""
        if not self._ftp_credentials_ok():
            return
        targets = self._iptc_write_targets(
            only_paths=self._commercial_allowed_paths())
        if not targets:
            return

        # Write IPTC first; only successfully written files are uploaded.
        files = []
        for path, write_path, remote in targets:
            try:
                actual = iptc.write_iptc(path, self._iptc_store.get(path, {}),
                                         constants=self._iptc_constants(),
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
        # Sending a file to an agency IS the channel decision (0.12.4): mark
        # these as commercial so they are greyed out and skipped on the
        # Commons side from now on. This is the choke point for both FTP
        # buttons, so one call covers them.
        self._mark_uploaded_channel([p for p, _remote in files],
                                    channels.MARK_COMMERCIAL)
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
        for attr, key, _l, _c in self._CONSTANT_UI:
            s.setValue('iptc_const_' + key, getattr(self, attr).text())

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
        for attr, key, _l, _c in self._CONSTANT_UI:
            getattr(self, attr).setText(s.value('iptc_const_' + key, ''))

    def _ftp_load_settings(self):
        s = self.settings
        # 0.14.1: encrypted transport as the default for FRESH setups (a
        # stored choice always wins). Plain FTP sends the password and the
        # images in cleartext and stays available for servers that need it.
        proto = s.value('ftp_protocol', 'ftps')
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
