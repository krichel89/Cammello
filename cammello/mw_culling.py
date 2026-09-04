"""MainWindow mixin: the Culling tab (Phase 1b).

Keyboard model (the whole point of the tab - one hand, no dialogs):
  Right/Left   next / previous image
  1-5, 0       RATING mode: stars / clear - COLOR mode: label / clear
  M            toggle the number mode (shown in the toolbar)
  X            reject (rating -1) + advance
  6-9          red/yellow/green/blue directly (Lightroom's own key layout;
               purple has no key in LR either)
  Z            toggle 100% zoom, F fullscreen (double-click does too; in
               the grid a double-click opens that picture fullscreen)
  Home/End     jump to the first / last image
  I            toggle the EXIF info overlay
Number keys auto-advance (checkbox to turn that off).

The tab widget itself owns the keyboard: every child has NoFocus so arrow
keys are never eaten by a list widget. Ratings go through the write-behind
queue; the UI never waits for disk.
"""
import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget,
    QListWidgetItem, QComboBox, QCheckBox, QFileDialog, QMessageBox, QSplitter,
    QStyledItemDelegate, QFormLayout, QGroupBox, QStyleOptionViewItem, QStyle,
    QToolButton, QInputDialog, QShortcut, QDialog, QDialogButtonBox,
    QLineEdit, QRadioButton, QApplication)
from PyQt5.QtGui import (QIcon, QPixmap, QColor, QPen, QPainter,
                         QKeySequence)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize, QTimer

from PyQt5.QtCore import QUrl, QMimeData, QItemSelectionModel, QObject

from .constants import *
# Explicit alongside the star import: the dialog added in 0.18.5 uses it,
# and a star-import name is one pyflakes cannot verify.
from .constants import current_input_style
from . import culling
from . import channels, previews, edits, camera
from .edit_panel import EditPanel
from .culling_view import CullImageView
from .widgets import (UploadProgressDialog, toolbar_separator,
                      slim_toolbar)
from .i18n import tr

# Zoom ladder: 12 roughly proportional steps (factor ~1.4-1.5) between 5% and
# 400%, all of them easy mental-arithmetic values (thirds, halves, doublings);
# 100% is an exact member.
ZOOM_STEPS = [5, 10, 15, 25, 33, 50, 67, 100, 150, 200, 300, 400]


# 0.12.7: rating -> glyphs, in ONE place and structurally bounded.
#
# Harald saw a file drawn with an endless row of stars. The read path now
# clamps (culling.read_item_metadata), but a value can also reach the UI
# from elsewhere (an item built by hand, a future importer), and every
# painter used its own `'*' * rating` expression - three chances to repeat
# the same unbounded multiplication. Public name: `from .widgets import *`
# style imports skip underscored names, and this is used across modules.
def rating_marks(rating, empty=False):
    """Return the rating as text: 'X' for rejected, else up to five stars.

    `empty=True` pads with hollow stars to a constant width of five.
    Any value outside -1..5 is clamped, so the result can never grow
    beyond five glyphs no matter what reaches this function.
    """
    try:
        value = int(rating)
    except (TypeError, ValueError):
        value = 0
    value = max(-1, min(5, value))
    if value == -1:
        return '✕'
    return '★' * value + ('☆' * (5 - value) if empty else '')


class _LabelBarDelegate(QStyledItemDelegate):
    """Filmstrip/grid cell painting, scheme-aware:

      * SELECTED cells get a medium-gray background (instead of the theme's
        blue highlight), so a multi-selection is recognizable at a glance in
        the grid AND in the filmstrip.
      * The CURRENT image additionally carries a frame: very light on the
        dark scheme, very dark on the light scheme.
      * A label paints a discreet color bar (6 px) along the bottom edge
        (color index in Qt.UserRole, None = no label).
    """

    BAR = 6
    FRAME_W = 5                          # frame stroke width ("breiter")
    SEL_FRAME = QColor('#8a8a8a')        # medium-gray SELECTION frame
    FRAME_DARK = QColor('#f5f5f5')       # current image: very light (dark)
    FRAME_LIGHT = QColor('#1c1c1c')      # current image: very dark (light)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_row = -1
        self.dark = False

    def set_dark(self, dark):
        self.dark = bool(dark)

    @property
    def sel_frame(self):
        return self.SEL_FRAME

    @property
    def frame_color(self):
        return self.FRAME_DARK if self.dark else self.FRAME_LIGHT

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        selected = bool(opt.state & QStyle.State_Selected)
        # Take over the selection rendering: the theme highlight is dropped;
        # the thumbnail itself stays untouched, selection and current image
        # are FRAMES around the cell.
        opt.state &= ~QStyle.State_Selected
        painter.save()
        super().paint(painter, opt, index)
        r = option.rect
        w = self.FRAME_W
        inset = 2 * w + 4
        fm = opt.fontMetrics
        text_color = opt.palette.color(opt.palette.Text)
        # Bottom area, fully delegate-drawn: the file name line, and below it
        # ONE band shared 50/50 - stars on the left, color bar on the right.
        band_h = max(self.BAR + 2, fm.height())
        band_top = r.bottom() - inset - band_h
        name_bottom = band_top - 2
        name = index.data(Qt.UserRole + 2) or ''
        if name:
            painter.setPen(text_color)
            painter.drawText(r.x() + inset, name_bottom - fm.descent(),
                             fm.elidedText(name, Qt.ElideMiddle,
                                           r.width() - 2 * inset))
        half = (r.width() - 2 * inset) // 2
        rating = index.data(Qt.UserRole + 1)
        if rating:
            marks = rating_marks(rating)
            painter.setPen(text_color)
            painter.drawText(r.x() + inset,
                             band_top + band_h - fm.descent() - 1, marks)
        idx = index.data(Qt.UserRole)
        if idx is not None:
            painter.fillRect(r.x() + inset + half + 2,
                             band_top + (band_h - self.BAR) // 2,
                             half - 2, self.BAR,
                             QColor(culling.LABEL_COLORS[idx]))
        # Channel mark (0.12.6): a small filled dot in the TOP-LEFT corner -
        # teal = Commons, orange = commercial. Top-left because the top-right
        # corner carries the reject cross.
        mark = index.data(Qt.UserRole + 3)
        if mark:
            color = (channels.COLOR_COMMONS if mark == channels.MARK_COMMONS
                     else channels.COLOR_COMMERCIAL)
            d = 10
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setPen(QPen(QColor('#00000060'), 1))
            painter.setBrush(QColor(color))
            painter.drawEllipse(r.x() + inset, r.y() + inset, d, d)
            painter.setBrush(Qt.NoBrush)
        # Crop/edit badge (0.13): a small scissors glyph top-left, offset when
        # a channel dot is already there. Marks a file that will upload as an
        # edited copy.
        if index.data(Qt.UserRole + 4):
            painter.setPen(QColor('#ffd24d'))
            f = painter.font()
            f.setPixelSize(13)
            f.setBold(True)
            painter.setFont(f)
            bx = r.x() + inset + (14 if mark else 0)
            painter.drawText(bx, r.y() + inset + 12, '\u2702')
        if rating == -1:
            # Rejected (0.12.6): grey the thumbnail out and put a small x in
            # the top-right corner - visible at a glance in strip and grid.
            painter.fillRect(r.adjusted(2, 2, -3, -3), QColor(0, 0, 0, 110))
            painter.setPen(QPen(QColor('#e05050'), 2))
            f = painter.font()
            f.setPixelSize(14)
            f.setBold(True)
            painter.setFont(f)
            painter.drawText(r.right() - inset - 14, r.y() + inset + 12, '✕')
        if selected:
            painter.setPen(QPen(self.sel_frame, w))
            painter.drawRect(r.adjusted(2, 2, -3, -3))
        if index.row() == self.current_row:
            # White (dark scheme) / black (light scheme); drawn inside the
            # selection frame so both stay visible on a selected current cell.
            painter.setPen(QPen(self.frame_color, w))
            painter.drawRect(r.adjusted(2 + w + 1, 2 + w + 1,
                                        -(3 + w + 1), -(3 + w + 1))
                             if selected else r.adjusted(2, 2, -3, -3))
        painter.restore()


class _CullStrip(QListWidget):
    """Filmstrip/grid list: multi-select, and selected images can be dragged
    out as file URLs (e.g. onto the Files tab - the tab bar switches on
    hover, the file table accepts URL drops)."""

    def __init__(self, owner):
        super().__init__()
        self._owner = owner
        self.setSelectionMode(QListWidget.ExtendedSelection)
        self.setDragEnabled(True)

    def mimeData(self, items):
        md = QMimeData()
        rows = sorted(self.row(it) for it in items)
        md.setUrls([QUrl.fromLocalFile(p)
                    for p in self._owner._cull_paths_for_rows(rows)])
        return md

    def mouseDoubleClickEvent(self, event):
        """0.18.4: double-click in the grid opens that picture fullscreen.

        The single image view has done this since 0.9 (double-click toggles
        fullscreen); in the grid a double-click did nothing, which reads as
        broken. Leaving fullscreen returns to the grid it came from.
        """
        item = self.itemAt(event.pos())
        if item is not None and self._owner._cull_grid:
            self._owner._cull_fullscreen_from_row(self.row(item))
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def resizeEvent(self, event):
        """A resize changes which rows are on screen, and since 0.18.4 rows
        are decorated lazily, the newly exposed ones must be filled in."""
        super().resizeEvent(event)
        owner = self._owner
        if hasattr(owner, '_cull_request_visible_thumbs'):
            owner._cull_request_visible_thumbs()


class _TransferDialog(QDialog):
    """Target folder, operation and scope in ONE dialog (0.18.5).

    Harald's two notes: the move path should be able to copy as well, and
    there should be an option to take only RAW + sidecar instead of the
    whole group. His wording for the first was that it must not become a
    third button - so it is a choice inside the dialog that "Move to…"
    already opens, and the plain folder picker is replaced by this.

    The scope choice is what makes it interesting: 0.18.2 FORCED the whole
    group because half a moved pair is worthless. That reasoning does not
    survive the user asking for the other half to stay behind on purpose,
    so the whole group stays the DEFAULT and the narrow scope is a
    deliberate, visible choice - never a silent one.
    """

    def __init__(self, parent, start_dir=''):
        super().__init__(parent)
        self.setWindowTitle(tr('Move or copy to folder') + f' - {APP_NAME}')
        self.setMinimumWidth(520)
        self.setStyleSheet(current_input_style())

        layout = QVBoxLayout(self)

        row = QHBoxLayout()
        row.addWidget(QLabel(tr('Destination folder:')))
        self.dest_edit = QLineEdit(start_dir or '')
        row.addWidget(self.dest_edit, 1)
        browse = QPushButton(tr('Browse…'))
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        layout.addLayout(row)

        op_box = QGroupBox(tr('Operation'))
        op_lay = QVBoxLayout(op_box)
        self.move_rb = QRadioButton(tr('Move (the files leave this folder)'))
        self.copy_rb = QRadioButton(tr('Copy (the files stay here as well)'))
        self.move_rb.setChecked(True)
        op_lay.addWidget(self.move_rb)
        op_lay.addWidget(self.copy_rb)
        layout.addWidget(op_box)

        scope_box = QGroupBox(tr('Which files'))
        scope_lay = QVBoxLayout(scope_box)
        self.group_rb = QRadioButton(
            tr('The whole group: RAW, JPEG and .xmp sidecar'))
        self.raw_rb = QRadioButton(tr('RAW and .xmp sidecar only'))
        self.group_rb.setChecked(True)
        self.raw_rb.setToolTip(tr(
            'The JPEG of a pair stays behind. An entry without a RAW file '
            'still travels - there is no partner to leave.'))
        scope_lay.addWidget(self.group_rb)
        scope_lay.addWidget(self.raw_rb)
        layout.addWidget(scope_box)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok
                                   | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._ok_btn = buttons.button(QDialogButtonBox.Ok)

    def _browse(self):
        start = self.dest_edit.text().strip()
        chosen = QFileDialog.getExistingDirectory(
            self, tr('Move or copy to folder'), start)
        if chosen:
            self.dest_edit.setText(chosen)

    def _accept_if_valid(self):
        """An OK with a folder that is not there would fail one file at a
        time in the worker; refuse it here instead."""
        dest = self.dest_edit.text().strip()
        if not dest or not os.path.isdir(dest):
            QMessageBox.warning(self, tr('Move or copy to folder'), tr(
                'Pick a folder that exists.'))
            return
        self.accept()

    def result_values(self):
        """(dest, move, scope) - only meaningful after accept()."""
        return (self.dest_edit.text().strip(),
                self.move_rb.isChecked(),
                culling.SCOPE_RAW if self.raw_rb.isChecked()
                else culling.SCOPE_GROUP)


class _TabBarDropSwitcher(QObject):
    """Event filter for the tab bar: hovering a tab during a drag switches to
    it, so a drag from the culling strip can reach the Files tab.

    MUST be a QObject: as a QWidget (pre-fix) it became an invisible child
    widget of default size at (0,0) of the tab bar, sitting ON TOP of the
    leftmost tabs and swallowing their mouse clicks - Files and FTP were not
    clickable."""

    def __init__(self, tabs):
        super().__init__(tabs)
        self._tabs = tabs
        bar = tabs.tabBar()
        bar.setAcceptDrops(True)
        bar.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() in (event.DragEnter, event.DragMove):
            event.accept()
            idx = self._tabs.tabBar().tabAt(event.pos())
            if idx >= 0 and idx != self._tabs.currentIndex():
                self._tabs.setCurrentIndex(idx)
            return True
        return False


class _MetadataReader(QThread):
    """Reads rating/label of all items in the background after a folder scan.

    0.18.4, both changes measured rather than guessed:

    * The reads run in a small thread pool. Every read is file I/O (the head
      of a sidecar or JPEG), so the GIL is released and threads actually
      overlap. On a warm local SSD the gain is modest; on a card reader,
      where per-file latency dominates the transfer, it is the point.
    * Results are emitted in BATCHES. One signal per item meant one queued
      cross-thread event and one row decoration per file; measured on 800
      rows that path cost 0.52 s of GUI thread against 0.002 s for the same
      work done in one pass. Over a 3000-image card it was seconds of
      stutter for rows that are mostly off screen anyway.
    """
    items_ready = pyqtSignal(list)    # indices into the item list
    done = pyqtSignal(int)            # count

    #: how many results are collected before the GUI hears about them, and
    #: how long a partial batch may wait. The first screenful must appear
    #: immediately, so the very first batch is deliberately small.
    BATCH = 64
    FIRST_BATCH = 12
    MAX_WAIT = 0.15                   # seconds
    WORKERS = 8

    def __init__(self, items):
        super().__init__()
        self.items = items
        self._stop = False

    def stop(self):
        self._stop = True

    def _read(self, pair):
        i, item = pair
        if self._stop:
            return None
        try:
            culling.read_item_metadata(item)
        except Exception:
            pass                       # unreadable file: keep defaults
        return i

    def run(self):
        n = 0
        pending = []
        last = time.monotonic()
        limit = self.FIRST_BATCH
        # chunksize=1 on purpose: the pool must not hand one worker a
        # contiguous block, or the first screenful waits for the last file
        # in that block.
        with ThreadPoolExecutor(max_workers=self.WORKERS) as pool:
            for i in pool.map(self._read, enumerate(self.items),
                              chunksize=1):
                if i is None:          # stop() was seen
                    continue
                n += 1
                pending.append(i)
                now = time.monotonic()
                if len(pending) >= limit or now - last >= self.MAX_WAIT:
                    self.items_ready.emit(pending)
                    pending = []
                    last = now
                    limit = self.BATCH
        if pending:
            self.items_ready.emit(pending)
        self.done.emit(n)


class _FolderCopyWorker(QThread):
    """Copies files to a local folder off the GUI thread (large RAW batches
    must not freeze the UI). Mirrors the FtpUploadWorker interface: progress
    per file, cancel between files, a summary at the end. Existing target
    files are SKIPPED (never overwritten - an exported copy may have been
    edited meanwhile)."""
    file_started = pyqtSignal(int, str)    # index, filename
    progress = pyqtSignal(int, str)        # index, status text
    error = pyqtSignal(int, str)           # index, message
    done = pyqtSignal(str)                 # summary (QThread.finished stays
    #                                        untouched under its own name)

    def __init__(self, paths, dest_dir, logger, edit_map=None, move=False):
        super().__init__()
        self.paths = paths
        self.dest_dir = dest_dir
        self.log = logger
        # 0.18.2: the same worker MOVES when asked to. Deliberately not a
        # second class - progress, cancel and the summary are identical and
        # would have drifted apart. Two differences, both in run():
        # shutil.move instead of copy2, and no rendered "_edit.jpg" export,
        # because moving must not turn Harald's original into a rendering.
        self.move = move
        self.moved = []
        # 0.13: {source_path: record}. A file with an edit is exported as a
        # rendered "<stem>_edit.jpg" copy (Harald's choice); everything else
        # is a plain copy2. Sidecars are never edited.
        self.edit_map = edit_map or {}
        self._cancelled = False

    def cancel(self):
        self._cancelled = True
        self.log.info('Folder copy cancel requested: stopping after the '
                      'current file.')

    def run(self):
        total = len(self.paths)
        self.log.info('=== %s to "%s" started: %d file(s) ===',
                      'Move' if self.move else 'Copy', self.dest_dir, total)
        ok = skipped = failed = 0
        cancelled_at = None
        for i, path in enumerate(self.paths):
            if self._cancelled:
                cancelled_at = i
                self.progress.emit(i, tr('Cancelled'))
                break
            name = os.path.basename(path)
            self.file_started.emit(i, name)
            record = None if self.move else self.edit_map.get(path)
            if record:
                name = edits.export_name(path)
            target = os.path.join(self.dest_dir, name)
            try:
                if os.path.exists(target):
                    skipped += 1
                    self.progress.emit(i, '\u2022 ' + tr('Skipped (exists)'))
                    continue
                if record:
                    rendered = edits.render_edited(path, record, target,
                                                   self.log)
                    if not rendered:
                        # Rendering failed - fall back to the untouched
                        # original rather than exporting nothing.
                        shutil.copy2(path, os.path.join(
                            self.dest_dir, os.path.basename(path)))
                elif self.move:
                    shutil.move(path, target)
                    self.moved.append(path)
                else:
                    shutil.copy2(path, target)
            except Exception as e:
                failed += 1
                self.log.error('✗ %s failed for "%s": %s',
                               'Move' if self.move else 'Copy', name, e,
                               exc_info=True)
                self.error.emit(i, f'{name}: {e}')
                self.progress.emit(i, '✗ ' + tr('Error'))
                continue
            ok += 1
            self.progress.emit(
                i, '✓ ' + (tr('Moved') if self.move else tr('Copied')))
        if cancelled_at is not None:
            summary = (tr('Cancelled: {ok}/{total} file(s) moved, '
                          '{n} not started.') if self.move else
                       tr('Cancelled: {ok}/{total} file(s) copied, '
                          '{n} not started.')).format(
                ok=ok, total=total, n=total - cancelled_at)
        else:
            summary = ((tr('Done: {ok}/{total} file(s) moved') if self.move
                        else tr('Done: {ok}/{total} file(s) copied')).format(
                           ok=ok, total=total)
                       + (', ' + tr('{n} skipped (already there)').format(
                              n=skipped) if skipped else '')
                       + (', ' + tr('{n} failed').format(n=failed)
                          if failed else '') + '.')
        self.log.info('=== %s finished: %s ===',
                      'Move' if self.move else 'Copy', summary)
        self.done.emit(summary)



class _CameraImportWorker(QThread):
    """Copies files off a PTP camera into a local folder, off the GUI thread.

    Same signal shape as _FolderCopyWorker so the existing progress dialog
    can drive it unchanged. The listing step is in here too: walking the
    card's folders costs a round trip per file for the size, which is far
    too slow for the GUI thread.
    """
    listing = pyqtSignal(int)              # files seen while walking the card
    ready = pyqtSignal(int)                # how many will actually be copied
    file_started = pyqtSignal(int, str)    # index, filename
    progress = pyqtSignal(int, str)        # index, status text
    fatal = pyqtSignal(str)                # nothing could be done
    done = pyqtSignal(str)                 # summary

    def __init__(self, device, dest_dir, logger):
        super().__init__()
        self.device = device
        self.dest_dir = dest_dir
        self.log = logger
        self.copied = 0
        self._cancelled = False

    def cancel(self):
        self._cancelled = True
        self.log.info('Camera import cancel requested: stopping after the '
                      'current file.')

    def run(self):
        backend = None
        try:
            backend = camera.make_backend()
            backend.connect(self.device)
            files = backend.list_files(progress=self.listing.emit)
            existing = camera.scan_dest(self.dest_dir)
            todo, skipped, conflicts = camera.plan_import(files, existing)
            self.log.info(
                '=== Camera import from "%s" to "%s": %d file(s) on the '
                'card, %d to copy, %d already there, %d name clash(es) ===',
                self.device.name if self.device else '?', self.dest_dir,
                len(files), len(todo), len(skipped), len(conflicts))
            for name in [f.name for f in conflicts][:12]:
                self.log.warning('Name clash, left alone: %s', name)
            self.ready.emit(len(todo))
        except camera.CameraError as exc:
            self.fatal.emit(str(exc))
            self.done.emit('')
            if backend is not None:
                backend.close()
            return
        except Exception as exc:                      # pragma: no cover
            self.log.error('Camera import failed before copying: %s', exc,
                           exc_info=True)
            self.fatal.emit(str(exc))
            self.done.emit('')
            if backend is not None:
                backend.close()
            return

        failed = 0
        cancelled_at = None
        try:
            for i, cfile in enumerate(todo):
                if self._cancelled:
                    cancelled_at = i
                    self.progress.emit(i, tr('Cancelled'))
                    break
                self.file_started.emit(i, cfile.name)
                target = os.path.join(self.dest_dir, cfile.name)
                try:
                    backend.download(cfile, target)
                except Exception as exc:
                    failed += 1
                    self.log.error('Camera import failed for "%s": %s',
                                   cfile.name, exc, exc_info=True)
                    self.progress.emit(i, '\u2717 ' + str(exc))
                    continue
                self.copied += 1
                self.progress.emit(i, '\u2713 ' + camera.format_size(
                    cfile.size))
        finally:
            backend.close()

        summary = camera.summary_text(self.copied, len(skipped), failed,
                                      len(conflicts),
                                      cancelled=cancelled_at is not None)
        self.log.info('=== Camera import finished: %s ===', summary)
        self.done.emit(summary)


class _CullTab(QWidget):
    """Plain container that forwards its key events to the mixin."""
    def __init__(self, owner):
        super().__init__()
        self._owner = owner
        self.setFocusPolicy(Qt.StrongFocus)

    def keyPressEvent(self, event):
        if not self._owner._cull_key(event):
            super().keyPressEvent(event)


class MWCullingMixin:

    # ── Tab construction ──────────────────────────────────────────────────────

    def _build_culling_tab(self):
        self._cull_items = []          # all items of the folder
        self._cull_visible = []        # after filtering
        self._cull_index = -1
        self._cull_direction = 1
        self._cull_number_mode = 'rating'      # or 'color'
        self._cull_grid = False
        # 0.18.4: set when fullscreen was entered from the grid.
        self._cull_fs_from_grid = False
        self._cull_fs = None
        self._cull_show_exif = False   # i key: EXIF overlay on/off
        self._cull_row_by_path = {}
        self._cull_row_by_item = {}
        self._cull_reader = None
        self._cull_wb = culling.WriteBehind(self.logger)
        self._cull_loader = previews.PreviewLoader()
        self._cull_loader.signals.loaded.connect(self._cull_on_loaded)
        self._cull_loader.signals.failed.connect(self._cull_on_failed)
        # 0.15.0: watchdog for previews that never arrive. Until now every
        # lost image was final - a decode error only reached the log, an
        # entry evicted from the cache between "loaded" and the handler made
        # the handler do nothing at all, and a job cancelled by a folder
        # change returned without any signal at all. Nothing ever asked
        # again, so the view stayed blank until the user navigated away and
        # came back. This timer asks again.
        self._cull_retry_timer = QTimer(self)
        self._cull_retry_timer.setSingleShot(True)
        self._cull_retry_timer.timeout.connect(self._cull_retry_current)
        self._cull_retry_left = 0
        self._cull_failed_paths = set()
        # 0.15.0: undo for IMAGE EDITS only (crop, exposure, white balance).
        # Every writing path calls _cull_remember_edit() BEFORE it changes
        # anything, so the stack holds the state to go back to.
        self._cull_undo = edits.EditHistory()

        w = _CullTab(self)
        # 0.15.0: Ctrl+Z / Cmd+Z for the image edits. Scoped to the culling
        # page on purpose (WidgetWithChildrenShortcut): a window-wide undo
        # would swallow the built-in undo of every text field in the other
        # tabs. QKeySequence.Undo already means Cmd+Z on macOS.
        self._cull_undo_sc = QShortcut(QKeySequence.Undo, w)
        self._cull_undo_sc.setContext(Qt.WidgetWithChildrenShortcut)
        self._cull_undo_sc.activated.connect(self._cull_undo_edit)
        outer = QVBoxLayout(w)

        # Toolbar - deliberately slim (0.12.4): tight margins and a fixed,
        # short control height, so the bar costs as little vertical room as
        # possible and the images get the space.
        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 2)
        bar.setSpacing(6)
        open_btn = QPushButton(tr('Open…'))
        open_btn.setToolTip(tr('Open a folder of images for culling.'))
        open_btn.clicked.connect(self._cull_open_folder)
        bar.addWidget(open_btn)
        # Reload sits right next to Open as a compact icon button. The ⟳ glyph
        # is tiny at the default font size, so scale it up to button height.
        self.cull_reload_btn = QToolButton()
        # The "⟳" glyph rendered as a barely-visible hairline (and as tofu in
        # some font fallbacks), so use the platform's own reload icon and keep
        # a text label as the fallback when a style has no such icon.
        _reload_icon = self.style().standardIcon(QStyle.SP_BrowserReload)
        if _reload_icon.isNull():
            self.cull_reload_btn.setText(tr('Reload'))
        else:
            self.cull_reload_btn.setIcon(_reload_icon)
            self.cull_reload_btn.setIconSize(QSize(18, 18))
        self.cull_reload_btn.setMinimumSize(32, 28)
        self.cull_reload_btn.setToolTip(tr('Read the current folder again from disk.'))
        self.cull_reload_btn.clicked.connect(self._cull_reload_folder)
        bar.addWidget(self.cull_reload_btn)
        # 0.18.3: Canon bodies speak PTP, so the card never becomes a volume
        # and "Open…" has nothing to point at. This is the backup path for a
        # missing card reader: copy off the camera, then open the copy.
        cam_btn = QPushButton(tr('From camera…'))
        cam_btn.setToolTip(tr(
            'Copy pictures straight off a connected camera into a folder and '
            'open that folder.\nMeant as the backup when no card reader is '
            'at hand - a reader is considerably faster.'))
        cam_btn.clicked.connect(self._cull_import_from_camera)
        bar.addWidget(cam_btn)
        self.cull_camera_btn = cam_btn
        # 0.18.7: both settings sit next to the folder actions they change,
        # and both are remembered - a card is opened the same way every time
        # or the automatic opening would be a surprise rather than a help.
        self.cull_subfolders_cb = QCheckBox(tr('subfolders'))
        self.cull_subfolders_cb.setToolTip(tr(
            'Also read the subfolders of the folder that is opened. A full '
            'card holds\n100EOSR5, 101EOSR5 and so on, so a card needs '
            'this; a working folder\nusually does not.'))
        self.cull_subfolders_cb.setChecked(
            self.settings.value('cull_subfolders', False, type=bool))
        self.cull_subfolders_cb.stateChanged.connect(
            lambda _s: self.settings.setValue(
                'cull_subfolders', self.cull_subfolders_cb.isChecked()))
        bar.addWidget(self.cull_subfolders_cb)
        self.cull_autocard_cb = QCheckBox(tr('open cards'))
        self.cull_autocard_cb.setToolTip(tr(
            'Opens a memory card by itself as soon as it is plugged in, '
            'subfolders and all.\nA volume counts as a card when it has a '
            'DCIM folder. Whatever was open\nbefore is replaced, so turn '
            'this off while working from a card.'))
        self.cull_autocard_cb.setChecked(
            self.settings.value('cull_autocard', True, type=bool))
        self.cull_autocard_cb.stateChanged.connect(self._cull_autocard_toggled)
        bar.addWidget(self.cull_autocard_cb)
        # 0.18.11: sort order. Free, because the file time comes out of the
        # directory entry the scan reads anyway - see culling.ORDER_TIME.
        bar.addWidget(QLabel(tr('Order:')))
        self.cull_order_combo = QComboBox()
        self.cull_order_combo.addItem(tr('file name'), culling.ORDER_NAME)
        self.cull_order_combo.addItem(tr('time taken'), culling.ORDER_TIME)
        self.cull_order_combo.setToolTip(tr(
            'Time taken is the file time the camera wrote, not the EXIF '
            'field:\nreading EXIF would mean opening every RAW on the card. '
            'On a card\nstraight from the camera the two are the same.'))
        saved = self.settings.value('cull_order', culling.ORDER_NAME,
                                    type=str)
        idx = self.cull_order_combo.findData(saved)
        self.cull_order_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.cull_order_combo.currentIndexChanged.connect(
            lambda _i: self._cull_order_changed())
        bar.addWidget(self.cull_order_combo)
        self.cull_mode_lbl = QLabel()
        self.cull_mode_lbl.setToolTip(tr('Number keys 1-5 set stars or colors; '
                                      'M toggles the mode.'))
        bar.addWidget(self.cull_mode_lbl)
        # Zoom (wheel / Cmd+-), the view modes (E loupe, G grid, F fullscreen)
        # and the folder actions all live on the keyboard and in the View
        # menu now - the toolbar only keeps what needs a widget.
        # The filter cluster is CENTRED between two separators: stretch on
        # both sides pushes the folder actions left and the hand-off actions
        # right (0.12.5).
        bar.addStretch(1)
        bar.addWidget(toolbar_separator())
        bar.addWidget(QLabel(tr('Filter:')))
        # Minimum rating as STARS, not a dropdown (Harald): click a star to
        # show that rating and up, click the active star again for "all".
        self._cull_minrating = 0
        self.cull_star_btns = []
        for n in range(1, 6):
            b = QToolButton()
            b.setText('★')
            b.setCheckable(True)
            b.setAutoRaise(True)
            b.setFixedSize(22, 22)
            # Fixed-size square: opt out of the common horizontal padding
            # (constants.BUTTON_STYLE), which would clip the glyph.
            b.setProperty('cammelloCompact', True)
            b.setToolTip(tr('Show only images with {n} stars or more '
                            '(click again for all).').format(n=n))
            b.clicked.connect(lambda _c, n=n: self._cull_set_min_rating(n))
            self.cull_star_btns.append(b)
            bar.addWidget(b)
        self._cull_update_stars()
        # 0.12.7 (Harald's decision): rejects stay VISIBLE by default - grey
        # with a red X, courtesy of _LabelBarDelegate - instead of vanishing
        # from the strip. The checkbox is therefore INVERTED: it now hides
        # them, and starts unchecked. Renamed rather than reused with the
        # opposite meaning, because a `cull_rejects_cb` that means "hide"
        # would mislead every later reader (and every later test).
        self.cull_hide_rejects_cb = QCheckBox(tr('hide rejects'))
        self.cull_hide_rejects_cb.setToolTip(
            tr('Rejected images are shown greyed out with a red X. Check '
               'this to hide them completely.'))
        self.cull_hide_rejects_cb.stateChanged.connect(self._cull_apply_filter)
        bar.addWidget(self.cull_hide_rejects_cb)
        # Colour filter: multi-select swatches, part of the same filter cluster.
        # None active = all colours; any active = only those colours (grey
        # swatch = "no label"). Each swatch's tooltip names the colour.
        bar.addSpacing(8)
        self._cull_color_btns = []
        swatches = list(culling.LABEL_COLORS) + ['#888']   # last = no label
        for i, col in enumerate(swatches):
            b = QToolButton()
            b.setCheckable(True)
            b.setFixedSize(20, 20)
            # Frame/checked marker come from constants.BUTTON_STYLE
            # (cammelloSwatch); only the fill is per-swatch. The rule needs
            # to stay a widget stylesheet because the colour differs per
            # button - but it no longer duplicates the chrome.
            b.setProperty('cammelloSwatch', True)
            b.setProperty('cammelloCompact', True)
            # The :checked variant must be repeated here: the generic
            # "pressed/checked = blue" rule in BUTTON_STYLE would otherwise
            # win over a plain QToolButton rule and paint the swatch blue.
            b.setStyleSheet(f'QToolButton, QToolButton:checked,'
                            f' QToolButton:hover, QToolButton:pressed'
                            f' {{background:{col};}}')
            b.setToolTip(tr('no label') if i == len(swatches) - 1
                         else tr('colour {n}').format(n=i + 1))
            b.clicked.connect(self._cull_apply_filter)
            self._cull_color_btns.append(b)
            bar.addWidget(b)
        bar.addWidget(toolbar_separator())
        bar.addStretch(1)      # second half of the centring pair
        # "Apply" (Übernehmen) hands the selection (or all filtered images) to
        # the MediaWiki tab AND the IPTC tab AND the FTP tab's list at once (the
        # three share one file list; nothing is uploaded yet). "Export…"
        # (folder export) stays a separate action.
        apply_btn = QPushButton(tr('Add to tabs'))
        apply_btn.setToolTip(tr('Adds the selected images (or all filtered '
                                'images when nothing is selected) to the '
                                'MediaWiki, IPTC and FTP tabs. Nothing is '
                                'uploaded yet.'))
        apply_btn.clicked.connect(self._cull_apply)
        bar.addWidget(apply_btn)
        # 0.18.5: back to "Export" (Harald's own note) - "Save to…" read as
        # if it saved the app's state, which it never did.
        to_folder_btn = QPushButton(tr('Export…'))
        to_folder_btn.setToolTip(
            tr('Copies the selected images into a local folder. RAW files bring '
            'their .xmp sidecar along; existing files in the target folder '
            'are never overwritten.'))
        to_folder_btn.clicked.connect(self._cull_to_folder)
        bar.addWidget(to_folder_btn)
        move_btn = QPushButton(tr('Move to…'))
        move_btn.setToolTip(tr(
            'Moves or copies the selected images into a local folder. The '
            'dialog asks\nwhich of the two, and whether to take the whole '
            'group (RAW, JPEG and\n.xmp sidecar) or RAW + sidecar only. '
            'Nothing in the target folder is\never overwritten.'))
        move_btn.clicked.connect(self._cull_move_to_folder)
        bar.addWidget(move_btn)
        slim_toolbar(bar)
        outer.addLayout(bar)

        split = QSplitter(Qt.Vertical)
        self.cull_view = CullImageView()
        # Crop store (0.13): loaded once, kept in memory, saved on each edit.
        self._cull_edits = edits.load_edits(self.settings)
        # 0.14.1: persisting is debounced. save_edits() forces a settings
        # sync (full JSON dump + disk flush); doing that on EVERY sixth-stop
        # keypress meant a dozen flushes for one +2 EV correction. A short
        # timer batches them; folder change and shutdown flush explicitly.
        self._cull_edits_timer = QTimer(self)
        self._cull_edits_timer.setSingleShot(True)
        self._cull_edits_timer.setInterval(400)
        self._cull_edits_timer.timeout.connect(self._cull_flush_edits)
        # 0.14.2: same idea for the on-screen tone preview - holding +/-
        # would otherwise queue one full-image pass per keypress.
        self._cull_tone_timer = QTimer(self)
        self._cull_tone_timer.setSingleShot(True)
        self._cull_tone_timer.setInterval(90)
        self._cull_tone_timer.timeout.connect(self._cull_flush_tone)
        self._cull_tone_pending = None
        self._cull_cropping = False
        self.cull_edit_panel = EditPanel(self.cull_view)
        self.cull_view.edit_panel = self.cull_edit_panel
        self.cull_edit_panel.crop_requested.connect(self._cull_toggle_crop)
        self.cull_edit_panel.pipette_toggled.connect(self._cull_set_pipette)
        self.cull_edit_panel.ev_step_requested.connect(self._cull_step_ev)
        self.cull_edit_panel.reset_requested.connect(self._cull_reset_edits)
        self.cull_view.pixel_picked.connect(self._cull_wb_from_pixel)
        self.cull_view.crop.changed.connect(self._cull_update_crop_readout)
        self.cull_view.crop.committed.connect(
            lambda *_a: None)   # commit is driven from the tab (Enter key)
        self.cull_view.zoom_requested.connect(self._cull_request_full)
        self.cull_view.fullscreen_requested.connect(
            self._cull_toggle_fullscreen)
        self.cull_view.zoom_changed.connect(self._cull_zoom_changed)
        split.addWidget(self.cull_view)

        self.cull_strip = _CullStrip(self)
        self.cull_strip.setViewMode(QListWidget.IconMode)
        self.cull_strip.setFlow(QListWidget.LeftToRight)
        self.cull_strip.setWrapping(False)
        self.cull_strip.setResizeMode(QListWidget.Adjust)
        self.cull_strip.setIconSize(QSize(128, 96))
        self.cull_strip.setMaximumHeight(172)
        self.cull_strip.setMovement(QListWidget.Static)
        self.cull_strip.setFocusPolicy(Qt.NoFocus)     # keys stay with the tab
        # 0.15.0: the same middle grey as the image view, so switching
        # between single image and grid does not change the surround the
        # photographs are judged against.
        self._cull_delegate = _LabelBarDelegate(self.cull_strip)
        self._cull_delegate.set_dark(self._is_dark_scheme())
        self._cull_apply_bg(self._is_dark_scheme())
        self.cull_strip.setItemDelegate(self._cull_delegate)
        self.cull_strip.currentRowChanged.connect(self._cull_show_index)
        self.cull_strip.itemSelectionChanged.connect(self._cull_set_status)
        # Thumbs are loaded lazily for the visible range only (3000 eager
        # decode jobs at folder open starved the GUI).
        self.cull_strip.horizontalScrollBar().valueChanged.connect(
            lambda _v: self._cull_request_visible_thumbs())
        self.cull_strip.verticalScrollBar().valueChanged.connect(
            lambda _v: self._cull_request_visible_thumbs())
        split.addWidget(self.cull_strip)
        split.setSizes([620, 172])
        self._cull_split = split
        outer.addWidget(split, 1)

        self.cull_status = QLabel(tr('No folder open. Open one to start culling.'))
        outer.addWidget(self.cull_status)

        # Keyboard stays with the tab: no child may take focus.
        for child in w.findChildren(QWidget):
            if child is not w:
                child.setFocusPolicy(Qt.NoFocus)

        self._cull_update_mode_label()
        self._cull_start_card_watch()
        return w

    def _build_culling_settings_box(self):
        """Culling section of the Settings tab. Built BEFORE the culling tab
        (the culling code reads these widgets)."""
        box = QGroupBox(tr('Culling'))
        form = QFormLayout(box)

        self.cull_advance_cb = QCheckBox(
            tr('Advance to the next image after rating/labeling'))
        self.cull_advance_cb.setChecked(True)
        form.addRow(tr('Auto-advance:'), self.cull_advance_cb)

        self.cull_labelset_combo = QComboBox()
        self.cull_labelset_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.cull_labelset_combo.addItems(sorted(culling.LABEL_SETS))
        self.cull_labelset_combo.setToolTip(
            tr('Language of the label TEXT written to XMP - must match the color '
            'label set of your Lightroom, or LR shows the label in white.'))
        form.addRow(tr('Color label set:'), self.cull_labelset_combo)

        self.cull_pair_combo = QComboBox()
        self.cull_pair_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.cull_pair_combo.addItems(
            [tr('pair: JPEG'), tr('pair: RAW'), tr('pair: both')])
        self.cull_pair_combo.setToolTip(
            tr('Which file of a RAW+JPEG pair goes to the file table (button and '
            'drag-and-drop).'))
        form.addRow(tr('RAW+JPEG pairs:'), self.cull_pair_combo)

        return box

    def _cull_save_settings(self):
        s = self.settings
        s.setValue('cull_auto_advance', self.cull_advance_cb.isChecked())
        s.setValue('cull_label_set', self.cull_labelset_combo.currentText())
        s.setValue('cull_pair_mode', self.cull_pair_combo.currentIndex())

    def _cull_load_settings(self):
        s = self.settings
        self.cull_advance_cb.setChecked(
            s.value('cull_auto_advance', True, type=bool))
        ls = s.value('cull_label_set', 'de')
        idx = self.cull_labelset_combo.findText(ls)
        if idx >= 0:
            self.cull_labelset_combo.setCurrentIndex(idx)
        self.cull_pair_combo.setCurrentIndex(
            int(s.value('cull_pair_mode', 0)))

    # ── Folder handling ───────────────────────────────────────────────────────

    def _cull_open_folder(self, folder=None, recursive=None):
        # Defensive: with pyexiv2 missing the culling tab (and its state)
        # was never built - degrade to a no-op instead of an AttributeError
        # (0.14.1; seen when the folder action is reached programmatically).
        if not hasattr(self, '_cull_reader'):
            return
        if not folder:
            folder = QFileDialog.getExistingDirectory(
                self, tr('Open folder'), remembered_dir(self.settings))
            if not folder:
                return
            remember_dir(self.settings, folder)
        if self._cull_reader is not None:
            self._cull_reader.stop()
            self._cull_reader.wait(2000)
        self._cull_wb.flush(10)
        self._cull_flush_edits()
        self._cull_loader.new_generation()

        t0 = time.monotonic()
        report = {}
        if recursive is None:
            recursive = self.cull_subfolders_cb.isChecked()
            # 0.18.10: a card is one shoot, not three folders. 100EOSR5 and
            # its successors are the camera's file-numbering housekeeping,
            # so opening any part of a card opens the whole card. Only when
            # the caller left the scope open - an explicit scope (reload,
            # the automatic card open) already knows what it wants.
            card = camera.card_scope(folder)
            if card:
                if os.path.normpath(card) != os.path.normpath(folder):
                    self.logger.info(
                        'Culling: "%s" is part of a card, opening the '
                        'whole card at "%s".', folder, card)
                    folder = card
                # Recursion is not optional here, whatever the checkbox
                # says: DCIM holds no pictures of its own, they are all one
                # level down in 100EOSR5 and its successors. Opening DCIM
                # flat found nothing at all (0.18.10, fixed here).
                recursive = True
        self._cull_items = culling.scan_folder(folder, report,
                                               recursive=recursive,
                                               order=self._cull_order())
        self._cull_folder = folder
        self._cull_recursive = recursive
        # Always logged, not just on demand: when a folder yields fewer
        # entries than expected, this line says whether files were skipped
        # (unknown extension) or folded into RAW+JPEG pairs.
        self.logger.info('Culling scan: %s', culling.scan_report_text(report))
        if not previews.raw_available():
            raw_only = sum(1 for i in self._cull_items
                           if i.raw_path and not i.jpg_path)
            if raw_only:
                self.logger.warning(
                    '%d RAW-only file(s) cannot be previewed: %s',
                    raw_only, previews.raw_unavailable_reason())
        self._cull_folders = sorted({
            os.path.dirname(i.display_path) for i in self._cull_items})
        if len(self._cull_folders) > 1:
            self.logger.info(
                'Culling: opened "%s", %d image(s) from %d folder(s): %s.',
                folder, len(self._cull_items), len(self._cull_folders),
                ', '.join(os.path.basename(f) for f in self._cull_folders))
        else:
            self.logger.info('Culling: opened "%s", %d image(s).',
                             folder, len(self._cull_items))

        # Ratings/labels arrive in the background, in batches (0.18.4).
        self._cull_meta_t0 = time.monotonic()
        # 0.18.11: the reader gets its OWN list. Its results come back as
        # indices, and re-sorting _cull_items under a running reader would
        # point every one of them at the wrong picture.
        self._cull_reader = _MetadataReader(list(self._cull_items))
        self._cull_reader.items_ready.connect(self._cull_meta_arrived)
        self._cull_reader.done.connect(self._cull_meta_done)
        self._cull_reader.start()

        self._cull_apply_filter()
        # 0.18.4: three numbers in the log, so "reading the card takes too
        # long" can be answered instead of guessed - the rows, the metadata
        # pass, and the moment the first screenful of thumbnails is actually
        # there. They are the three candidates, and only a real card can say
        # which one dominates.
        self.logger.info('Culling: folder ready in %.2f s (scan + rows).',
                         time.monotonic() - t0)
        first, last = self._cull_visible_range()
        if first is not None:
            self._cull_screenful_t0 = t0
            self._cull_screenful = {
                self._cull_visible[i].display_path
                for i in range(first, last + 1)}
        else:
            self._cull_screenful = set()

    def _cull_meta_done(self, count):
        self._cull_set_status()
        t0 = getattr(self, '_cull_meta_t0', None)
        if t0 is not None:
            self.logger.info(
                'Culling: ratings/labels for %d entry/entries read in '
                '%.2f s.', count, time.monotonic() - t0)

    def _cull_meta_arrived(self, indices):
        """A batch of items got their rating/label. Only rows on screen are
        redrawn now; the rest are marked dirty and decorated when they
        scroll into view - decorating 3000 invisible rows was pure cost."""
        decorated = getattr(self, '_cull_decorated', None)
        if decorated is None:
            return
        rows = []
        reader_items = self._cull_reader.items if self._cull_reader else []
        for index in indices:
            if index >= len(reader_items):
                continue
            item = reader_items[index]
            vis_idx = self._cull_row_by_item.get(id(item))
            if vis_idx is not None:
                decorated.discard(vis_idx)
                rows.append(vis_idx)
        if not rows:
            return
        first, last = self._cull_visible_range()
        if first is None:
            return
        for vis_idx in rows:
            if first <= vis_idx <= last:
                self._cull_decorate_row(vis_idx)

    def _cull_visible_range(self):
        """(first, last) row currently intersecting the viewport, or
        (None, None). Split out in 0.18.4 because two callers need it now:
        the thumbnail request and the lazy row decoration."""
        n = self.cull_strip.count()
        if not n:
            return None, None
        vp = self.cull_strip.viewport().rect()
        first = last = None
        for i in range(n):
            if self.cull_strip.visualItemRect(
                    self.cull_strip.item(i)).intersects(vp):
                if first is None:
                    first = i
                last = i
            elif first is not None:
                break
        if first is None:
            return None, None
        return first, last

    def _cull_decorate_visible(self, margin=24):
        """Decorate the rows on screen (plus a margin) that are not
        decorated yet.

        0.18.4: opening a folder used to decorate EVERY row up front -
        3000 rows of stars, labels, badges and tooltips built on the GUI
        thread before the window came back. Measured at roughly 0.65 ms a
        row, that is the visible part of "reading the card takes too long",
        and nearly all of it was spent on rows nobody was looking at.
        """
        first, last = self._cull_visible_range()
        if first is None:
            return
        n = self.cull_strip.count()
        done = getattr(self, '_cull_decorated', None)
        if done is None:
            done = self._cull_decorated = set()
        for i in range(max(0, first - margin), min(n, last + 1 + margin)):
            if i not in done:
                self._cull_decorate_row(i)

    def _cull_request_visible_thumbs(self, margin=24):
        """Request thumbs for the on-screen filmstrip/grid range plus a
        margin - never for the whole folder at once."""
        first, last = self._cull_visible_range()
        if first is None:
            return
        n = self.cull_strip.count()
        # Rows scrolled into view need their stars as much as their thumb,
        # and both callers fire from the same scroll signal.
        self._cull_decorate_visible(margin)
        for i in range(max(0, first - margin), min(n, last + 1 + margin)):
            self._cull_loader.request(self._cull_visible[i].display_path,
                                      'thumb',
                                      previews.PreviewLoader.P_THUMBS)

    # ── Filter and filmstrip ──────────────────────────────────────────────────

    def _cull_min_rating(self):
        return getattr(self, '_cull_minrating', 0)

    def _cull_set_min_rating(self, stars):
        """Star filter: `stars` (1-5) shows that rating and up; clicking the
        star that is already the threshold clears the filter (0 = all)."""
        self._cull_minrating = 0 if stars == self._cull_minrating else stars
        self._cull_update_stars()
        self._cull_apply_filter()

    def _cull_update_stars(self):
        """Fill the stars up to the current threshold."""
        for i, b in enumerate(getattr(self, 'cull_star_btns', []), start=1):
            active = i <= self._cull_minrating
            b.setChecked(active)
            b.setText('★' if active else '☆')

    def _cull_label_filter(self):
        """Selected colour swatches -> a set of label indices for
        culling.filter_items (0-4 = colours, -1 = no label), or None when no
        swatch is active (= all colours)."""
        btns = getattr(self, '_cull_color_btns', [])
        sel = set()
        for i, b in enumerate(btns):
            if b.isChecked():
                sel.add(-1 if i == len(btns) - 1 else i)
        return sel or None

    def _cull_apply_filter(self, *_a):
        current_item = (self._cull_visible[self._cull_index]
                        if 0 <= self._cull_index < len(self._cull_visible)
                        else None)
        self._cull_visible = culling.filter_items(
            self._cull_items,
            min_rating=self._cull_min_rating(),
            exclude_rejects=self.cull_hide_rejects_cb.isChecked(),
            label_indices=self._cull_label_filter())
        self.cull_strip.blockSignals(True)
        self.cull_strip.clear()
        cell = 230 if self._cull_grid else 152
        for item in self._cull_visible:
            li = QListWidgetItem(item.stem)
            li.setSizeHint(QSize(cell, cell))
            self.cull_strip.addItem(li)
        self.cull_strip.blockSignals(False)
        # O(1) lookups for thumb arrival and metadata arrival (the previous
        # list.index() per event was O(n^2) over a 3000-image folder).
        self._cull_row_by_path = {}
        self._cull_row_by_item = {}
        # 0.18.4: the maps are built for every row (cheap, dict writes), the
        # DECORATION is not - see _cull_decorate_visible().
        self._cull_decorated = set()
        for i, item in enumerate(self._cull_visible):
            self._cull_row_by_path.setdefault(item.display_path, i)
            self._cull_row_by_item[id(item)] = i
        self._cull_request_visible_thumbs()
        if not self._cull_visible:
            self._cull_index = -1
            self.cull_view.clear_image()
            self._cull_set_status()
            return
        try:
            idx = self._cull_visible.index(current_item)
        except ValueError:
            idx = 0
        self._cull_show_index(idx)

    def _cull_decorate_row(self, vis_idx):
        if not (0 <= vis_idx < self.cull_strip.count()):
            return
        # Bookkeeping lives HERE, not at the call sites: every path that
        # decorates a row (rating change, thumb arrival, scrolling) must
        # mark it, and a second hand-kept list would drift apart - the
        # sdc._ASSIGN_RE lesson.
        if not hasattr(self, '_cull_decorated'):
            self._cull_decorated = set()
        self._cull_decorated.add(vis_idx)
        item = self._cull_visible[vis_idx]
        li = self.cull_strip.item(vis_idx)
        pair = ' [P]' if item.is_pair else ''
        table = ' [T]' if item.in_table else ''
        # The delegate paints name, stars and color bar itself in fixed
        # geometry (item text is bottom-aligned by the style and collided
        # with everything placed near the bottom).
        li.setText('')
        li.setData(Qt.UserRole, item.label_color_index)
        li.setData(Qt.UserRole + 1, item.rating)
        li.setData(Qt.UserRole + 2, f'{item.stem}{pair}{table}')
        # Channel mark AT the image (0.12.6): the delegate paints a small
        # colored dot in the thumbnail corner - teal for Commons, orange for
        # commercial. The mark is path-based (channels.py); the culling item
        # may sit on the RAW while the mark was set on the staged JPEG, so
        # both paths of a pair are checked.
        mark = None
        if hasattr(self, '_channel_mark'):
            for cand in filter(None, (item.display_path,
                                      getattr(item, 'raw_path', None),
                                      getattr(item, 'jpg_path', None))):
                mark = self._channel_mark(cand)
                if mark:
                    break
        li.setData(Qt.UserRole + 3, mark)
        # Crop/edit badge (0.13): path-based, like the channel mark.
        li.setData(Qt.UserRole + 4,
                   edits.has_edit(self._cull_edits, item.display_path)
                   if hasattr(self, '_cull_edits') else False)
        tips = []
        # 0.18.10: with several folders in one strip the file name alone no
        # longer says where a picture is - two DCIM folders can hold the
        # same number.
        if len(getattr(self, '_cull_folders', ())) > 1:
            tips.append(tr('Folder: {name}').format(
                name=os.path.basename(os.path.dirname(item.display_path))))
        if item.is_pair:
            tips.append(tr('[P] RAW+JPEG pair (one picture, two files)'))
        if item.in_table:
            tips.append(tr('[T] already in the file table'))
        li.setToolTip('\n'.join(tips))
        thumb = self._cull_loader.cache.get('thumb', item.display_path)
        if thumb is not None:
            li.setIcon(QIcon(QPixmap.fromImage(thumb)))

    # ── Display ───────────────────────────────────────────────────────────────

    def _cull_show_index(self, idx):
        if not (0 <= idx < len(self._cull_visible)):
            return
        if idx != self._cull_index:
            self._cull_direction = 1 if idx >= self._cull_index else -1
        prev = self._cull_delegate.current_row
        self._cull_index = idx
        self._cull_delegate.current_row = idx
        if prev != idx:
            self.cull_strip.viewport().update()
        if self.cull_strip.currentRow() != idx:
            self.cull_strip.blockSignals(True)
            # NoUpdate: navigation moves the CURRENT marker without touching
            # the selection. setCurrentRow selects as a side effect, which
            # made "no selection" practically impossible after browsing and
            # broke the selection semantics of "Selection -> file table".
            self.cull_strip.selectionModel().setCurrentIndex(
                self.cull_strip.model().index(idx, 0),
                QItemSelectionModel.NoUpdate)
            self.cull_strip.blockSignals(False)
            self.cull_strip.scrollToItem(self.cull_strip.item(idx))
        item = self._cull_visible[idx]
        path = item.display_path
        # 0.18.8: carry the zoom to the next picture. Harald asked for it,
        # and it is what the zoom is FOR while culling - stepping through a
        # burst at 100% to see which frame is sharp. Kept as an on-screen
        # width and a relative centre, not as a scale factor: a factor only
        # means something against the pixmap it applies to, and the two
        # preview levels of one picture differ by about three (0.18.6).
        self._cull_sticky = (
            None if self.cull_view.is_fit
            else (self.cull_view.apparent_width(),
                  self.cull_view.relative_center()))
        # 0.14: show the picture the way the crop leaves it. The full frame
        # comes back the moment crop mode is entered, so the box can be
        # dragged further.
        self.cull_view.set_crop_display(self._cull_crop_for(path))
        # 0.14.2: white balance and exposure are set BEFORE the pixels
        # arrive, so the corrected version is what appears - no flash of
        # the uncorrected image on every image change.
        self._cull_apply_tone(immediate=True)
        img = self._cull_loader.cache.get('screen', path)
        if img is not None:
            self.cull_view.set_image(img)
            self._cull_restore_zoom()
        else:
            self.cull_view.clear_image()
            self._cull_loader.request(path, 'screen',
                                      previews.PreviewLoader.P_CURRENT)
            # Arm the watchdog: if the pixels are not on screen a moment
            # from now, ask again instead of leaving the view blank.
            self._cull_retry_left = CULL_RETRIES
            self._cull_retry_timer.start(CULL_RETRY_MS)
        self._cull_loader.prefetch_around(
            [i.display_path for i in self._cull_visible],
            idx, self._cull_direction)
        self._cull_set_status()
        self._cull_update_info_overlay()
        self._cull_update_edit_panel()

    def _cull_order(self):
        """The sort order the toolbar is set to."""
        combo = getattr(self, 'cull_order_combo', None)
        if combo is None:
            return culling.ORDER_NAME
        return combo.currentData() or culling.ORDER_NAME

    def _cull_order_changed(self):
        """Re-sort what is already open - no folder is read again.

        The entries are the same objects, so ratings, labels and everything
        the reader has already filled in survive; only their order changes.
        The picture that was on screen stays on screen.
        """
        order = self._cull_order()
        self.settings.setValue('cull_order', order)
        if not self._cull_items:
            return
        current = (self._cull_visible[self._cull_index]
                   if 0 <= self._cull_index < len(self._cull_visible)
                   else None)
        culling.sort_items(self._cull_items, order)
        self._cull_apply_filter()
        if current is not None:
            row = self._cull_row_by_item.get(id(current))
            if row is not None:
                self._cull_show_index(row)
        self.logger.info('Culling: order changed to %s.', order)

    def _cull_restore_zoom(self):
        """Re-apply the zoom carried over from the previous picture, once.

        Consumed on use: the next image change captures its own state, and
        leaving it lying around would re-zoom a view the user has since
        fitted by hand.
        """
        sticky = getattr(self, '_cull_sticky', None)
        if not sticky:
            return
        self._cull_sticky = None
        width, rel_center = sticky
        self.cull_view.set_apparent_width(width, rel_center)

    def _cull_on_loaded(self, key, level):
        if not (0 <= self._cull_index < len(self._cull_visible)):
            return
        current = self._cull_visible[self._cull_index]
        if level == 'screen' and key == current.display_path:
            img = self._cull_loader.cache.get('screen', key)
            if img is not None and (self.cull_view.is_fit
                                    or getattr(self, '_cull_sticky', None)):
                # The sticky case matters: the view is NOT fitted while the
                # pixels are on their way, so the old is_fit test alone left
                # a zoomed-in step showing nothing at all.
                self.cull_view.set_image(img)
                self._cull_restore_zoom()
                self._cull_retry_timer.stop()
            elif img is None:
                # 0.15.0: the signal carries only the path, and the entry can
                # be gone again by the time we look (byte-budgeted LRU, and
                # the prefetch keeps putting). Silently doing nothing here is
                # what left the view empty for good - ask again.
                self._cull_loader.request(
                    key, 'screen', previews.PreviewLoader.P_CURRENT)
        elif level == 'full' and key == current.display_path:
            img = self._cull_loader.cache.get('full', key)
            if img is not None and not self.cull_view.is_fit:
                self.cull_view.set_image(img, keep_view=True)
        elif level == 'thumb':
            i = self._cull_row_by_path.get(key)
            if i is not None:
                self._cull_decorate_row(i)
            pending = getattr(self, '_cull_screenful', None)
            if pending:
                pending.discard(key)
                if not pending:
                    self.logger.info(
                        'Culling: first screenful of thumbnails complete '
                        '%.2f s after opening.',
                        time.monotonic() - self._cull_screenful_t0)

    def _cull_apply_bg(self, dark):
        """Surround colour for image view and strip (0.15.0). One call site
        for both, so the two halves of the culling module cannot drift, and
        it follows the colour scheme: darker in the dark theme, lighter in
        the light one."""
        col = cull_bg(dark)
        self.cull_view.set_background(col)
        self.cull_strip.setStyleSheet(
            f'QListWidget {{background:{col}; border:none;}}')

    def _cull_on_failed(self, key, msg):
        """A preview could not be decoded. Logged as before, but no longer
        ONLY logged: the status line says so, and the watchdog stops for
        this file so it does not retry a file that cannot be read."""
        self.logger.error('Preview failed for "%s": %s',
                          os.path.basename(key), msg)
        self._cull_failed_paths.add(key)
        if (0 <= self._cull_index < len(self._cull_visible)
                and key == self._cull_visible[self._cull_index].display_path):
            self._cull_retry_timer.stop()
            self._cull_retry_left = 0
            self.statusBar().showMessage(
                tr('Preview could not be read: {name}').format(
                    name=os.path.basename(key)), 6000)

    def _cull_retry_current(self):
        """Watchdog: the current image still has no pixels - ask again.

        Covers every way a request could be lost without a signal (job
        cancelled by a folder change, cache entry evicted, a `loaded` that
        arrived while another image was current). Bounded by CULL_RETRIES so
        an unreadable file cannot spin."""
        if not (0 <= self._cull_index < len(self._cull_visible)):
            return
        path = self._cull_visible[self._cull_index].display_path
        if self.cull_view.has_image() or path in self._cull_failed_paths:
            return
        if self._cull_retry_left <= 0:
            self.logger.warning('Preview for "%s" did not arrive after %d '
                                'attempts.', os.path.basename(path),
                                CULL_RETRIES)
            return
        self._cull_retry_left -= 1
        self.logger.info('Preview for "%s" has not arrived; asking again.',
                         os.path.basename(path))
        img = self._cull_loader.cache.get('screen', path)
        if img is not None:
            self.cull_view.set_image(img)
            return
        self._cull_loader.request(path, 'screen',
                                  previews.PreviewLoader.P_CURRENT)
        self._cull_retry_timer.start(CULL_RETRY_MS)

    def _cull_request_full(self):
        """Click/Z zoom: swap in the unscaled preview when it arrives."""
        if 0 <= self._cull_index < len(self._cull_visible):
            self._cull_loader.request(
                self._cull_visible[self._cull_index].display_path,
                'full', previews.PreviewLoader.P_CURRENT)

    def _cull_set_status(self):
        total = len(self._cull_items)
        shown = len(self._cull_visible)
        pos = self._cull_index + 1 if self._cull_index >= 0 else 0
        item = (self._cull_visible[self._cull_index]
                if 0 <= self._cull_index < len(self._cull_visible) else None)
        detail = ''
        if item:
            stars = rating_marks(item.rating)
            # 0.18.10: with a whole card open the file name is ambiguous -
            # name the subfolder it came from, but only then.
            sub = ''
            if len(getattr(self, '_cull_folders', ())) > 1:
                sub = os.path.basename(
                    os.path.dirname(item.display_path)) + '/'
            detail = (f' — {sub}{os.path.basename(item.display_path)}'
                      f'{" [pair]" if item.is_pair else ""} {stars} '
                      f'{item.label}')
        text = (tr('{pos}/{shown} shown ({total} in folder)').format(
                    pos=pos, shown=shown, total=total) + detail)
        # Folder name up front (Harald, 0.12.10): with several cards or
        # shoots open in sequence, the counts alone do not say WHICH folder
        # they belong to. Name only, not the whole path - the path is in the
        # log and would push the picture details off the bar.
        folder = getattr(self, '_cull_folder', '')
        if folder:
            head = os.path.basename(os.path.normpath(folder))
            n_folders = len(getattr(self, '_cull_folders', ()))
            if n_folders > 1:
                head += ' (' + tr('{n} folders').format(n=n_folders) + ')'
            text = head + '  ·  ' + text
        n_sel = len(self.cull_strip.selectedItems())
        if n_sel:
            text += '  ·  ' + tr('{n} selected').format(n=n_sel)
        self.cull_status.setText(text)
        # Fullscreen overlay: running number, stars/X, and a dot in the label
        # color.
        if item is not None:
            stars = rating_marks(item.rating, empty=True)
            idx = item.label_color_index
            dot = (f'<span style="color:{culling.LABEL_COLORS[idx]};">'
                   f'&#11044;</span> ' if idx is not None else '')
            # Channel mark in the overlay too (0.12.6): same dot colors as
            # on the thumbnails; toggles with the whole overlay.
            mark = None
            if hasattr(self, '_channel_mark'):
                for cand in filter(None, (item.display_path,
                                          getattr(item, 'raw_path', None),
                                          getattr(item, 'jpg_path', None))):
                    mark = self._channel_mark(cand)
                    if mark:
                        break
            chan = ''
            if mark:
                color = (channels.COLOR_COMMONS
                         if mark == channels.MARK_COMMONS
                         else channels.COLOR_COMMERCIAL)
                chan = (f'&nbsp; <span style="color:{color};">'
                        f'&#11044;</span>')
            self.cull_view.set_overlay(
                f'{pos}/{shown} &nbsp; {dot}{stars}{chan}')
        else:
            self.cull_view.set_overlay('')

    def _cull_update_info_overlay(self):
        """EXIF overlay (i key): filename plus camera/lens/exposure summary,
        top-left of the image view. Reading one file's EXIF header via Pillow
        is fast enough to do synchronously on navigation. RAW-only items have
        no Pillow-readable EXIF; the overlay says so instead of hiding."""
        if not self._cull_show_exif:
            self.cull_view.show_info_overlay(False)
            return
        item = self._cull_current_item()
        if item is None:
            self.cull_view.show_info_overlay(False)
            return
        info = previews.read_exif_summary(item.display_path)
        lines = [f'<b>{os.path.basename(item.display_path)}</b>']
        if info:
            if 'camera' in info:
                lines.append(info['camera'])
            if 'lens' in info:
                lines.append(info['lens'])
            expo = '  ·  '.join(info[k] for k in
                                ('focal', 'aperture', 'shutter', 'iso')
                                if k in info)
            if expo:
                lines.append(expo)
            if 'captured' in info:
                lines.append(info['captured'])
        else:
            lines.append(tr('No EXIF data'))
        self.cull_view.set_info_overlay('<br>'.join(lines))
        self.cull_view.show_info_overlay(True)

    # ── Keyboard ──────────────────────────────────────────────────────────────

    def _cull_update_mode_label(self):
        mode = (tr('numbers = STARS') if self._cull_number_mode == 'rating'
                else tr('numbers = COLORS'))
        self.cull_mode_lbl.setText(f'[M] {mode}')

    def _cull_key(self, event):
        key = event.key()
        # Crop mode swallows the keys it needs; everything else falls through
        # to normal culling so rating a neighbouring image still works.
        if getattr(self, '_cull_cropping', False):
            if self._cull_crop_key(key, event):
                return
        if key == Qt.Key_C and not (event.modifiers() & Qt.ControlModifier):
            self._cull_toggle_crop()
            return
        if key == Qt.Key_F2:
            self._cull_rename_current()
            return
        if key == Qt.Key_W and not (event.modifiers() & Qt.ControlModifier):
            self._cull_set_pipette(not self.cull_view.pipette_active())
            return
        # Plain +/- change the exposure; WITH Ctrl/Cmd they stay the zoom
        # shortcuts, which they were long before this panel existed.
        _zoom_mods = Qt.ControlModifier | Qt.MetaModifier
        if key in (Qt.Key_Plus, Qt.Key_Equal) \
                and not (event.modifiers() & _zoom_mods):
            self._cull_step_ev(1)
            return
        if key == Qt.Key_Minus and not (event.modifiers() & _zoom_mods):
            self._cull_step_ev(-1)
            return
        if key == Qt.Key_Right:
            self._cull_step(+1)
        elif key == Qt.Key_Left:
            self._cull_step(-1)
        elif key in (Qt.Key_Down, Qt.Key_Up):
            # One ROW in the grid (exact column count from the layout),
            # one image in loupe view.
            step = self._cull_grid_columns() if self._cull_grid else 1
            self._cull_step(step if key == Qt.Key_Down else -step)
        elif key == Qt.Key_Home:
            if self._cull_visible:
                self._cull_show_index(0)
        elif key == Qt.Key_End:
            if self._cull_visible:
                self._cull_show_index(len(self._cull_visible) - 1)
        elif key == Qt.Key_I:
            self._cull_show_exif = not self._cull_show_exif
            self._cull_update_info_overlay()
        elif key == Qt.Key_M:
            self._cull_number_mode = ('color'
                                      if self._cull_number_mode == 'rating'
                                      else 'rating')
            self._cull_update_mode_label()
        elif key == Qt.Key_X:
            self._cull_set_rating(-1)
        elif Qt.Key_0 <= key <= Qt.Key_5:
            n = key - Qt.Key_0
            if self._cull_number_mode == 'rating':
                self._cull_set_rating(n)
            else:
                self._cull_set_label(n - 1 if n else None)
        elif Qt.Key_6 <= key <= Qt.Key_9:
            self._cull_set_label(key - Qt.Key_6)     # LR layout: 6-9 = red..blue
        elif key == Qt.Key_Z:
            self._cull_request_full()
            self.cull_view.toggle_zoom()
        elif key == Qt.Key_E:
            self._cull_loupe_view()
        elif (key in (Qt.Key_Plus, Qt.Key_Equal)
              and event.modifiers() & Qt.ControlModifier):
            # Qt maps macOS Cmd to ControlModifier, so this is Cmd+ on the
            # Mac and Ctrl+ elsewhere; Key_Equal covers layouts where '+'
            # needs Shift.
            self._cull_zoom_in()
        elif key == Qt.Key_Minus and event.modifiers() & Qt.ControlModifier:
            self._cull_zoom_out()
        elif key == Qt.Key_G:
            self._cull_toggle_grid()
        elif key == Qt.Key_F:
            self._cull_toggle_fullscreen()
        elif key == Qt.Key_Escape and self._cull_fs is not None:
            self._cull_toggle_fullscreen()
        elif key == Qt.Key_A and event.modifiers() & Qt.ControlModifier:
            # Ctrl+A (Windows/Linux) / Cmd+A (macOS, mapped to ControlModifier
            # by Qt): select every visible thumbnail.
            self.cull_strip.selectAll()
            self._cull_set_status()
        elif key == Qt.Key_D and event.modifiers() & Qt.ControlModifier:
            self.cull_strip.clearSelection()
            self._cull_set_status()
        else:
            return False
        return True

    def _cull_zoom_in(self):
        """Next ladder value ABOVE the current scale."""
        pct = self.cull_view.zoom_factor() * 100
        for step in ZOOM_STEPS:
            if step > pct + 0.5:
                self._cull_request_full()
                self.cull_view.set_zoom(step / 100.0)
                return

    def _cull_zoom_out(self):
        """Next ladder value BELOW the current scale."""
        pct = self.cull_view.zoom_factor() * 100
        for step in reversed(ZOOM_STEPS):
            if step < pct - 0.5:
                self.cull_view.set_zoom(step / 100.0)
                return

    def _cull_zoom_changed(self, factor):
        # The toolbar zoom read-out was removed in 0.12; keep the handler
        # tolerant so the signal (still emitted on wheel/keyboard zoom) is a
        # harmless no-op unless a label exists.
        lbl = getattr(self, 'cull_zoom_lbl', None)
        if lbl is not None:
            lbl.setText('Fit' if self.cull_view.is_fit
                        else f'{int(round(factor*100))} %')

    def _cull_set_grid(self, grid):
        """Grid = thumbnails fill the whole tab; loupe = image + filmstrip."""
        self._cull_grid = grid
        self.cull_view.setVisible(not grid)
        if grid:
            self.cull_strip.setWrapping(True)
            self.cull_strip.setMaximumHeight(16777215)
            self.cull_strip.setIconSize(QSize(192, 144))
        else:
            self.cull_strip.setWrapping(False)
            self.cull_strip.setMaximumHeight(172)
            self.cull_strip.setIconSize(QSize(128, 96))
        self._cull_apply_filter()
        # Keep the current image in view after the relayout.
        if 0 <= self._cull_index < self.cull_strip.count():
            self.cull_strip.scrollToItem(self.cull_strip.item(self._cull_index))

    # ── View modes (keyboard E/G/F and the View menu share these) ────────────

    def _cull_loupe_view(self):
        """Loupe view (E, Lightroom-style): leave fullscreen and grid, show
        the single image fitted to the window."""
        if self._cull_fs is not None:
            # E/G name the mode they want, so the 0.18.4 "return to the grid
            # you came from" must not overrule them.
            self._cull_fs_from_grid = False
            self._cull_toggle_fullscreen()
        if self._cull_grid:
            self._cull_set_grid(False)
        self.cull_view.fit()

    def _cull_toggle_grid(self):
        """Grid view (G): thumbnails instead of the large image. From
        fullscreen this leaves fullscreen first."""
        if self._cull_fs is not None:
            self._cull_fs_from_grid = False      # see _cull_loupe_view
            self._cull_toggle_fullscreen()
        self._cull_set_grid(not self._cull_grid)

    def _cull_fullscreen_from_row(self, row):
        """Double-click in the grid (0.18.4): show THAT picture fullscreen.

        The row is made current first, so fullscreen shows the picture that
        was double-clicked and not whatever was selected before.
        """
        if not (0 <= row < len(self._cull_visible)):
            return
        self._cull_show_index(row)
        if self._cull_fs is None:
            self._cull_toggle_fullscreen()

    def _cull_toggle_fullscreen(self):
        """Image-only fullscreen: the view is reparented into a borderless
        fullscreen window; keys keep working (same forwarding container).
        F or Esc leaves."""
        if self._cull_fs is None:
            # From the grid, F used to do nothing (looked broken): leave the
            # grid first, then go fullscreen. 0.18.4 remembers that it came
            # from the grid and puts it back on the way out - otherwise a
            # double-click into fullscreen quietly changes the view mode.
            self._cull_fs_from_grid = bool(self._cull_grid)
            if self._cull_grid:
                self._cull_set_grid(False)
            # 0.18.8: fullscreen does not edit, so a crop in progress is
            # ended (committing it silently would be worse) and the pipette
            # is put away before the panel goes.
            if getattr(self, '_cull_cropping', False):
                self._cull_crop_cancel()
            if self.cull_view.pipette_active():
                self.cull_view.set_pipette(False)
                self.cull_edit_panel.set_pipette_checked(False)
            fs = _CullTab(self)
            lay = QVBoxLayout(fs)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.addWidget(self.cull_view)
            # 0.18.9: taking the view out leaves a hole in the splitter. It
            # is only ever seen when something puts the main window in front
            # (macOS does, coming back from another program), but a hole is
            # exactly the "komische Ansicht" - so stand a label in it that
            # says what is going on and how to get out.
            self._cull_split.insertWidget(0, self._cull_fs_placeholder())
            self._cull_fs_ph.show()
            fs.showFullScreen()
            fs.setFocus()
            self._cull_fs = fs
            self._cull_fs_watch(True)
            self.cull_view.show_overlay(True)
            self._cull_set_status()          # fill the overlay
            self._cull_update_edit_panel()   # 0.18.8: hides it
            # 0.18.8: a fitted view refits to the new window; a ZOOMED view
            # keeps the size it had, so switching to fullscreen to look
            # closer does not throw the detail away.
            self._cull_keep_zoom_across_resize()
        else:
            self._cull_fs_watch(False)
            self._cull_fs.layout().removeWidget(self.cull_view)
            ph = getattr(self, '_cull_fs_ph', None)
            if ph is not None:
                ph.setParent(None)
                ph.deleteLater()
                self._cull_fs_ph = None
            self._cull_split.insertWidget(0, self.cull_view)
            self._cull_split.setSizes([620, 172])
            self._cull_fs.close()
            self._cull_fs = None
            self.cull_view.show_overlay(False)
            self._cull_tab_widget.setFocus()
            self._cull_keep_zoom_across_resize()
            self._cull_update_edit_panel()   # 0.18.8: brings it back
            if getattr(self, '_cull_fs_from_grid', False):
                self._cull_fs_from_grid = False
                self._cull_set_grid(True)
            # Coming back: the strip may have scrolled/emptied meanwhile.
            if 0 <= self._cull_index < self.cull_strip.count():
                self.cull_strip.scrollToItem(
                    self.cull_strip.item(self._cull_index))
            self._cull_request_visible_thumbs()

    def _cull_fs_placeholder(self):
        """The label that stands in the splitter while the view is away."""
        ph = QLabel(tr('Fullscreen is open on another window.\n'
                       'F or Esc there brings the picture back here.'))
        ph.setAlignment(Qt.AlignCenter)
        ph.setWordWrap(True)
        self._cull_fs_ph = ph
        return ph

    # ── Coming back from another application (0.18.9) ────────────────────────

    def _cull_fs_watch(self, on):
        """Watch for the app being activated while fullscreen is up.

        Harald, on macOS: switch from fullscreen to another program and
        back, and the view is a mess. The reason is that the fullscreen
        window is a SEPARATE, borderless top-level window, while the image
        view has been reparented into it - so the main window is standing
        there with a hole where the picture used to be. When macOS brings
        the application back it raises the main window, not the borderless
        one, and that hole is what you see.

        So: on every activation, put the fullscreen window back in front.
        """
        app = QApplication.instance()
        if app is None:
            return
        if on:
            if not getattr(self, '_cull_fs_hooked', False):
                app.applicationStateChanged.connect(self._cull_fs_app_state)
                self._cull_fs_hooked = True
        elif getattr(self, '_cull_fs_hooked', False):
            try:
                app.applicationStateChanged.disconnect(
                    self._cull_fs_app_state)
            except (TypeError, RuntimeError):
                pass
            self._cull_fs_hooked = False

    def _cull_fs_app_state(self, state):
        if state != Qt.ApplicationActive or self._cull_fs is None:
            return
        # Deferred by one turn of the event loop: macOS is still ordering
        # its own windows at this point, and raising into that loses.
        QTimer.singleShot(0, self._cull_fs_reassert)

    def _cull_fs_reassert(self):
        """Put the fullscreen window back in front, whole."""
        fs = self._cull_fs
        if fs is None:
            return
        if not fs.isFullScreen():
            # It can come back as an ordinary window; showFullScreen() is
            # what puts it over the menu bar again.
            fs.showFullScreen()
        fs.raise_()
        fs.activateWindow()
        fs.setFocus()
        # The view sat in a window that was not being composited; a fitted
        # picture is refitted in case the screen changed underneath it (an
        # external monitor unplugged while away is exactly that case).
        self._cull_keep_zoom_across_resize()
        self.cull_view.viewport().update()

    def _cull_keep_zoom_across_resize(self):
        """Entering or leaving fullscreen changes the viewport, not the
        picture (0.18.8).

        A fitted view has to be refitted - the window is a different size.
        A zoomed view must NOT be: the scale is still valid, because the
        pixmap did not change, and re-fitting would undo exactly the look
        the user went fullscreen for.
        """
        if self.cull_view.is_fit:
            self.cull_view.fit()

    def _cull_grid_columns(self):
        """Items per row in the wrapped grid, read off the ACTUAL layout
        (exact regardless of spacing/scrollbar math): the first item whose
        rectangle starts on a new y is the column count."""
        lw = self.cull_strip
        if lw.count() < 2:
            return 1
        y0 = lw.visualItemRect(lw.item(0)).y()
        for i in range(1, lw.count()):
            if lw.visualItemRect(lw.item(i)).y() != y0:
                return i
        return lw.count()

    def _cull_step(self, delta):
        if not self._cull_visible:
            return
        self._cull_show_index(
            max(0, min(len(self._cull_visible) - 1, self._cull_index + delta)))

    # ── No editing in fullscreen (0.18.8) ────────────────────────────────────

    def _cull_edits_locked(self):
        """True while the image-only fullscreen is up.

        Harald: "no edit in Full view". Fullscreen shows the picture and
        nothing else - the edit panel is not on screen, so crop, white
        balance and exposure would be changed blind, and the keys that do it
        (C, W, plain +/-) sit right next to the rating keys that fullscreen
        exists for. Ratings, labels, navigation and zoom keep working; only
        the things that change PIXELS are off.

        The guard sits in the actions, not in the key handler, so the
        floating panel cannot reach around it either.
        """
        return getattr(self, '_cull_fs', None) is not None

    def _cull_say_locked(self):
        """Say why nothing happened - a dead key with no explanation is
        worse than the key being there."""
        self.cull_view.set_info_overlay(
            tr('Editing is off in fullscreen \u2014 F or Esc to leave'))
        self.cull_view.show_info_overlay(True)
        QTimer.singleShot(2500, self._cull_update_info_overlay)

    # -- crop mode (0.13) --------------------------------------------------
    # Aspect presets on the number keys. Each entry is the ratio in its
    # LANDSCAPE form (width:height >= 1) or None for free. Pressing the same
    # number again flips the orientation to portrait and back - so one key
    # gives both 3:2 and 2:3 without spending a second key on it.
    ASPECT_PRESETS = {
        1: None,          # free
        2: 3 / 2,         # 3:2  <-> 2:3
        3: 4 / 3,         # 4:3  <-> 3:4
        4: 1 / 1,         # square (orientation flip is a no-op)
        5: 16 / 9,        # 16:9 <-> 9:16
        6: 5 / 4,         # 5:4  <-> 4:5
    }
    _ASPECT_KEYS = {
        Qt.Key_1: 1, Qt.Key_2: 2, Qt.Key_3: 3,
        Qt.Key_4: 4, Qt.Key_5: 5, Qt.Key_6: 6,
    }

    def _cull_rename_current(self):
        """F2: rename the current image ON DISK (0.14).

        Lightroom-style in the sense that matters here: you name the picture,
        not its parts - a RAW+JPEG pair and any .xmp sidecar are renamed
        together, so the item stays one item. Ratings, channel marks and
        edits are keyed by path, so they are moved across too; otherwise a
        renamed picture would lose its stars and its crop.
        """
        item = self._cull_current_item()
        if item is None:
            return
        old_display = item.display_path
        folder = os.path.dirname(old_display)
        stem = os.path.splitext(os.path.basename(old_display))[0]
        new_stem, ok = QInputDialog.getText(
            self, tr('Rename file'), tr('New name (without extension):'),
            text=stem)
        if not ok:
            return
        new_stem = (new_stem or '').strip()
        if not new_stem or new_stem == stem:
            return
        if any(ch in new_stem for ch in '/\\:*?"<>|'):
            QMessageBox.warning(self, tr('Rename file'),
                                tr('That name contains characters a file '
                                   'name cannot hold.'))
            return
        if culling.rename_stem_problem(new_stem):
            QMessageBox.warning(
                self, tr('Rename file'),
                tr('That name is reserved on Windows or ends with a dot '
                   'or space.'))
            return
        # A pure case change ("img" -> "IMG") is a legitimate rename. On a
        # case-insensitive file system (macOS default) the target "exists" -
        # it IS the source - so the collision check below must not fire for
        # it; os.rename handles the case change fine (0.14.1).
        case_only = new_stem.lower() == stem.lower()

        # Every file that belongs to this picture, with its extension.
        parts = [p for p in (item.raw_path, item.jpg_path) if p]
        sidecar = item.sidecar_path if item.raw_path else None
        if sidecar and os.path.exists(sidecar):
            parts.append(sidecar)
        planned = []
        for old in parts:
            new = os.path.join(folder,
                               new_stem + os.path.splitext(old)[1])
            collides = os.path.exists(new)
            if collides and case_only:
                try:                    # same inode = the source itself
                    collides = not os.path.samefile(old, new)
                except OSError:
                    pass
            if collides:
                QMessageBox.warning(
                    self, tr('Rename file'),
                    tr('A file called "{name}" already exists.').format(
                        name=os.path.basename(new)))
                return
            planned.append((old, new))

        done = []
        try:
            for old, new in planned:
                os.rename(old, new)
                done.append((old, new))
        except OSError as exc:
            # Put back whatever already moved, so a half-renamed picture
            # cannot survive the error.
            for old, new in reversed(done):
                try:
                    os.rename(new, old)
                except OSError:
                    pass
            self.logger.error('Rename failed for %s: %s', old_display, exc)
            QMessageBox.warning(self, tr('Rename file'),
                                tr('Renaming failed: {error}').format(
                                    error=str(exc)))
            return

        moved = dict(done)
        if item.raw_path:
            item.raw_path = moved.get(item.raw_path, item.raw_path)
        if item.jpg_path:
            item.jpg_path = moved.get(item.jpg_path, item.jpg_path)
        self._cull_migrate_paths(old_display, item.display_path)
        self.logger.info('Renamed %s -> %s (%d file(s))', stem, new_stem,
                         len(done))
        self._cull_rebuild_after_rename(old_display, item)

    def _cull_save_edits_soon(self):
        """Persist the edit store soon (debounced, 0.14.1). The in-memory
        dict is always current; only the QSettings write is deferred."""
        self._cull_edits_timer.start()

    def _cull_flush_edits(self):
        """Persist the edit store now; cancels a pending debounce."""
        self._cull_edits_timer.stop()
        edits.save_edits(self.settings, self._cull_edits)

    def _cull_migrate_paths(self, old_path, new_path):
        """Move the path-keyed records (edits, channel marks) to the new
        name. Ratings live in the file's own XMP and travel with it."""
        record = edits.get_edit(self._cull_edits, old_path)
        if record:
            self._cull_edits[edits.norm(new_path)] = record
            edits.clear_edit(self._cull_edits, old_path)
            self._cull_flush_edits()    # a rename must persist immediately
        marks = channels.load_marks(self.settings)
        mark = marks.get(channels.norm(old_path))
        if mark:
            marks[channels.norm(new_path)] = mark
            marks.pop(channels.norm(old_path), None)
            channels.save_marks(self.settings, marks)

    def _cull_rebuild_after_rename(self, old_path, item):
        """Refresh the strip row and the view for the renamed item."""
        self._cull_row_by_path.pop(old_path, None)
        row = self._cull_row_by_item.get(id(item))
        if row is None:
            return
        self._cull_row_by_path[item.display_path] = row
        if 0 <= row < self.cull_strip.count():
            self._cull_decorate_row(row)
        # The preview cache is keyed by path, so the renamed file has to be
        # loaded again under its new name.
        self._cull_show_index(self._cull_index)

    def _cull_set_pipette(self, on):
        """Turn the white-balance pipette on or off (key W or the panel)."""
        if on and self._cull_edits_locked():
            self._cull_say_locked()
            return
        self.cull_view.set_pipette(on)
        self.cull_edit_panel.set_pipette_checked(on)
        if on:
            self.cull_view.set_info_overlay(
                tr('Click a neutral grey or white spot \u2014 W ends it'))
            self.cull_view.show_info_overlay(True)
        else:
            self._cull_update_info_overlay()

    def _cull_wb_from_pixel(self, r, g, b):
        """A pipette click arrived: turn the sampled pixel neutral."""
        item = self._cull_current_item()
        if item is None:
            return
        gains = edits.wb_from_neutral(r, g, b)
        if not gains:
            self.logger.info('White balance: the sampled spot is too dark or '
                             'already neutral (%d, %d, %d).', r, g, b)
            self.statusBar().showMessage(
                tr('That spot is too dark to balance on.'), 4000)
            return
        self._cull_remember_edit(item.display_path)
        edits.set_wb(self._cull_edits, item.display_path, gains)
        self._cull_save_edits_soon()
        self.logger.info('White balance for %s from (%d, %d, %d) -> %s',
                         os.path.basename(item.display_path), r, g, b,
                         tuple(round(v, 3) for v in gains))
        self._cull_set_pipette(False)
        self._cull_refresh_edit_badge(item)
        self._cull_update_edit_panel()
        self._cull_apply_tone(immediate=True)   # a single click

    def _cull_step_ev(self, direction):
        """Move the exposure by one sixth of a stop."""
        if self._cull_edits_locked():
            self._cull_say_locked()
            return
        item = self._cull_current_item()
        if item is None:
            return
        path = item.display_path
        current = edits.get_ev(self._cull_edits, path)
        new = round((current + direction * edits.EV_STEP) / edits.EV_STEP) \
            * edits.EV_STEP
        new = max(edits.EV_MIN, min(edits.EV_MAX, new))
        if abs(new - current) < 1e-9:
            return
        self._cull_remember_edit(path)
        edits.set_ev(self._cull_edits, path, new)
        self._cull_save_edits_soon()
        self._cull_refresh_edit_badge(item)
        self._cull_update_edit_panel()
        self._cull_apply_tone()          # debounced: +/- repeats

    def _cull_remember_edit(self, path):
        """Put the CURRENT state of one file on the undo stack, before it is
        changed. Called by every writing path - crop, exposure, white
        balance, reset."""
        self._cull_undo.push(path, edits.get_edit(self._cull_edits, path))

    def _cull_undo_edit(self):
        """One step back in the image edits (Ctrl+Z / Cmd+Z, 0.15.0).

        Deliberately limited to image edits: ratings, renames and
        coordinates are NOT on this stack. A rename has already touched the
        file system by the time it would be undone, which is a different
        problem and needs a different answer.
        """
        if self._cull_edits_locked():
            self._cull_say_locked()
            return
        entry = self._cull_undo.pop()
        if entry is None:
            self.statusBar().showMessage(tr('Nothing left to undo.'), 3000)
            return
        path, record = entry
        changed = edits.apply_record(self._cull_edits, path, record)
        if changed:
            self._cull_save_edits_soon()
        self.logger.info('Undo: image edits of %s restored.',
                         os.path.basename(path))
        # Jump to the file the undo belongs to, or the user sees nothing.
        visible = False
        for i, it in enumerate(self._cull_visible):
            if edits.norm(it.display_path) == path:
                visible = True
                if i != self._cull_index:
                    self.cull_strip.setCurrentRow(i)
                break
        if not visible:
            # The stack survives a folder change on purpose (edits do too),
            # but an undo the user cannot SEE needs saying - review 0.15.0.
            self.statusBar().showMessage(
                tr('Undone in another folder: {name}').format(
                    name=os.path.basename(path)), 5000)
            return
        item = self._cull_current_item()
        if item is not None:
            rec = edits.get_edit(self._cull_edits, item.display_path)
            self.cull_view.set_crop_display(
                (rec or {}).get('crop'))
            self._cull_refresh_edit_badge(item)
        self._cull_update_edit_panel()
        self._cull_apply_tone(immediate=True)
        self.statusBar().showMessage(tr('Undone.'), 3000)

    def _cull_reset_edits(self):
        """Drop every edit on the current image."""
        if self._cull_edits_locked():
            self._cull_say_locked()
            return
        item = self._cull_current_item()
        if item is None:
            return
        self._cull_remember_edit(item.display_path)
        if edits.clear_edit(self._cull_edits, item.display_path):
            self._cull_save_edits_soon()
            self.logger.info('All edits removed for %s',
                             os.path.basename(item.display_path))
        self.cull_view.set_crop_display(None)
        self._cull_refresh_edit_badge(item)
        self._cull_update_edit_panel()
        self._cull_apply_tone(immediate=True)

    def _cull_apply_tone(self, immediate=False):
        """Push the current image's white balance and exposure into the view
        (0.14.2). The tone pass runs over a multi-megapixel image, so key
        repeat on +/- is debounced; an image change applies it immediately
        because there is nothing to coalesce."""
        if not hasattr(self, 'cull_view'):
            return
        item = self._cull_current_item()
        rec = (edits.get_edit(self._cull_edits, item.display_path)
               if item is not None else None) or {}
        wb = rec.get('wb')
        ev = rec.get('ev', 0.0)
        if immediate:
            self._cull_tone_timer.stop()
            self.cull_view.set_tone(wb, ev)
        else:
            self._cull_tone_pending = (wb, ev)
            self._cull_tone_timer.start()

    def _cull_flush_tone(self):
        pending = getattr(self, '_cull_tone_pending', None)
        if pending is not None:
            self.cull_view.set_tone(*pending)
            self._cull_tone_pending = None

    def _cull_update_edit_panel(self):
        """Show the current image's edits in the floating panel."""
        if not hasattr(self, 'cull_edit_panel'):
            return
        if self._cull_edits_locked():
            # 0.18.8: nothing to edit in fullscreen, so nothing to float
            # over the picture either.
            self.cull_edit_panel.hide()
            return
        item = self._cull_current_item()
        if item is None:
            self.cull_edit_panel.hide()
            return
        self.cull_edit_panel.show_state(
            edits.get_edit(self._cull_edits, item.display_path),
            cropping=getattr(self, '_cull_cropping', False))
        self.cull_edit_panel.show()
        self.cull_edit_panel.place()

    def _cull_crop_for(self, path):
        """The stored crop box for a path, or None."""
        rec = edits.get_edit(self._cull_edits, path)
        return tuple(rec['crop']) if rec and 'crop' in rec else None

    def _cull_toggle_crop(self):
        """C: turn the crop overlay on for the current image, or commit it
        if it is already on. Esc cancels, Shift+C removes an existing crop."""
        if self._cull_edits_locked():
            self._cull_say_locked()
            return
        if getattr(self, '_cull_cropping', False):
            self._cull_crop_commit()
            return
        item = self._cull_current_item()
        if item is None:
            return
        self._cull_cropping = True
        self._cull_crop_aspect = None
        self._cull_crop_aspect_key = None
        self._cull_crop_portrait = False
        box = self._cull_crop_for(item.display_path)
        # Put the whole frame back while cropping - otherwise the box could
        # only ever shrink, never be pulled outwards again.
        self.cull_view.set_crop_display(None)
        self.cull_view.crop.begin(box)
        self._cull_set_crop_legend(True)
        self._cull_update_crop_readout(box or (0.1, 0.1, 0.8, 0.8))

    def _cull_crop_key(self, key, event):
        """Keys while cropping. Returns True if the key was consumed."""
        if key in (Qt.Key_Return, Qt.Key_Enter):
            self._cull_crop_commit()
            return True
        if key == Qt.Key_Escape:
            self._cull_crop_cancel()
            return True
        if key == Qt.Key_C and (event.modifiers() & Qt.ShiftModifier):
            self._cull_crop_remove()
            return True
        if key in self._ASPECT_KEYS:
            digit = self._ASPECT_KEYS[key]
            ratio = self.ASPECT_PRESETS[digit]
            # Pressing the SAME preset again flips landscape <-> portrait;
            # a different preset starts landscape. Free (None) and square
            # have nothing to flip.
            if ratio and digit == getattr(self, '_cull_crop_aspect_key', None):
                self._cull_crop_portrait = not getattr(
                    self, '_cull_crop_portrait', False)
            else:
                self._cull_crop_portrait = False
            self._cull_crop_aspect_key = digit
            if ratio and self._cull_crop_portrait:
                ratio = 1.0 / ratio
            self._cull_crop_aspect = ratio
            self.cull_view.crop.set_aspect(ratio)
            self.logger.debug('Crop aspect preset %d -> %s (%s)', digit, ratio,
                              'portrait' if self._cull_crop_portrait
                              else 'landscape')
            return True
        return False

    def _cull_crop_commit(self):
        overlay = self.cull_view.crop
        item = self._cull_current_item()
        if item is not None and overlay.has_box():
            box = overlay._box_tuple()
            self._cull_remember_edit(item.display_path)
            if edits.set_crop(self._cull_edits, item.display_path, box):
                self._cull_save_edits_soon()
                self._cull_refresh_edit_badge(item)
                self.logger.info('Crop set for %s: %s',
                                 os.path.basename(item.display_path), box)
            self.cull_view.set_crop_display(box)
        self._cull_end_crop()

    def _cull_crop_cancel(self):
        self.cull_view.crop.finish_cancel()
        item = self._cull_current_item()
        if item is not None:
            self.cull_view.set_crop_display(
                self._cull_crop_for(item.display_path))
        self._cull_end_crop()

    def _cull_crop_remove(self):
        item = self._cull_current_item()
        if item is not None:
            self._cull_remember_edit(item.display_path)
            if edits.set_crop(self._cull_edits, item.display_path, None):
                self._cull_save_edits_soon()
                self._cull_refresh_edit_badge(item)
                self.logger.info('Crop removed for %s',
                                 os.path.basename(item.display_path))
            self.cull_view.set_crop_display(None)
        self._cull_end_crop()

    def _cull_end_crop(self):
        self._cull_cropping = False
        if self.cull_view.crop.isVisible():
            self.cull_view.crop.hide()
        self.cull_view.crop._box = None
        self._cull_set_crop_legend(False)
        self._cull_update_crop_readout(None)

    def _cull_set_crop_legend(self, on):
        """While cropping, the toolbar's mode label becomes a crop-key
        legend; leaving crop restores the normal "numbers = STARS/COLORS"
        text. One label, two meanings, so the keys are explained exactly
        where the eye already looks for what the numbers do."""
        # 0.14.2: the floating panel carries the same legend, right where
        # the eye is while cropping.
        if hasattr(self, 'cull_edit_panel'):
            self.cull_edit_panel.set_cropping(on)
        if on:
            self.cull_mode_lbl.setText(tr(
                '[crop] 1 free \u00b7 2 3:2 \u00b7 3 4:3 \u00b7 4 1:1 \u00b7 '
                '5 16:9 \u00b7 6 5:4  (same key again = rotate)  \u00b7  '
                'Enter apply \u00b7 Esc cancel \u00b7 \u21e7C remove'))
            self.cull_mode_lbl.setToolTip(tr(
                'Crop keys:\n'
                '  1  free    2  3:2    3  4:3    4  1:1    5  16:9    6  5:4\n'
                'Press the same number again to switch that ratio between '
                'landscape\nand portrait (2:3, 3:4, 9:16, 4:5). Drag the box '
                'or its handles to\nplace it. Enter applies, Esc cancels, '
                'Shift+C removes the crop.'))
        else:
            self._cull_update_mode_label()
            self.cull_mode_lbl.setToolTip(tr(
                'Number keys 1-5 set stars or colors; M toggles the mode.'))

    def _cull_update_crop_readout(self, box):
        """Show the resulting pixel size in the top-left info overlay while
        cropping."""
        if not getattr(self, '_cull_cropping', False) or box is None:
            # restore the normal info overlay
            self._cull_update_info_overlay()
            return
        px = self.cull_view.crop.current_pixels()
        if px:
            self.cull_view.set_info_overlay(
                tr('Crop: {w}\u00d7{h} px  \u2014  Enter: apply, Esc: cancel, '
                   'Shift+C: remove').format(w=px[0], h=px[1]))
            self.cull_view.show_info_overlay(True)

    def _cull_refresh_edit_badge(self, item):
        """Update the strip row's badge data and repaint it."""
        try:
            row = self._cull_visible.index(item)
        except ValueError:
            return
        if 0 <= row < self.cull_strip.count():
            li = self.cull_strip.item(row)
            li.setData(Qt.UserRole + 4,
                       edits.has_edit(self._cull_edits, item.display_path))
            self.cull_strip.update(self.cull_strip.indexFromItem(li))

    def _cull_current_item(self):
        if 0 <= self._cull_index < len(self._cull_visible):
            return self._cull_visible[self._cull_index]
        return None

    def _cull_target_rows(self):
        """Rows a rating/label key applies to: the multi-selection if there
        is one, else the current image."""
        rows = sorted({self.cull_strip.row(it)
                       for it in self.cull_strip.selectedItems()})
        if len(rows) > 1:
            return rows
        if 0 <= self._cull_index < len(self._cull_visible):
            return [self._cull_index]
        return []

    def _cull_set_rating(self, rating):
        self._cull_apply_to_targets(lambda it: setattr(it, 'rating', rating))

    def _cull_set_label(self, color_index):
        text = ('' if color_index is None else culling.label_text(
            color_index, self.cull_labelset_combo.currentText()))
        self._cull_apply_to_targets(lambda it: setattr(it, 'label', text))

    def _cull_apply_to_targets(self, change):
        rows = self._cull_target_rows()
        if not rows:
            return
        for r in rows:
            item = self._cull_visible[r]
            change(item)
            self._cull_wb.enqueue(item)
            self._cull_decorate_row(r)
        self._cull_set_status()
        # Auto-advance only for single-image rating; after rating a
        # multi-selection, jumping away would be disorienting.
        if len(rows) == 1 and self.cull_advance_cb.isChecked():
            self._cull_step(+1)

    # ── Hand-over to the three targets ────────────────────────────────────────

    def _cull_send_rows(self):
        """Strip rows a send action applies to: the multi-selection, or every
        image passing the filter when nothing is selected (same convention as
        the Upload button). None if there is nothing to send (reported)."""
        rows = sorted({self.cull_strip.row(it)
                       for it in self.cull_strip.selectedItems()})
        if not rows:
            rows = list(range(len(self._cull_visible)))
        if not rows:
            QMessageBox.information(self, tr('Culling'),
                                    tr('Nothing passes the current filter.'))
            return None
        return rows

    def _cull_paths_for_rows(self, rows):
        """File paths for the given strip rows, honoring the pair selector
        (JPEG / RAW / both). Used by the buttons and by drag-and-drop."""
        mode = self.cull_pair_combo.currentIndex()   # 0 jpeg, 1 raw, 2 both
        paths = []
        for r in rows:
            if not (0 <= r < len(self._cull_visible)):
                continue
            item = self._cull_visible[r]
            if item.is_pair:
                if mode == 0:
                    paths.append(item.jpg_path)
                elif mode == 1:
                    paths.append(item.raw_path)
                else:
                    paths.extend([item.jpg_path, item.raw_path])
            else:
                paths.append(item.display_path)
        return paths

    def _cull_apply(self):
        """Combined hand-over: add to the MediaWiki table (which the IPTC and
        FTP tabs share) and refresh those tabs' lists. Nothing is uploaded."""
        self._cull_to_table()
        if hasattr(self, '_iptc_refresh_list'):
            self._iptc_refresh_list()
        if hasattr(self, '_ftp_refresh_list'):
            self._ftp_refresh_list()

    def _cull_reload_folder(self):
        """Re-read the current folder from disk (ratings/labels may have
        changed in another program)."""
        folder = getattr(self, '_cull_folder', None)
        if not folder:
            QMessageBox.information(self, tr('Culling'),
                                    tr('No folder is open yet.'))
            return
        # 0.18.7: reload with the scope the folder was opened with, not with
        # whatever the checkbox says now - a reload must show the same
        # folder, not a different one.
        self._cull_open_folder(folder, getattr(self, '_cull_recursive', False))

    def _cull_to_table(self):
        """Target 1: the MediaWiki tab's file table."""
        rows = self._cull_send_rows()
        if rows is None:
            return
        paths = self._cull_paths_for_rows(rows)
        added, dupes, failed = self._add_paths(paths)
        table_paths = {os.path.normpath(
            self.table.item(r, self.COL_FILENAME).data(Qt.UserRole))
            for r in range(self.table.rowCount())
            if self.table.item(r, self.COL_FILENAME)}
        for item in self._cull_items:
            item.in_table = any(
                p and os.path.normpath(p) in table_paths
                for p in (item.jpg_path, item.raw_path))
        for i in range(len(self._cull_visible)):
            self._cull_decorate_row(i)
        self.cull_status.setText(
            tr('{added} file(s) added to the table, {dupes} duplicate(s) '
               'skipped, {failed} failed.').format(
                added=added, dupes=dupes, failed=failed))

    # (The direct FTP/Flickr send targets were removed with their buttons in
    # 0.11.8 - "Add to tabs" stages files into the MW/IPTC/FTP tabs instead,
    # and Flickr keeps its own tab. Their handlers were deleted in 0.12.0.)

    def _cull_to_folder(self):
        """Target 3: a local folder. Copies (never moves) the files chosen by
        the pair selector; a copied RAW brings its .xmp sidecar along so the
        ratings/labels travel with it. The write-behind queue is flushed
        first, so ratings given seconds ago are on disk before copying."""
        rows = self._cull_send_rows()
        if rows is None:
            return
        paths = self._cull_paths_for_rows(rows)
        if not paths:
            return
        dest = QFileDialog.getExistingDirectory(
            self, tr('Copy selection to folder'))
        if not dest:
            return
        # Pending XMP writes must land before the sidecars are copied.
        self._cull_wb.flush(10)
        path_set = set(paths)
        with_sidecars = list(paths)
        for r in rows:
            if not (0 <= r < len(self._cull_visible)):
                continue
            item = self._cull_visible[r]
            sc = item.sidecar_path
            if (sc and item.raw_path in path_set and os.path.exists(sc)
                    and sc not in path_set):
                with_sidecars.append(sc)
        self._cull_copy_dlg = UploadProgressDialog(
            len(with_sidecars), self, verb=tr('Copying'),
            title=tr('Copy') + f' - {APP_NAME}')
        self._cull_copy_done = 0
        edit_map = {p: edits.get_edit(self._cull_edits, p)
                    for p in with_sidecars
                    if edits.has_edit(self._cull_edits, p)}
        self._cull_copy_worker = _FolderCopyWorker(with_sidecars, dest,
                                                   self.logger, edit_map)
        self._cull_copy_worker.file_started.connect(
            self._cull_copy_dlg.set_current)
        self._cull_copy_worker.progress.connect(self._cull_on_copy_progress)
        self._cull_copy_worker.done.connect(self._cull_on_copy_finished)
        self._cull_copy_dlg.cancel_requested.connect(
            self._cull_copy_worker.cancel)
        self._cull_copy_dlg.show()
        self._cull_copy_worker.start()

    def _cull_move_to_folder(self):
        """Target 4 (0.18.2, reworked in 0.18.5): move OR copy into a local
        folder.

        Harald: "Beim Culling möchte ich das ganze RAW/JPG Paar mit sidecar
        verschieben können." So unlike "Export" this ignores the pair
        selector: moving the JPEG alone would leave a RAW behind with an
        .xmp describing a file that is no longer next to it.

        0.18.5 puts both of his follow-ups into the one dialog rather than
        onto new buttons: the operation (move or copy) and the scope (whole
        group, or RAW + sidecar only). The whole group stays the default -
        leaving half a pair behind is now possible, but never by accident.

        Guards before anything is touched: the folder that is currently
        open is refused outright, and for a MOVE a name that already exists
        in the target stops the whole run.
        """
        rows = self._cull_send_rows()
        if rows is None:
            return
        dlg = _TransferDialog(self, remembered_dir(self.settings))
        if dlg.exec_() != QDialog.Accepted:
            return
        dest, move, scope = dlg.result_values()
        remember_dir(self.settings, dest)
        group = []
        for r in rows:
            if not (0 <= r < len(self._cull_visible)):
                continue
            for path in culling.group_paths(self._cull_visible[r], scope):
                if os.path.exists(path) and path not in group:
                    group.append(path)
        if not group:
            return
        title = tr('Move to folder') if move else tr('Copy to folder')
        here = getattr(self, '_cull_folder', None)
        if here and os.path.normpath(dest) == os.path.normpath(here):
            QMessageBox.information(self, title, tr(
                'That is the folder that is open - there is nothing to '
                'move.'))
            return
        # The collision guard belongs to MOVING only. A move that overwrote
        # something would destroy the target AND the last copy of the
        # source, so it stops the whole run; a copy leaves the source in
        # place, so an existing name is simply skipped, exactly as "Export"
        # has always done.
        if move:
            clash = culling.move_collisions(group, dest)
            if clash:
                QMessageBox.warning(self, title, tr(
                    'These files are already in the target folder, so '
                    'nothing was moved:\n\n{names}').format(
                        names='\n'.join(clash[:12])
                        + ('\n…' if len(clash) > 12 else '')))
                return
        # Pending XMP writes must land before the sidecars travel.
        self._cull_wb.flush(10)
        self.logger.info('%s %d file(s) from %d entry/entries to "%s" '
                         '(scope: %s).',
                         'Moving' if move else 'Copying', len(group),
                         len(rows), dest, scope)
        self._cull_copy_dlg = UploadProgressDialog(
            len(group), self, verb=tr('Moving') if move else tr('Copying'),
            title=(tr('Move') if move else tr('Copy')) + f' - {APP_NAME}')
        self._cull_copy_done = 0
        self._cull_copy_worker = _FolderCopyWorker(group, dest, self.logger,
                                                   move=move)
        self._cull_copy_worker.file_started.connect(
            self._cull_copy_dlg.set_current)
        self._cull_copy_worker.progress.connect(self._cull_on_copy_progress)
        self._cull_copy_worker.done.connect(
            self._cull_on_move_finished if move
            else self._cull_on_copy_finished)
        self._cull_copy_dlg.cancel_requested.connect(
            self._cull_copy_worker.cancel)
        self._cull_copy_dlg.show()
        self._cull_copy_worker.start()

    def _cull_on_move_finished(self, summary):
        """After a move the files are gone from the open folder, so the
        strip, the preview cache and the path-keyed records would all point
        at nothing. Re-reading the folder rebuilds every one of them, and
        the crop/channel records travel to the new location first."""
        self._cull_copy_dlg.force_close()
        moved = list(getattr(self._cull_copy_worker, 'moved', []))
        for old in moved:
            new = os.path.join(self._cull_copy_worker.dest_dir,
                               os.path.basename(old))
            self._cull_migrate_paths(old, new)
        self.cull_status.setText(f'Folder: {summary}')
        QMessageBox.information(self, tr('Move to folder'), summary)
        if moved:
            self._cull_reload_folder()

    def _cull_on_copy_progress(self, _index, status):
        if status.startswith(('✓', '✗', '•')):
            self._cull_copy_done += 1
            self._cull_copy_dlg.set_done(self._cull_copy_done)

    def _cull_on_copy_finished(self, summary):
        self._cull_copy_dlg.force_close()
        self.cull_status.setText(f'Folder: {summary}')
        QMessageBox.information(self, tr('Copy to folder'), summary)

    # ── Watching for a card in the reader (0.18.7) ───────────────────────────

    def _cull_start_card_watch(self):
        """Notice a memory card being plugged in.

        Polled rather than watched: QFileSystemWatcher would do on macOS
        (/Volumes is a directory) but there is no such directory on Windows,
        where volumes are drive letters. One listing of /Volumes every few
        seconds costs nothing and is the same code on all three systems.

        The volumes present at startup are the BASELINE, so the disk that
        was already in the reader when Cammello launched is not opened
        behind the user's back.
        """
        self._cull_known_volumes = camera.list_volumes()
        self._cull_card_timer = QTimer(self)
        self._cull_card_timer.setInterval(2500)
        self._cull_card_timer.timeout.connect(self._cull_poll_cards)
        if self.cull_autocard_cb.isChecked():
            self._cull_card_timer.start()

    def _cull_autocard_toggled(self, _state):
        on = self.cull_autocard_cb.isChecked()
        self.settings.setValue('cull_autocard', on)
        timer = getattr(self, '_cull_card_timer', None)
        if timer is None:
            return
        if on:
            # Re-seed: volumes that appeared while the watch was off are not
            # "new", or switching the box back on would open a stale card.
            self._cull_known_volumes = camera.list_volumes()
            timer.start()
        else:
            timer.stop()

    def _cull_poll_cards(self):
        current = camera.list_volumes()
        known = getattr(self, '_cull_known_volumes', current)
        cards = camera.new_cards(known, current)
        self._cull_known_volumes = current
        if not cards:
            return
        folder = cards[0]
        if len(cards) > 1:
            self.logger.info('Culling: %d cards appeared at once, opening '
                             'the first one.', len(cards))
        self.logger.info('Culling: card detected, opening "%s".', folder)
        self.cull_status.setText(f'Card: {folder}')
        # Always recursive: DCIM is a container, the pictures are one level
        # down in 100EOSR5 and its successors.
        self._cull_open_folder(folder, True)

    # ── Import from a camera (0.18.3) ────────────────────────────────────────

    def _cull_import_from_camera(self):
        """Canon bodies present the card over PTP, not as a volume, so there
        is no folder to open. Copy first, then open the copy - everything
        downstream (pyexiv2, rawpy, edits, sidecars, F2) needs real local
        paths."""
        problem = camera.backend_problem()
        if problem:
            QMessageBox.information(self, tr('Import from camera'),
                                    tr(problem))
            return
        try:
            devices = camera.make_backend().list_devices()
        except camera.CameraError as exc:
            QMessageBox.warning(self, tr('Import from camera'), tr(str(exc)))
            return
        except Exception as exc:
            self.logger.error('Camera detection failed: %s', exc,
                              exc_info=True)
            QMessageBox.warning(self, tr('Import from camera'), str(exc))
            return
        if not devices:
            QMessageBox.information(self, tr('Import from camera'), tr(
                'No camera answered. Switch it on, connect the USB cable, '
                'and close any other program that may be holding the '
                'camera.'))
            return
        device = devices[0]
        if len(devices) > 1:
            names = [f'{d.name} ({d.addr})' for d in devices]
            pick, ok = QInputDialog.getItem(
                self, tr('Import from camera'), tr('Which camera?'),
                names, 0, False)
            if not ok:
                return
            device = devices[names.index(pick)]
        dest = QFileDialog.getExistingDirectory(
            self, tr('Import from camera into folder'),
            remembered_dir(self.settings))
        if not dest:
            return
        remember_dir(self.settings, dest)
        self.logger.info('Camera import: "%s" -> "%s".', device.name, dest)
        self._cull_camera_dest = dest
        self._cull_copy_dlg = UploadProgressDialog(
            0, self, verb=tr('Importing'),
            title=tr('Import from camera') + f' - {APP_NAME}')
        self._cull_copy_done = 0
        self._cull_camera_worker = _CameraImportWorker(device, dest,
                                                       self.logger)
        w = self._cull_camera_worker
        w.listing.connect(self._cull_on_camera_listing)
        w.ready.connect(self._cull_on_camera_ready)
        w.file_started.connect(self._cull_copy_dlg.set_current)
        w.progress.connect(self._cull_on_copy_progress)
        w.fatal.connect(self._cull_on_camera_fatal)
        w.done.connect(self._cull_on_camera_finished)
        self._cull_copy_dlg.cancel_requested.connect(w.cancel)
        self._cull_copy_dlg.show()
        w.start()

    def _cull_on_camera_listing(self, count):
        self._cull_copy_dlg.set_detail(
            tr('Reading the card: {n} file(s) so far…').format(n=count))

    def _cull_on_camera_ready(self, count):
        self._cull_copy_dlg.set_total(count)

    def _cull_on_camera_fatal(self, message):
        self._cull_camera_fatal = message

    def _cull_on_camera_finished(self, summary):
        self._cull_copy_dlg.force_close()
        fatal = getattr(self, '_cull_camera_fatal', None)
        self._cull_camera_fatal = None
        if fatal:
            QMessageBox.warning(self, tr('Import from camera'), tr(fatal))
            return
        self.cull_status.setText(f'Camera: {summary}')
        QMessageBox.information(self, tr('Import from camera'), summary)
        if getattr(self._cull_camera_worker, 'copied', 0):
            self._cull_open_folder(self._cull_camera_dest)

    # ── Shutdown ──────────────────────────────────────────────────────────────

    def _cull_shutdown(self):
        # 0.18.9: drop the activation hook before anything is torn down.
        self._cull_fs_watch(False)
        # 0.18.7: stop the card poll first - a timer firing during teardown
        # would open a folder into half-dismantled widgets.
        timer = getattr(self, '_cull_card_timer', None)
        if timer is not None:
            timer.stop()
        self._cull_flush_edits()
        if self._cull_reader is not None:
            self._cull_reader.stop()
            self._cull_reader.wait(2000)
        self._cull_wb.stop()
        # Let decode jobs drain before Qt objects go away - worker threads
        # racing process teardown were a reproducible segfault on exit.
        self._cull_loader.new_generation()
        self._cull_loader.wait_idle(10000)
