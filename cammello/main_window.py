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
from PyQt5.QtCore import (QT_VERSION_STR,
                          Qt, QThread, pyqtSignal, QSettings, QObject, QUrl,
                          QSize, QRegExp, QTimer, QStringListModel, QEvent,
                          QLocale)
from PyQt5.QtGui import (QPixmap, QFont, QDesktopServices, QIcon, QImageReader,
                         QRegExpValidator, QPalette, QColor)
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
from .mw_iptc import MWIptcMixin
from .mw_culling import MWCullingMixin, _TabBarDropSwitcher
from .mw_flickr import FlickrMixin
from . import iptc as iptc_mod
from . import mw_oauth
from . import credentials
from . import channels
from .menus import MenusMixin
from .wikidata import refresh_wd_fields
from .i18n import (tr, UI_LANGUAGES, set_language,
                   default_language_from_locale, current_language)


_SYSTEM_APPEARANCE = None    # (palette, style name) captured at first use
_APPLIED_SCHEME = ['system']  # the app starts in the system scheme


class MainWindow(FlickrMixin,
                 MWSettingsMixin, MWFilesMixin, MWEditorMixin, MWUploadMixin,
                 MWIptcMixin, MWCullingMixin, MenusMixin, QMainWindow):
    COLS = ['', 'Source file', 'Target filename (Commons)', 'Date',
            'Description (file, hidden)', 'Wikitext', 'Status']
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

        # Translated column headers: an INSTANCE attribute, so tr() runs
        # after main() selected the language (the class attribute stays as
        # the English fallback).
        self.COLS = ['', tr('Source file'), tr('Target filename (Commons)'),
                     tr('Date'), tr('Description (file, hidden)'),
                     tr('Wikitext'), tr('Status')]
        self.setWindowTitle(f'{APP_NAME} v{__version__}')
        self.setMinimumSize(1150, 740)
        # Higher-contrast borders for all input fields (cascades to children,
        # incl. the per-language Information wikitext boxes).
        # 0.11.0: sync the input-style VARIANT with the actual palette first.
        # Up to now the light variant was always applied at construction, so
        # scheme='system' on a dark desktop (macOS dark mode) mixed light
        # inputs into a dark UI - and the Wikidata fields, styled once at
        # build time, kept the wrong variant permanently.
        set_current_input_style(
            QApplication.instance().palette().color(
                QPalette.Window).lightness() < 128)
        # 0.11.0: ONE application-level stylesheet (inputs + group chrome +
        # About page; see constants.app_style) - per-widget stylesheets on
        # the collapsible groups kept producing wrongly rendered child
        # fields on macOS.
        QApplication.instance().setStyleSheet(app_style())
        self.api = None
        self.settings = QSettings(APP_NAME, 'Main')
        # Channel marks (0.12.1): Commons/CC vs. commercial, persisted across
        # sessions keyed by normalized path - loaded BEFORE the UI is built so
        # list population can style rows right away.
        self._channel_settings = QSettings(APP_NAME, 'Channels')
        self._channel_marks = channels.load_marks(self._channel_settings)
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
        # Lightroom-style module strip (0.12.6): a flat text row ABOVE the
        # pages, right-aligned, replaces the hidden Qt tab bar as the visible
        # workflow map (Harald: 'Tabs wiederhaben ... wie bei Lightroom oben
        # rechts'). The QTabWidget stays the page container - every mixin
        # and feature switch keeps addressing it - but its own bar remains
        # hidden; the strip is a separate widget synced both ways.
        central = QWidget()
        _central_lay = QVBoxLayout(central)
        _central_lay.setContentsMargins(0, 0, 0, 0)
        _central_lay.setSpacing(0)
        self.module_strip = ModuleStrip(self.tabs)
        _central_lay.addWidget(self.module_strip)
        _central_lay.addWidget(self.tabs, 1)
        self.setCentralWidget(central)

        # The MediaWiki (upload) tab is built first (its widgets are read by
        # the IPTC tab), but added to the tab bar AFTER the Culling tab.
        mw_tab = self._build_upload_tab()
        # Keep a reference so the MediaWiki widgets survive even when the tab
        # is hidden (not added to the bar): the IPTC tab and the Settings
        # mirrors read author_edit & Co., and _restore_settings writes them.
        # Without this reference Qt garbage-collects the unparented widget.
        self._mw_tab = mw_tab

        # Hidden per-tab switches (no UI): QSettings booleans, flipped from
        # the command line via --disable-tab / --enable-tab (see main()).
        # pyexiv2 remains the hard gate for all three, as before.
        avail = iptc_mod.available()
        self._feat_culling = avail and self.settings.value(
            'feature_culling', True, type=bool)
        self.logger.info(
            'Features: pyexiv2 %s | culling=%s iptc=%s ftp=%s flickr=%s',
            f'available (via {iptc_mod.GATE_MODE})' if avail else
            f'UNAVAILABLE ({iptc_mod.unavailable_reason()})',
            self._feat_culling if avail else False,
            self.settings.value('feature_iptc', False, type=bool) and avail,
            self.settings.value('feature_ftp', True, type=bool) and avail,
            self.settings.value('feature_flickr', True, type=bool))
        # RELEASE DEFAULT 0.10.0: the IPTC tab is hidden; `--enable-tab
        # iptc` brings it back (persists in QSettings).
        self._feat_iptc = avail and self.settings.value(
            'feature_iptc', False, type=bool)
        self._feat_ftp = avail and self.settings.value(
            'feature_ftp', True, type=bool)
        # Flickr is INDEPENDENT of pyexiv2 (it only needs the file table).
        # Read BEFORE the culling tab is built: its toolbar shows the
        # '-> Flickr' target only when the feature is on.
        self._feat_flickr = self.settings.value('feature_flickr', True,
                                                type=bool)
        # MediaWiki and Log are hideable too (everything except Settings and
        # About). Both are independent of pyexiv2. Their widgets are always
        # BUILT - the IPTC tab and the Settings mirrors read the MediaWiki
        # fields, and the GUI log handler writes into the Log widget - only
        # the tab is withheld from the bar. Applied at the next start.
        self._feat_mediawiki = self.settings.value(
            'feature_mediawiki', True, type=bool)
        if not self._feat_flickr:
            self.logger.info('Flickr tab disabled via hidden switch '
                             '(re-enable with --enable-tab flickr).')
        if not avail:
            self.logger.info('IPTC, FTP and Culling tabs disabled: %s',
                             iptc_mod.unavailable_reason())
        else:
            for flag, name in ((self._feat_culling, 'Culling'),
                               (self._feat_iptc, 'IPTC'),
                               (self._feat_ftp, 'FTP')):
                if not flag:
                    self.logger.info(
                        '%s tab disabled via hidden switch (re-enable with '
                        '--enable-tab %s).', name, name.lower())

        if self._feat_culling:
            # Culling first (most-used tab for a shoot workflow).
            self._cull_settings_box = self._build_culling_settings_box()
            self._cull_tab_widget = self._build_culling_tab()
            self.tabs.addTab(self._cull_tab_widget, tr('Culling'))
            self._cull_load_settings()
        if self._feat_mediawiki:
            self._mw_tab_widget = mw_tab
            self.tabs.addTab(mw_tab, 'MediaWiki')
        if self._feat_iptc:
            self._iptc_tab_widget = self._build_iptc_tab()
            self.tabs.addTab(self._iptc_tab_widget, 'IPTC')
            self._iptc_load_settings()
        if self._feat_ftp or self._feat_flickr:
            # Merged FTP / Flickr tab (title reflects what is enabled).
            title = ('FTP / Flickr' if (self._feat_ftp and self._feat_flickr)
                     else ('FTP' if self._feat_ftp else 'Flickr'))
            self._ftpflickr_tab_widget = self._build_ftp_tab()
            self.tabs.addTab(self._ftpflickr_tab_widget, title)
            if self._feat_ftp:
                self._ftp_load_settings()
            if self._feat_flickr:
                self._flickr_load_settings()

        if self._feat_culling:
            # Drag from the culling strip switches tabs on hover.
            self._tab_drop_switcher = _TabBarDropSwitcher(self.tabs)
        if (self._feat_culling or self._feat_iptc or self._feat_ftp
                or self._feat_flickr):
            self.tabs.currentChanged.connect(self._on_tab_changed)
        # Settings, Log and About are DIALOGS since 0.12.6 (Harald: 'der
        # Konvention nach je ein Unterfenster') - the tab row carries only
        # the four workflow steps. The page WIDGETS are built exactly as
        # before and re-parented into lazy dialogs by _open_page_dialog, so
        # every existing reference (mirrors, log handler, feature switches)
        # keeps working; they are simply not added to the QTabWidget.
        self._page_dialogs = {}
        self._settings_tab_widget = self._build_settings_tab()
        # Restore the persisted color scheme (setCurrentText fires
        # _apply_color_scheme; 'system' applies explicitly for the delegate).
        saved_scheme = self.settings.value('color_scheme', 'system')
        # No repolish during construction (see _apply_color_scheme). The
        # combo signal is blocked so restoring does not trigger the
        # user-switch path on a half-built window. The combo stores the
        # scheme CODE as item data (the visible text is translated).
        self.scheme_combo.blockSignals(True)
        _si = self.scheme_combo.findData(saved_scheme)
        if _si >= 0:
            self.scheme_combo.setCurrentIndex(_si)
        self.scheme_combo.blockSignals(False)
        self._apply_color_scheme(saved_scheme, repolish=False)
        self._log_tab = self._build_log_tab()  # always built: the GUI log
        # handler writes into it even while no window shows it
        self._about_tab_widget = self._build_about_tab()

        # Native menu bar (0.12.3). Built last: it enumerates the pages that
        # exist, and hides the now-redundant tab bar.
        self._build_menus()

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage(tr('Ready. Please log in first.'))

    def _build_upload_tab(self):
        page = QWidget()
        main_layout = QVBoxLayout(page)

        # ── Toolbar ──
        # Deliberately minimal (0.12.5): the file actions all live in the
        # menus now (File > Add files, Metadata/File > list commands, Upload >
        # Log in / Test connection). Long German labels used to squeeze the
        # row until the buttons painted over each other - and a row of eight
        # buttons cannot be made slim at all. What stays is the session state
        # and the one action that is used constantly.
        toolbar = QHBoxLayout()
        self.login_btn = QPushButton(tr('Login'))
        self.login_btn.clicked.connect(self.do_login)

        self.test_btn = QPushButton(tr('Test connection'))
        self.test_btn.clicked.connect(self.test_connection)
        self.test_btn.setEnabled(False)

        # 'Not logged in' is a LINK (0.12.6): one click opens the (OAuth)
        # login instead of making the user hunt for the menu entry. The
        # logged-in state shows the plain username.
        self.login_label = QLabel()
        self.login_label.setTextFormat(Qt.RichText)
        self.login_label.linkActivated.connect(lambda _url: self.do_login())
        self._set_login_state('out')

        self.ignore_warnings_cb = QCheckBox(tr('Ignore warnings (overwrite)'))

        # Label is kept in sync with the selection by _update_upload_btn:
        # selected rows are uploaded, or all rows when nothing is selected.
        self.upload_btn = QPushButton(tr('Upload all'))
        self.upload_btn.clicked.connect(self.start_upload)
        # The accent look lives in constants.BUTTON_STYLE (0.12.7) so that
        # every button in the app is styled from ONE place; an inline
        # stylesheet here would win over it and drift again.
        self.upload_btn.setProperty('cammelloPrimary', True)

        toolbar.addWidget(self.login_label)
        toolbar.addStretch()
        toolbar.addWidget(self.ignore_warnings_cb)
        toolbar.addWidget(self.upload_btn)
        slim_toolbar(toolbar)
        main_layout.addLayout(toolbar)

        # ── Splitter ──
        splitter = QSplitter(Qt.Horizontal)

        self.table = FileDropTableWidget(
            0, len(self.COLS),
            on_files_dropped=self._add_dropped_files,
            logger=self.logger,
            on_rename=self._rename_selected)
        self.table.setHorizontalHeaderLabels(self.COLS)
        # Thumbnails on the left: icon size and row height.
        self.table.setIconSize(QSize(THUMB_W, THUMB_H))
        self.table.verticalHeader().setDefaultSectionSize(THUMB_ROW_HEIGHT)
        self.table.verticalHeader().setVisible(False)
        # Fixed extension in the target filename (via delegate).
        self.table.setItemDelegateForColumn(
            self.COL_TITLE, FilenameDelegate(self._ext_for_row, self.table))

        ht = self.table.horizontalHeaderItem(self.COL_TITLE)
        if ht:
            ht.setToolTip(tr('Name under which the file is stored on Commons '
                          '(without "File:"). The extension is taken from the '
                          'source file and cannot be changed. Empty = source filename.')
                          + ' ' + tr('F2 renames; with several rows selected '
                                     'F2 opens the bulk rename.'))
        hs = self.table.horizontalHeaderItem(self.COL_FILENAME)
        if hs:
            hs.setToolTip(tr('Local source file (not modified).'))
        htb = self.table.horizontalHeaderItem(self.COL_THUMB)
        if htb:
            htb.setToolTip(tr('Preview'))
        he = self.table.horizontalHeaderItem(self.COL_EFFECTIVE)
        if he:
            he.setToolTip(tr('Effective wikitext (upload settings + base '
                          'description + this file). Read-only; shown at most '
                          '{max_lines} lines high - hover a cell for '
                          'the full text.').format(max_lines=WIKITEXT_MAX_LINES))

        header = self.table.horizontalHeader()
        # Draggable between 1x and 2x; the icon size follows the width
        # (see _on_thumb_column_resized). Source pixmaps are 2x, so no blur.
        header.setSectionResizeMode(self.COL_THUMB, QHeaderView.Interactive)
        self.table.setColumnWidth(self.COL_THUMB, THUMB_COL_WIDTH)
        header.sectionResized.connect(self._on_thumb_column_resized)
        # 0.9.8: the neighbours of the Wikitext column are narrower so the
        # stretching Wikitext column gets noticeably more room (was 250 / 240
        # / 150). All three stay interactive and can be widened by hand.
        header.setSectionResizeMode(self.COL_FILENAME, QHeaderView.Interactive)
        self.table.setColumnWidth(self.COL_FILENAME, 180)
        header.setSectionResizeMode(self.COL_TITLE, QHeaderView.Interactive)
        self.table.setColumnWidth(self.COL_TITLE, 200)
        header.setSectionResizeMode(self.COL_DESC, QHeaderView.Interactive)
        self.table.setColumnWidth(self.COL_DESC, 220)
        # Interactive instead of Stretch: a Stretch section cannot be resized
        # by dragging in Qt. The last section stretches instead, so the table
        # still has no dead space on the right.
        header.setSectionResizeMode(self.COL_EFFECTIVE, QHeaderView.Interactive)
        self.table.setColumnWidth(self.COL_EFFECTIVE, 480)
        header.setSectionResizeMode(self.COL_STATUS, QHeaderView.Interactive)
        self.table.setColumnWidth(self.COL_STATUS, 110)
        header.setStretchLastSection(True)
        # Split cursor on draggable column edges (see HeaderResizeCursorFilter).
        self._header_cursor_filter = HeaderResizeCursorFilter(header)

        # The per-file description is kept as the editable data store (the side
        # editor writes to it and upload reads it) but hidden from the table;
        # the "Description" column now shows the combined effective text.
        self.table.setColumnHidden(self.COL_DESC, True)
        # Wrap long effective text and let each row grow with its content -
        # but the Wikitext column is capped at WIKITEXT_MAX_LINES lines by the
        # delegate, so a single long description cannot blow up the row.
        self.table.setWordWrap(True)
        self.table.setItemDelegateForColumn(
            self.COL_EFFECTIVE,
            CappedRowHeightDelegate(WIKITEXT_MAX_LINES, self.table))
        self.table.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents)

        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        # Right-click menu: channel marks (Commons/CC vs. commercial, 0.12.1).
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._table_context_menu)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked)
        self.table.itemSelectionChanged.connect(self.on_row_selected)
        self.table.itemSelectionChanged.connect(self._update_upload_btn)
        # Click a column header to sort. Sorting is switched off while rows
        # are being inserted (see _add_paths) so the table is not reshuffled
        # mid-population.
        self.table.setSortingEnabled(True)
        splitter.addWidget(self.table)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right.setMinimumWidth(360)

        settings_group = CollapsibleGroupBox(tr('Author and license'))
        # Section tooltips (Harald's wording): they say what SCOPE a section
        # has - the three blocks differ in how far their values reach, and
        # that is exactly what is not obvious from the headings.
        settings_group.setToolTip(tr(
            'What probably stays the same for a photographer forever.'))
        settings_form = QFormLayout(settings_group.content)
        self.author_edit = QLineEdit()
        self.author_edit.setPlaceholderText(tr('e.g.') + ' [[User:Seewolf|Harald Krichel]]')
        self.creator_edit = QLineEdit()
        self.creator_edit.setPlaceholderText(tr('e.g.') + ' Q640')
        _style_wd_field(self.creator_edit, searchable=True)
        self._creator_suggest = WikidataSuggest(self.creator_edit, multi=False)
        self.source_edit = QLineEdit('{{own}}')
        self.source_edit.setPlaceholderText(tr('e.g.') + ' {{own}}')
        self.permission_edit = QLineEdit()
        self.permission_edit.setPlaceholderText(tr('e.g. (leave empty unless needed)'))
        # Licence and copyright status as DROPDOWNS (Harald, 0.12.14). All
        # three stay editable - the presets are the common cases, not a
        # restriction. Picking a licence in one of the two licence fields
        # sets the matching value in the other (see _link_license_fields),
        # because a template and a P275 item that disagree are a defect.
        self.license_edit = PresetComboBox()
        for _label, _tmpl, _qid in LICENSE_PRESETS:
            self.license_edit.add_choice(_label, _tmpl)
        self.license_edit.setText('{{Cc-by-sa-4.0}}')
        self.license_edit.setPlaceholderText(tr('e.g.') + ' {{Cc-by-sa-4.0}}')
        self.license_sdc_edit = PresetComboBox()
        for _label, _tmpl, _qid in LICENSE_PRESETS:
            self.license_sdc_edit.add_choice(_label, _qid)
        self.license_sdc_edit.setText('Q18199165')
        _style_wd_field(self.license_sdc_edit)
        self.copyright_sdc_edit = PresetComboBox()
        for _label, _qid in COPYRIGHT_PRESETS:
            self.copyright_sdc_edit.add_choice(tr(_label), _qid)
        self.copyright_sdc_edit.setText('Q73566113')
        _style_wd_field(self.copyright_sdc_edit)
        self._link_license_fields()
        # These SDC values are prepended to every file at upload; keep the
        # per-row "Effective" preview in sync when they change.
        for _e in (self.creator_edit, self.license_sdc_edit, self.copyright_sdc_edit):
            _e.textChanged.connect(lambda *_: self._refresh_all_effective())
        self.other_templates_edit = QLineEdit()
        self.other_templates_edit.setPlaceholderText(
            tr('e.g.') + ' {{WikiPortraits at Berlinale 2026}}')
        self.other_fields_edit = QLineEdit()
        self.other_fields_edit.setPlaceholderText(
            tr('e.g.') + ' {{Credit line|Author=Harald Krichel|Other=WikiPortraits}}')
        self.gallery_prefix_edit = QLineEdit()
        self.gallery_prefix_edit.setPlaceholderText(tr('e.g.') + ' User:Seewolf')
        self.timeout_edit = QLineEdit('120')
        self.timeout_edit.setMaximumWidth(80)

        self.creator_edit.setToolTip(tr(
            'P170 "creator": the photographer as a Wikidata item, IF there '
            'is one\nabout you - e.g. Q1583452 (Harald Krichel). Type your '
            'name and pick\nfrom the suggestions, or enter the Q-number.\n\n'
            'SAME FACT AS "Author" ABOVE, in the second form: the author '
            'line is\nthe wikitext half, P170 the structured half. Commons '
            'stores both.\nWithout an own item leave this empty - the '
            'author line alone is fine.'))
        self.license_sdc_edit.setToolTip(tr(
            'P275 "copyright license": the SAME license as the template '
            'above, as a\nWikidata item - Q18199165 is CC BY-SA 4.0 and '
            'matches {{Cc-by-sa-4.0}}.\n\n'
            'Again the same fact twice: the template is the wikitext half, '
            'P275 the\nstructured half. Picking a license in EITHER '
            'dropdown sets the other\none too, so the two cannot '
            'contradict each other.'))
        self.copyright_sdc_edit.setToolTip(tr(
            'P6216 "copyright status": how the work stands in copyright '
            'terms.\n\n'
            'Q73566113 - available under a Creative Commons license: the '
            'right one\nfor own photographs published here (the default).\n'
            'Q50423863 - copyrighted, without such a release.\n'
            'Q19652 - public domain.\n\n'
            'This has no wikitext counterpart of its own; it exists only as '
            'structured\ndata. Pick from the dropdown or enter another '
            'Q-number.'))
        self.author_edit.setToolTip(tr(
            'Who took the pictures, as wikitext - typically a link to your '
            'Commons\nuser page with your real name as the visible text:\n\n'
            '  [[User:Seewolf|Harald Krichel]]\n\n'
            'Goes word for word into the author= field of every upload. '
            'This is the\nWIKITEXT half; "Creator (P170)" below is the '
            'same fact as structured\ndata. Commons keeps both, so both '
            'fields exist here.'))
        self.source_edit.setToolTip(tr(
            'Where the file comes from. For your own photographs enter '
            '{{own}} -\nthe template that renders as "Own work".\n\n'
            'Only for third-party material would a description or web '
            'address of the\norigin go here instead.'))
        self.permission_edit.setToolTip(tr(
            'Evidence of permission, ONLY for the special case that a '
            'rights holder\nhas filed a release with the volunteer team - '
            'then the VRT ticket\ntemplate goes here.\n\n'
            'For your own pictures under a free license this stays EMPTY; '
            'the\nlicense below is the permission.'))
        self.license_edit.setToolTip(tr(
            'The license template under which every file in this batch is '
            'published,\ne.g. {{Cc-by-sa-4.0}} for Creative Commons '
            'Attribution-ShareAlike 4.0.\n\n'
            'Must be one of the free licenses Commons accepts. The '
            'WIKITEXT half -\n"License (P275)" below says the same as '
            'structured data, and the two\nmust not disagree.'))
        settings_form.addRow(tr('Author:'), self.author_edit)
        settings_form.addRow(tr('Creator (P170):'), self.creator_edit)
        settings_form.addRow(tr('Source:'), self.source_edit)
        settings_form.addRow(tr('Permission:'), self.permission_edit)
        settings_form.addRow(tr('License:'), self.license_edit)
        for _w in (self.author_edit, self.source_edit,
                   self.permission_edit, self.license_edit,
                   self.creator_edit, self.license_sdc_edit,
                   self.copyright_sdc_edit):
            _lbl = settings_form.labelForField(_w)
            if _lbl is not None:
                _lbl.setToolTip(_w.toolTip())
        settings_form.addRow(tr('License (P275):'), self.license_sdc_edit)
        settings_form.addRow(tr('Copyright (P6216):'), self.copyright_sdc_edit)
        settings_form.addRow(tr('Other fields:'), self.other_fields_edit)
        settings_form.addRow(tr('Gallery prefix:'), self.gallery_prefix_edit)
        settings_form.addRow(tr('HTTP timeout (s):'), self.timeout_edit)
        apply_form_ratio(settings_form)
        # 0.10.0 regression fix: this group was detached from the tab for the
        # "everything in the Settings tab" move but never added THERE either,
        # so the upload settings were invisible in both tabs. They now live
        # HERE (primary widgets, attribute names unchanged) and are mirrored
        # into the Settings tab (see _build_mw_settings_mirror).
        right_layout.addWidget(settings_group)
        self._mw_settings_group = settings_group

        # Mode toggle: expert mode shows the raw description_all text; when it is
        # off (the default), the structured fields are shown.
        self.expert_cb = QCheckBox(tr('Expert mode (raw description_all text)'))
        self.expert_cb.setToolTip(tr('Edit the raw description_all text directly '
                                  'instead of using the structured single-line '
                                  'fields.'))
        self.expert_cb.stateChanged.connect(self._toggle_expert)
        right_layout.addWidget(self.expert_cb)

        # ── Base description (for all files) ──
        base_group = CollapsibleGroupBox(tr('Base description (for all files)'))
        base_group.setToolTip(tr(
            'For one upload session, e.g. all pictures of one event.'))
        base_layout = QVBoxLayout(base_group.content)
        self.base_text_edit = QTextEdit()
        self.base_text_edit.setPlaceholderText(
            tr('Shared lines for every file, e.g.') + '\n'
            'depicts=Q42; Q64\n'
            'gallery_suffix=Berlinale 2026\n'
            '\n'
            '{{en|1=…}}\n'
            '[[Category:…]]')
        self.base_text_edit.setMinimumHeight(110)
        self.base_text_edit.textChanged.connect(self._on_base_text_changed)
        base_layout.addWidget(self.base_text_edit)
        self.base_struct = StructuredDescriptionEditor(is_base=True)
        self.base_struct.suggest_requested.connect(
            self._suggest_created_during_category)
        self.base_struct.changed.connect(self._on_base_struct_changed)
        self.base_struct.setVisible(False)
        base_layout.addWidget(self.base_struct)
        # 0.12.6: event-bound templates ({{WikiPortraits at ...}}) belong to
        # the per-event base description, not to the constant author/license
        # block. The field object keeps its identity (QSettings key
        # 'other_templates', file export, live wikitext all unchanged).
        ot_form = QFormLayout()
        ot_form.addRow(tr('Other templates:'), self.other_templates_edit)
        apply_form_ratio(ot_form)
        base_layout.addLayout(ot_form)
        clear_base_btn = QPushButton(tr('Clear base description'))
        clear_base_btn.clicked.connect(self._clear_base_description)
        base_layout.addWidget(clear_base_btn)
        right_layout.addWidget(base_group)

        save_settings_btn = QPushButton(tr('Save settings'))
        save_settings_btn.setToolTip(tr('Save the upload settings and the base '
                                     'description so they are restored next time.'))
        save_settings_btn.clicked.connect(self._on_save_settings)
        right_layout.addWidget(save_settings_btn)

        # Settings import/export to a plain text file (optionally incl. the
        # selected file's description). FlowLayout, not QHBoxLayout: the right
        # column is ~380 px wide, where three side-by-side controls used to
        # overlap each other (0.12.4). Now they wrap onto a second line.
        file_io = FlowLayout(margin=0, spacing=6)
        save_file_btn = QPushButton(tr('Save to file…'))
        save_file_btn.setToolTip(tr('Write settings + base description to a text file.'))
        save_file_btn.clicked.connect(self._save_settings_to_file)
        load_file_btn = QPushButton(tr('Load from file…'))
        load_file_btn.setToolTip(tr('Read settings back from a text file.'))
        load_file_btn.clicked.connect(self._load_settings_from_file)
        self.export_file_desc_cb = QCheckBox(tr('incl. selected file'))
        self.export_file_desc_cb.setToolTip(
            tr("Also write the selected file's description into the settings file."))
        file_io.addWidget(save_file_btn)
        file_io.addWidget(load_file_btn)
        file_io.addWidget(self.export_file_desc_cb)
        right_layout.addLayout(file_io)

        # ── Selected file description ──
        file_group = CollapsibleGroupBox(tr('Selected file(s) - description'))
        file_group.setToolTip(tr(
            'The subject of one picture, possibly of several.'))
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
        self.file_struct.suggest_depicts_requested.connect(
            self._suggest_depicts_categories)
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
        # 0.9.8: more room for the table (and thus for the Wikitext column).
        splitter.setSizes([880, 400])
        main_layout.addWidget(splitter)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        return page

    def _on_thumb_column_resized(self, index, _old, new):
        if index != self.COL_THUMB:
            return
        clamped = max(THUMB_COL_WIDTH, min(THUMB_COL_MAX, new))
        if clamped != new:
            # Guard against recursion: setColumnWidth re-fires this handler
            # once with the clamped value, which then passes through.
            self.table.setColumnWidth(self.COL_THUMB, clamped)
            return
        w = clamped - 12
        self.table.setIconSize(QSize(w, int(w * THUMB_H / THUMB_W)))
        self.table.resizeRowsToContents()

    def _build_tabs_group(self):
        """Checkboxes to show/hide every tab except Settings and About.
        Backed by the same feature_* QSettings keys as the hidden
        --enable-tab/--disable-tab switches; applied at the next start (like
        the language setting). Tabs that need pyexiv2 are disabled with a hint
        when it is unavailable."""
        from PyQt5.QtWidgets import QGroupBox, QVBoxLayout, QCheckBox
        avail = iptc_mod.available()
        box = QGroupBox(tr('Modules'))
        v = QVBoxLayout(box)
        v.addWidget(QLabel(tr('Show these modules (applies after restart):')))
        # (settings key, label, default, needs_pyexiv2)
        # Log is no longer listed: since 0.12.6 it is a window, not a
        # module, and the log handler writes into it regardless.
        specs = [
            ('feature_culling', tr('Culling'), True, True),
            ('feature_mediawiki', 'MediaWiki', True, False),
            ('feature_iptc', 'IPTC', False, True),
            ('feature_ftp', 'FTP', True, True),
            ('feature_flickr', 'Flickr', True, False),
        ]
        self._tab_feature_cbs = {}
        for key, label, default, needs in specs:
            cb = QCheckBox(label)
            cb.setChecked(self.settings.value(key, default, type=bool))
            if needs and not avail:
                cb.setEnabled(False)
                cb.setToolTip(tr('Requires pyexiv2, which is not available.'))
            cb.toggled.connect(
                lambda checked, k=key: self._on_tab_feature_toggled(k, checked))
            v.addWidget(cb)
            self._tab_feature_cbs[key] = cb
        return box

    def _on_tab_feature_toggled(self, key, checked):
        self.settings.setValue(key, bool(checked))
        self.settings.sync()

    def _build_settings_tab(self):
        """One tab for everything configurable. Sections appear depending on
        the available features; the widgets keep their attribute names, so
        the code that reads them is untouched."""
        w = QWidget()
        outer = QVBoxLayout(w)
        inner = QWidget()
        lay = QVBoxLayout(inner)

        # Appearance: color scheme (system / light / dark), applied app-wide
        # via a Fusion palette and persisted.
        appearance = QGroupBox(tr('Appearance'))
        af = QFormLayout(appearance)
        # NoWheel: this page scrolls; the wheel must not flip the scheme.
        self.scheme_combo = NoWheelComboBox()
        self.scheme_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        for _code, _label in (('system', tr('system')), ('light', tr('light')),
                              ('dark', tr('dark'))):
            self.scheme_combo.addItem(_label, _code)
        self.scheme_combo.currentIndexChanged.connect(
            lambda _i: self._apply_color_scheme(self.scheme_combo.currentData()))
        af.addRow(tr('Color scheme:'), self.scheme_combo)
        # UI language: persisted immediately, applied at the NEXT start (no
        # live retranslation of an already-built window).
        self.language_combo = NoWheelComboBox()
        self.language_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        for _code, _name in UI_LANGUAGES:
            self.language_combo.addItem(_name, _code)
        _li = self.language_combo.findData(current_language())
        if _li >= 0:
            self.language_combo.setCurrentIndex(_li)
        self.language_combo.currentIndexChanged.connect(self._on_ui_language)
        _lang_row = QHBoxLayout()
        _lang_row.addWidget(self.language_combo)
        _lang_hint = QLabel(tr('(takes effect after a restart)'))
        _lang_hint.setStyleSheet('color: gray;')
        _lang_row.addWidget(_lang_hint)
        _lang_row.addStretch()
        af.addRow(tr('Language:'), _lang_row)
        lay.addWidget(appearance)

        lay.addWidget(self._build_tabs_group())

        # The MediaWiki / IPTC / FTP settings appear TWICE: in their
        # functional tab (primary widgets - QSettings persistence unchanged)
        # and here as linked mirrors (see widgets.link_line_edits & Co.).
        lay.addWidget(self._build_mw_account_group())
        lay.addWidget(self._build_mw_settings_mirror())
        if hasattr(self, 'iptc_inplace_cb'):
            lay.addWidget(self._build_iptc_settings_mirror())
            lay.addWidget(self._build_iptc_creator_mirror())
        if hasattr(self, 'ftp_host_edit'):
            lay.addWidget(self._build_ftp_settings_mirror())
        if hasattr(self, 'flickr_api_key_edit'):
            lay.addWidget(self._build_flickr_settings_mirror())
        if hasattr(self, '_cull_settings_box'):
            lay.addWidget(self._cull_settings_box)  # Culling preferences
        note = QLabel(tr('Settings are saved when the window is closed.'))
        lay.addWidget(note)
        lay.addStretch()
        # A full-window form stretches every line edit to absurd widths; cap
        # the content column and give short-content fields short widths.
        inner.setMaximumWidth(720)
        self._settings_apply_field_widths()
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(inner)
        rl.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(row)
        outer.addWidget(scroll)
        return w

    # ── Settings-tab mirrors ─────────────────────────────────────────────────
    # Second instances of the MediaWiki / IPTC / FTP settings, kept in sync
    # with the primaries in their functional tabs. Persistence stays with the
    # primaries; the mirrors write through (so e.g. changing the creator here
    # also refreshes the effective wikitext, via the primary's signals).

    def _build_mw_account_group(self):
        """MediaWiki login in the Settings page (0.12.6 layout): OAuth is THE
        sign-in; the BotPassword credentials moved into a sub-dialog behind a
        small button UNDER the OAuth row. The fields keep their object names
        and storage (QSettings scope 'Login' + keyring), so the login dialog
        and _save_settings stay in sync, and stored passwords are NOT
        deleted - BotPassword remains the consumer-independent fallback (a
        blocked OAuth consumer would invalidate every user's access tokens
        at once)."""
        box = QGroupBox(tr('MediaWiki account'))
        form = QFormLayout(box)
        self._login_settings = QSettings(APP_NAME, 'Login')
        # The fields exist always (login dialog + save/load read them); they
        # are shown inside the BotPassword sub-dialog.
        self.mw_user_edit = QLineEdit(
            self._login_settings.value('username', ''))
        self.mw_user_edit.setPlaceholderText(tr('e.g.') + ' Seewolf@Cammello')
        # BotPassword: NOT loaded here (0.12.12). Reading it at window build
        # was keychain prompt no. 1 of four AT EVERY START on macOS - before
        # the user did anything. The field starts empty and is filled the
        # moment the BotPassword dialog opens (_ensure_mw_password_loaded);
        # the LoginDialog loads its own copy anyway. The _mw_password_loaded
        # flag guards saving: an untouched empty field must never DELETE the
        # stored secret on close.
        self.mw_password_edit = QLineEdit()
        self.mw_password_edit.setEchoMode(QLineEdit.Password)
        self._mw_password_loaded = False
        # OAuth sign-in: only offered in builds with a registered consumer
        # (mw_oauth.CONSUMER_KEY filled in) - see mw_oauth module docstring.
        if mw_oauth.is_configured():
            self.oauth_status_label = QLabel()
            self.oauth_status_label.setWordWrap(True)
            oauth_btn = QPushButton(tr('Sign in with Wikimedia (OAuth)…'))
            oauth_btn.clicked.connect(self._on_oauth_login)
            self.oauth_remove_btn = QPushButton(tr('Remove authorization'))
            self.oauth_remove_btn.clicked.connect(self._on_oauth_remove)
            row = QHBoxLayout()
            row.addWidget(oauth_btn)
            row.addWidget(self.oauth_remove_btn)
            row.addStretch()
            form.addRow('OAuth:', self.oauth_status_label)
            form.addRow('', row)
            # 0.12.12: no _refresh_oauth_status() here. Reading the stored
            # tokens was keychain prompts 2 and 3 at every start; the status
            # is refreshed when the Settings window opens instead - the
            # moment someone can actually see it.
            self.oauth_status_label.setText('…')
        # Small, deliberately unobtrusive entry point UNDER OAuth (Harald):
        # opens the BotPassword sub-dialog.
        # 0.12.8: this edits the STORED bot-password credentials. Signing
        # in with them happens in the shared sign-in window, so the label
        # says what the button actually does.
        bp_btn = QPushButton(tr('Edit bot password…'))
        bp_btn.setToolTip(
            tr('Stores the bot password used by the fallback sign-in.'))
        bp_btn.clicked.connect(self._open_botpassword_dialog)
        bp_row = QHBoxLayout()
        bp_row.addWidget(bp_btn)
        bp_row.addStretch()
        form.addRow('', bp_row)
        apply_form_ratio(form)
        return box

    def _ensure_mw_password_loaded(self):
        """Fill the BotPassword field from the keyring on FIRST use (0.12.12).
        This is where the keychain prompt now happens - when the user opens
        the credentials dialog, not at application start."""
        if self._mw_password_loaded:
            return
        self.mw_password_edit.setText(
            credentials.load_mediawiki_password(
                self._login_settings, self.mw_user_edit.text()))
        self._mw_password_loaded = True

    def _open_botpassword_dialog(self):
        self._ensure_mw_password_loaded()
        """Sub-dialog with the BotPassword credentials (0.12.6). The field
        widgets are the persistent self.mw_user_edit/mw_password_edit, so
        everything that reads them keeps working; the dialog is just where
        they live now."""
        dlg = getattr(self, '_botpassword_dialog', None)
        if dlg is None:
            dlg = QDialog(self)
            dlg.setWindowTitle(tr('Bot password'))
            form = QFormLayout(dlg)
            form.addRow(tr('Username:'), self.mw_user_edit)
            form.addRow(tr('Password:'), self.mw_password_edit)
            grants = tr('Create one at Special:BotPasswords and log in with the '
                        'name shown there (e.g. YourName@Cammello). Required '
                        'grants: edit existing pages; create, edit and move pages; '
                        'upload new files; upload, replace and move files.')
            link = ('<a href="https://commons.wikimedia.org/wiki/'
                    'Special:BotPasswords">Special:BotPasswords</a>')
            grants_html = grants.replace('Special:BotPasswords', link)
            if credentials.backend_available():
                store = tr('The password is stored in your system keyring - leave '
                           'it empty to be asked at login instead.')
            else:
                store = tr('No system keyring available, so the password is stored '
                           'in plain text - leave it empty to be asked at login '
                           'instead.')
            note = QLabel(grants_html + '<br>' + store)
            note.setOpenExternalLinks(True)
            note.setTextFormat(Qt.RichText)
            note.setWordWrap(True)
            form.addRow('', note)
            buttons = QDialogButtonBox(QDialogButtonBox.Close)
            buttons.rejected.connect(dlg.reject)
            buttons.clicked.connect(lambda _b: dlg.close())
            form.addRow(buttons)
            dlg.resize(520, 260)
            self._botpassword_dialog = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _link_license_fields(self):
        """Keep the licence template and the P275 item on the same licence.

        Only PRESET picks propagate: choosing "CC BY 4.0" in one field sets
        the other field's value for CC BY 4.0. Typed text is left alone -
        someone entering an unusual template must not have their Q-number
        rewritten under them.
        """
        tmpl_to_qid = {t: q for _l, t, q in LICENSE_PRESETS}
        qid_to_tmpl = {q: t for _l, t, q in LICENSE_PRESETS}

        def _pair(source, target, mapping):
            def _handler(index):
                value = source.itemData(index)
                other = mapping.get(value)
                if other and target.text() != other:
                    target.setText(other)
            return _handler

        self.license_edit.activated.connect(
            _pair(self.license_edit, self.license_sdc_edit, tmpl_to_qid))
        self.license_sdc_edit.activated.connect(
            _pair(self.license_sdc_edit, self.license_edit, qid_to_tmpl))

    def _refresh_oauth_status(self):
        # The status widgets only exist when a consumer is configured (see
        # _build_mw_account_group). Since 0.12.8 this method is also called
        # from the shared sign-in path, which runs in builds without one -
        # so it has to tolerate their absence instead of raising.
        if not hasattr(self, 'oauth_status_label'):
            return
        token, secret = stored_oauth_tokens()
        if token and secret:
            user = self._login_settings.value('oauth_username', '') or '?'
            self.oauth_status_label.setText(
                tr('Authorized as {username}.').format(username=user))
            self.oauth_remove_btn.setEnabled(True)
        else:
            self.oauth_status_label.setText(tr('Not authorized.'))
            self.oauth_remove_btn.setEnabled(False)

    def _on_oauth_login(self):
        # 0.12.8: same window as the link on the MediaWiki page. force=True
        # because pressing this button IS the request to see it - the user
        # may want to re-authorize or switch account.
        self.open_signin_dialog(force=True)
        self._refresh_oauth_status()

    def _on_oauth_remove(self):
        clear_stored_oauth()
        self._refresh_oauth_status()
        self.status_bar.showMessage(tr('Authorization removed. To revoke it '
                                       'on the server side, visit '
                                       'Special:OAuthManageMyGrants.'), 8000)

    def _build_mw_settings_mirror(self):
        box = QGroupBox(tr('MediaWiki upload'))
        form = QFormLayout(box)
        self.author_mirror = mirror_line_edit(self.author_edit)
        self.creator_mirror = mirror_line_edit(self.creator_edit)
        _style_wd_field(self.creator_mirror, searchable=True)
        self._creator_mirror_suggest = WikidataSuggest(self.creator_mirror,
                                                       multi=False)
        self.source_mirror = mirror_line_edit(self.source_edit)
        self.permission_mirror = mirror_line_edit(self.permission_edit)
        # Dropdown in the module, dropdown in the Settings mirror.
        self.license_mirror = mirror_preset_combo(self.license_edit)
        self.license_sdc_mirror = mirror_preset_combo(self.license_sdc_edit)
        _style_wd_field(self.license_sdc_mirror)
        self.copyright_sdc_mirror = mirror_preset_combo(self.copyright_sdc_edit)
        _style_wd_field(self.copyright_sdc_mirror)
        self.other_fields_mirror = mirror_line_edit(self.other_fields_edit)
        self.gallery_prefix_mirror = mirror_line_edit(self.gallery_prefix_edit)
        self.timeout_mirror = mirror_line_edit(self.timeout_edit)

        form.addRow(tr('Author:'), self.author_mirror)
        form.addRow(tr('Creator (P170):'), self.creator_mirror)
        form.addRow(tr('Source:'), self.source_mirror)
        form.addRow(tr('Permission:'), self.permission_mirror)
        form.addRow(tr('License:'), self.license_mirror)
        form.addRow(tr('License (P275):'), self.license_sdc_mirror)
        form.addRow(tr('Copyright (P6216):'), self.copyright_sdc_mirror)
        form.addRow(tr('Other fields:'), self.other_fields_mirror)
        form.addRow(tr('Gallery prefix:'), self.gallery_prefix_mirror)
        form.addRow(tr('HTTP timeout (s):'), self.timeout_mirror)
        apply_form_ratio(form)
        return box

    def _build_iptc_settings_mirror(self):
        box = QGroupBox(tr('IPTC writing'))
        v = QVBoxLayout(box)
        self.iptc_inplace_mirror = mirror_checkbox(self.iptc_inplace_cb)
        v.addWidget(self.iptc_inplace_mirror)
        dir_row = QHBoxLayout()
        self.iptc_export_dir_mirror = mirror_line_edit(self.iptc_export_dir_edit)
        dir_row.addWidget(self.iptc_export_dir_mirror)
        browse = QPushButton('…')
        browse.setFixedWidth(30)
        # Writing into the MIRROR is enough: the link forwards to the primary.
        browse.clicked.connect(lambda: self._pick_dir_into(
            self.iptc_export_dir_mirror, tr('Export folder')))
        dir_row.addWidget(browse)
        v.addLayout(dir_row)
        return box

    def _build_iptc_creator_mirror(self):
        """Settings-tab mirror of the IPTC constant creator / rights / contact
        block (primaries live in the IPTC tab)."""
        from PyQt5.QtWidgets import QFormLayout
        box = QGroupBox(tr('Creator / rights / contact (same for all images)'))
        form = QFormLayout(box)
        for attr, _key, label, _contact in self._CONSTANT_UI:
            mirror = mirror_line_edit(getattr(self, attr))
            setattr(self, attr + '_mirror', mirror)
            form.addRow(tr(label) + ':', mirror)
        return box

    def _build_flickr_settings_mirror(self):
        box = QGroupBox(tr('Flickr account'))
        form = QFormLayout(box)
        self.flickr_api_key_mirror = mirror_line_edit(self.flickr_api_key_edit)
        form.addRow(tr('API key:'), self.flickr_api_key_mirror)
        self.flickr_api_secret_mirror = mirror_line_edit(
            self.flickr_api_secret_edit)
        form.addRow(tr('API secret:'), self.flickr_api_secret_mirror)
        note = QLabel(tr('The authorization steps are on the Flickr tab.'))
        form.addRow('', note)
        apply_form_ratio(form)
        return box

    def _build_ftp_settings_mirror(self):
        box = QGroupBox(tr('FTP server'))
        form = QFormLayout(box)
        self.ftp_protocol_mirror = mirror_combo(self.ftp_protocol_combo)
        form.addRow(tr('Protocol:'), self.ftp_protocol_mirror)
        self.ftp_host_mirror = mirror_line_edit(self.ftp_host_edit)
        form.addRow(tr('Host:'), self.ftp_host_mirror)
        self.ftp_port_mirror = mirror_line_edit(self.ftp_port_edit)
        form.addRow(tr('Port:'), self.ftp_port_mirror)
        self.ftp_user_mirror = mirror_line_edit(self.ftp_user_edit)
        form.addRow(tr('User:'), self.ftp_user_mirror)
        self.ftp_password_mirror = mirror_line_edit(self.ftp_password_edit)
        form.addRow(tr('Password:'), self.ftp_password_mirror)
        self.ftp_store_pw_mirror = mirror_checkbox(self.ftp_store_pw_cb)
        form.addRow('', self.ftp_store_pw_mirror)
        self.ftp_dir_mirror = mirror_line_edit(self.ftp_dir_edit)
        form.addRow(tr('Remote directory:'), self.ftp_dir_mirror)
        apply_form_ratio(form)
        return box


    def _build_about_tab(self):
        """About: name, tagline, links, license, components - the usual."""
        page = QWidget()
        page.setObjectName('aboutPage')   # dark background via ABOUT_STYLE
        outer = QVBoxLayout(page)
        outer.addStretch()
        icon_file = asset_path('icon.png')
        if os.path.exists(icon_file):
            logo = QLabel()
            logo.setPixmap(QPixmap(icon_file).scaled(
                128, 128, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            logo.setAlignment(Qt.AlignCenter)
            outer.addWidget(logo)
        title = QLabel(f'<h1>{APP_NAME}</h1>')
        title.setAlignment(Qt.AlignCenter)
        outer.addWidget(title)
        version = QLabel(tr('Version {version}').format(version=__version__))
        version.setAlignment(Qt.AlignCenter)
        outer.addWidget(version)
        tagline = QLabel(tr('A WikiPortraits tool by Harald Krichel'))
        tagline.setAlignment(Qt.AlignCenter)
        f = tagline.font()
        f.setPointSize(f.pointSize() + 2)
        tagline.setFont(f)
        outer.addWidget(tagline)

        deps = [f'Python {sys.version.split()[0]}', f'PyQt5 (Qt {QT_VERSION_STR})',
                'requests']
        for mod, name in ((iptc_mod.available(), 'pyexiv2'),):
            if mod:
                deps.append(name)
        links = QLabel(
            '<div align="center">'
            '<p><a style="color:#8ec2ff;" '
            'href="https://github.com/krichel89/Cammello">GitHub: '
            'krichel89/Cammello</a><br>'
            '<a style="color:#8ec2ff;" href="https://wikiportraits.org">'
            'WikiPortraits</a> · '
            '<a style="color:#8ec2ff;" href="https://commons.wikimedia.org/wiki/User:Seewolf">'
            'Commons: User:Seewolf</a> · '
            '<a style="color:#8ec2ff;" href="https://fotografie.krichel.de">fotografie.krichel.de'
            '</a></p>'
            '<p>' + tr('License:') + ' <a style="color:#8ec2ff;" href='
            '"https://creativecommons.org/publicdomain/zero/1.0/">CC0 1.0 '
            '(public domain)</a></p>'
            '<p style="color: #9fb3c8;">' + tr('Built with:') + ' '
            + ', '.join(deps) + '</p>'
            '</div>')
        links.setOpenExternalLinks(True)
        links.setTextInteractionFlags(Qt.TextBrowserInteraction)
        links.setAlignment(Qt.AlignCenter)
        outer.addWidget(links)
        outer.addStretch()
        return page

    def _open_page_dialog(self, key, widget, title, size=(760, 620)):
        """Show a former tab page as a modeless dialog (0.12.6).

        The widget is re-parented into a lazily created dialog and kept
        there; all outside references to the widget stay valid. Settings is
        large, so the dialog is resizable with a scroll area already inside
        the page itself where needed.
        """
        dlg = self._page_dialogs.get(key)
        if dlg is None:
            dlg = QDialog(self)
            dlg.setWindowTitle(title)
            lay = QVBoxLayout(dlg)
            lay.setContentsMargins(8, 8, 8, 8)
            lay.addWidget(widget)
            dlg.resize(*size)
            self._page_dialogs[key] = dlg
        widget.setVisible(True)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _open_settings_dialog(self):
        # Deferred from window build (0.12.12): the two token reads prompt
        # the macOS keychain, so they happen when the status becomes
        # visible - here - instead of at every start.
        self._refresh_oauth_status()
        self._open_page_dialog('settings', self._settings_tab_widget,
                               tr('Settings'))

    def _open_log_dialog(self):
        self._open_page_dialog('log', self._log_tab, tr('Log'),
                               size=(820, 520))

    def _open_about_dialog(self):
        self._open_page_dialog('about', self._about_tab_widget,
                               tr('About Cammello'), size=(560, 480))

    def _clear_base_description(self):
        """Empties the base description (expert text AND structured editor)
        after confirmation - the live sync then updates every row."""
        if QMessageBox.question(
                self, tr('Clear base description'),
                tr('Really clear the whole base description? This updates '
                   'the wikitext of every file.'),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No) != QMessageBox.Yes:
            return
        self.base_text_edit.setPlainText('')
        self.base_struct.load('')
        # Other templates belongs to the base description now (0.12.6):
        # switching to the next event clears it too.
        self.other_templates_edit.setText('')
        self.logger.info('Base description cleared.')

    def _on_ui_language(self, _index):
        """Persist the UI language; it is applied at the next start."""
        self.settings.setValue('ui_language', self.language_combo.currentData())
        self.settings.sync()
        if hasattr(self, 'status_bar'):
            self.status_bar.showMessage(
                tr('The language change takes effect after a restart.'), 6000)

    def _pick_dir_into(self, line_edit, title):
        d = QFileDialog.getExistingDirectory(self, title)
        if d:
            line_edit.setText(d)

    def _settings_apply_field_widths(self):
        """Content-appropriate widths for fields whose values are short:
        QIDs, ports, timeouts - and combo boxes, which a QFormLayout
        otherwise stretches across the whole column (a full-width dropdown
        for "ftp" looked broken). Free-text fields keep the column width."""
        short = [getattr(self, n, None) for n in (
            'creator_edit', 'copyright_sdc_edit', 'license_sdc_edit',
            'creator_mirror', 'copyright_sdc_mirror', 'license_sdc_mirror')]
        for e in short:
            if e is not None:
                e.setMaximumWidth(180)          # QIDs: Q18199165 fits easily
        for name, wpx in (('ftp_port_edit', 90), ('timeout_edit', 70),
                          ('ftp_port_mirror', 90), ('timeout_mirror', 70),
                          # Combos: room for the widest entry + indicator.
                          ('scheme_combo', 130),
                          ('language_combo', 140),
                          ('ftp_protocol_combo', 110),
                          ('ftp_protocol_mirror', 110),
                          ('cull_labelset_combo', 110),
                          ('cull_pair_combo', 150)):
            e = getattr(self, name, None)
            if e is not None:
                e.setMaximumWidth(wpx)

    def _apply_color_scheme(self, scheme, repolish=True):
        """system: the palette/style Qt started with; light/dark: an explicit
        Fusion palette. The input stylesheet switches to its matching variant
        (see constants.input_style), and the widget tree is repolished on a
        user-triggered switch."""
        app = QApplication.instance()
        # Snapshot ONCE per application, not per window: a second window
        # created while 'dark' is active would otherwise mistake the dark
        # palette for the system one.
        global _SYSTEM_APPEARANCE
        if _SYSTEM_APPEARANCE is None:
            _SYSTEM_APPEARANCE = (QPalette(app.palette()),
                                  app.style().objectName())
        self._system_palette, self._system_style = _SYSTEM_APPEARANCE
        # Idempotent: QApplication.setStyle DESTROYS the previous style
        # object app-wide; doing that on every window construction (the
        # settings restore runs in __init__) crashed reliably. Only a real
        # scheme CHANGE touches the application.
        if scheme == _APPLIED_SCHEME[0]:
            if hasattr(self, '_cull_delegate'):
                self._cull_delegate.set_dark(self._is_dark_scheme_for(scheme))
            return
        _APPLIED_SCHEME[0] = scheme
        def _ensure_style(name):
            # setStyle destroys the previous QStyle app-wide; only touch it
            # when the style actually differs.
            if app.style().objectName().lower() != name.lower():
                app.setStyle(name)

        if scheme == 'dark':
            _ensure_style('Fusion')
            pal = QPalette()
            base, text = QColor('#2b2b2b'), QColor('#e8e8e8')
            pal.setColor(QPalette.Window, QColor('#353535'))
            pal.setColor(QPalette.WindowText, text)
            pal.setColor(QPalette.Base, base)
            pal.setColor(QPalette.AlternateBase, QColor('#3c3c3c'))
            pal.setColor(QPalette.Text, text)
            pal.setColor(QPalette.Button, QColor('#3c3c3c'))
            pal.setColor(QPalette.ButtonText, text)
            pal.setColor(QPalette.ToolTipBase, base)
            pal.setColor(QPalette.ToolTipText, text)
            pal.setColor(QPalette.Highlight, QColor('#2a6db0'))
            pal.setColor(QPalette.HighlightedText, QColor('white'))
            pal.setColor(QPalette.Disabled, QPalette.Text, QColor('#808080'))
            pal.setColor(QPalette.Disabled, QPalette.ButtonText,
                         QColor('#808080'))
            app.setPalette(pal)
        elif scheme == 'light':
            _ensure_style('Fusion')
            app.setPalette(app.style().standardPalette())
        else:
            # "System": follow the platform - EXCEPT on Windows.
            #
            # 0.12.7 (Harald, Windows dark mode): disabled menu entries were
            # still drawn as if enabled, while macOS was fine after the
            # 0.12.6 fix. Reason: the native "windowsvista" style paints menu
            # items itself and honours neither the stylesheet colour nor,
            # reliably, the palette's Disabled group. Fusion does both. The
            # PALETTE is still the system one, so the app keeps the system's
            # colours (dark stays dark) - only the painter changes.
            if sys.platform.startswith('win'):
                _ensure_style('Fusion')
            else:
                _ensure_style(self._system_style)
            pal = QPalette(self._system_palette)
            # Some platform palettes leave the Disabled group equal to the
            # active one; then nothing looks greyed no matter who paints.
            # Derive a grey that has contrast against the actual window
            # colour instead of hard-coding one for a light background.
            win = pal.color(QPalette.Window)
            grey = QColor('#909090') if win.lightness() < 128 else QColor('#808080')
            for role in (QPalette.Text, QPalette.ButtonText,
                         QPalette.WindowText):
                pal.setColor(QPalette.Disabled, role, grey)
            app.setPalette(pal)
        # Inputs follow the scheme: re-apply the matching stylesheet variant
        # on the window (dialogs pick it up at construction).
        dark = self._is_dark_scheme_for(scheme)
        set_current_input_style(dark)
        QApplication.instance().setStyleSheet(app_style())
        refresh_wd_fields()   # WD fields carry their own (border) stylesheet
        # A style/palette change does not repolish existing widgets; without
        # this pass, parts of the UI kept the previous scheme ("switching is
        # not clean"). Restricted to THIS window's tree: app.allWidgets()
        # also touches foreign/half-torn-down widgets (segfault in tests
        # with several windows); dialogs pick the active variant at
        # construction anyway.
        # Repolishing mid-construction crashed (half-built widget tree);
        # at startup the palette propagates by itself, the pass is only
        # needed for a user-triggered switch on a finished window.
        if repolish:
            for wdg in [self] + self.findChildren(QWidget):
                try:
                    wdg.style().unpolish(wdg)
                    wdg.style().polish(wdg)
                    wdg.update()
                except RuntimeError:
                    pass                  # C++ side already gone
        # The culling delegate adapts its frames.
        if hasattr(self, '_cull_delegate'):
            self._cull_delegate.set_dark(dark)
            self.cull_strip.viewport().update()

    def _is_dark_scheme(self):
        """Effective darkness: explicit choice, or the system palette."""
        choice = self.scheme_combo.currentData() if hasattr(
            self, 'scheme_combo') else 'system'
        return self._is_dark_scheme_for(choice)

    def _is_dark_scheme_for(self, choice):
        if choice in ('light', 'dark'):
            return choice == 'dark'
        pal = QApplication.instance().palette()
        return pal.color(QPalette.Window).lightness() < 128

    def _on_tab_changed(self, _index):
        # Entering the IPTC tab: sync its file list with the main table.
        if self.tabs.currentWidget() is getattr(self, '_iptc_tab_widget', None):
            self._iptc_refresh_list()
        # Same for the merged FTP / Flickr file list.
        if self.tabs.currentWidget() is getattr(self, '_ftpflickr_tab_widget',
                                                None):
            self._ftp_refresh_list()
        # Entering the Culling tab: keyboard must land on the tab widget.
        if self.tabs.currentWidget() is getattr(self, '_cull_tab_widget', None):
            self._cull_tab_widget.setFocus()

    def _build_log_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        top = QHBoxLayout()
        self.verbose_cb = QCheckBox(tr('Verbose logging'))
        self.verbose_cb.stateChanged.connect(self._toggle_verbose)
        clear_log_btn = QPushButton(tr('Clear'))
        clear_log_btn.clicked.connect(lambda: self.log_view.clear())
        copy_log_btn = QPushButton(tr('Copy'))
        copy_log_btn.clicked.connect(self._copy_log)
        open_file_btn = QPushButton(tr('Open log file'))
        open_file_btn.clicked.connect(self._open_log_file)
        open_dir_btn = QPushButton(tr('Open folder'))
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
        # QFontDatabase, not a family name: 'Monospace' exists on Linux but
        # not on macOS, where Qt then walks all families to find a substitute
        # (and logs a warning). The system fixed font is right everywhere.
        from PyQt5.QtGui import QFontDatabase
        _mono = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        _mono.setPointSize(9)
        self.log_view.setFont(_mono)
        self.log_view.document().setMaximumBlockCount(5000)
        layout.addWidget(self.log_view)

        path_label = QLabel(tr('Log file: {path}').format(path=self.log_path))
        path_label.setStyleSheet('color: gray; font-size: 11px;')
        path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(path_label)

        return page

    # ── Log helpers ──────────────────────────────────────────────────────────


# ── Entry point ────────────────────────────────────────────────────────────────


# Names accepted by the hidden --enable-tab / --disable-tab switches.
_FEATURE_TABS = ('culling', 'iptc', 'ftp', 'flickr')


def _apply_feature_cli(argv):
    """Hidden per-tab switches: --disable-tab NAME / --enable-tab NAME
    (NAME: culling | iptc | ftp; repeatable). The choice is PERSISTED in
    QSettings and the app then starts normally, so the flag is needed only
    once. Returns argv with the consumed arguments removed. Unknown names
    are reported on stderr and ignored."""
    settings = QSettings(APP_NAME, 'Main')
    out = [argv[0]]
    i = 1
    while i < len(argv):
        arg = argv[i]
        if arg in ('--disable-tab', '--enable-tab') and i + 1 < len(argv):
            name = argv[i + 1].strip().lower()
            if name in _FEATURE_TABS:
                settings.setValue(f'feature_{name}', arg == '--enable-tab')
                print(f'Cammello: {name} tab '
                      f'{"enabled" if arg == "--enable-tab" else "disabled"}.',
                      file=sys.stderr)
            else:
                print(f'Cammello: unknown tab "{name}" for {arg} '
                      f'(expected one of: {", ".join(_FEATURE_TABS)}).',
                      file=sys.stderr)
            i += 2
            continue
        out.append(arg)
        i += 1
    settings.sync()
    return out


def main():
    argv = _apply_feature_cli(sys.argv)
    # UI language BEFORE any window construction: saved choice, else the
    # system locale if it is one of the five UI languages, else English.
    _s = QSettings(APP_NAME, 'Main')
    set_language(_s.value('ui_language', '')
                 or default_language_from_locale(QLocale.system().name()))
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    # Slightly larger UI font (0.12.7, Harald). Before any window exists, so
    # every size hint is computed with the final font.
    apply_ui_font(app)
    # Window/Dock icon, if an icon file is bundled (see assets/README.md).
    _icon_file = asset_path('icon.png')
    if os.path.exists(_icon_file):
        app.setWindowIcon(QIcon(_icon_file))

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
