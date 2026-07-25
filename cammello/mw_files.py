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
    QStyledItemDelegate, QComboBox, QScrollArea, QCompleter,
    QListWidgetItem, QMenu)
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
from .widgets import *
from .editors import *
from . import mw_oauth
from . import channels
from . import previews


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
        if mw_oauth.is_configured():
            token, secret = stored_oauth_tokens()
            if token and secret and not force:
                self._login_with_stored_oauth(token, secret)
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
            token, secret = stored_oauth_tokens()
            if token and secret:
                self._login_with_stored_oauth(token, secret)
            if hasattr(self, '_refresh_oauth_status'):
                self._refresh_oauth_status()
            return
        # No consumer in this build: the bot password IS the way in.
        self._login_with_botpassword()

    def _login_with_stored_oauth(self, token, secret):
        s = QSettings(APP_NAME, 'Login')
        api_url = (s.value('api_url', '')
                   or 'https://commons.wikimedia.org/w/api.php')
        username = s.value('oauth_username', '') or 'OAuth'
        self._start_login_worker(api_url, username, '',
                                 oauth_token=token, oauth_secret=secret)

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
                            oauth_token=None, oauth_secret=None):
        self.login_btn.setEnabled(False)
        self._set_login_state('busy')

        self._login_worker = LoginWorker(
            api_url, username, password, self._get_timeout(), self.logger,
            oauth_token=oauth_token, oauth_secret=oauth_secret)
        self._login_worker.success.connect(
            lambda api: self._on_login_success(api, username))
        self._login_worker.failure.connect(self._on_login_failure)
        self._login_worker.start()

    def _on_login_success(self, api, username):
        self.api = api
        self.login_btn.setEnabled(True)
        self.test_btn.setEnabled(True)
        self._set_login_state('in', username)
        self.status_bar.showMessage(tr('Logged in as {username}').format(username=username))

    def _on_login_failure(self, error_msg):
        self.login_btn.setEnabled(True)
        self._set_login_state('out')
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

    def _add_paths(self, paths):
        """Add the given files to the table, skipping duplicates.

        Returns (added, duplicates, failed). Sorting is disabled for the
        duration of the batch so setSortingEnabled does not reshuffle rows
        while they are only partially populated.
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
            header.setSectionResizeMode(QHeaderView.ResizeToContents)
            self.table.setUpdatesEnabled(True)
            self.table.setSortingEnabled(was_sorting)
        # Freshly added files may already carry a persisted channel mark.
        self._apply_channel_marks_to_table()
        self._update_upload_btn()   # the row count changed
        return added, duplicates, failed

    def _report_add_result(self, added, duplicates, failed):
        parts = []
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

    def _rename_selected(self):
        """F2 in the file table (Lightroom habit): one selected row edits its
        target filename inline (via the FilenameDelegate, extension fixed);
        several rows open the bulk-rename dialog whose template names them all
        with a running number. Only the target Commons name changes - the
        source files on disk are never touched."""
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        if not rows and self.table.currentRow() >= 0:
            rows = [self.table.currentRow()]
        if not rows:
            return
        if len(rows) == 1:
            item = self.table.item(rows[0], self.COL_TITLE)
            if item:
                self.table.setCurrentItem(item)
                self.table.editItem(item)
            return
        dlg = BulkRenameDialog(len(rows), self)
        if dlg.exec() != QDialog.Accepted:
            return
        for row, base in zip(rows, dlg.names()):
            item = self.table.item(row, self.COL_TITLE)
            if item:
                item.setText(base + self._ext_for_row(row))
        self.logger.info('Bulk-renamed %d target filenames.', len(rows))

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
