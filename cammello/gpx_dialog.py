"""The GPX matching dialog (0.15.0).

One dialog, driven by hand: pick the track, check the offset the system
zone guessed, set the maximum gap, look at the preview, then apply. The
preview is the point - a time-based match that writes without showing its
work is exactly the kind of tool that quietly pins a whole shoot to the
wrong street.
"""
import os

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QLineEdit, QSpinBox, QFileDialog,
                             QTableWidget, QTableWidgetItem, QCheckBox,
                             QDialogButtonBox)
from PyQt5.QtCore import Qt

from .i18n import tr
from . import gpx
from . import geo


class GpxMatchDialog(QDialog):
    """Match a .gpx track against the files of the MediaWiki table.

    The caller passes [(path, date_text, has_coords)] and reads
    `results` after exec(): {path: (lat, lon)} for every file the user
    chose to apply. The dialog never writes anything itself.
    """

    def __init__(self, files, parent=None, settings=None):
        super().__init__(parent)
        self.setWindowTitle(tr('Match GPX track'))
        self._files = files
        self._points = []
        self._matches = {}
        self.results = {}
        self._settings = settings

        lay = QVBoxLayout(self)

        # Track picker.
        row = QHBoxLayout()
        self._gpx_edit = QLineEdit()
        self._gpx_edit.setPlaceholderText(tr('No track picked yet'))
        self._gpx_edit.setReadOnly(True)
        pick = QPushButton(tr('Pick GPX file…'))
        pick.clicked.connect(self._pick)
        row.addWidget(QLabel(tr('Track')))
        row.addWidget(self._gpx_edit, 1)
        row.addWidget(pick)
        lay.addLayout(row)

        # Offset and gap.
        row2 = QHBoxLayout()
        self._offset = QSpinBox()
        self._offset.setRange(-24 * 60, 24 * 60)
        self._offset.setSuffix(' min')
        self._offset.setValue(gpx.system_utc_offset_s() // 60)
        self._offset.setToolTip(tr(
            'How far the CAMERA clock stood from UTC when the pictures were '
            'taken.\nPreset from this computer\'s time zone - right exactly '
            'when the camera\nclock stood in this zone. A trip abroad or a '
            'drifting camera clock\nneeds a correction here.'))
        self._gap = QSpinBox()
        self._gap.setRange(1, 24 * 60)
        self._gap.setSuffix(' min')
        self._gap.setValue(gpx.DEFAULT_MAX_GAP_S // 60)
        self._gap.setToolTip(tr(
            'A photo further than this from every track point gets NO '
            'position\nrather than a wrong one - a logger that was off for '
            'an hour must not\npin the photo to wherever the track stopped.'))
        row2.addWidget(QLabel(tr('Camera clock offset from UTC')))
        row2.addWidget(self._offset)
        row2.addSpacing(16)
        row2.addWidget(QLabel(tr('Maximum time gap')))
        row2.addWidget(self._gap)
        row2.addStretch()
        lay.addLayout(row2)

        self._offset.valueChanged.connect(self._rematch)
        self._gap.valueChanged.connect(self._rematch)

        # Preview.
        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(
            [tr('File'), tr('Capture time'), tr('Matched position')])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionMode(QTableWidget.NoSelection)
        lay.addWidget(self._table, 1)

        self._overwrite = QCheckBox(tr(
            'Overwrite camera positions the files already have'))
        self._overwrite.setToolTip(tr(
            'Off: only files WITHOUT a camera position get one. On: the '
            'matched\nposition replaces what is there - for the case where '
            'the camera GPS\nwas wrong and has been cleared or is to be '
            'replaced outright.'))
        self._overwrite.toggled.connect(self._rematch)
        lay.addWidget(self._overwrite)

        self._summary = QLabel('')
        lay.addWidget(self._summary)

        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self._ok_btn = box.button(QDialogButtonBox.Ok)
        self._ok_btn.setText(tr('Apply to files'))
        self._ok_btn.setEnabled(False)
        box.accepted.connect(self._accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

        self.resize(680, 480)
        self._fill_table()

    # ── mechanics ────────────────────────────────────────────────────────────

    def _pick(self):
        start = ''
        if self._settings is not None:
            start = self._settings.value('gpx_last_dir', '') or ''
        path, _f = QFileDialog.getOpenFileName(
            self, tr('Pick GPX file…'), start, 'GPX (*.gpx)')
        if not path:
            return
        if self._settings is not None:
            self._settings.setValue('gpx_last_dir', os.path.dirname(path))
        self._gpx_edit.setText(path)
        self._points = gpx.index_points(gpx.parse_gpx(path))
        self._rematch()

    def _rematch(self, *_a):
        self._matches = {}
        if self._points:
            self._matches = gpx.match_files(
                self._points,
                [(p, d) for p, d, _has in self._files],
                self._offset.value() * 60,
                self._gap.value() * 60)
        self._fill_table()

    def _would_apply(self, path, has_coords):
        """Whether this file would receive a position on Apply."""
        hit = self._matches.get(path)
        if hit is None:
            return False
        return self._overwrite.isChecked() or not has_coords

    def _fill_table(self):
        self._table.setRowCount(len(self._files))
        applied = 0
        matched = 0
        for row, (path, date_text, has_coords) in enumerate(self._files):
            self._table.setItem(row, 0, QTableWidgetItem(
                os.path.basename(path)))
            self._table.setItem(row, 1, QTableWidgetItem(
                date_text or tr('no capture time')))
            hit = self._matches.get(path)
            if hit is not None:
                matched += 1
                text = geo.format_pair(hit)
                if not self._would_apply(path, has_coords):
                    text += '  ' + tr('(kept - has a position)')
                else:
                    applied += 1
            elif not self._points:
                text = ''
            elif not date_text:
                text = tr('no capture time')
            else:
                text = tr('no track point close enough')
            item = QTableWidgetItem(text)
            self._table.setItem(row, 2, item)
        if self._points:
            self._summary.setText(tr(
                '{points} track points; {matched} of {total} files matched, '
                '{applied} would be written.').format(
                    points=len(self._points), matched=matched,
                    total=len(self._files), applied=applied))
        elif self._gpx_edit.text():
            self._summary.setText(tr('The track holds no usable points.'))
        else:
            self._summary.setText('')
        self._ok_btn.setEnabled(applied > 0)

    def _accept(self):
        self.results = {
            path: self._matches[path]
            for path, _d, has_coords in self._files
            if self._would_apply(path, has_coords)}
        self.accept()
