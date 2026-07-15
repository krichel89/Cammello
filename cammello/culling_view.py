"""Image view widget for the culling tab: fit-to-window or 100% zoom anchored
at the mouse position, panning by drag while zoomed. Pure display - all
keyboard handling and data logic live in mw_culling.py.
"""
from PyQt5.QtWidgets import (QGraphicsView, QGraphicsScene,
                             QGraphicsPixmapItem, QLabel)
from PyQt5.QtGui import QPixmap, QPainter
from PyQt5.QtCore import Qt, pyqtSignal, QRectF


class CullImageView(QGraphicsView):

    zoom_requested = pyqtSignal()      # emitted on click/Z; mixin loads 'full'
    zoom_changed = pyqtSignal(float)   # current scale factor (1.0 = 100%)

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

    # -- content ---------------------------------------------------------------

    def set_image(self, qimage, keep_view=False):
        """Show a QImage. keep_view=True swaps the pixels without resetting
        zoom/pan (used when the 'full' level arrives while zoomed in)."""
        pm = QPixmap.fromImage(qimage)
        self._item.setPixmap(pm)
        self._scene.setSceneRect(QRectF(pm.rect()))
        if not keep_view:
            self.fit()

    def clear_image(self):
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

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._fit:
            self.fit()
        self._place_overlay()

    def mousePressEvent(self, event):
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

    def mouseReleaseEvent(self, event):
        if (event.button() == Qt.LeftButton and not self._fit
                and getattr(self, '_press_pos', None) is not None
                and (event.pos() - self._press_pos).manhattanLength() < 4):
            self.fit()
        self._press_pos = None
        super().mouseReleaseEvent(event)
