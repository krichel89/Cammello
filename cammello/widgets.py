"""Small custom widgets (grip, collapsible group, drop table, delegates, login)."""
import os
from PyQt5.QtWidgets import (QWidget, QLabel, QLineEdit, QPushButton,
                             QToolButton, QFrame,
                             QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
                             QTextEdit, QDialog, QDialogButtonBox, QCheckBox,
                             QTableWidget, QTableWidgetItem, QStyledItemDelegate,
                             QAbstractItemView)
from PyQt5.QtCore import Qt, QEvent, pyqtSignal, QUrl, QSize
from PyQt5.QtGui import QDesktopServices, QPixmap, QIcon
from .constants import *
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
        self.setWindowTitle('Login – Wikimedia Commons')
        self.setMinimumWidth(420)
        self.settings = QSettings(APP_NAME, 'Login')

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.url_edit = QLineEdit(self.settings.value(
            'api_url', 'https://commons.wikimedia.org/w/api.php'))
        self.url_edit.setVisible(False)  # hidden; always Commons by default
        self.user_edit = QLineEdit(self.settings.value('username', ''))
        self.user_edit.setPlaceholderText('e.g. Seewolf@Cammello')
        self.pass_edit = QLineEdit()
        self.pass_edit.setEchoMode(QLineEdit.Password)

        form.addRow('Username:', self.user_edit)
        form.addRow('Password:', self.pass_edit)
        layout.addLayout(form)

        hint = QLabel(
            'Use a <b>BotPassword</b>: create one at '
            '<a href="https://commons.wikimedia.org/wiki/Special:BotPasswords">'
            'Special:BotPasswords</a> and log in with the name shown there '
            '(e.g. <i>YourName@Cammello</i>).<br><br>'
            'Required grants:'
            '<ul style="margin-top:2px;">'
            '<li>Edit existing pages</li>'
            '<li>Create, edit, and move pages</li>'
            '<li>Upload new files</li>'
            '<li>Upload, replace, and move files</li>'
            '</ul>')
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
        self.setToolTip('Drag to resize the field')
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
