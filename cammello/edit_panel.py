"""The floating edit panel (0.14): crop, white balance and exposure in one
small window that sits in the top-right corner of the culling view.

It is a CHILD of the view, not a separate top-level window: it then travels
with fullscreen, never lands behind the main window, and needs no separate
show/hide bookkeeping. It starts top-right with a margin and can be DRAGGED
anywhere in the view by its title bar (0.14.2); the position is remembered
as a fraction of the view, so it keeps its place when the window is resized
or goes fullscreen, and it is clamped so it can never leave the view.

The panel holds no state of its own - it displays what the tab tells it and
emits what the user asked for. All edits live in edits.py.
"""
from PyQt5.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QToolButton, QSizePolicy,
                             QAbstractButton)
from PyQt5.QtCore import Qt, pyqtSignal

from .i18n import tr
from . import edits


class EditPanel(QFrame):
    """Compact controls for the ad-hoc edits. Keyboard remains the fast
    path (C, W, +/-); the panel makes the state visible and reachable with
    the mouse."""

    crop_requested = pyqtSignal()
    pipette_toggled = pyqtSignal(bool)
    ev_step_requested = pyqtSignal(int)     # +1 / -1 sixths of a stop
    reset_requested = pyqtSignal()

    MARGIN = 12

    def __init__(self, view):
        super().__init__(view)
        self._view = view
        self.setObjectName('cammelloEditPanel')
        self.setFrameShape(QFrame.StyledPanel)
        self.setAttribute(Qt.WA_StyledBackground, True)
        # Slightly translucent dark panel: readable over both a bright and a
        # dark photograph without stealing attention from it.
        self.setStyleSheet(
            '#cammelloEditPanel { background: rgba(28, 30, 34, 218);'
            ' border: 1px solid rgba(255, 255, 255, 40); border-radius: 8px; }'
            '#cammelloEditPanel QLabel { color: #f0f0f0; }'
            '#cammelloEditPanel QPushButton, #cammelloEditPanel QToolButton {'
            ' color: #f0f0f0; background: rgba(255, 255, 255, 26);'
            ' border: 1px solid rgba(255, 255, 255, 40); border-radius: 4px;'
            ' padding: 3px 8px; }'
            '#cammelloEditPanel QToolButton:checked {'
            ' background: #d8a12a; color: #202020; }'
            '#cammelloEditPanel QLabel#cammelloCropHelp {'
            ' color: #d7dde3; font-size: 11px; }')

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)

        # Title doubles as the drag handle; the grip dots say so without
        # needing a word for it.
        self.title = QLabel('\u2059  ' + tr('Edit'))
        f = self.title.font()
        f.setBold(True)
        self.title.setFont(f)
        self.title.setToolTip(tr('Drag to move this panel'))
        lay.addWidget(self.title)

        self.crop_btn = QPushButton(tr('Crop (C)'))
        self.crop_btn.setToolTip(tr('Draw a crop on this image. Enter '
                                    'applies it, Esc cancels.'))
        self.crop_btn.clicked.connect(self.crop_requested)
        lay.addWidget(self.crop_btn)

        # The crop key legend (0.14.2). The toolbar shows the same thing,
        # but while cropping the eye is on the picture - and the panel sits
        # right there. Hidden until crop mode starts, so the panel stays
        # small the rest of the time.
        self.crop_help = QLabel()
        self.crop_help.setObjectName('cammelloCropHelp')
        self.crop_help.setTextFormat(Qt.RichText)
        self.crop_help.setWordWrap(True)
        self.crop_help.setMaximumWidth(260)
        self.crop_help.hide()
        lay.addWidget(self.crop_help)

        self.wb_btn = QToolButton()
        self.wb_btn.setText(tr('White balance (W)'))
        self.wb_btn.setCheckable(True)
        self.wb_btn.setToolTip(tr(
            'Pick a spot that should be neutral grey or white.\n'
            'Click the picture with the pipette; press W again to stop.'))
        self.wb_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.wb_btn.toggled.connect(self.pipette_toggled)
        lay.addWidget(self.wb_btn)

        ev_row = QHBoxLayout()
        ev_row.setSpacing(4)
        self.ev_minus = QPushButton('\u2212')
        self.ev_plus = QPushButton('+')
        for b in (self.ev_minus, self.ev_plus):
            b.setFixedWidth(30)
            b.setToolTip(tr('Exposure in sixths of a stop'))
        self.ev_lbl = QLabel('EV 0')
        self.ev_lbl.setAlignment(Qt.AlignCenter)
        self.ev_lbl.setMinimumWidth(64)
        self.ev_minus.clicked.connect(lambda: self.ev_step_requested.emit(-1))
        self.ev_plus.clicked.connect(lambda: self.ev_step_requested.emit(1))
        ev_row.addWidget(self.ev_minus)
        ev_row.addWidget(self.ev_lbl)
        ev_row.addWidget(self.ev_plus)
        lay.addLayout(ev_row)

        self.reset_btn = QPushButton(tr('Reset all'))
        self.reset_btn.setToolTip(tr('Remove crop, white balance and '
                                     'exposure from this image.'))
        self.reset_btn.clicked.connect(self.reset_requested)
        lay.addWidget(self.reset_btn)

        # Drag state (0.14.2). _rel_pos is None while the panel sits at its
        # default corner; a drag turns it into a (x, y) fraction of the view.
        self._rel_pos = None
        self._drag_offset = None
        self.setCursor(Qt.OpenHandCursor)

        self.adjustSize()
        self.hide()

    # -- state ------------------------------------------------------------
    def show_state(self, record, cropping=False):
        """Reflect one image's edit record. record may be None."""
        record = record or {}
        ev = record.get('ev', 0.0)
        self.ev_lbl.setText(self._format_ev(ev))
        has_wb = 'wb' in record
        self.wb_btn.setText(tr('White balance (W)')
                            + (' \u2713' if has_wb else ''))
        self.crop_btn.setText(tr('Crop (C)')
                              + (' \u2713' if 'crop' in record else ''))
        self.crop_btn.setDown(cropping)
        self.reset_btn.setEnabled(bool(record))

    @staticmethod
    def _format_ev(ev):
        """EV as sixths, the unit it is edited in: 'EV +0 4/6'."""
        if not ev:
            return 'EV 0'
        sixths = int(round(ev / edits.EV_STEP))
        whole, rest = divmod(abs(sixths), 6)
        sign = '+' if sixths > 0 else '\u2212'
        if rest == 0:
            return f'EV {sign}{whole}'
        if whole == 0:
            return f'EV {sign}{rest}/6'
        return f'EV {sign}{whole} {rest}/6'

    def set_pipette_checked(self, on):
        """Keep the button in step when the mode was toggled by key."""
        if self.wb_btn.isChecked() != on:
            self.wb_btn.blockSignals(True)
            self.wb_btn.setChecked(on)
            self.wb_btn.blockSignals(False)

    def set_cropping(self, on):
        """Show or hide the crop key legend (0.14.2). The same keys the
        toolbar lists, repeated where the eye is while cropping."""
        if on:
            self.crop_help.setText(
                '<b>' + tr('Crop keys') + '</b><br>'
                '1 ' + tr('free') + ' &middot; 2 3:2 &middot; 3 4:3 &middot; '
                '4 1:1 &middot; 5 16:9 &middot; 6 5:4<br>'
                + tr('Same number again = rotate') + '<br>'
                '<b>\u21b5</b> ' + tr('apply') + ' &middot; '
                '<b>Esc</b> ' + tr('cancel') + ' &middot; '
                '<b>\u21e7C</b> ' + tr('remove'))
            self.crop_help.show()
        else:
            self.crop_help.hide()
        self.adjustSize()
        self.place()

    # -- placement --------------------------------------------------------
    def place(self):
        """Put the panel where the user left it, or top-right by default.

        The stored position is a FRACTION of the view, so a resize or a
        jump to fullscreen keeps the panel in the same relative spot
        instead of stranding it outside the visible area. The result is
        clamped to the view either way.
        """
        self.adjustSize()
        vw, vh = self._view.width(), self._view.height()
        if self._rel_pos is None:
            x = vw - self.width() - self.MARGIN
            y = self.MARGIN
        else:
            x = self._rel_pos[0] * vw
            y = self._rel_pos[1] * vh
        max_x = max(0, vw - self.width())
        max_y = max(0, vh - self.height())
        self.move(int(max(0, min(x, max_x))), int(max(0, min(y, max_y))))
        self.raise_()

    def reset_position(self):
        """Back to the top-right default."""
        self._rel_pos = None
        self.place()

    def _remember_position(self):
        vw, vh = max(1, self._view.width()), max(1, self._view.height())
        self._rel_pos = (self.x() / vw, self.y() / vh)

    # -- dragging ---------------------------------------------------------
    def _in_drag_zone(self, pos):
        """True where a press starts a drag: the title, the labels and the
        panel background - anywhere that is not a button.

        Deliberately NOT just the title bar: that strip is barely 20 px
        high, which is a fiddly target over a photograph, and its geometry
        is only valid once the layout has run (a press arriving before
        that would silently do nothing).
        """
        child = self.childAt(pos)
        return not isinstance(child, QAbstractButton)

    def mousePressEvent(self, event):
        # Buttons keep their own clicks; everything else drags the panel.
        if (event.button() == Qt.LeftButton
                and self._in_drag_zone(event.pos())):
            self._drag_offset = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None:
            target = self.mapToParent(event.pos() - self._drag_offset)
            max_x = max(0, self._view.width() - self.width())
            max_y = max(0, self._view.height() - self.height())
            self.move(max(0, min(target.x(), max_x)),
                      max(0, min(target.y(), max_y)))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag_offset is not None:
            self._drag_offset = None
            self.setCursor(Qt.OpenHandCursor)
            self._remember_position()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self._in_drag_zone(event.pos()):
            self.reset_position()       # double-click the title = back home
            event.accept()
            return
        super().mouseDoubleClickEvent(event)
