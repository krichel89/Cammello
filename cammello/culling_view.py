"""Image view widget for the culling tab: fit-to-window or 100% zoom anchored
at the mouse position, panning by drag while zoomed. Pure display - all
keyboard handling and data logic live in mw_culling.py.
"""
from PyQt5.QtWidgets import (QGraphicsView, QGraphicsScene,
                             QGraphicsPixmapItem, QLabel)
from PyQt5.QtGui import QPixmap, QPainter, QColor, QPen, QBrush
from PyQt5.QtCore import Qt, pyqtSignal, QRectF, QRect, QPoint


class CropOverlay(QLabel):
    """A transparent child widget over the whole view that lets the user
    drag a crop rectangle. It works in NORMALIZED image coordinates (0..1),
    so the same box is valid whether the fitted image or the 100% image is
    shown, and can be handed straight to edits.set_crop.

    Kept deliberately simple: no rotation, no free-hand outside the image.
    Number keys pick an aspect ratio (handled by the tab, which calls
    set_aspect); the eight handles resize, the inside drags, outside starts
    a fresh box.
    """
    HANDLE = 9              # half-size of a grab handle, in device px
    committed = pyqtSignal(tuple)   # (x, y, w, h) normalized, on Enter
    cancelled = pyqtSignal()
    changed = pyqtSignal(tuple)     # live, for the pixel readout

    def __init__(self, view):
        super().__init__(view)
        self._view = view
        self.setMouseTracking(True)
        # A translucent background gives the widget a real alpha channel, so
        # the dim rectangles below composite over the image instead of over
        # opaque black. Without this the "darkened" area renders solid.
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setStyleSheet('background: transparent;')
        self._box = None            # QRectF in normalized coords, or None
        self._aspect = None         # float w/h, or None for free
        self._drag = None           # ('move'|'new'|handle-name, start...)
        self.hide()

    # -- geometry helpers (normalized <-> the on-screen image rect) --------
    def _image_rect(self):
        """The image's rectangle in this widget's pixels (what the view is
        currently showing of the pixmap)."""
        item = self._view._item
        if item.pixmap().isNull():
            return None
        # mapFromScene on a scene rect returns a QPolygon, whose
        # boundingRect() is an integer QRect. Everything downstream
        # (intersected, contains, translate against the normalized box) works
        # in QRectF, and PyQt5 will not silently mix the two - so convert here
        # once, at the source, rather than at every call site.
        poly = self._view.mapFromScene(
            item.mapToScene(item.boundingRect()))
        return QRectF(poly.boundingRect())

    def _norm_to_px(self, box):
        r = self._image_rect()
        if r is None or box is None:
            return None
        return QRectF(r.x() + box.x() * r.width(),
                     r.y() + box.y() * r.height(),
                     box.width() * r.width(), box.height() * r.height())

    def _px_to_norm(self, px):
        r = self._image_rect()
        if r is None or not r.width() or not r.height():
            return None
        x = (px.x() - r.x()) / r.width()
        y = (px.y() - r.y()) / r.height()
        w = px.width() / r.width()
        h = px.height() / r.height()
        # clamp into the image
        x = max(0.0, min(1.0, x))
        y = max(0.0, min(1.0, y))
        w = max(0.0, min(1.0 - x, w))
        h = max(0.0, min(1.0 - y, h))
        return QRectF(x, y, w, h)

    # -- public API used by the tab ---------------------------------------
    def begin(self, existing=None):
        """Show the overlay. existing: a normalized (x,y,w,h) to edit, or
        None to start with a default centered box."""
        self.setGeometry(self._view.rect())
        if existing:
            self._box = QRectF(*existing)
        else:
            self._box = QRectF(0.1, 0.1, 0.8, 0.8)
        self.show()
        self.raise_()
        self.update()
        self._emit_changed()

    def finish_commit(self):
        if self._box is not None:
            self.committed.emit(self._box_tuple())
        self.hide()
        self._box = None
        self._drag = None

    def finish_cancel(self):
        self.hide()
        self._box = None
        self._drag = None
        self.cancelled.emit()

    def set_aspect(self, ratio):
        """ratio: float w/h, or None for free. Re-fits the current box to the
        ratio, keeping the top-left, staying inside the image."""
        self._aspect = ratio
        if self._box is not None and ratio:
            self._apply_aspect_keep_origin()
            self.update()
            self._emit_changed()

    def has_box(self):
        return self._box is not None

    def _box_tuple(self):
        b = self._box
        return (round(b.x(), 6), round(b.y(), 6),
                round(b.width(), 6), round(b.height(), 6))

    def current_pixels(self):
        """The resulting crop size in real image pixels, for the readout."""
        item = self._view._item
        if item.pixmap().isNull() or self._box is None:
            return None
        pm = item.pixmap()
        return (int(round(self._box.width() * pm.width())),
                int(round(self._box.height() * pm.height())))

    def _emit_changed(self):
        if self._box is not None:
            self.changed.emit(self._box_tuple())

    def _apply_aspect_keep_origin(self):
        """Reshape the current box to self._aspect (width/height in the
        DISPLAYED image), keeping the top-left corner and staying inside the
        image. Derives the height from the width; if that would run past the
        bottom edge, derives the width from the available height instead - so
        tall (portrait) ratios fit as readily as wide ones."""
        r = self._image_rect()
        if r is None or not self._aspect:
            return
        # The box is in normalized coords; the target ratio is in pixels, so
        # convert through the image rect's pixel aspect.
        img_ar = r.width() / r.height() if r.height() else 1.0
        new_h_norm = self._box.width() * img_ar / self._aspect
        nb = QRectF(self._box.x(), self._box.y(), self._box.width(),
                    new_h_norm)
        if nb.y() + nb.height() > 1.0:
            # Too tall to fit from this origin: fix the height to what's
            # left and derive the width from it.
            nb.setHeight(1.0 - nb.y())
            nb.setWidth(nb.height() * self._aspect / img_ar)
        if nb.x() + nb.width() > 1.0:
            # And if THAT width overflows the right edge, clamp width and
            # re-derive height - covers very wide ratios on a narrow origin.
            nb.setWidth(1.0 - nb.x())
            nb.setHeight(nb.width() * img_ar / self._aspect)
        self._box = nb

    # -- painting ----------------------------------------------------------
    def paintEvent(self, event):
        if self._box is None:
            return
        box = self._norm_to_px(self._box)
        if box is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        # Darken outside the box by painting four rectangles AROUND it,
        # rather than filling the whole widget and clearing the middle. The
        # clear trick needs a backing store with alpha and renders as solid
        # black where that is missing (Harald's Mac); four dim rects always
        # composite correctly over the image below.
        dim = QColor(0, 0, 0, 130)
        full = QRectF(self.rect())
        top = QRectF(full.left(), full.top(), full.width(),
                     box.top() - full.top())
        bottom = QRectF(full.left(), box.bottom(), full.width(),
                        full.bottom() - box.bottom())
        left = QRectF(full.left(), box.top(),
                      box.left() - full.left(), box.height())
        right = QRectF(box.right(), box.top(),
                       full.right() - box.right(), box.height())
        for band in (top, bottom, left, right):
            if band.width() > 0 and band.height() > 0:
                p.fillRect(band, dim)
        # rule-of-thirds grid
        pen = QPen(QColor(255, 255, 255, 160), 1)
        p.setPen(pen)
        for i in (1, 2):
            x = box.x() + box.width() * i / 3.0
            y = box.y() + box.height() * i / 3.0
            p.drawLine(int(x), int(box.y()), int(x), int(box.bottom()))
            p.drawLine(int(box.x()), int(y), int(box.right()), int(y))
        # border
        p.setPen(QPen(QColor(255, 255, 255, 230), 2))
        p.drawRect(box)
        # handles
        p.setBrush(QBrush(QColor(255, 255, 255, 230)))
        p.setPen(QPen(QColor(0, 0, 0, 200), 1))
        for cx, cy in self._handle_centers(box):
            p.drawRect(int(cx - self.HANDLE / 2), int(cy - self.HANDLE / 2),
                       self.HANDLE, self.HANDLE)
        p.end()

    def _handle_centers(self, box):
        xs = (box.x(), box.center().x(), box.right())
        ys = (box.y(), box.center().y(), box.bottom())
        for j, cy in enumerate(ys):
            for i, cx in enumerate(xs):
                if i == 1 and j == 1:
                    continue        # no center handle
                yield cx, cy

    def _handle_at(self, pos, box):
        names = ['tl', 'tm', 'tr', 'ml', 'mr', 'bl', 'bm', 'br']
        centers = list(self._handle_centers(box))
        for name, (cx, cy) in zip(names, centers):
            if abs(pos.x() - cx) <= self.HANDLE and abs(pos.y() - cy) <= self.HANDLE:
                return name
        return None

    # -- mouse -------------------------------------------------------------
    def mousePressEvent(self, event):
        if self._box is None:
            return
        box = self._norm_to_px(self._box)
        pos = event.pos()
        handle = self._handle_at(pos, box) if box else None
        if handle:
            self._drag = (handle, pos, QRectF(box))
        elif box and box.contains(pos):
            self._drag = ('move', pos, QRectF(box))
        else:
            # start a new box from here
            r = self._image_rect()
            if r and r.contains(pos):
                self._drag = ('new', pos, None)
        event.accept()

    def mouseMoveEvent(self, event):
        if self._drag is None or self._box is None:
            return
        kind, start, orig = self._drag
        r = self._image_rect()
        if r is None:
            return
        pos = event.pos()
        dx, dy = pos.x() - start.x(), pos.y() - start.y()
        if kind == 'move':
            nb = QRectF(orig)
            nb.translate(dx, dy)
            # keep inside the image rect
            if nb.left() < r.left():
                nb.moveLeft(r.left())
            if nb.top() < r.top():
                nb.moveTop(r.top())
            if nb.right() > r.right():
                nb.moveRight(r.right())
            if nb.bottom() > r.bottom():
                nb.moveBottom(r.bottom())
            self._box = self._px_to_norm(nb)
        elif kind == 'new':
            nb = QRectF(start, pos).normalized()
            nb = nb.intersected(r)
            self._box = self._px_to_norm(nb)
            if self._aspect:
                self._apply_aspect_keep_origin()
        else:
            self._resize_handle(kind, orig, dx, dy, r)
        self.update()
        self._emit_changed()
        event.accept()

    def mouseReleaseEvent(self, event):
        self._drag = None
        event.accept()

    def _resize_handle(self, name, orig, dx, dy, r):
        nb = QRectF(orig)
        if 'l' in name:
            nb.setLeft(orig.left() + dx)
        if 'r' in name:
            nb.setRight(orig.right() + dx)
        if 't' in name:
            nb.setTop(orig.top() + dy)
        if 'b' in name:
            nb.setBottom(orig.bottom() + dy)
        nb = nb.normalized().intersected(r)
        if nb.width() < 8 or nb.height() < 8:
            return
        self._box = self._px_to_norm(nb)
        if self._aspect:
            self._apply_aspect_keep_origin()


class CullImageView(QGraphicsView):

    zoom_requested = pyqtSignal()      # emitted on click/Z; mixin loads 'full'
    zoom_changed = pyqtSignal(float)   # current scale factor (1.0 = 100%)
    fullscreen_requested = pyqtSignal()  # double-click toggles fullscreen
    pixel_picked = pyqtSignal(int, int, int)   # r, g, b under the pipette

    MIN_ZOOM, MAX_ZOOM = 0.05, 4.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self._item = QGraphicsPixmapItem()
        self._item.setTransformationMode(Qt.SmoothTransformation)
        self._scene.addItem(self._item)
        self.setScene(self._scene)
        self.setRenderHints(QPainter.SmoothPixmapTransform)
        self.setBackgroundBrush(Qt.black)
        self.setFrameShape(QGraphicsView.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setFocusPolicy(Qt.NoFocus)    # keys are handled by the tab
        self._fit = True

        # Bottom-right status overlay (stars + label color), used in
        # fullscreen where the toolbar/status bar are not visible.
        self.overlay = QLabel(self)
        self.overlay.setStyleSheet(
            'background: rgba(0, 0, 0, 165); color: white;'
            'padding: 6px 12px; border-radius: 6px; font-size: 20px;')
        self.overlay.setTextFormat(Qt.RichText)
        self.overlay.hide()

        # Top-left info overlay (EXIF summary, toggled with the i key).
        self.info_overlay = QLabel(self)
        self.info_overlay.setStyleSheet(
            'background: rgba(0, 0, 0, 165); color: white;'
            'padding: 8px 12px; border-radius: 6px; font-size: 13px;')
        self.info_overlay.setTextFormat(Qt.RichText)
        self.info_overlay.hide()

        # Crop overlay (0.13): a transparent child that edits a crop box in
        # normalized coordinates. Hidden until the tab turns crop mode on.
        self.crop = CropOverlay(self)
        # 0.14: the untouched pixmap plus the crop currently DISPLAYED.
        self._full_pixmap = QPixmap()
        self._crop_display = None
        self._pipette = False

    # -- content ---------------------------------------------------------------

    def set_image(self, qimage, keep_view=False):
        """Show a QImage. keep_view=True swaps the pixels without resetting
        zoom/pan (used when the 'full' level arrives while zoomed in)."""
        self._full_pixmap = QPixmap.fromImage(qimage)
        self._apply_crop_display(keep_view)

    def set_crop_display(self, box):
        """Show the image cropped to `box` (normalized x, y, w, h) or, with
        box=None, in full (0.14).

        The full pixmap is kept, so entering crop mode can put the whole
        frame back and the box stays draggable beyond its current edges.
        """
        if box == self._crop_display:
            return
        self._crop_display = tuple(box) if box else None
        if not self._full_pixmap.isNull():
            self._apply_crop_display(False)

    def crop_display(self):
        return self._crop_display

    def _apply_crop_display(self, keep_view):
        pm = self._full_pixmap
        if pm.isNull():
            self._item.setPixmap(QPixmap())
            return
        if self._crop_display:
            x, y, w, h = self._crop_display
            rect = QRect(int(round(x * pm.width())),
                         int(round(y * pm.height())),
                         max(1, int(round(w * pm.width()))),
                         max(1, int(round(h * pm.height()))))
            rect = rect.intersected(pm.rect())
            if rect.width() > 0 and rect.height() > 0:
                pm = pm.copy(rect)
        self._item.setPixmap(pm)
        self._scene.setSceneRect(QRectF(pm.rect()))
        if not keep_view:
            self.fit()

    def clear_image(self):
        self._full_pixmap = QPixmap()
        self._item.setPixmap(QPixmap())
        self._fit = True

    # -- zoom ------------------------------------------------------------------

    @property
    def is_fit(self):
        return self._fit

    def zoom_factor(self):
        return self.transform().m11()

    def _ratios(self):
        pm = self._item.pixmap()
        if pm.isNull() or not pm.width() or not pm.height():
            return None
        vp = self.viewport()
        return (vp.width() / pm.width(), vp.height() / pm.height())

    def fit_factor(self):
        """Scale at which the whole image fits the viewport."""
        r = self._ratios()
        return min(r) if r else 1.0

    def fill_factor(self):
        """Scale at which the image covers the viewport (Lightroom 'Fill')."""
        r = self._ratios()
        return max(r) if r else 1.0

    def fit(self):
        self._fit = True
        self.setDragMode(QGraphicsView.NoDrag)
        if not self._item.pixmap().isNull():
            self.fitInView(self._item, Qt.KeepAspectRatio)
        self.zoom_changed.emit(self.zoom_factor())

    def set_zoom(self, factor, anchor_scene_pos=None):
        """Continuous zoom (slider / Ctrl-Cmd +/-). 1.0 = 100%."""
        factor = max(self.MIN_ZOOM, min(self.MAX_ZOOM, factor))
        self._fit = False
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        center = (anchor_scene_pos if anchor_scene_pos is not None
                  else self.mapToScene(self.viewport().rect().center()))
        self.resetTransform()
        self.scale(factor, factor)
        self.centerOn(center)
        self.zoom_changed.emit(factor)

    def zoom_step(self, direction):
        """One Lightroom-style step (x1.25) in or out around the center."""
        self.set_zoom(self.zoom_factor() * (1.25 ** direction))

    def zoom_100(self, anchor_scene_pos=None):
        """1:1 pixels, centered on the given scene position (or the middle)."""
        self.set_zoom(1.0, anchor_scene_pos
                      if anchor_scene_pos is not None else None)

    def toggle_zoom(self, anchor_scene_pos=None):
        if self._fit:
            self.zoom_100(anchor_scene_pos)
        else:
            self.fit()

    # -- events ----------------------------------------------------------------

    def set_overlay(self, html):
        self.overlay.setText(html)
        self.overlay.adjustSize()
        self._place_overlay()

    def show_overlay(self, on):
        self.overlay.setVisible(on)
        if on:
            self._place_overlay()

    def _place_overlay(self):
        m = 14
        self.overlay.move(self.width() - self.overlay.width() - m,
                          self.height() - self.overlay.height() - m)

    def set_info_overlay(self, html):
        self.info_overlay.setText(html)
        self.info_overlay.adjustSize()
        self.info_overlay.move(14, 14)

    def show_info_overlay(self, on):
        self.info_overlay.setVisible(on)
        if on:
            self.info_overlay.move(14, 14)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._fit:
            self.fit()
        self._place_overlay()
        if self.crop.isVisible():
            self.crop.setGeometry(self.rect())
            self.crop.update()
        # The edit panel is a child of the view, so it has to be re-placed
        # whenever the view changes size (window resize, fullscreen).
        panel = getattr(self, 'edit_panel', None)
        if panel is not None and panel.isVisible():
            panel.place()

    def set_pipette(self, on):
        """White-balance pipette mode (0.14): the next left click samples a
        pixel instead of zooming."""
        self._pipette = bool(on)
        self.setCursor(Qt.CrossCursor if on else Qt.ArrowCursor)

    def pipette_active(self):
        return self._pipette

    def _sample_at(self, view_pos):
        """-> (r, g, b) under a viewport position, or None if off-image."""
        pm = self._item.pixmap()
        if pm.isNull():
            return None
        pt = self._item.mapFromScene(self.mapToScene(view_pos)).toPoint()
        if not pm.rect().contains(pt):
            return None
        colour = pm.toImage().pixelColor(pt)
        return colour.red(), colour.green(), colour.blue()

    def mousePressEvent(self, event):
        if self._pipette and event.button() == Qt.LeftButton:
            sample = self._sample_at(event.pos())
            if sample:
                self.pixel_picked.emit(*sample)
            event.accept()
            return
        if event.button() == Qt.LeftButton and self._fit \
                and not self._item.pixmap().isNull():
            # Click while fitted: zoom to 100% at the click position. The
            # mixin may swap in the 'full' image right after.
            self.zoom_requested.emit()
            self.toggle_zoom(self.mapToScene(event.pos()))
            event.accept()
            return
        if event.button() == Qt.LeftButton and not self._fit:
            # While zoomed, a plain click (no drag) toggles back in
            # mouseReleaseEvent; store the press position to tell them apart.
            self._press_pos = event.pos()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Qt delivers the second press of a double-click as THIS event,
            # but the FIRST press already ran the single-click zoom-to-100%.
            # Undo that so fullscreen starts fitted, then let the tab toggle
            # fullscreen (same path as the F key).
            if not self._fit:
                self.fit()
            self.fullscreen_requested.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mouseReleaseEvent(self, event):
        if (event.button() == Qt.LeftButton and not self._fit
                and getattr(self, '_press_pos', None) is not None
                and (event.pos() - self._press_pos).manhattanLength() < 4):
            self.fit()
        self._press_pos = None
        super().mouseReleaseEvent(event)
