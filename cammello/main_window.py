"""Main application window and entry point."""
import os
import sys
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QPushButton, QLabel, QLineEdit,
    QTextEdit, QFileDialog, QMessageBox, QProgressBar, QSplitter,
    QGroupBox, QFormLayout, QHeaderView, QAbstractItemView, QDialog,
    QDialogButtonBox, QCheckBox, QStatusBar, QTabWidget, QPlainTextEdit,
    QStyledItemDelegate, QComboBox, QScrollArea, QCompleter)
from PyQt5.QtCore import (Qt, QThread, pyqtSignal, QSettings, QObject, QUrl,
                          QSize, QRegExp, QTimer, QStringListModel, QEvent)
from PyQt5.QtGui import (QPixmap, QFont, QDesktopServices, QIcon, QImageReader,
                         QRegExpValidator)
from .constants import *
from .constants import __version__
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
from .mw_settings import MWSettingsMixin
from .mw_files import MWFilesMixin
from .mw_editor import MWEditorMixin
from .mw_upload import MWUploadMixin


class MainWindow(MWSettingsMixin, MWFilesMixin, MWEditorMixin, MWUploadMixin, QMainWindow):
    COLS = ['', 'Source file', 'Target filename (Commons)', 'Date',
            'Description (file, hidden)', 'Description', 'Status']
    COL_THUMB = 0
    COL_FILENAME = 1
    COL_TITLE = 2
    COL_DATE = 3
    COL_DESC = 4
    COL_EFFECTIVE = 5
    COL_STATUS = 6

    def __init__(self, logger, emitter, gui_handler, log_path):
        super().__init__()
        self.logger = logger
        self.emitter = emitter
        self.gui_handler = gui_handler
        self.log_path = log_path

        self.setWindowTitle(f'{APP_NAME} v{__version__}')
        self.setMinimumSize(1150, 740)
        # Higher-contrast borders for all input fields (cascades to children,
        # incl. the per-language Information wikitext boxes).
        self.setStyleSheet(INPUT_STYLE)
        self.api = None
        self.settings = QSettings(APP_NAME, 'Main')
        self._loading_desc = False  # guard against feedback loops while loading
        self._editor_item = None     # COL_FILENAME item of the row loaded in the
        #                              per-file editor; item.row() stays correct
        #                              even after sorting or row removal.

        self._build_ui()
        self._restore_settings()

        # Mirror the live log into the GUI.
        self.emitter.log_record.connect(self._append_log)

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.tabs.addTab(self._build_upload_tab(), '⬆ Upload')
        self.tabs.addTab(self._build_log_tab(), '🐞 Log')

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage('Ready. Please log in first.')

    def _build_upload_tab(self):
        page = QWidget()
        main_layout = QVBoxLayout(page)

        # ── Toolbar ──
        toolbar = QHBoxLayout()
        self.login_btn = QPushButton('Login')
        self.login_btn.clicked.connect(self.do_login)

        self.test_btn = QPushButton('Test connection')
        self.test_btn.clicked.connect(self.test_connection)
        self.test_btn.setEnabled(False)

        self.login_label = QLabel('Not logged in')
        self.login_label.setStyleSheet('color: red')

        add_btn = QPushButton('Add files')
        add_btn.clicked.connect(self.add_files)
        remove_btn = QPushButton('Remove selected')
        remove_btn.clicked.connect(self.remove_selected)
        bulk_btn = QPushButton('Bulk edit selected')
        bulk_btn.clicked.connect(self.bulk_edit_selected)
        clear_btn = QPushButton('Clear all')
        clear_btn.clicked.connect(self.clear_all)

        self.upload_btn = QPushButton('Upload all')
        self.upload_btn.clicked.connect(self.start_upload)
        self.upload_btn.setStyleSheet(
            'font-weight: bold; background: #2a7; color: white; padding: 4px 12px;')

        self.ignore_warnings_cb = QCheckBox('Ignore warnings (overwrite)')

        toolbar.addWidget(self.login_btn)
        toolbar.addWidget(self.test_btn)
        toolbar.addWidget(self.login_label)
        toolbar.addSpacing(20)
        toolbar.addWidget(add_btn)
        toolbar.addWidget(remove_btn)
        toolbar.addWidget(bulk_btn)
        toolbar.addWidget(clear_btn)
        toolbar.addStretch()
        toolbar.addWidget(self.ignore_warnings_cb)
        toolbar.addWidget(self.upload_btn)
        main_layout.addLayout(toolbar)

        # ── Splitter ──
        splitter = QSplitter(Qt.Horizontal)

        self.table = FileDropTableWidget(
            0, len(self.COLS),
            on_files_dropped=self._add_dropped_files,
            logger=self.logger)
        self.table.setHorizontalHeaderLabels(self.COLS)
        # Thumbnails on the left: icon size and row height.
        self.table.setIconSize(QSize(96, 64))
        self.table.verticalHeader().setDefaultSectionSize(70)
        self.table.verticalHeader().setVisible(False)
        # Fixed extension in the target filename (via delegate).
        self.table.setItemDelegateForColumn(
            self.COL_TITLE, FilenameDelegate(self._ext_for_row, self.table))

        ht = self.table.horizontalHeaderItem(self.COL_TITLE)
        if ht:
            ht.setToolTip('Name under which the file is stored on Commons '
                          '(without "File:"). The extension is taken from the '
                          'source file and cannot be changed. Empty = source filename.')
        hs = self.table.horizontalHeaderItem(self.COL_FILENAME)
        if hs:
            hs.setToolTip('Local source file (not modified).')
        htb = self.table.horizontalHeaderItem(self.COL_THUMB)
        if htb:
            htb.setToolTip('Preview')

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(self.COL_THUMB, QHeaderView.Fixed)
        self.table.setColumnWidth(self.COL_THUMB, 104)
        header.setSectionResizeMode(self.COL_FILENAME, QHeaderView.Interactive)
        self.table.setColumnWidth(self.COL_FILENAME, 250)
        header.setSectionResizeMode(self.COL_TITLE, QHeaderView.Interactive)
        self.table.setColumnWidth(self.COL_TITLE, 240)
        header.setSectionResizeMode(self.COL_DESC, QHeaderView.Interactive)
        self.table.setColumnWidth(self.COL_DESC, 220)
        header.setSectionResizeMode(self.COL_EFFECTIVE, QHeaderView.Stretch)
        header.setSectionResizeMode(self.COL_STATUS, QHeaderView.Interactive)
        self.table.setColumnWidth(self.COL_STATUS, 150)

        # The per-file description is kept as the editable data store (the side
        # editor writes to it and upload reads it) but hidden from the table;
        # the "Description" column now shows the combined effective text.
        self.table.setColumnHidden(self.COL_DESC, True)
        # Wrap long effective text and let each row grow to show all of it.
        self.table.setWordWrap(True)
        self.table.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents)

        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked)
        self.table.itemSelectionChanged.connect(self.on_row_selected)
        # Click a column header to sort. Sorting is switched off while rows
        # are being inserted (see _add_paths) so the table is not reshuffled
        # mid-population.
        self.table.setSortingEnabled(True)
        splitter.addWidget(self.table)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right.setMinimumWidth(360)

        settings_group = CollapsibleGroupBox('Upload settings')
        settings_group.setStyleSheet(GROUP_TITLE_STYLE)
        settings_form = QFormLayout(settings_group.content)
        self.author_edit = QLineEdit()
        self.author_edit.setPlaceholderText('e.g. [[User:Seewolf|Harald Krichel]]')
        self.creator_edit = QLineEdit()
        self.creator_edit.setPlaceholderText('e.g. Q640')
        _style_wd_field(self.creator_edit, searchable=True)
        self._creator_suggest = WikidataSuggest(self.creator_edit, multi=False)
        self.source_edit = QLineEdit('{{own}}')
        self.source_edit.setPlaceholderText('e.g. {{own}}')
        self.permission_edit = QLineEdit()
        self.permission_edit.setPlaceholderText('e.g. (leave empty unless needed)')
        self.license_edit = QLineEdit('{{Cc-by-sa-4.0}}')
        self.license_edit.setPlaceholderText('e.g. {{Cc-by-sa-4.0}}')
        self.license_sdc_edit = QLineEdit('Q18199165')
        _style_wd_field(self.license_sdc_edit)
        self.copyright_sdc_edit = QLineEdit('Q73566113')
        _style_wd_field(self.copyright_sdc_edit)
        # These SDC values are prepended to every file at upload; keep the
        # per-row "Effective" preview in sync when they change.
        for _e in (self.creator_edit, self.license_sdc_edit, self.copyright_sdc_edit):
            _e.textChanged.connect(lambda *_: self._refresh_all_effective())
        self.other_templates_edit = QLineEdit()
        self.other_templates_edit.setPlaceholderText(
            'e.g. {{WikiPortraits at Berlinale 2026}}')
        self.other_fields_edit = QLineEdit()
        self.other_fields_edit.setPlaceholderText(
            'e.g. {{Credit line|Author=Harald Krichel|Other=WikiPortraits}}')
        self.gallery_prefix_edit = QLineEdit()
        self.gallery_prefix_edit.setPlaceholderText('e.g. User:Seewolf')
        self.timeout_edit = QLineEdit('120')
        self.timeout_edit.setMaximumWidth(80)

        settings_form.addRow('Author:', self.author_edit)
        settings_form.addRow('Creator (P170):', self.creator_edit)
        settings_form.addRow('Source:', self.source_edit)
        settings_form.addRow('Permission:', self.permission_edit)
        settings_form.addRow('License:', self.license_edit)
        settings_form.addRow('License (P275):', self.license_sdc_edit)
        settings_form.addRow('Copyright (P6216):', self.copyright_sdc_edit)
        settings_form.addRow('Other templates:', self.other_templates_edit)
        settings_form.addRow('Other fields:', self.other_fields_edit)
        settings_form.addRow('Gallery prefix:', self.gallery_prefix_edit)
        settings_form.addRow('HTTP timeout (s):', self.timeout_edit)
        apply_form_ratio(settings_form)
        right_layout.addWidget(settings_group)

        # Mode toggle: expert mode shows the raw description_all text; when it is
        # off (the default), the structured fields are shown.
        self.expert_cb = QCheckBox('Expert mode (raw description_all text)')
        self.expert_cb.setToolTip('Edit the raw description_all text directly '
                                  'instead of using the structured single-line '
                                  'fields.')
        self.expert_cb.stateChanged.connect(self._toggle_expert)
        right_layout.addWidget(self.expert_cb)

        # ── Base description (for all files) ──
        base_group = CollapsibleGroupBox('Base description (for all files)')
        base_group.setStyleSheet(GROUP_TITLE_STYLE)
        base_layout = QVBoxLayout(base_group.content)
        self.base_text_edit = QTextEdit()
        self.base_text_edit.setPlaceholderText(
            'Shared lines for every file, e.g.\n'
            'depicts=Q42; Q64\n'
            'gallery_suffix=Berlinale 2026\n'
            '\n'
            '{{en|1=…}}\n'
            '[[Category:…]]')
        self.base_text_edit.setMinimumHeight(110)
        self.base_text_edit.textChanged.connect(self._on_base_text_changed)
        base_layout.addWidget(self.base_text_edit)
        self.base_struct = StructuredDescriptionEditor(is_base=True)
        self.base_struct.changed.connect(self._on_base_struct_changed)
        self.base_struct.setVisible(False)
        base_layout.addWidget(self.base_struct)
        right_layout.addWidget(base_group)

        save_settings_btn = QPushButton('Save settings')
        save_settings_btn.setToolTip('Save the upload settings and the base '
                                     'description so they are restored next time.')
        save_settings_btn.clicked.connect(self._on_save_settings)
        right_layout.addWidget(save_settings_btn)

        # Settings import/export to a plain text file (optionally incl. the
        # selected file's description).
        file_io = QHBoxLayout()
        save_file_btn = QPushButton('Save to file…')
        save_file_btn.setToolTip('Write settings + base description to a text file.')
        save_file_btn.clicked.connect(self._save_settings_to_file)
        load_file_btn = QPushButton('Load from file…')
        load_file_btn.setToolTip('Read settings back from a text file.')
        load_file_btn.clicked.connect(self._load_settings_from_file)
        self.export_file_desc_cb = QCheckBox('incl. selected file')
        self.export_file_desc_cb.setToolTip(
            "Also write the selected file's description into the settings file.")
        file_io.addWidget(save_file_btn)
        file_io.addWidget(load_file_btn)
        file_io.addWidget(self.export_file_desc_cb)
        file_io.addStretch()
        right_layout.addLayout(file_io)

        # ── Selected file description ──
        file_group = CollapsibleGroupBox('Selected file – description')
        file_group.setStyleSheet(GROUP_TITLE_STYLE)
        file_layout = QVBoxLayout(file_group.content)
        self.file_desc_edit = FocusOutTextEdit()
        self.file_desc_edit.setPlaceholderText(EXAMPLE_FILE_DESCRIPTION)
        self.file_desc_edit.setMinimumHeight(150)
        # Live sync to the table on every edit (does not depend on focus
        # events); editingFinished stays connected as a harmless safety net.
        self.file_desc_edit.textChanged.connect(self._commit_editor)
        self.file_desc_edit.editingFinished.connect(self._commit_editor)
        file_layout.addWidget(self.file_desc_edit)
        self.file_struct = StructuredDescriptionEditor(is_base=False)
        self.file_struct.changed.connect(self._commit_editor)
        self.file_struct.committed.connect(self._commit_editor)
        self.file_struct.setVisible(False)
        file_layout.addWidget(self.file_struct)
        right_layout.addWidget(file_group)

        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumHeight(140)
        self.preview_label.setStyleSheet('background: #111; border-radius: 4px;')
        right_layout.addWidget(self.preview_label)
        right_layout.addStretch()

        # Wrap the right panel in a scroll area so fields are never compressed.
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setWidget(right)
        right_scroll.setMinimumWidth(380)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        splitter.addWidget(right_scroll)
        splitter.setSizes([720, 420])
        main_layout.addWidget(splitter)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        return page

    def _build_log_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        top = QHBoxLayout()
        self.verbose_cb = QCheckBox('Verbose logging')
        self.verbose_cb.stateChanged.connect(self._toggle_verbose)
        clear_log_btn = QPushButton('Clear')
        clear_log_btn.clicked.connect(lambda: self.log_view.clear())
        copy_log_btn = QPushButton('Copy')
        copy_log_btn.clicked.connect(self._copy_log)
        open_file_btn = QPushButton('Open log file')
        open_file_btn.clicked.connect(self._open_log_file)
        open_dir_btn = QPushButton('Open folder')
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

        path_label = QLabel(f'Log file: {self.log_path}')
        path_label.setStyleSheet('color: gray; font-size: 11px;')
        path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(path_label)

        return page

    # ── Log helpers ──────────────────────────────────────────────────────────


# ── Entry point ────────────────────────────────────────────────────────────────


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)

    logger, emitter, gui_handler, log_path = setup_logging()

    # Write unhandled exceptions to the log as well.
    def excepthook(exc_type, exc_value, exc_tb):
        logger.critical('Unhandled exception:\n%s',
                        ''.join(traceback.format_exception(exc_type, exc_value, exc_tb)))
        sys.__excepthook__(exc_type, exc_value, exc_tb)
    sys.excepthook = excepthook

    window = MainWindow(logger, emitter, gui_handler, log_path)
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
