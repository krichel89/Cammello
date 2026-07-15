"""Small custom widgets (grip, collapsible group, drop table, delegates, login)."""
import os
from PyQt5.QtWidgets import (QWidget, QLabel, QLineEdit, QPushButton,
                             QToolButton, QFrame, QHeaderView,
                             QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
                             QTextEdit, QDialog, QDialogButtonBox, QCheckBox,
                             QTableWidget, QTableWidgetItem, QStyledItemDelegate,
                             QAbstractItemView, QProgressBar, QComboBox)
from PyQt5.QtCore import (Qt, QEvent, pyqtSignal, QUrl, QSize, QSettings,
                          QObject)
from PyQt5.QtGui import QDesktopServices, QPixmap, QIcon
from .constants import *
from .i18n import tr
from .sdc import *


class FilenameDelegate(QStyledItemDelegate):
    """Editor for the target-filename column.

    While editing, only the base name (without extension) is shown; the source
    file's extension is firmly re-appended on commit and therefore cannot be
    changed.
    """

    def __init__(self, ext_for_row, parent=None):
        super().__init__(parent)
        self.ext_for_row = ext_for_row  # callable(row) -> '.jpg'

    @staticmethod
    def _strip_image_ext(text):
        root, ext = os.path.splitext(text)
        return root if ext.lower() in IMAGE_EXTS else text

    def createEditor(self, parent, option, index):
        return QLineEdit(parent)

    def setEditorData(self, editor, index):
        editor.setText(self._strip_image_ext(index.data() or ''))

    def setModelData(self, editor, model, index):
        base = self._strip_image_ext(editor.text().strip())
        if not base:
            return  # empty name -> keep the previous value
        ext = self.ext_for_row(index.row()) or ''
        model.setData(index, base + ext)


# ── Login dialog ───────────────────────────────────────────────────────────────


class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('Login – Wikimedia Commons'))
        self.setMinimumWidth(420)
        self.settings = QSettings(APP_NAME, 'Login')

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.url_edit = QLineEdit(self.settings.value(
            'api_url', 'https://commons.wikimedia.org/w/api.php'))
        self.url_edit.setVisible(False)  # hidden; always Commons by default
        self.user_edit = QLineEdit(self.settings.value('username', ''))
        self.user_edit.setPlaceholderText(tr('e.g.') + ' Seewolf@Cammello')
        # Prefilled when a password is stored via Settings -> MediaWiki
        # account; otherwise empty = asked per session (old behavior).
        self.pass_edit = QLineEdit(self.settings.value('password', ''))
        self.pass_edit.setEchoMode(QLineEdit.Password)

        form.addRow(tr('Username:'), self.user_edit)
        form.addRow(tr('Password:'), self.pass_edit)
        layout.addLayout(form)

        hint = QLabel(
            tr('Use a <b>BotPassword</b>: create one at '
            '<a href="https://commons.wikimedia.org/wiki/Special:BotPasswords">'
            'Special:BotPasswords</a> and log in with the name shown there '
            '(e.g. <i>YourName@Cammello</i>).<br><br>'
            'Required grants:'
            '<ul style="margin-top:2px;">'
            '<li>Edit existing pages</li>'
            '<li>Create, edit, and move pages</li>'
            '<li>Upload new files</li>'
            '<li>Upload, replace, and move files</li>'
            '</ul>'))
        hint.setStyleSheet('color: gray; font-size: 11px;')
        hint.setWordWrap(True)
        hint.setOpenExternalLinks(True)
        hint.setTextInteractionFlags(Qt.TextBrowserInteraction)
        layout.addWidget(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_credentials(self):
        self.settings.setValue('api_url', self.url_edit.text())
        self.settings.setValue('username', self.user_edit.text())
        return self.url_edit.text(), self.user_edit.text(), self.pass_edit.text()


# ── Structured editor: language list, example, captions editor ──────────────────

# Curated language list for the caption dropdown (code, display name).

class FocusOutTextEdit(QTextEdit):
    """QTextEdit that emits editingFinished when it loses focus.

    QTextEdit has no built-in editingFinished (unlike QLineEdit); this lets the
    raw description editor commit to the table on field switch instead of per
    keystroke.
    """
    editingFinished = pyqtSignal()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.editingFinished.emit()



class _VGrip(QWidget):
    """A thin horizontal grip strip that lets the user drag-resize the height of
    a target widget. Used to make the extra-wikitext box resizable."""

    def __init__(self, target, min_height, parent=None):
        super().__init__(parent)
        self._target = target
        self._min_height = min_height
        self.setFixedHeight(7)
        self.setCursor(Qt.SizeVerCursor)
        self.setToolTip(tr('Drag to resize the field'))
        self.setStyleSheet('background:#b0b0b0; border-radius:3px; margin:1px 0;')
        self._press_y = None
        self._start_h = 0

    def mousePressEvent(self, event):
        self._press_y = event.globalPos().y()
        self._start_h = self._target.height()

    def mouseMoveEvent(self, event):
        if self._press_y is None:
            return
        delta = event.globalPos().y() - self._press_y
        self._target.setFixedHeight(max(self._min_height, self._start_h + delta))

    def mouseReleaseEvent(self, event):
        self._press_y = None



class CollapsibleGroupBox(QWidget):
    """A section with a simple collapse arrow.

    The header is a checkable QToolButton showing an arrow (down = expanded,
    right = collapsed) plus the section title; clicking it toggles the framed
    content widget. Keeps the isCheckable/setChecked/isChecked/title interface
    of the previous QGroupBox-based version.
    """

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self._btn = QToolButton(self)
        self._btn.setObjectName('groupTitle')
        self._btn.setText(title)
        self._btn.setCheckable(True)
        self._btn.setChecked(True)
        self._btn.setArrowType(Qt.DownArrow)
        self._btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._btn.setCursor(Qt.PointingHandCursor)

        self.content = QFrame(self)
        self.content.setObjectName('groupContent')

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 4, 0, 4)
        outer.setSpacing(4)
        outer.addWidget(self._btn)
        outer.addWidget(self.content)

        self._btn.toggled.connect(self._on_toggled)

    def _on_toggled(self, expanded):
        self.content.setVisible(expanded)
        self._btn.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)

    # Interface compatibility with the previous QGroupBox-based version.
    def title(self):
        return self._btn.text()

    def isCheckable(self):
        return True

    def isChecked(self):
        return self._btn.isChecked()

    def setChecked(self, on):
        self._btn.setChecked(bool(on))


# ── Mirrored settings widgets ──────────────────────────────────────────────────
#
# A Qt widget can live in exactly ONE layout, but several settings groups are
# wanted in TWO tabs at once (the functional tab AND the Settings tab). The
# solution is a second, independent widget instance ("mirror") that is kept in
# sync with the primary bidirectionally. Persistence (QSettings) stays with
# the primary widgets only, so all existing save/load code is untouched; the
# mirrors write through to the primaries, which also re-fires any slots
# connected to the primaries (e.g. the effective-wikitext refresh).
#
# Every sync handler compares before setting, so the update chain terminates
# regardless of whether the setter emits its change signal unconditionally.


def link_line_edits(a, b):
    """Keep two QLineEdits' text in sync, in both directions."""
    def _to(dst):
        def _h(text):
            if dst.text() != text:
                dst.setText(text)
        return _h
    a.textChanged.connect(_to(b))
    b.textChanged.connect(_to(a))


def link_checkboxes(a, b):
    def _to(dst):
        def _h(checked):
            if dst.isChecked() != checked:
                dst.setChecked(checked)
        return _h
    a.toggled.connect(_to(b))
    b.toggled.connect(_to(a))


def link_combos(a, b):
    def _to(dst):
        def _h(index):
            if dst.currentIndex() != index:
                dst.setCurrentIndex(index)
        return _h
    a.currentIndexChanged.connect(_to(b))
    b.currentIndexChanged.connect(_to(a))


def mirror_line_edit(primary):
    """A new QLineEdit mirroring the primary (text, placeholder, echo mode)."""
    m = QLineEdit(primary.text())
    m.setPlaceholderText(primary.placeholderText())
    m.setEchoMode(primary.echoMode())
    link_line_edits(primary, m)
    return m


def mirror_checkbox(primary, text=None):
    m = QCheckBox(text if text is not None else primary.text())
    m.setChecked(primary.isChecked())
    m.setToolTip(primary.toolTip())
    link_checkboxes(primary, m)
    return m


def mirror_combo(primary):
    m = QComboBox()
    m.setSizeAdjustPolicy(primary.sizeAdjustPolicy())
    for i in range(primary.count()):
        m.addItem(primary.itemText(i), primary.itemData(i))
    m.setCurrentIndex(primary.currentIndex())
    m.setToolTip(primary.toolTip())
    link_combos(primary, m)
    return m


def apply_form_ratio(form, label_width=FORM_LABEL_WIDTH):
    """Give a QFormLayout narrow labels and wide fields (~30:70).

    QFormLayout has no column-stretch API, so this fixes each label to
    label_width (with word wrap) and lets the field column take the rest.
    Call after all rows have been added.
    """
    form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
    form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    for i in range(form.rowCount()):
        item = form.itemAt(i, QFormLayout.LabelRole)
        if item is None:
            continue
        lbl = item.widget()
        if isinstance(lbl, QLabel):
            lbl.setFixedWidth(label_width)
            lbl.setWordWrap(True)



class HeaderResizeCursorFilter(QObject):
    """Shows a horizontal-split cursor when the mouse hovers a draggable
    column boundary of a QHeaderView. Qt does this natively in most setups,
    but not reliably with app-level stylesheets on macOS; this filter makes
    it deterministic."""

    MARGIN = 5

    def __init__(self, header):
        super().__init__(header)
        self._header = header
        header.setMouseTracking(True)
        header.installEventFilter(self)

    def _on_boundary(self, x):
        h = self._header
        for i in range(h.count()):
            if h.isSectionHidden(i):
                continue
            edge = h.sectionViewportPosition(i) + h.sectionSize(i)
            if abs(x - edge) <= self.MARGIN:
                # The edge is draggable if the section left of it is
                # Interactive (Fixed/Stretch edges cannot be dragged).
                if h.sectionResizeMode(i) == QHeaderView.Interactive:
                    return True
        return False

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseMove:
            if self._on_boundary(event.pos().x()):
                self._header.setCursor(Qt.SplitHCursor)
            else:
                self._header.unsetCursor()
        elif event.type() == QEvent.Leave:
            self._header.unsetCursor()
        return False


class CappedRowHeightDelegate(QStyledItemDelegate):
    """Item delegate that limits how tall a word-wrapped cell may become.

    The table's vertical header uses QHeaderView.ResizeToContents, so a row
    grows until the whole wrapped text of every cell fits. For the Wikitext
    column (the effective description) that can be dozens of lines. This
    delegate reports at most max_lines lines as its size hint; text beyond
    that is clipped by the painter. The complete text remains available in
    the cell's tooltip, which is set in MWEditorMixin._refresh_effective.
    """

    def __init__(self, max_lines=WIKITEXT_MAX_LINES, parent=None):
        super().__init__(parent)
        self.max_lines = max(1, int(max_lines))

    def sizeHint(self, option, index):
        hint = super().sizeHint(option, index)
        # Padding: same top/bottom margin Qt adds around the text (2 x 4 px).
        cap = option.fontMetrics.lineSpacing() * self.max_lines + 8
        if hint.height() > cap:
            hint.setHeight(cap)
        return hint


class UploadProgressDialog(QDialog):
    """Modeless progress window shown while an upload run is going on.

    Cancel does not kill the worker thread; it asks it to stop after the file
    it is currently working on (see UploadWorker.cancel), so no file is left
    half-uploaded on Commons. The dialog has no close button in its title bar:
    it is closed by the upload finishing or by Cancel + finishing.
    """

    cancel_requested = pyqtSignal()

    def __init__(self, total, parent=None, verb=None, title=None):
        """verb/title are optional and default to the upload wording, so all
        existing call sites are unchanged; the culling folder export passes
        verb='Copying'."""
        super().__init__(parent)
        self.setWindowTitle(title or tr('Upload') + f' - {APP_NAME}')
        self.setMinimumWidth(460)
        self.setWindowFlags(
            (self.windowFlags() | Qt.CustomizeWindowHint)
            & ~Qt.WindowCloseButtonHint)
        self.setStyleSheet(current_input_style())
        self.total = total
        self._verb = verb or tr('Uploading')
        self._cancelling = False
        # QDialog.close() raises a close event, and QDialog handles it by
        # calling reject(). Since reject() is overridden below to mean "the
        # user wants to cancel", close() alone would NOT close this window
        # (0.9.11 bug: the progress window stayed on screen after the upload
        # had finished). force_close() is the way out for the caller.
        self._closable = False

        layout = QVBoxLayout(self)
        self.headline = QLabel(tr('{verb} {i} of {total} file(s)…').format(
            verb=self._verb, i=0, total=total))
        f = self.headline.font()
        f.setBold(True)
        self.headline.setFont(f)
        layout.addWidget(self.headline)

        self.detail = QLabel(tr('Preparing…'))
        self.detail.setWordWrap(True)
        self.detail.setStyleSheet('color: gray;')
        layout.addWidget(self.detail)

        self.bar = QProgressBar()
        self.bar.setMinimum(0)
        self.bar.setMaximum(max(1, total))
        self.bar.setValue(0)
        layout.addWidget(self.bar)

        row = QHBoxLayout()
        row.addStretch()
        self.cancel_btn = QPushButton(tr('Cancel'))
        self.cancel_btn.clicked.connect(self._on_cancel)
        row.addWidget(self.cancel_btn)
        layout.addLayout(row)

    def _on_cancel(self):
        if self._cancelling:
            return
        self._cancelling = True
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setText(tr('Cancelling…'))
        self.detail.setText(tr('Cancelling: the file currently being uploaded is '
                            'finished first, then the run stops.'))
        self.cancel_requested.emit()

    def set_current(self, index, filename):
        """index is 0-based; called when a file starts uploading."""
        if self._cancelling:
            return
        self.headline.setText(tr('{verb} {i} of {total} file(s)…').format(
            verb=self._verb, i=index + 1, total=self.total))
        self.detail.setText(filename)

    def set_done(self, count):
        self.bar.setValue(min(count, self.bar.maximum()))

    def force_close(self):
        """Close the window for real. Called by MainWindow.on_finished."""
        self._closable = True
        self.accept()

    def reject(self):
        # Esc must not close the window and leave the upload running blind: it
        # means "cancel" instead. Only force_close() gets through.
        if self._closable:
            super().reject()
        else:
            self._on_cancel()

    def closeEvent(self, event):
        if self._closable:
            event.accept()
        else:
            self._on_cancel()
            event.ignore()


class FileDropTableWidget(QTableWidget):
    """QTableWidget that accepts image files dropped onto it.

    Dropped files with a known image extension (and immediate image files
    inside a dropped folder) are passed to on_files_dropped as a list of
    absolute paths. Files with unsupported extensions, non-existent paths
    and per-URL exceptions are skipped so a single bad entry does not abort
    the whole drop.
    """

    def __init__(self, rows, cols, on_files_dropped=None, logger=None,
                 parent=None):
        super().__init__(rows, cols, parent)
        self._on_files_dropped = on_files_dropped
        self._logger = logger
        # IMPORTANT: only accept drops on the widget itself. This is exactly
        # the configuration that worked in 0.7.2. Do NOT additionally call
        # viewport().setAcceptDrops(True) or setDragDropMode(...): doing so
        # lets QAbstractItemView's built-in item-drop handling intercept the
        # drop and collapse a multi-file drop down to a single item.
        self.setAcceptDrops(True)

    def _collect(self, urls):
        paths = []
        skipped = 0
        for url in urls:
            try:
                path = url.toLocalFile()
                if not path:
                    skipped += 1
                    continue
                if os.path.isdir(path):
                    # Immediate image files inside a dropped folder (not recursive).
                    try:
                        entries = sorted(os.listdir(path))
                    except OSError as e:
                        if self._logger:
                            self._logger.warning(
                                'Could not list dropped folder %r: %s', path, e)
                        continue
                    for name in entries:
                        full = os.path.join(path, name)
                        try:
                            if (os.path.isfile(full)
                                    and os.path.splitext(name)[1].lower()
                                        in IMAGE_EXTS):
                                paths.append(full)
                        except OSError:
                            pass
                elif (os.path.isfile(path)
                        and os.path.splitext(path)[1].lower() in IMAGE_EXTS):
                    paths.append(path)
                else:
                    skipped += 1
            except Exception as e:
                skipped += 1
                if self._logger:
                    self._logger.warning(
                        'Skipping dropped URL %r: %s', url, e)
        if skipped and self._logger:
            self._logger.debug(
                '%d dropped item(s) skipped (unsupported / not a file).', skipped)
        return paths

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            paths = self._collect(event.mimeData().urls())
            if paths and self._on_files_dropped:
                self._on_files_dropped(paths)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)
