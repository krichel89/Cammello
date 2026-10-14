"""Part of MainWindow, split out as a mixin. See main_window.py for the class
that combines these mixins. Mixins are plain classes holding grouped methods;
they rely on attributes created in MainWindow.__init__ / _build_* and on the
COL_* / COLS class attributes defined on MainWindow."""
import os
import re
import sys
import traceback
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QPushButton, QLabel, QLineEdit,
    QTextEdit, QFileDialog, QMessageBox, QProgressBar, QSplitter,
    QGroupBox, QFormLayout, QHeaderView, QAbstractItemView, QDialog,
    QDialogButtonBox, QCheckBox, QStatusBar, QTabWidget, QPlainTextEdit,
    QStyledItemDelegate, QComboBox, QScrollArea, QCompleter,
    QListWidgetItem, QMenu, QProgressDialog)
from PyQt5.QtCore import (Qt, QThread, pyqtSignal, QSettings, QObject, QUrl,
                          QSize, QRegExp, QTimer, QStringListModel, QEvent,
                          QItemSelectionModel)
from PyQt5.QtGui import (QPixmap, QImage, QFont, QDesktopServices, QIcon,
                         QImageReader, QRegExpValidator, QColor, QBrush)
from .constants import *
from .i18n import tr
from .constants import __version__, _WD_SINGLE_RE, _WD_LIST_RE
from .logging_setup import *
from .sdc import *
from .sdc import _strip_sd_lines
from .exif import *
from .api import *
from .workers import *
from .wikidata import *
from .wikidata import _style_wd_field
from .wikidata import (fetch_caption_entities, category_suggestions,
                       fetch_in_background, wd_error_text)
from .constants import APP_NAME, _caption_extra_langs
from .widgets import *
from .widgets import (stored_oauth2_tokens, store_oauth2_tokens,
                      clear_stored_oauth2,
                      NamesFromDescriptionDialog, GenerateCaptionsDialog)
from .editors import *
from .i18n import current_language
from . import sdc
from . import culling
from . import captions as captions_mod
from . import mw_oauth2
from . import channels
from . import previews
from . import geo


def _with_channel_dot(icon, color_hex, dot=12):
    """Return the icon with a small colored dot drawn into its top-left
    corner. Falls back to the plain dot when there is no thumbnail yet."""
    from PyQt5.QtGui import QPixmap, QPainter
    if icon is None or icon.isNull():
        return _channel_dot_icon(color_hex)
    sizes = icon.availableSizes()
    pm = QPixmap(icon.pixmap(sizes[0] if sizes else QSize(96, 64)))
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setBrush(QColor(color_hex))
    p.setPen(QColor('#00000080'))
    p.drawEllipse(2, 2, dot, dot)
    p.end()
    return QIcon(pm)


def _channel_dot_icon(color_hex, size=12):
    """A tiny colored dot as a QIcon for the file table / IPTC list."""
    from PyQt5.QtGui import QPixmap, QPainter
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setBrush(QColor(color_hex))
    p.setPen(Qt.NoPen)
    p.drawEllipse(1, 1, size - 2, size - 2)
    p.end()
    return QIcon(pm)


class MWFilesMixin:
    # ── ONE place to sign in (0.12.8) ────────────────────────────────────
    #
    # Until 0.12.7 there were two doors with different rooms behind them:
    # the "not signed in" link on the MediaWiki page called do_login(),
    # which fell through to the BOT PASSWORD dialog when no OAuth token was
    # stored, while Settings offered the OAUTH dialog. A user who had never
    # authorized was therefore sent down the fallback path by the more
    # prominent of the two entry points (Harald, 0.12.7 testing).
    #
    # Both doors now open open_signin_dialog(). The dialog itself carries
    # the bot-password fallback, so Settings keeps only the status and
    # "remove authorization".

    def open_signin_dialog(self, force=False):
        """Sign in, showing the shared sign-in window when one is needed.

        force=True always shows the window - that is what the Settings
        button wants (re-authorize, switch account). With force=False (the
        link, the Login button, an upload without a session) an existing
        authorization signs in silently: making the user confirm a window
        that only says "you are already authorized" would be a step
        backwards from 0.12.7.
        """
        # 0.18.22: the gate is the OAuth 2.0 client, not the old 1.0a
        # consumer key. It used to be mw_oauth.is_configured(), which meant
        # removing 1.0a would have switched OAuth 2 off with it (QK finding
        # of 2026-08-07).
        if mw_oauth2.is_configured():
            access, refresh = stored_oauth2_tokens()
            if access and not force:
                self._login_with_stored_oauth2(access)
                return
            dlg = OAuthLoginDialog(self)
            result = dlg.exec()
            if getattr(dlg, 'use_botpassword', False):
                self._login_with_botpassword()
                return
            if result != QDialog.Accepted:
                return
            # Authorizing is not the same as being signed in: without this
            # the user would have to press Login again after the browser
            # round-trip.
            access, refresh = stored_oauth2_tokens()
            if access:
                self._login_with_stored_oauth2(access)
            if hasattr(self, '_refresh_oauth_status'):
                self._refresh_oauth_status()
            return
        # No consumer in this build: the bot password IS the way in.
        self._login_with_botpassword()

    def _login_with_stored_oauth2(self, access):
        """Sign in with the stored OAuth 2.0 access token (0.17.0).

        The refresher hands api.py a fresh token when the four-hour expiry
        strikes mid-session: it renews via the CURRENT stored refresh
        token and persists the ROTATED pair the server answers with -
        keeping the old one would kill the sign-in on the second renewal.
        """
        def _refresher():
            from . import mw_oauth2
            _cur, cur_refresh = stored_oauth2_tokens()
            if not cur_refresh:
                return None
            payload = mw_oauth2.refresh_tokens(cur_refresh)
            store_oauth2_tokens(payload['access_token'],
                                payload.get('refresh_token', cur_refresh))
            return payload['access_token']

        s = QSettings(APP_NAME, 'Login')
        api_url = (s.value('api_url', '')
                   or 'https://commons.wikimedia.org/w/api.php')
        username = s.value('oauth_username', '') or 'OAuth'
        self._start_login_worker(api_url, username, '',
                                 bearer_token=access,
                                 bearer_refresher=_refresher)

    def _login_with_botpassword(self):
        dlg = LoginDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        api_url, username, password = dlg.get_credentials()
        self._start_login_worker(api_url, username, password)

    def do_login(self):
        """Kept as the name every caller already uses (link, Login button,
        the menu entry, an upload without a session)."""
        self.open_signin_dialog()

    def _set_login_state(self, state, username=''):
        """One place for the login label (0.12.6). 'out' renders a clickable
        link straight to the login; 'busy' and 'in' are plain text."""
        if state == 'in':
            self.login_label.setText(
                f'<span style="color:#2a7;">✓ {username}</span>')
        elif state == 'busy':
            self.login_label.setText(
                '<span style="color:orange;">' + tr('Logging in…') + '</span>')
        else:
            self.login_label.setText(
                '<a href="#login" style="color:#d33;">'
                + tr('Not logged in – sign in') + '</a>')

    def _start_login_worker(self, api_url, username, password,
                            oauth_token=None, oauth_secret=None,
                            bearer_token=None, bearer_refresher=None):
        self.login_btn.setEnabled(False)
        self._set_login_state('busy')
        # Remembered for _on_login_failure: a dead stored token is answered
        # with a new authorization, not with a raw HTTP error.
        self._login_used_bearer = bool(bearer_token)

        self._login_worker = LoginWorker(
            api_url, username, password, self._get_timeout(), self.logger,
            oauth_token=oauth_token, oauth_secret=oauth_secret,
            bearer_token=bearer_token, bearer_refresher=bearer_refresher)
        self._login_worker.success.connect(
            lambda api: self._on_login_success(api, username))
        self._login_worker.failure.connect(self._on_login_failure)
        self._login_worker.start()

    def _on_login_success(self, api, username):
        self.api = api
        self._login_retrying = False
        self.login_btn.setEnabled(True)
        self.test_btn.setEnabled(True)
        self._set_login_state('in', username)
        self.status_bar.showMessage(tr('Logged in as {username}').format(username=username))
        # 0.14.2: a resume that had to log in first continues by itself now,
        # instead of making the user find the menu entry again.
        if getattr(self, '_resume_after_login', False):
            self._resume_after_login = False
            self.resume_upload()

    def _on_login_failure(self, error_msg):
        self.login_btn.setEnabled(True)
        self._set_login_state('out')
        # 0.18.32: the stored OAuth token was rejected (HTTP 401, e.g. "Jwt
        # is expired") and could not be renewed - the refresh token is dead
        # too (revoked, or unused for too long). Showing the raw error left
        # the user stuck, because every further Login pressed the same dead
        # token again. Forget the pair and open the authorization window.
        if (getattr(self, '_login_used_bearer', False)
                and not getattr(self, '_login_retrying', False)
                and ('401' in error_msg or 'expired' in error_msg.lower())):
            self.logger.warning('Stored OAuth token rejected and not '
                                'renewable (%s) - asking for a new '
                                'authorization.', error_msg[:200])
            clear_stored_oauth2()
            self._login_used_bearer = False
            self.status_bar.showMessage(
                tr('The saved sign-in has expired - please authorize '
                   'again.'), 8000)
            # Stays set until a login succeeds: a FRESH token that is
            # rejected too must show its error, not loop the dialog.
            self._login_retrying = True
            self.open_signin_dialog(force=True)
            return
        QMessageBox.critical(self, 'Login error', error_msg)

    def test_connection(self):
        if not self.api:
            return
        self.test_btn.setEnabled(False)
        self.status_bar.showMessage(tr('Testing connection…'))
        self._test_worker = TestWorker(self.api)
        self._test_worker.done.connect(self._on_test_done)
        self._test_worker.fail.connect(self._on_test_fail)
        self._test_worker.start()

    def _on_test_done(self, info):
        self.test_btn.setEnabled(True)
        self.logger.info('Connection OK: %s', info)
        self.status_bar.showMessage(tr('Connection OK: {info}').format(info=info), 8000)
        QMessageBox.information(self, 'Connection OK', f'Logged in as:\n{info}')

    def _on_test_fail(self, msg):
        self.test_btn.setEnabled(True)
        self.logger.error('Connection test failed: %s', msg)
        QMessageBox.warning(self, 'Connection problem', msg)

    # ── Table ────────────────────────────────────────────────────────────────


    def add_files(self):
        pattern = ' '.join('*' + ext for ext in IMAGE_EXTS)
        files, _ = QFileDialog.getOpenFileNames(
            self, tr('Select image files'), remembered_dir(self.settings),
            tr('Images') + f' ({pattern})'
        )
        if files:
            remember_dir(self.settings, files[0])
        added, dups, failed = self._add_paths(files)
        if added:
            self.logger.debug('%d file(s) added to the table.', added)
        self._report_add_result(added, dups, failed)

    @staticmethod
    def folder_image_files(folder):
        """The uploadable files directly inside `folder`, sorted by name.

        NOT recursive (0.16.0, Harald): only the top level, the way a card
        or a day's folder is organised. And only the extensions the upload
        path itself accepts - IMAGE_EXTS, the very list add_files filters
        its dialog with, so there is no second list to keep in step. RAW
        files are deliberately not among them: Cammello has no raw
        converter, so they could not be uploaded anyway - which also means
        a folder holding RAW+JPEG pairs yields one row per picture instead
        of two.
        """
        try:
            with os.scandir(folder) as it:
                entries = sorted(it, key=lambda e: e.name)
                out = []
                for entry in entries:
                    # scandir answers is_file() from the directory read on
                    # most systems - no extra stat per name, which is what
                    # made the listdir version slow on large folders.
                    try:
                        if not entry.is_file():
                            continue
                    except OSError:
                        continue
                    if os.path.splitext(entry.name)[1].lower() in IMAGE_EXTS:
                        out.append(entry.path)
                return out
        except OSError:
            return []

    def open_directory(self):
        """Load a whole folder into the table, skipping the culling module.

        The short way in for a batch that needs no picking: choose a
        folder, every uploadable file in it becomes a row.
        """
        folder = QFileDialog.getExistingDirectory(
            self, tr('Select directory'), remembered_dir(self.settings))
        if not folder:
            return
        remember_dir(self.settings, folder)
        paths = self.folder_image_files(folder)
        if not paths:
            QMessageBox.information(
                self, tr('Open directory'),
                tr('No uploadable files in this directory.'))
            return
        if len(paths) > FOLDER_WARN_COUNT:
            answer = QMessageBox.question(
                self, tr('Open directory'),
                tr('This directory holds {n} files. Loading them all takes a '
                   'while and a lot of memory. Continue?').format(
                       n=len(paths)),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                return
        self.logger.info('Opening directory %r with %d file(s).',
                         folder, len(paths))
        self._add_paths_with_progress(paths)

    def _add_paths_with_progress(self, paths):
        """_add_paths with a progress dialog that can be cancelled.

        The dialog is shown, never exec()d - an exec would block the very
        loop it reports on. Cancelling keeps the rows added so far; that is
        friendlier than throwing away work the user has already waited for.
        """
        total = len(paths)
        dlg = QProgressDialog(
            tr('Reading files\u2026'), tr('Cancel'), 0, total, self)
        dlg.setWindowTitle(tr('Open directory'))
        dlg.setWindowModality(Qt.WindowModal)
        # Half a second of grace: a small folder is loaded before the
        # dialog would even have finished appearing.
        dlg.setMinimumDuration(500)
        dlg.setValue(0)

        def step(done, count):
            dlg.setLabelText(tr('Reading file {i} of {n}\u2026').format(
                i=done + 1, n=count))
            dlg.setValue(done)
            QApplication.processEvents()
            return not dlg.wasCanceled()

        try:
            added, dups, failed, cancelled = self._add_paths(
                paths, progress=step)
        finally:
            dlg.close()
        if cancelled:
            self.logger.info('Folder import cancelled after %d file(s).',
                             added)
        self._report_add_result(added, dups, failed, cancelled)

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

    def _selection_count_text(self, selected, total):
        """Uniform 'n of m selected' / 'm file(s)' label text."""
        if selected:
            return tr('{sel} of {total} selected').format(
                sel=selected, total=total)
        return tr('{n} file(s)').format(n=total)

    def _populate_shared_list(self, list_widget, keep_path=None):
        """Fill a QListWidget with the main table's files: icon copied
        from the table (zero decoding), path in UserRole, target name in
        UserRole+1. Used by the IPTC, FTP and Flickr tabs so the three
        lists look and behave identically."""
        list_widget.blockSignals(True)
        list_widget.clear()
        restored = None
        commercial_list = list_widget is getattr(self, 'ftp_list', None)
        for path, name, target, r in self._iptc_paths():
            it = QListWidgetItem(name)
            it.setData(Qt.UserRole, path)
            it.setData(Qt.UserRole + 1, target)
            thumb_item = self.table.item(r, self.COL_THUMB)
            if thumb_item is not None and not thumb_item.icon().isNull():
                it.setIcon(thumb_item.icon())
            it.setSizeHint(QSize(0, 70))
            if commercial_list:
                # FTP/Flickr = commercial channel: gray out commons-marked
                # files, colour-code commercial-marked ones (0.12.1).
                self._style_shared_list_item(it, path)
            # Channel dot (0.12.6): drawn ONTO the thumbnail, never instead
            # of it - setting a plain dot icon here replaced the preview and
            # left the IPTC list without images.
            if hasattr(self, '_channel_mark'):
                mark = self._channel_mark(path)
                if mark:
                    color = (channels.COLOR_COMMONS
                             if mark == channels.MARK_COMMONS
                             else channels.COLOR_COMMERCIAL)
                    it.setIcon(_with_channel_dot(it.icon(), color))
            list_widget.addItem(it)
            if keep_path is not None and path == keep_path:
                restored = it
        list_widget.blockSignals(False)
        return restored

    def _add_paths(self, paths, progress=None):
        """Add the given files to the table, skipping duplicates.

        Returns (added, duplicates, failed) - or, when a `progress`
        callback is given, (added, duplicates, failed, cancelled). The
        callback is called as progress(done, total) before each file and
        returns False to stop; the rows added so far stay.

        Sorting is disabled for the duration of the batch so
        setSortingEnabled does not reshuffle rows while they are only
        partially populated.
        """
        was_sorting = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)
        # Batch mode: without this, every inserted row triggered a relayout of
        # ALL row heights (ResizeToContents) plus a repaint - adding a few
        # hundred files froze the GUI for many seconds (quadratic cost).
        header = self.table.verticalHeader()
        self.table.setUpdatesEnabled(False)
        header.setSectionResizeMode(QHeaderView.Fixed)
        seen = self._current_filepaths()
        added = duplicates = failed = 0
        cancelled = False
        total = len(paths)
        try:
            for done, filepath in enumerate(paths):
                if progress is not None and not progress(done, total):
                    cancelled = True
                    break
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
            header.setSectionResizeMode(QHeaderView.ResizeToContents)
            self.table.setUpdatesEnabled(True)
            self.table.setSortingEnabled(was_sorting)
        # Freshly added files may already carry a persisted channel mark.
        self._apply_channel_marks_to_table()
        self._update_upload_btn()   # the row count changed
        if progress is not None:
            return added, duplicates, failed, cancelled
        return added, duplicates, failed

    def _report_add_result(self, added, duplicates, failed,
                           cancelled=False):
        parts = []
        if cancelled:
            parts.append(tr('cancelled'))
        if added:
            parts.append(tr('{n} added').format(n=added))
        if duplicates:
            parts.append(tr('{n} duplicate(s) skipped').format(n=duplicates))
        if failed:
            parts.append(tr('{n} skipped (see log)').format(n=failed))
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

    # ── Channel marks (0.12.1): Commons/CC vs. commercial (FTP/Flickr) ────────
    # A file marked for one channel stays visible in the other channel's list
    # but is grayed out (disabled) there and excluded from that channel's
    # upload. Unmarked files behave as before. See channels.py.

    def _channel_mark(self, path):
        """The file's mark ('commons' | 'commercial') or None."""
        return self._channel_marks.get(channels.norm(path))

    def _set_channel_mark(self, paths, mark):
        """Mark (or unmark, mark=None) paths; persist and restyle both lists."""
        if not paths:
            return
        changed = channels.set_mark(self._channel_marks, paths, mark)
        if not changed:
            return
        channels.save_marks(self._channel_settings, self._channel_marks)
        self._apply_channel_marks_to_table()
        if hasattr(self, 'ftp_list'):
            self._ftp_refresh_list()
        # The thumbnails carry the mark as a colored dot (0.12.6): refresh
        # the visible culling rows so the dots follow the change at once.
        if hasattr(self, '_cull_visible') and hasattr(self, 'cull_strip'):
            for i in range(len(self._cull_visible)):
                self._cull_decorate_row(i)
            self.cull_strip.viewport().update()
            self._cull_set_status()      # loupe/fullscreen overlay dot
        self.logger.info('Channel mark %s for %d file(s).',
                         mark or 'removed', changed)


    def _apply_channel_marks_to_table(self):
        """Restyle every table row from its mark. Commercial rows are disabled
        (auto-grayed by the style, unselectable, uneditable) - they belong to
        the FTP/Flickr channel. Commons rows get the green colour code on the
        name columns. Keyed by path, so sorting cannot detach a mark."""
        commons_brush = QBrush(QColor(channels.COLOR_COMMONS))
        for r in range(self.table.rowCount()):
            src = self.table.item(r, self.COL_FILENAME)
            if src is None:
                continue
            mark = self._channel_mark(src.data(Qt.UserRole) or '')
            enabled = mark != channels.MARK_COMMERCIAL
            tip = ''
            if mark == channels.MARK_COMMERCIAL:
                tip = tr('Marked for commercial use - excluded from the '
                         'Commons upload.')
            elif mark == channels.MARK_COMMONS:
                tip = tr('Marked for Commons (CC).')
            for c in range(self.table.columnCount()):
                item = self.table.item(r, c)
                if item is None:
                    continue
                flags = item.flags()
                item.setFlags((flags | Qt.ItemIsEnabled) if enabled
                              else (flags & ~Qt.ItemIsEnabled))
                if c in (self.COL_FILENAME, self.COL_TITLE):
                    if mark == channels.MARK_COMMONS:
                        item.setForeground(commons_brush)
                    elif mark == channels.MARK_COMMERCIAL:
                        item.setForeground(QBrush(QColor(channels.COLOR_COMMERCIAL)))
                    else:
                        item.setData(Qt.ForegroundRole, None)  # style default
                    item.setToolTip(tip)
                # A small colored dot on the filename cell (same visual as
                # the culling thumbnails, 0.12.6 fix).
                if c == self.COL_FILENAME:
                    if mark:
                        color = (channels.COLOR_COMMONS
                                 if mark == channels.MARK_COMMONS
                                 else channels.COLOR_COMMERCIAL)
                        item.setIcon(_channel_dot_icon(color))
                    else:
                        item.setIcon(QIcon())

    def _style_shared_list_item(self, it, path):
        """Channel styling for one FTP/Flickr list item (commercial channel):
        commons-marked files are disabled (grayed, unselectable), commercial-
        marked files get the orange colour code."""
        mark = self._channel_mark(path)
        if mark == channels.MARK_COMMONS:
            it.setFlags(it.flags() & ~Qt.ItemIsEnabled)
            it.setToolTip(tr('Marked for Commons (CC) - excluded from '
                             'commercial uploads (FTP/Flickr).'))
        elif mark == channels.MARK_COMMERCIAL:
            it.setForeground(QBrush(QColor(channels.COLOR_COMMERCIAL)))
            it.setToolTip(tr('Marked for commercial use.'))

    def _channel_menu_actions(self, menu, paths):
        """Append the three mark actions to a context menu."""
        a1 = menu.addAction(tr('Mark for Commons (CC)'))
        a1.triggered.connect(
            lambda: self._set_channel_mark(paths, channels.MARK_COMMONS))
        a2 = menu.addAction(tr('Mark for commercial use (FTP/Flickr)'))
        a2.triggered.connect(
            lambda: self._set_channel_mark(paths, channels.MARK_COMMERCIAL))
        a3 = menu.addAction(tr('Remove channel mark'))
        a3.triggered.connect(lambda: self._set_channel_mark(paths, None))

    def _table_context_menu(self, pos):
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        if not rows:
            idx = self.table.indexAt(pos)
            if idx.isValid():
                rows = [idx.row()]
        paths = []
        for r in rows:
            item = self.table.item(r, self.COL_FILENAME)
            fp = item.data(Qt.UserRole) if item else None
            if fp:
                paths.append(fp)
        if not paths:
            return
        menu = QMenu(self.table)
        self._channel_menu_actions(menu, paths)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _ftp_context_menu(self, pos):
        items = self.ftp_list.selectedItems()
        if not items:
            it = self.ftp_list.itemAt(pos)
            items = [it] if it else []
        paths = [it.data(Qt.UserRole) for it in items if it is not None]
        paths = [p for p in paths if p]
        if not paths:
            return
        menu = QMenu(self.ftp_list)
        self._channel_menu_actions(menu, paths)
        menu.exec(self.ftp_list.viewport().mapToGlobal(pos))

    def _mark_uploaded_channel(self, paths, mark):
        """Record the channel a file was actually sent to (0.12.4).

        Uploading IS the decision: a file pushed to Commons is CC from then
        on, a file pushed to an agency is commercial - so the mark is set
        automatically instead of relying on the user to right-click first.
        Files already carrying the mark are untouched (set_mark counts only
        real changes), and a file already marked for the OTHER channel can
        never reach here: both upload paths filter those out beforehand.
        """
        if not paths:
            return
        self._set_channel_mark(list(paths), mark)

    def _row_caption(self, row):
        """The caption of one row, base description merged in (0.18.19).

        Merged, not just the per-file cell: a photographer who captions a
        whole shoot once in the base description and only varies the name
        per file would otherwise get no caption at all here.
        """
        item = self.table.item(row, self.COL_DESC)
        per_file = item.text() if item else ''
        try:
            text = self._effective_text(per_file)
        except Exception:                        # pragma: no cover
            text = per_file
        fields, _cats = sdc.decompose_fields(text)
        return sdc.pick_caption(fields, [current_language()])

    def _row_captions(self, row):
        """Every language's caption of one row, base description merged in.

        Same merge as _row_caption, but the whole {lang: text} table
        instead of one pick, so the dialog can offer the languages the
        selection actually has (0.18.21).
        """
        item = self.table.item(row, self.COL_DESC)
        per_file = item.text() if item else ''
        try:
            text = self._effective_text(per_file)
        except Exception:                        # pragma: no cover
            text = per_file
        fields, _cats = sdc.decompose_fields(text)
        out = {}
        for key, value in (fields or {}).items():
            if key.startswith('caption_') and (value or '').strip():
                out[key[len('caption_'):]] = value.strip()
        return out

    def _row_event(self, row):
        """The created_during value of one row, '' when it has none."""
        item = self.table.item(row, self.COL_DESC)
        per_file = item.text() if item else ''
        try:
            text = self._effective_text(per_file)
        except Exception:                        # pragma: no cover
            text = per_file
        fields, _cats = sdc.decompose_fields(text)
        return ((fields or {}).get('created_during') or '').strip()

    def _row_depicts(self, row):
        """The depicts QIDs of one row (base merged), deduped, in order."""
        item = self.table.item(row, self.COL_DESC)
        per_file = item.text() if item else ''
        try:
            text = self._effective_text(per_file)
        except Exception:                        # pragma: no cover
            text = per_file
        fields, _cats = sdc.decompose_fields(text)
        raw = (fields or {}).get('depicts') or ''
        out, seen = [], set()
        for qid in re.split(r'[;,]', raw):
            qid = qid.strip()
            if re.fullmatch(r'Q\d+', qid) and qid not in seen:
                out.append(qid)
                seen.add(qid)
        return out

    def _caption_langs(self):
        """The languages captions are generated in: the four defaults plus
        the languages the user added in the caption-language dropdown (they
        stay until removed there). A hand-set '|'-joined list under QSettings
        'Captions'/'languages' still overrides both."""
        raw = QSettings(APP_NAME, 'Captions').value('languages', '', type=str)
        langs = [c.strip() for c in raw.split('|') if c.strip()]
        if langs:
            return langs
        out = list(CAPTION_LANGS_DEFAULT)
        for code in _caption_extra_langs():
            if code not in out:
                out.append(code)
        return out

    def _generate_captions(self):
        """Fill the structured-data captions in every configured language
        from each file's depicts and created-during (0.18.24).

        Harald: "die caption soll in allen sprachen gleichzeitig verfügbar
        sein … die sollen erzeugt werden … eigenständig." One Wikidata call
        for the whole selection; a review dialog where the per-event, per-
        language conjunction can be corrected and is remembered; then the
        captions are written into the descriptions, the file overriding the
        base as captions always do. Nothing is written before the dialog is
        confirmed - a column of hand-written captions is not to be lost on a
        mis-click.
        """
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        if not rows:
            rows = list(range(self.table.rowCount()))
        if not rows:
            return
        material = []
        qids = []
        seen = set()
        for row in rows:
            depicts = self._row_depicts(row)
            event = self._row_event(row)
            material.append({'row': row, 'depicts': depicts, 'event': event,
                             'captions': self._row_captions(row)})
            for qid in depicts + ([event] if event else []):
                if qid and qid not in seen:
                    qids.append(qid)
                    seen.add(qid)
        if not qids:
            QMessageBox.information(
                self, tr('Generate captions'),
                tr('No depicts or "created during" found - fill those '
                   'first, then generate the captions.'))
            return
        result, exc, cancelled = fetch_in_background(
            self, tr('Asking Wikidata…'), fetch_caption_entities, qids)
        if cancelled:
            return
        if exc is not None:
            self.logger.error('Caption generation: Wikidata failed: %s', exc)
            QMessageBox.warning(self, tr('Generate captions'),
                                wd_error_text(exc))
            return
        entities = result or {}
        langs = self._caption_langs()
        # Start from what was learned before, then fill any gap from the
        # captions already in this selection - a hand-captioned file teaches
        # the rest. The dialog may correct either.
        settings = QSettings(APP_NAME, 'Captions')
        table = captions_mod.FuegungTable.from_json(
            settings.value('fuegungen', '', type=str))
        table.merge_from(captions_mod.derive_table(material, entities, langs))

        dlg = GenerateCaptionsDialog(entities, material, table, langs, self)
        if dlg.exec() != QDialog.Accepted:
            return
        chosen_langs = dlg.languages()
        final_table = dlg.result_table()
        with_links = dlg.with_links()
        # Remember the conjunctions for next time (gaps filled, dialog wins).
        stored = captions_mod.FuegungTable.from_json(
            settings.value('fuegungen', '', type=str))
        stored.merge_from(final_table, overwrite=True)
        settings.setValue('fuegungen', stored.to_json())

        written = 0
        for m in material:
            caps = captions_mod.all_captions(
                m['depicts'], m['event'], entities, final_table, chosen_langs)
            if not caps:
                continue
            changes = {f'caption_{lang}': text for lang, text in caps.items()}
            if with_links:
                for lang in chosen_langs:
                    linked = captions_mod.linked_description(
                        m['depicts'], m['event'], entities, final_table,
                        lang, [lang, 'en', 'de'])
                    if linked:
                        changes[f'info:{lang}'] = linked
            row = m['row']
            item = self.table.item(row, self.COL_DESC)
            if item is None:
                continue
            item.setText(apply_field_changes(item.text(), changes))
            if hasattr(self, '_refresh_effective'):
                self._refresh_effective(row)
            written += 1
        self.logger.info(
            'Generated captions for %d file(s) in %d language(s)%s.',
            written, len(chosen_langs),
            ' with linked descriptions' if with_links else '')
        self.status_bar.showMessage(
            tr('Captions written for {f} file(s) in {l} language(s).').format(
                f=written, l=len(chosen_langs)), 5000)

    def _suggest_captions(self):
        """'Suggest captions' under depicts in the per-file editor (0.18.29).

        Harald: one button that makes the captions in the several languages,
        the category and the description wikitext, "wie bei LrMediaWiki2".
        It is the per-file sibling of the batch dialog: no dialog, the
        configured languages and the learned conjunctions, the description
        with interwiki links, and the categories of the depicts entries.
        It fills ONLY what is empty, so a corrected caption survives
        pressing it again after a depicts change. Works on every selected
        file; each file uses its own depicts.
        """
        self._commit_editor()
        rows = self._selected_rows_all()
        title = tr('Suggest captions')
        if not rows:
            self.status_bar.showMessage(
                tr('Select a file first.'), 5000)
            return
        material, depicts_all, qids, seen = [], [], [], set()
        for row in rows:
            depicts = self._row_depicts(row)
            if not depicts:
                continue
            event = self._row_event(row)
            material.append({'row': row, 'depicts': depicts, 'event': event,
                             'captions': self._row_captions(row)})
            for qid in depicts + ([event] if event else []):
                if qid not in seen:
                    qids.append(qid)
                    seen.add(qid)
            depicts_all.extend(q for q in depicts if q not in depicts_all)
        if not material:
            QMessageBox.information(
                self, title,
                tr('No depicts QIDs found - fill depicts first.'))
            return

        # ONE request: the entities carry the Commons category (P373) too.
        result, exc, cancelled = fetch_in_background(
            self, tr('Asking Wikidata…'), fetch_caption_entities, qids)
        if cancelled:
            return
        if exc is not None:
            self.logger.error('Suggest captions: Wikidata failed: %s', exc)
            QMessageBox.warning(self, title, wd_error_text(exc))
            return
        entities = result or {}
        fetched_cats = captions_mod.commons_categories(entities, depicts_all)
        langs = self._caption_langs()
        # The learned conjunctions plus what the selection's own captions
        # teach. Not stored back: without the dialog nobody reviewed it.
        settings = QSettings(APP_NAME, 'Captions')
        table = captions_mod.FuegungTable.from_json(
            settings.value('fuegungen', '', type=str))
        table.merge_from(captions_mod.derive_table(material, entities, langs))

        files = fields = cat_count = 0
        for m in material:
            row = m['row']
            item = self.table.item(row, self.COL_DESC)
            if item is None:
                continue
            per_file = item.text()
            try:
                effective = self._effective_text(per_file)
            except Exception:                    # pragma: no cover
                effective = per_file
            eff_fields, eff_cats = sdc.decompose_fields(effective)
            # 0.18.32 (Harald): "suggest captions did nothing because
            # something was already there" - it was the BASE description's
            # caption. The button fills the SELECTED FILE's own fields, so
            # only what stands in this file counts as already there (a file
            # caption overrides the base one anyway). Categories still look
            # at the merged text: one the base has must not be added twice.
            own_fields = sdc.decompose_fields(per_file)[0] or {}
            have_caps = {k[len('caption_'):]: v
                         for k, v in own_fields.items()
                         if k.startswith('caption_')}
            have_infos = {k[len('info:'):]: v
                          for k, v in own_fields.items()
                          if k.startswith('info:')}
            caps = captions_mod.all_captions(
                m['depicts'], m['event'], entities, table, langs)
            linked = {}
            for lang in langs:
                text = captions_mod.linked_description(
                    m['depicts'], m['event'], entities, table, lang,
                    [lang, 'en', 'de'])
                if text:
                    linked[lang] = text
            changes = captions_mod.fill_missing(
                have_caps, have_infos, caps, linked)
            date_item = self.table.item(row, self.COL_DATE)
            new_cats = category_suggestions(
                m['depicts'], '', fetched_cats,
                date_item.text() if date_item else '', eff_cats)
            if not changes and not new_cats:
                continue
            own_cats = sdc.decompose_fields(per_file)[1]
            item.setText(sdc.apply_field_changes(
                per_file, changes,
                (list(own_cats) + new_cats) if new_cats else None))
            self._refresh_effective(row)
            files += 1
            fields += len(changes)
            cat_count += len(new_cats)

        # The editor still shows the text from before: load it again, so the
        # new fields are what is on screen (and what the next commit writes).
        self._load_selected_desc()
        if not files:
            self.status_bar.showMessage(
                tr('Nothing to fill - captions, descriptions and categories '
                   'are already there.'), 5000)
            return
        self.logger.info(
            'Suggest captions: %d field(s) and %d categor(y/ies) in %d '
            'file(s), %d language(s).', fields, cat_count, files, len(langs))
        self.status_bar.showMessage(
            tr('{n} field(s) and {k} category suggestion(s) filled in {f} '
               'file(s).').format(n=fields, k=cat_count, f=files), 5000)

    def _caption_rows(self, rows):
        """The per-row material sdc.propose_names needs, in `rows` order."""
        out = []
        for row in rows:
            path = self._row_path(row) if hasattr(self, '_row_path') else None
            if not path:
                item = self.table.item(row, self.COL_FILENAME)
                path = (item.data(Qt.UserRole) or item.text()) if item else ''
            out.append({
                'captions': self._row_captions(row),
                'event': self._row_event(row),
                'source': os.path.splitext(os.path.basename(path or ''))[0],
                'old': (self.table.item(row, self.COL_TITLE).text()
                        if self.table.item(row, self.COL_TITLE) else ''),
            })
        return out

    def _names_from_descriptions(self):
        """Fill the target-filename column from the captions.

        Harald: "eine Funktion, die vor dem Hochladen per Knopfdruck
        sinnvolle Dateinamen aus den Beschreibungen erzeugt".

        Works on the selection, or on every row when nothing is selected.
        Nothing is written before the user has seen the list: overwriting a
        column of hand-made names on a mis-click would be the kind of
        damage that is not undoable.

        0.18.21: the proposal itself lives in sdc.propose_names and the
        dialog recomputes it while the caption options are changed, so this
        only collects the material and writes the result.
        """
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        if not rows:
            rows = list(range(self.table.rowCount()))
        if not rows:
            return
        material = self._caption_rows(rows)
        dlg = NamesFromDescriptionDialog(
            material, self,
            digits=BulkRenameDialog.auto_digits([m['source']
                                                 for m in material]),
            exts=[self._ext_for_row(r) for r in rows])
        if dlg.exec() != QDialog.Accepted:
            return
        changed = without = 0
        for row, base in zip(rows, dlg.names()):
            if not base:
                without += 1
                continue                    # no caption: the row is left alone
            item = self.table.item(row, self.COL_TITLE)
            if item:
                item.setText(base + self._ext_for_row(row))
                changed += 1
        self.logger.info(
            'Named %d target filename(s) from the descriptions; %d row(s) '
            'had no caption and were left alone.', changed, without)

    def _rename_selected(self):
        """The one way to rename, from the toolbar button and from F2
        (0.18.21 - "Umbenennen" is a word in the bar, and F2 does the same).

        Opens the rename dialog whose scheme names every selected row
        with a running number, or with the camera's own number via {c}.
        0.18.32 (Harald): the name is applied ON DISK as well - the source
        file (with its RAW/JPEG partner and sidecar) gets the new name, and
        so does the Commons target name."""
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        if not rows and self.table.currentRow() >= 0:
            rows = [self.table.currentRow()]
        if not rows:
            return
        # 0.18.21 (Harald): the dialog opens for ONE row as well. It used
        # to start an inline edit there, which put the caption schemes out
        # of reach for a single file - and typing a name directly is still
        # one double-click into the cell away.
        # 0.16.0: the dialog needs the SOURCE names so {c} can take the
        # camera's own number from them.
        sources, exts, dates = [], [], []
        for row in rows:
            path = self._row_path(row) if hasattr(self, '_row_path') else None
            if not path:
                item = self.table.item(row, self.COL_FILENAME)
                path = (item.data(Qt.UserRole) or item.text()) if item else ''
            sources.append(os.path.splitext(os.path.basename(path or ''))[0])
            exts.append(self._ext_for_row(row))
            date_item = self.table.item(row, self.COL_DATE)
            dates.append(date_item.text().strip() if date_item else '')
        dlg = BulkRenameDialog(len(rows), self, sources=sources,
                               exts=exts, dates=dates,
                               captions=[self._row_caption(r) for r in rows],
                               caption_rows=self._caption_rows(rows))
        if dlg.exec() != QDialog.Accepted:
            return
        names = list(dlg.names())
        # Disk first: if a file cannot be renamed, nothing changes at all -
        # table and disk must not drift apart.
        entries = []
        for row, base in zip(rows, names):
            path = self._row_path(row)
            if path:
                entries.append((path, base))
        plan, problems = culling.plan_disk_renames(entries)
        if problems:
            self._warn_rename_problems(problems)
            return
        moved = {}
        if plan:
            try:
                culling.execute_disk_renames(plan)
            except OSError as exc:
                self.logger.error('Rename on disk failed: %s', exc)
                QMessageBox.warning(self, tr('Rename file'),
                                    tr('Renaming failed: {error}').format(
                                        error=str(exc)))
                return
            moved = dict(plan)
            self._after_disk_rename(moved)
        for row, base in zip(rows, names):
            item = self.table.item(row, self.COL_TITLE)
            if item:
                item.setText(base + self._ext_for_row(row))
        self.logger.info('Bulk-renamed %d file(s): %d file(s) on disk, '
                         'target names set.', len(rows), len(moved))

    def _warn_rename_problems(self, problems):
        texts = {
            'chars': tr('That name contains characters a file name cannot '
                        'hold.'),
            'reserved': tr('That name is reserved on Windows or ends with '
                           'a dot or space.'),
            'trailing': tr('That name is reserved on Windows or ends with '
                           'a dot or space.'),
            'empty': tr('The new name is empty.'),
            'clash': tr('A file called "{name}" already exists.'),
            'twice': tr('Two files would get the name "{name}".'),
        }
        lines = []
        for code, name in problems[:8]:
            lines.append(texts.get(code, code).replace('{name}', name)
                         + ('' if '{name}' in texts.get(code, '')
                            else f'  ({name})'))
        if len(problems) > 8:
            lines.append('…')
        QMessageBox.warning(
            self, tr('Rename file'),
            '\n'.join(lines) + '\n\n' + tr('Nothing was renamed.'))

    def _after_disk_rename(self, moved):
        """Bring everything that remembers a path up to date: the table
        rows, the culling items and the records keyed by path."""
        norm = {os.path.normcase(o): n for o, n in moved.items()}
        for row in range(self.table.rowCount()):
            item = self.table.item(row, self.COL_FILENAME)
            old = item.data(Qt.UserRole) if item else None
            new = norm.get(os.path.normcase(old)) if old else None
            if new:
                item.setData(Qt.UserRole, new)
                item.setText(os.path.basename(new))
        if not hasattr(self, '_cull_items'):
            return
        for old, new in moved.items():
            self._cull_migrate_paths(old, new)
        current = None
        for ci in self._cull_items:
            before = ci.display_path
            changed = False
            if ci.raw_path and os.path.normcase(ci.raw_path) in norm:
                ci.raw_path = norm[os.path.normcase(ci.raw_path)]
                changed = True
            if ci.jpg_path and os.path.normcase(ci.jpg_path) in norm:
                ci.jpg_path = norm[os.path.normcase(ci.jpg_path)]
                changed = True
            if not changed:
                continue
            ci.stem = os.path.splitext(os.path.basename(ci.display_path))[0]
            row = self._cull_row_by_item.get(id(ci))
            self._cull_row_by_path.pop(before, None)
            if row is not None:
                self._cull_row_by_path[ci.display_path] = row
                if 0 <= row < self.cull_strip.count():
                    self._cull_decorate_row(row)
            if ci is self._cull_current_item():
                current = ci
        if current is not None:
            # the preview cache is keyed by path: load it under the new name
            self._cull_show_index(self._cull_index)

    def _make_thumbnail(self, filepath, w=THUMB_SRC_W, h=THUMB_SRC_H):
        """Create a downscaled preview efficiently (without full resolution).

        RAW files do NOT go through QImageReader (0.12.6 fix): Qt cannot
        decode CR2/NEF/ARW - it recognises them as TIFF, fails on the
        old-style JPEG compression inside, and libtiff floods the console
        with warnings while the table stays empty. The camera's embedded
        preview via rawpy is both readable and much faster.
        """
        ext = os.path.splitext(filepath)[1].lower()
        try:
            if ext in previews._RAW_EXTS:
                data = previews.extract_preview_bytes(filepath)
                img = QImage.fromData(data)
                if not img.isNull():
                    orient = previews.read_orientation(filepath)
                    img = previews._apply_orientation(img, orient)
                    if img.width() > w or img.height() > h:
                        img = img.scaled(w, h, Qt.KeepAspectRatio,
                                         Qt.SmoothTransformation)
                    return QPixmap.fromImage(img)
                return None
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
        # 0.12.15: the camera position rides along with the date - both come
        # from the same EXIF read the user never has to think about. Off by
        # switch for anyone who does not want to publish positions; files
        # without GPS (and RAW, which Pillow cannot read) simply get nothing.
        coords = None
        if self.settings.value('exif_coordinates', True, type=bool):
            coords = read_gps(filepath, self.logger)

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
        self.table.setItem(row, self.COL_DESC, QTableWidgetItem(
            f'coordinates={format_coordinates(*coords)}' if coords else ''))

        # 0.15.0: Location column. Reads the SAME description cell the
        # structured editor writes to - one fact, one place. The camera
        # position is already in there via the coordinates= line above.
        loc_item = QTableWidgetItem('')
        loc_item.setFlags(loc_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row, self.COL_LOCATION, loc_item)

        # Effective (base + file) preview, read-only.
        eff_item = QTableWidgetItem('')
        eff_item.setFlags(eff_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row, self.COL_EFFECTIVE, eff_item)

        status_item = QTableWidgetItem('—')
        status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row, self.COL_STATUS, status_item)

        self._refresh_effective(row)
        self._location_refresh_row(row)

        if seen is not None:
            seen.add(norm)
        return True
