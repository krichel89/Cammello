"""Native menu bar (0.12.3).

QMainWindow.menuBar() is native on both platforms without extra work: on
macOS Qt puts it in the system menu bar at the top of the screen, on Windows
and Linux it is drawn in the window. Actions carrying a MenuRole (About /
Preferences / Quit) are moved into the application menu by macOS itself.

The menu bar replaces the TAB BAR as the way to switch sections: the pages
themselves stay in the existing QTabWidget (it remains the page container,
so every feature switch, mixin and `self.tabs.currentWidget()` check keeps
working), but its bar is hidden and the View menu switches pages instead,
with Cmd/Ctrl+1..9 shortcuts.

Everything here is defensive: a page or handler that a feature switch turned
off is simply not offered. No action is created for a handler the window
does not have, so disabled tabs cannot produce dead menu entries.
"""
from PyQt5.QtWidgets import QAction, QActionGroup
from PyQt5.QtGui import QKeySequence
from PyQt5.QtCore import Qt

from .i18n import tr


class MenusMixin:
    """Builds the menu bar. Mixed into MainWindow; call _build_menus() at
    the end of _build_ui(), once every tab/page exists."""

    # ── helpers ──────────────────────────────────────────────────────────

    def _act(self, menu, text, handler, shortcut=None, tip=None, role=None):
        """Create + add an action, but ONLY if the handler exists.

        Returns the QAction, or None when the window has no such handler
        (feature switched off) - callers may ignore the result.
        """
        if isinstance(handler, str):
            if not hasattr(self, handler):
                return None
            handler = getattr(self, handler)
        elif handler is None:
            return None
        action = QAction(text, self)
        if shortcut is not None:
            action.setShortcut(shortcut)
        if tip:
            action.setStatusTip(tip)
        if role is not None:
            action.setMenuRole(role)
        action.triggered.connect(handler)
        menu.addAction(action)
        return action

    def _selected_table_paths(self):
        """Paths of the selected rows in the MediaWiki table (empty when the
        table does not exist or nothing is selected)."""
        table = getattr(self, 'table', None)
        if table is None:
            return []
        rows = sorted({i.row() for i in table.selectedIndexes()})
        paths = []
        for r in rows:
            item = table.item(r, self.COL_FILENAME)
            fp = item.data(Qt.UserRole) if item else None
            if fp:
                paths.append(fp)
        return paths

    def _mark_selected(self, mark):
        paths = self._selected_table_paths()
        if paths:
            self._set_channel_mark(paths, mark)

    def _scope(self, page, *actions):
        """Register actions as belonging to a page ('culling'/'mediawiki');
        they are enabled only while that page is shown."""
        self._menu_scope[page].extend(a for a in actions if a is not None)

    def _update_menu_state(self, _index=None):
        """Grey out actions that do not apply to the current page (0.12.6).
        Disabled actions also stop firing their plain-key shortcuts, so the
        digit keys never rate images invisibly from another page."""
        current = self.tabs.currentWidget()
        on_cull = current is getattr(self, '_cull_tab_widget', None)
        on_mw = current is getattr(self, '_mw_tab_widget', None)
        for a in self._menu_scope['culling']:
            a.setEnabled(on_cull)
        for a in self._menu_scope['mediawiki']:
            a.setEnabled(on_mw)

    def _menu_open_folder(self):
        """File > Open folder: the folder opens in the culling page, so show
        that page first (Harald: 'Ordner öffnen soll den Culling-Tab
        öffnen')."""
        page = getattr(self, '_cull_tab_widget', None)
        if page is not None:
            self._show_page(page)
        self._cull_open_folder()

    def _show_page(self, widget):
        idx = self.tabs.indexOf(widget)
        if idx >= 0:
            self.tabs.setCurrentIndex(idx)

    # ── the menu bar ─────────────────────────────────────────────────────

    def _build_menus(self):
        bar = self.menuBar()
        bar.clear()
        # Actions that only make sense on ONE page are collected here and
        # greyed out (not hidden - hiding reshuffles the menu every switch)
        # on the other pages by _update_menu_state.
        self._menu_scope = {'culling': [], 'mediawiki': []}
        # macOS only merges roles correctly for a non-native-looking bar when
        # it is the window's own menu bar - which menuBar() gives us.
        self._build_file_menu(bar.addMenu(tr('&File')))
        self._build_metadata_menu(bar.addMenu(tr('&Metadata')))
        self._build_view_menu(bar.addMenu(tr('&View')))
        upload = bar.addMenu(tr('&Upload'))
        self._build_upload_menu(upload)
        self._build_help_menu(bar.addMenu(tr('&Help')))
        self.tabs.currentChanged.connect(self._update_menu_state)
        self._update_menu_state(self.tabs.currentIndex())
        # The Lightroom-style module strip lists the pages that exist NOW
        # (feature switches applied), so it is built here, after every
        # addTab has run.
        if hasattr(self, 'module_strip'):
            self.module_strip.rebuild()
        # The module strip is THE visible page picker now; the Qt tab bar
        # must stay hidden so it does not double up (0.12.6 bug).
        self.tabs.tabBar().setVisible(False)

    def _build_file_menu(self, menu):
        # Open folder works from ANY page and takes you to Culling - the
        # folder is opened there, so the app should show it (0.12.6).
        if hasattr(self, '_cull_open_folder'):
            self._act(menu, tr('&Open folder…'), self._menu_open_folder,
                      QKeySequence.Open,
                      tr('Open a folder of images for culling.'))
        self._scope('culling', self._act(
            menu, tr('&Reload folder'), '_cull_reload_folder',
            QKeySequence.Refresh,
            tr('Read the current folder again from disk.')))
        menu.addSeparator()
        self._scope('mediawiki', self._act(
            menu, tr('&Add files…'), 'add_files',
            QKeySequence('Ctrl+Shift+O'),
            tr('Add image files to the upload list.')))
        self._scope('culling', self._act(
            menu, tr('&Save selection to folder…'), '_cull_to_folder',
            QKeySequence('Ctrl+Shift+S'),
            tr('Copy the selected images to a folder.')))
        menu.addSeparator()
        # List management lives with the other file-level commands (0.12.6):
        # these change WHICH files are in the upload list, not their metadata.
        self._scope('mediawiki', self._act(
            menu, tr('Remove &selected'), 'remove_selected',
            QKeySequence.Delete))
        self._scope('mediawiki', self._act(
            menu, tr('C&lear list'), 'clear_all',
            tip=tr('Remove every file from the list.')))
        menu.addSeparator()
        # macOS moves this into the application menu automatically.
        # NoRole on purpose (0.12.5): with PreferencesRole macOS moves the
        # entry into the application menu - which, when Cammello runs from
        # source, is called "Python", so the entry looked lost. Keeping it
        # here means it is always where the user put the cursor.
        self._act(menu, tr('&Settings…'), '_open_settings_dialog',
                  QKeySequence.Preferences, None, QAction.NoRole)
        self._act(menu, tr('&Quit'), self.close, QKeySequence.Quit,
                  None, QAction.QuitRole)

    def _build_metadata_menu(self, menu):
        """Everything that changes METADATA of images: rating, colour label,
        reject, rename, channel mark, base description. List management
        (remove/clear) lives in the File menu."""
        self._scope('mediawiki', self._act(
            menu, tr('&Rename…'), '_rename_selected',
            QKeySequence('F2'),
            tr('Rename the selected files for Commons.')))
        # Rating / colour actions mirror the culling keyboard (0-5, X, 6-9,
        # M toggles the digits to colours - purple is digit 5 in that mode).
        # Rating and colour actions are shown with their keyboard letter
        # BESIDE the entry (like Lightroom: "3" next to "★★★"), but the
        # letter is NOT a QAction shortcut.  A Qt shortcut fires BEFORE
        # keyPressEvent and would bypass the M-mode toggle entirely (the
        # 0-5 keys switch between stars and colours via _cull_key, which
        # checks _cull_number_mode). Only X (Rejected) stays a real
        # shortcut because it has no dual mode.
        self._cull_menu_actions = []
        if hasattr(self, '_cull_set_rating'):
            menu.addSeparator()
            rating = menu.addMenu(tr('&Rating'))
            self._cull_menu_actions.append(rating.menuAction())
            for n in range(0, 6):
                label = (tr('No stars') if n == 0
                         else '★' * n)
                # Show the key letter as right-aligned text instead of
                # QKeySequence — purely cosmetic, no handler.
                a = self._act(rating, f'{label}\t{n}',
                              (lambda _c=False, n=n:
                               self._cull_set_rating(n)))
                self._cull_menu_actions.append(a)
            a = self._act(rating, tr('Rejected'),
                          lambda: self._cull_set_rating(-1),
                          QKeySequence('X'))
            self._cull_menu_actions.append(a)
        if hasattr(self, '_cull_set_label'):
            colors = menu.addMenu(tr('&Color label'))
            colors.menuAction().setStatusTip(
                tr('M toggles the digit keys between stars and colors; in '
                   'color mode 5 is purple.'))
            self._cull_menu_actions.append(colors.menuAction())
            names = [(tr('Red'), 0, '6'), (tr('Yellow'), 1, '7'),
                     (tr('Green'), 2, '8'), (tr('Blue'), 3, '9'),
                     (tr('Purple'), 4, None)]
            for name, idx, key in names:
                # 6-9 are likewise cosmetic labels; the keys reach
                # _cull_key directly.
                label = f'{name}\t{key}' if key else name
                a = self._act(colors, label,
                              (lambda _c=False, i=idx:
                               self._cull_set_label(i)))
                self._cull_menu_actions.append(a)
            a = self._act(colors, tr('No label'),
                          lambda: self._cull_set_label(None))
            self._cull_menu_actions.append(a)
        self._scope('culling', *self._cull_menu_actions)
        menu.addSeparator()
        self._scope('mediawiki', self._act(
            menu, tr('Clear &base description'), '_clear_base_description'))
        if hasattr(self, '_set_channel_mark'):
            menu.addSeparator()
            marks = menu.addMenu(tr('Channel &mark'))
            from . import channels
            self._scope('mediawiki', marks.menuAction())
            self._act(marks, tr('Mark for Commons (CC)'),
                      lambda: self._mark_selected(channels.MARK_COMMONS))
            self._act(marks, tr('Mark for commercial use (FTP/Flickr)'),
                      lambda: self._mark_selected(channels.MARK_COMMERCIAL))
            self._act(marks, tr('Remove channel mark'),
                      lambda: self._mark_selected(None))

    def _build_view_menu(self, menu):
        # Only the WORKING sections get a page entry with Cmd/Ctrl+1..n.
        # Settings lives in the File/application menu, Log and About in Help -
        # they are not places you switch to while working.
        self._page_actions = []
        group = QActionGroup(self)
        group.setExclusive(True)
        n = 0
        for i in range(self.tabs.count()):
            widget = self.tabs.widget(i)
            action = QAction(self.tabs.tabText(i), self)
            action.setCheckable(True)
            action.setData(i)
            n += 1
            if n <= 9:
                action.setShortcut(QKeySequence(f'Ctrl+{n}'))
            action.triggered.connect(
                lambda _checked, w=widget: self._show_page(w))
            group.addAction(action)
            menu.addAction(action)
            self._page_actions.append(action)
        if self._page_actions:
            self._sync_page_actions(self.tabs.currentIndex())
            self.tabs.currentChanged.connect(self._sync_page_actions)
        menu.addSeparator()
        # Plain letters, matching the culling keyboard (no modifier): Qt's
        # text widgets claim printable keys via ShortcutOverride, so typing
        # an "f" into a field still types it.
        self._scope('culling', self._act(
            menu, tr('&Loupe view'), '_cull_loupe_view', QKeySequence('E'),
            tr('Single image, fitted to the window (E).')))
        self._scope('culling', self._act(
            menu, tr('&Grid view'), '_cull_toggle_grid', QKeySequence('G'),
            tr('Grid view: thumbnails instead of the large image (G).')))
        self._scope('culling', self._act(
            menu, tr('&Fullscreen'), '_cull_toggle_fullscreen',
            QKeySequence('F')))
        menu.addSeparator()
        self._scope('culling', self._act(
            menu, tr('Zoom &in'), '_cull_zoom_in', QKeySequence.ZoomIn))
        self._scope('culling', self._act(
            menu, tr('Zoom &out'), '_cull_zoom_out', QKeySequence.ZoomOut))

    def _sync_page_actions(self, index):
        """Tick the entry that belongs to the page now shown (the entries are
        a subset of the pages, so match on the stored tab index)."""
        for action in getattr(self, '_page_actions', []):
            if action.data() == index:
                action.setChecked(True)
                return

    def _build_upload_menu(self, menu):
        self._act(menu, tr('&Log in…'), 'do_login',
                  tip=tr('Sign in to Wikimedia Commons.'))
        self._act(menu, tr('&Test connection'), 'test_connection')
        menu.addSeparator()
        self._scope('mediawiki', self._act(
            menu, tr('&Upload to Commons'), 'start_upload',
            QKeySequence('Ctrl+U')))
        self._scope('culling', self._act(
            menu, tr('Add culling selection to &tabs'), '_cull_apply',
            QKeySequence('Ctrl+Shift+A')))

    def _build_help_menu(self, menu):
        # About and the Log live here and deliberately carry NO shortcut -
        # they are looked up, not used in the flow of work.
        # NoRole for the same reason as Settings above: AboutRole hides the
        # entry in the (possibly "Python"-named) application menu.
        self._act(menu, tr('&About Cammello'), '_open_about_dialog',
                  None, None, QAction.NoRole)
        menu.addSeparator()
        self._act(menu, tr('Show &log'), '_open_log_dialog')
        self._act(menu, tr('Open &log file'), '_open_log_file')
        self._act(menu, tr('Open log &folder'), '_open_log_folder')
        self._act(menu, tr('&Copy log'), '_copy_log')
