"""MainWindow mixin: the Culling tab (Phase 1b).

Keyboard model (the whole point of the tab - one hand, no dialogs):
  Right/Left   next / previous image
  1-5, 0       RATING mode: stars / clear - COLOR mode: label / clear
  M            toggle the number mode (shown in the toolbar)
  X            reject (rating -1) + advance
  6-9          red/yellow/green/blue directly (Lightroom's own key layout;
               purple has no key in LR either)
  Z            toggle 100% zoom, F fullscreen
Number keys auto-advance (checkbox to turn that off).

The tab widget itself owns the keyboard: every child has NoFocus so arrow
keys are never eaten by a list widget. Ratings go through the write-behind
queue; the UI never waits for disk.
"""
import os
import shutil

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget,
    QListWidgetItem, QComboBox, QCheckBox, QFileDialog, QMessageBox, QSplitter,
    QStyledItemDelegate, QFormLayout, QGroupBox, QStyleOptionViewItem, QStyle)
from PyQt5.QtGui import QIcon, QPixmap, QColor, QBrush, QPen
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize

from PyQt5.QtCore import QUrl, QMimeData, QItemSelectionModel, QObject

from .constants import *
from . import culling, previews
from .culling_view import CullImageView
from .ftp_workers import FtpUploadWorker
from .widgets import UploadProgressDialog
from .i18n import tr

# Zoom ladder: 12 roughly proportional steps (factor ~1.4-1.5) between 5% and
# 400%, all of them easy mental-arithmetic values (thirds, halves, doublings);
# 100% is an exact member.
ZOOM_STEPS = [5, 10, 15, 25, 33, 50, 67, 100, 150, 200, 300, 400]


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
            marks = '✕' if rating == -1 else '★' * int(rating)
            painter.setPen(text_color)
            painter.drawText(r.x() + inset,
                             band_top + band_h - fm.descent() - 1, marks)
        idx = index.data(Qt.UserRole)
        if idx is not None:
            painter.fillRect(r.x() + inset + half + 2,
                             band_top + (band_h - self.BAR) // 2,
                             half - 2, self.BAR,
                             QColor(culling.LABEL_COLORS[idx]))
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
    """Reads rating/label of all items in the background after a folder scan
    (3000 pyexiv2 reads must not block the UI)."""
    item_ready = pyqtSignal(int)      # index into the item list
    done = pyqtSignal(int)            # count

    def __init__(self, items):
        super().__init__()
        self.items = items
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        n = 0
        for i, item in enumerate(self.items):
            if self._stop:
                break
            try:
                culling.read_item_metadata(item)
            except Exception:
                pass                   # unreadable file: keep defaults
            n += 1
            self.item_ready.emit(i)
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

    def __init__(self, paths, dest_dir, logger):
        super().__init__()
        self.paths = paths
        self.dest_dir = dest_dir
        self.log = logger
        self._cancelled = False

    def cancel(self):
        self._cancelled = True
        self.log.info('Folder copy cancel requested: stopping after the '
                      'current file.')

    def run(self):
        total = len(self.paths)
        self.log.info('=== Copy to "%s" started: %d file(s) ===',
                      self.dest_dir, total)
        ok = skipped = failed = 0
        cancelled_at = None
        for i, path in enumerate(self.paths):
            if self._cancelled:
                cancelled_at = i
                self.progress.emit(i, tr('Cancelled'))
                break
            name = os.path.basename(path)
            self.file_started.emit(i, name)
            target = os.path.join(self.dest_dir, name)
            try:
                if os.path.exists(target):
                    skipped += 1
                    self.progress.emit(i, '• ' + tr('Skipped (exists)'))
                    continue
                shutil.copy2(path, target)
            except Exception as e:
                failed += 1
                self.log.error('✗ Copy failed for "%s": %s', name, e,
                               exc_info=True)
                self.error.emit(i, f'{name}: {e}')
                self.progress.emit(i, '✗ ' + tr('Error'))
                continue
            ok += 1
            self.progress.emit(i, '✓ ' + tr('Copied'))
        if cancelled_at is not None:
            summary = tr('Cancelled: {ok}/{total} file(s) copied, '
                         '{n} not started.').format(
                ok=ok, total=total, n=total - cancelled_at)
        else:
            summary = (tr('Done: {ok}/{total} file(s) copied').format(
                           ok=ok, total=total)
                       + (', ' + tr('{n} skipped (already there)').format(
                              n=skipped) if skipped else '')
                       + (', ' + tr('{n} failed').format(n=failed)
                          if failed else '') + '.')
        self.log.info('=== Copy finished: %s ===', summary)
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
        self._cull_fs = None
        self._cull_row_by_path = {}
        self._cull_row_by_item = {}
        self._cull_reader = None
        self._cull_wb = culling.WriteBehind(self.logger)
        self._cull_loader = previews.PreviewLoader()
        self._cull_loader.signals.loaded.connect(self._cull_on_loaded)
        self._cull_loader.signals.failed.connect(
            lambda key, msg: self.logger.error('Preview failed for "%s": %s',
                                               os.path.basename(key), msg))

        w = _CullTab(self)
        outer = QVBoxLayout(w)

        # Toolbar
        bar = QHBoxLayout()
        open_btn = QPushButton(tr('Open folder…'))
        open_btn.clicked.connect(self._cull_open_folder)
        bar.addWidget(open_btn)
        self.cull_mode_lbl = QLabel()
        self.cull_mode_lbl.setToolTip(tr('Number keys 1-5 set stars or colors; '
                                      'M toggles the mode.'))
        bar.addWidget(self.cull_mode_lbl)
        bar.addWidget(QLabel(tr('Zoom:')))
        self.cull_zoom_out_btn = QPushButton('−')
        self.cull_zoom_out_btn.setFixedWidth(28)
        self.cull_zoom_out_btn.setToolTip(tr('One zoom step out (Cmd/Ctrl -)'))
        self.cull_zoom_out_btn.clicked.connect(self._cull_zoom_out)
        bar.addWidget(self.cull_zoom_out_btn)
        self.cull_zoom_lbl = QLabel('Fit')
        self.cull_zoom_lbl.setFixedWidth(46)
        self.cull_zoom_lbl.setAlignment(Qt.AlignCenter)
        bar.addWidget(self.cull_zoom_lbl)
        self.cull_zoom_in_btn = QPushButton('+')
        self.cull_zoom_in_btn.setFixedWidth(28)
        self.cull_zoom_in_btn.setToolTip(tr('One zoom step in (Cmd/Ctrl +)'))
        self.cull_zoom_in_btn.clicked.connect(self._cull_zoom_in)
        bar.addWidget(self.cull_zoom_in_btn)
        self.cull_grid_btn = QPushButton(tr('Grid'))
        self.cull_grid_btn.setCheckable(True)
        self.cull_grid_btn.setToolTip(tr('Grid view (G): thumbnails instead of '
                                      'the large image.'))
        self.cull_grid_btn.toggled.connect(self._cull_set_grid)
        bar.addWidget(self.cull_grid_btn)
        bar.addSpacing(12)
        bar.addWidget(QLabel(tr('Show:')))
        self.cull_minrating_combo = QComboBox()
        self.cull_minrating_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.cull_minrating_combo.addItems(
            [tr('all'), '≥ 1', '≥ 2', '≥ 3', '≥ 4', '= 5'])
        self.cull_minrating_combo.currentIndexChanged.connect(
            self._cull_apply_filter)
        bar.addWidget(self.cull_minrating_combo)
        self.cull_rejects_cb = QCheckBox(tr('incl. rejects'))
        self.cull_rejects_cb.stateChanged.connect(self._cull_apply_filter)
        bar.addWidget(self.cull_rejects_cb)
        bar.addStretch()
        # Three targets for the selection (no selection = every image passing
        # the filter, same convention as before). Which file of a RAW+JPEG
        # pair is sent follows the pair selector in the Settings tab.
        bar.addWidget(QLabel(tr('Send to:')))
        to_table_btn = QPushButton('MediaWiki')
        to_table_btn.setToolTip(tr('Adds the selected images to the MediaWiki '
                                'tab; with no selection, every image passing '
                                'the filter. Images can also be dragged onto '
                                'the MediaWiki tab directly.'))
        to_table_btn.clicked.connect(self._cull_to_table)
        bar.addWidget(to_table_btn)
        if getattr(self, '_feat_ftp', False):
            self.cull_ftp_btn = QPushButton('FTP')
            self.cull_ftp_btn.setToolTip(
                tr('Uploads the selected images (as they are, no IPTC writing) '
                'to the server configured in the FTP tab / Settings.'))
            self.cull_ftp_btn.clicked.connect(self._cull_to_ftp)
            bar.addWidget(self.cull_ftp_btn)
        if getattr(self, '_feat_flickr', False):
            self.cull_flickr_btn = QPushButton('Flickr')
            self.cull_flickr_btn.setToolTip(
                tr('Uploads the selected images (as they are) to the Flickr '
                   'account authorized in the Flickr tab.'))
            self.cull_flickr_btn.clicked.connect(self._cull_to_flickr)
            bar.addWidget(self.cull_flickr_btn)
        to_folder_btn = QPushButton(tr('Folder…'))
        to_folder_btn.setToolTip(
            tr('Copies the selected images into a local folder. RAW files bring '
            'their .xmp sidecar along; existing files in the target folder '
            'are never overwritten.'))
        to_folder_btn.clicked.connect(self._cull_to_folder)
        bar.addWidget(to_folder_btn)
        outer.addLayout(bar)

        split = QSplitter(Qt.Vertical)
        self.cull_view = CullImageView()
        self.cull_view.zoom_requested.connect(self._cull_request_full)
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
        self._cull_delegate = _LabelBarDelegate(self.cull_strip)
        self._cull_delegate.set_dark(self._is_dark_scheme())
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

    def _cull_open_folder(self, folder=None):
        if not folder:
            folder = QFileDialog.getExistingDirectory(self, 'Open folder')
            if not folder:
                return
        if self._cull_reader is not None:
            self._cull_reader.stop()
            self._cull_reader.wait(2000)
        self._cull_wb.flush(10)
        self._cull_loader.new_generation()

        self._cull_items = culling.scan_folder(folder)
        if not previews.raw_available():
            raw_only = sum(1 for i in self._cull_items
                           if i.raw_path and not i.jpg_path)
            if raw_only:
                self.logger.warning(
                    '%d RAW-only file(s) cannot be previewed: %s',
                    raw_only, previews.raw_unavailable_reason())
        self.logger.info('Culling: opened "%s", %d image(s).',
                         folder, len(self._cull_items))

        # Ratings/labels arrive in the background.
        self._cull_reader = _MetadataReader(self._cull_items)
        self._cull_reader.item_ready.connect(self._cull_meta_arrived)
        self._cull_reader.done.connect(
            lambda n: self._cull_set_status())
        self._cull_reader.start()

        self._cull_apply_filter()

    def _cull_meta_arrived(self, index):
        item = self._cull_items[index]
        vis_idx = self._cull_row_by_item.get(id(item))
        if vis_idx is not None:
            self._cull_decorate_row(vis_idx)

    def _cull_request_visible_thumbs(self, margin=24):
        """Request thumbs for the on-screen filmstrip/grid range plus a
        margin - never for the whole folder at once."""
        n = self.cull_strip.count()
        if not n:
            return
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
            return
        for i in range(max(0, first - margin), min(n, last + 1 + margin)):
            self._cull_loader.request(self._cull_visible[i].display_path,
                                      'thumb',
                                      previews.PreviewLoader.P_THUMBS)

    # ── Filter and filmstrip ──────────────────────────────────────────────────

    def _cull_min_rating(self):
        return {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5}[
            self.cull_minrating_combo.currentIndex()]

    def _cull_apply_filter(self, *_a):
        current_item = (self._cull_visible[self._cull_index]
                        if 0 <= self._cull_index < len(self._cull_visible)
                        else None)
        self._cull_visible = culling.filter_items(
            self._cull_items,
            min_rating=self._cull_min_rating(),
            exclude_rejects=not self.cull_rejects_cb.isChecked())
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
        for i, item in enumerate(self._cull_visible):
            self._cull_decorate_row(i)
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
        tips = []
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
        img = self._cull_loader.cache.get('screen', path)
        if img is not None:
            self.cull_view.set_image(img)
        else:
            self.cull_view.clear_image()
            self._cull_loader.request(path, 'screen',
                                      previews.PreviewLoader.P_CURRENT)
        self._cull_loader.prefetch_around(
            [i.display_path for i in self._cull_visible],
            idx, self._cull_direction)
        self._cull_set_status()

    def _cull_on_loaded(self, key, level):
        if not (0 <= self._cull_index < len(self._cull_visible)):
            return
        current = self._cull_visible[self._cull_index]
        if level == 'screen' and key == current.display_path:
            img = self._cull_loader.cache.get('screen', key)
            if img is not None and self.cull_view.is_fit:
                self.cull_view.set_image(img)
        elif level == 'full' and key == current.display_path:
            img = self._cull_loader.cache.get('full', key)
            if img is not None and not self.cull_view.is_fit:
                self.cull_view.set_image(img, keep_view=True)
        elif level == 'thumb':
            i = self._cull_row_by_path.get(key)
            if i is not None:
                self._cull_decorate_row(i)

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
            stars = 'X' if item.rating == -1 else '★' * item.rating
            detail = (f' — {os.path.basename(item.display_path)}'
                      f'{" [pair]" if item.is_pair else ""} {stars} '
                      f'{item.label}')
        text = (tr('{pos}/{shown} shown ({total} in folder)').format(
                    pos=pos, shown=shown, total=total) + detail)
        n_sel = len(self.cull_strip.selectedItems())
        if n_sel:
            text += '  ·  ' + tr('{n} selected').format(n=n_sel)
        self.cull_status.setText(text)
        # Fullscreen overlay: stars/X plus a dot in the label color.
        if item is not None:
            stars = ('✕' if item.rating == -1
                     else '★' * item.rating + '☆' * (5 - max(item.rating, 0)))
            idx = item.label_color_index
            dot = (f'<span style="color:{culling.LABEL_COLORS[idx]};">'
                   f'&#11044;</span> ' if idx is not None else '')
            self.cull_view.set_overlay(f'{dot}{stars}')
        else:
            self.cull_view.set_overlay('')

    # ── Keyboard ──────────────────────────────────────────────────────────────

    def _cull_update_mode_label(self):
        mode = (tr('numbers = STARS') if self._cull_number_mode == 'rating'
                else tr('numbers = COLORS'))
        self.cull_mode_lbl.setText(f'[M] {mode}')

    def _cull_key(self, event):
        key = event.key()
        if key == Qt.Key_Right:
            self._cull_step(+1)
        elif key == Qt.Key_Left:
            self._cull_step(-1)
        elif key in (Qt.Key_Down, Qt.Key_Up):
            # One ROW in the grid (exact column count from the layout),
            # one image in loupe view.
            step = self._cull_grid_columns() if self._cull_grid else 1
            self._cull_step(step if key == Qt.Key_Down else -step)
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
            # Standard (loupe) view, like Lightroom's E: leave fullscreen and
            # grid, fit the image.
            if self._cull_fs is not None:
                self._cull_toggle_fullscreen()
            if self._cull_grid:
                self.cull_grid_btn.setChecked(False)
            self.cull_view.fit()
        elif (key in (Qt.Key_Plus, Qt.Key_Equal)
              and event.modifiers() & Qt.ControlModifier):
            # Qt maps macOS Cmd to ControlModifier, so this is Cmd+ on the
            # Mac and Ctrl+ elsewhere; Key_Equal covers layouts where '+'
            # needs Shift.
            self._cull_zoom_in()
        elif key == Qt.Key_Minus and event.modifiers() & Qt.ControlModifier:
            self._cull_zoom_out()
        elif key == Qt.Key_G:
            # From fullscreen, G means: leave fullscreen, then grid.
            if self._cull_fs is not None:
                self._cull_toggle_fullscreen()
            self.cull_grid_btn.toggle()
        elif key == Qt.Key_F:
            self._cull_toggle_fullscreen()
        elif key == Qt.Key_Escape and self._cull_fs is not None:
            self._cull_toggle_fullscreen()
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
        # Value display: 'Fit' in fit mode, the percentage otherwise.
        self.cull_zoom_lbl.setText(
            'Fit' if self.cull_view.is_fit else f'{int(round(factor*100))} %')

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

    def _cull_toggle_fullscreen(self):
        """Image-only fullscreen: the view is reparented into a borderless
        fullscreen window; keys keep working (same forwarding container).
        F or Esc leaves."""
        if self._cull_fs is None:
            # From the grid, F used to do nothing (looked broken): leave the
            # grid first, then go fullscreen.
            if self._cull_grid:
                self.cull_grid_btn.setChecked(False)
            fs = _CullTab(self)
            lay = QVBoxLayout(fs)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.addWidget(self.cull_view)
            fs.showFullScreen()
            fs.setFocus()
            self._cull_fs = fs
            self.cull_view.show_overlay(True)
            self._cull_set_status()          # fill the overlay
            if self.cull_view.is_fit:
                self.cull_view.fit()
        else:
            self._cull_fs.layout().removeWidget(self.cull_view)
            self._cull_split.insertWidget(0, self.cull_view)
            self._cull_split.setSizes([620, 172])
            self._cull_fs.close()
            self._cull_fs = None
            self.cull_view.show_overlay(False)
            self._cull_tab_widget.setFocus()
            if self.cull_view.is_fit:
                self.cull_view.fit()
            # Coming back: the strip may have scrolled/emptied meanwhile.
            if 0 <= self._cull_index < self.cull_strip.count():
                self.cull_strip.scrollToItem(
                    self.cull_strip.item(self._cull_index))
            self._cull_request_visible_thumbs()

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

    def _cull_to_ftp(self):
        """Target 2: the FTP/FTPS/SFTP server from the FTP tab. Files are
        sent AS THEY ARE (no IPTC writing - that workflow stays on the
        IPTC/FTP tabs)."""
        rows = self._cull_send_rows()
        if rows is None:
            return
        paths = self._cull_paths_for_rows(rows)
        if not paths:
            return
        host = self.ftp_host_edit.text().strip()
        if not host:
            QMessageBox.warning(self, 'FTP', tr('Host is missing (FTP tab or '
                                'Settings tab).'))
            return
        password = self.ftp_password_edit.text()
        if not password:
            QMessageBox.warning(self, 'FTP', tr('Password is missing (it is '
                                'asked per session unless you chose to '
                                'store it).'))
            return
        files = [(p, os.path.basename(p)) for p in paths]
        self.cull_ftp_btn.setEnabled(False)
        self._cull_ftp_dlg = UploadProgressDialog(len(files), self)
        self._cull_ftp_done = 0
        self._cull_ftp_worker = FtpUploadWorker(
            self.ftp_protocol_combo.currentText(), host,
            self.ftp_port_edit.text().strip(),
            self.ftp_user_edit.text().strip(), password,
            self.ftp_dir_edit.text().strip(), files, self.logger)
        self._cull_ftp_worker.file_started.connect(
            self._cull_ftp_dlg.set_current)
        self._cull_ftp_worker.progress.connect(self._cull_on_send_progress)
        self._cull_ftp_worker.error.connect(
            lambda i, m: self.logger.error('Culling -> FTP: %s', m))
        self._cull_ftp_worker.finished.connect(self._cull_on_ftp_finished)
        self._cull_ftp_dlg.cancel_requested.connect(
            self._cull_ftp_worker.cancel)
        self._cull_ftp_dlg.show()
        self._cull_ftp_worker.start()

    def _cull_to_flickr(self):
        """Target: Flickr (files as they are, title = filename stem)."""
        if not self._flickr_credentials_ok(need_token=True):
            return
        rows = self._cull_send_rows()
        if rows is None:
            return
        paths = self._cull_paths_for_rows(rows)
        if not paths:
            return
        files = [(p, os.path.splitext(os.path.basename(p))[0])
                 for p in paths]
        self._flickr_start_upload(files, self.cull_flickr_btn)

    def _cull_on_send_progress(self, _index, status):
        if status.startswith(('✓', '✗', '•')):
            self._cull_ftp_done += 1
            self._cull_ftp_dlg.set_done(self._cull_ftp_done)

    def _cull_on_ftp_finished(self, summary):
        self.cull_ftp_btn.setEnabled(True)
        self._cull_ftp_dlg.force_close()
        self.cull_status.setText(f'FTP: {summary}')
        QMessageBox.information(self, tr('FTP upload'), summary)

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
        self._cull_copy_worker = _FolderCopyWorker(with_sidecars, dest,
                                                   self.logger)
        self._cull_copy_worker.file_started.connect(
            self._cull_copy_dlg.set_current)
        self._cull_copy_worker.progress.connect(self._cull_on_copy_progress)
        self._cull_copy_worker.done.connect(self._cull_on_copy_finished)
        self._cull_copy_dlg.cancel_requested.connect(
            self._cull_copy_worker.cancel)
        self._cull_copy_dlg.show()
        self._cull_copy_worker.start()

    def _cull_on_copy_progress(self, _index, status):
        if status.startswith(('✓', '✗', '•')):
            self._cull_copy_done += 1
            self._cull_copy_dlg.set_done(self._cull_copy_done)

    def _cull_on_copy_finished(self, summary):
        self._cull_copy_dlg.force_close()
        self.cull_status.setText(f'Folder: {summary}')
        QMessageBox.information(self, tr('Copy to folder'), summary)

    # ── Shutdown ──────────────────────────────────────────────────────────────

    def _cull_shutdown(self):
        if self._cull_reader is not None:
            self._cull_reader.stop()
            self._cull_reader.wait(2000)
        self._cull_wb.stop()
        # Let decode jobs drain before Qt objects go away - worker threads
        # racing process teardown were a reproducible segfault on exit.
        self._cull_loader.new_generation()
        self._cull_loader.wait_idle(10000)
