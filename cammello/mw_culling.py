"""MainWindow mixin: the Culling tab (Phase 1b).

Keyboard model (the whole point of the tab - one hand, no dialogs):
  Right/Left   next / previous image
  1-5, 0       RATING mode: stars / clear - COLOR mode: label / clear
  M            toggle the number mode (shown in the toolbar)
  X            reject (rating -1) + advance
  6-9          red/yellow/green/blue directly (Lightroom's own key layout;
               purple has no key in LR either)
  Z            toggle 100% zoom, F fullscreen (double-click does too)
  Home/End     jump to the first / last image
  I            toggle the EXIF info overlay
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
    QStyledItemDelegate, QFormLayout, QGroupBox, QStyleOptionViewItem, QStyle,
    QToolButton)
from PyQt5.QtGui import QIcon, QPixmap, QColor, QPen, QPainter
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize

from PyQt5.QtCore import QUrl, QMimeData, QItemSelectionModel, QObject

from .constants import *
from . import culling
from . import channels, previews
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
        self._cull_show_exif = False   # i key: EXIF overlay on/off
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
        # three share one file list; nothing is uploaded yet). "Save to…"
        # (folder export) stays a separate action.
        apply_btn = QPushButton(tr('Add to tabs'))
        apply_btn.setToolTip(tr('Adds the selected images (or all filtered '
                                'images when nothing is selected) to the '
                                'MediaWiki, IPTC and FTP tabs. Nothing is '
                                'uploaded yet.'))
        apply_btn.clicked.connect(self._cull_apply)
        bar.addWidget(apply_btn)
        to_folder_btn = QPushButton(tr('Save to…'))
        to_folder_btn.setToolTip(
            tr('Copies the selected images into a local folder. RAW files bring '
            'their .xmp sidecar along; existing files in the target folder '
            'are never overwritten.'))
        to_folder_btn.clicked.connect(self._cull_to_folder)
        bar.addWidget(to_folder_btn)
        slim_toolbar(bar)
        outer.addLayout(bar)

        split = QSplitter(Qt.Vertical)
        self.cull_view = CullImageView()
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

        report = {}
        self._cull_items = culling.scan_folder(folder, report)
        self._cull_folder = folder
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
        self._cull_update_info_overlay()

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
            stars = rating_marks(item.rating)
            detail = (f' — {os.path.basename(item.display_path)}'
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
            text = (os.path.basename(os.path.normpath(folder))
                    + '  ·  ' + text)
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
            self._cull_toggle_fullscreen()
        if self._cull_grid:
            self._cull_set_grid(False)
        self.cull_view.fit()

    def _cull_toggle_grid(self):
        """Grid view (G): thumbnails instead of the large image. From
        fullscreen this leaves fullscreen first."""
        if self._cull_fs is not None:
            self._cull_toggle_fullscreen()
        self._cull_set_grid(not self._cull_grid)

    def _cull_toggle_fullscreen(self):
        """Image-only fullscreen: the view is reparented into a borderless
        fullscreen window; keys keep working (same forwarding container).
        F or Esc leaves."""
        if self._cull_fs is None:
            # From the grid, F used to do nothing (looked broken): leave the
            # grid first, then go fullscreen.
            if self._cull_grid:
                self._cull_set_grid(False)
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
        self._cull_open_folder(folder)

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
