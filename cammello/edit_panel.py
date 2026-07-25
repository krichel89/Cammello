"""The floating edit panel (0.14): crop, white balance and exposure in one
small window that sits in the top-right corner of the culling view.

It is a CHILD of the view, not a separate top-level window: it then travels
with fullscreen, never lands behind the main window, and needs no separate
show/hide bookkeeping. Position is top-right with a margin, re-applied on
every resize.

The panel holds no state of its own - it displays what the tab tells it and
emits what the user asked for. All edits live in edits.py.
"""
from PyQt5.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QToolButton, QSizePolicy)
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
            ' background: #d8a12a; color: #202020; }')

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)

        title = QLabel(tr('Edit'))
        f = title.font()
        f.setBold(True)
        title.setFont(f)
        lay.addWidget(title)

        self.crop_btn = QPushButton(tr('Crop (C)'))
        self.crop_btn.setToolTip(tr('Draw a crop on this image. Enter '
                                    'applies it, Esc cancels.'))
        self.crop_btn.clicked.connect(self.crop_requested)
        lay.addWidget(self.crop_btn)

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

    # -- placement --------------------------------------------------------
    def place(self):
        """Top-right of the view, with a margin - where it covers the least
        of a typical picture."""
        self.adjustSize()
        self.move(max(0, self._view.width() - self.width() - self.MARGIN),
                  self.MARGIN)
        self.raise_()
