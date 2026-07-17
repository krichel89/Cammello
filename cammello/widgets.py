"""Small custom widgets (grip, collapsible group, drop table, delegates, login)."""
import os
from PyQt5.QtWidgets import (QWidget, QLabel, QLineEdit, QPushButton,
                             QToolButton, QFrame, QHeaderView,
                             QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
                             QTextEdit, QDialog, QDialogButtonBox, QCheckBox,
                             QTableWidget, QTableWidgetItem, QStyledItemDelegate,
                             QAbstractItemView, QProgressBar, QComboBox,
                             QApplication, QLayout, QSizePolicy)
from PyQt5.QtCore import (Qt, QEvent, pyqtSignal, QUrl, QSize, QSettings,
                          QObject, QRect, QPoint)
from PyQt5.QtGui import QDesktopServices, QPixmap, QIcon
from .constants import *
from .i18n import tr
from .sdc import *
from . import credentials


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
        self.pass_edit = QLineEdit(
            credentials.load_mediawiki_password(
                self.settings, self.user_edit.text()))
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


# ── OAuth sign-in (mw_oauth) ─────────────────────────────────────────────────
# Storage glue lives here (UI layer): access token/secret go to the OS
# keyring (credentials.mw_oauth_slot); when no keyring backend exists they
# fall back to QSettings 'Login' - same trust level as the old plaintext
# BotPassword, so the app keeps working everywhere.

def stored_oauth_tokens():
    """-> (access_token, access_secret), ('', '') if not authorized."""
    tok = credentials.load(credentials.mw_oauth_slot('token'))
    sec = credentials.load(credentials.mw_oauth_slot('secret'))
    if tok and sec:
        return tok, sec
    s = QSettings(APP_NAME, 'Login')
    return (s.value('oauth_token', '') or '',
            s.value('oauth_secret', '') or '')


def clear_stored_oauth():
    """Remove the authorization locally (keyring + QSettings fallback).

    The server-side grant stays until the user revokes it on
    Special:OAuthManageMyGrants - worth mentioning in the docs."""
    credentials.delete(credentials.mw_oauth_slot('token'))
    credentials.delete(credentials.mw_oauth_slot('secret'))
    s = QSettings(APP_NAME, 'Login')
    for key in ('oauth_token', 'oauth_secret', 'oauth_username'):
        s.remove(key)
    s.sync()


class OAuthLoginDialog(QDialog):
    """Browser-based OAuth sign-in with a copyable authorize link.

    The loopback callback (mw_oauth) listens on 127.0.0.1 and is reached
    from ANY browser on this machine, so the link can be copied into a
    second browser that holds the wiki session instead of the default
    browser (explicit requirement).  The 'show link only' checkbox
    persists as 'oauth_show_only' in QSettings 'Login'.

    On success the tokens are stored (see stored_oauth_tokens above), the
    username lands in QSettings 'Login'/'oauth_username', and the dialog
    accepts; the caller reads .username afterwards.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('Wikimedia sign-in (OAuth)'))
        self.setMinimumWidth(520)
        self.settings = QSettings(APP_NAME, 'Login')
        self.username = ''
        self._worker = None

        v = QVBoxLayout(self)
        intro = QLabel(tr(
            'Cammello asks Wikimedia for permission to upload and edit on '
            'Commons in your name. No password is entered in Cammello. '
            'Open the link in any browser on this computer where you are '
            'signed in to Wikimedia - a second browser works too; Cammello '
            'receives the confirmation automatically.'))
        intro.setWordWrap(True)
        v.addWidget(intro)

        self.show_only_cb = QCheckBox(
            tr('Show the link only - do not open the default browser'))
        self.show_only_cb.setChecked(
            self.settings.value('oauth_show_only', False, type=bool))
        v.addWidget(self.show_only_cb)

        self.start_btn = QPushButton(tr('Start authorization'))
        self.start_btn.clicked.connect(self._start)
        v.addWidget(self.start_btn)

        url_row = QHBoxLayout()
        url_row.addWidget(QLabel(tr('Authorization link:')))
        self.url_edit = QLineEdit()
        self.url_edit.setReadOnly(True)
        url_row.addWidget(self.url_edit, 1)
        self.copy_btn = QPushButton(tr('Copy'))
        self.copy_btn.setEnabled(False)
        self.copy_btn.clicked.connect(self._copy_url)
        url_row.addWidget(self.copy_btn)
        self.open_btn = QPushButton(tr('Open in default browser'))
        self.open_btn.setEnabled(False)
        self.open_btn.clicked.connect(self._open_url)
        url_row.addWidget(self.open_btn)
        v.addLayout(url_row)

        self.status_label = QLabel('')
        self.status_label.setWordWrap(True)
        v.addWidget(self.status_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        buttons.rejected.connect(self.reject)
        v.addWidget(buttons)

    # ── worker plumbing ──────────────────────────────────────────────────

    def _start(self):
        from .mw_oauth import OAuthAuthorizeWorker
        self.settings.setValue('oauth_show_only',
                               self.show_only_cb.isChecked())
        self.settings.sync()
        self.start_btn.setEnabled(False)
        self.show_only_cb.setEnabled(False)
        self._set_status(tr('Waiting for authorization in the browser…'),
                         'orange')
        self._worker = OAuthAuthorizeWorker(
            auto_open=not self.show_only_cb.isChecked(), parent=self)
        self._worker.authorize_url_ready.connect(self._on_url)
        self._worker.succeeded.connect(self._on_success)
        self._worker.failed.connect(self._on_failure)
        self._worker.start()

    def _on_url(self, url):
        self.url_edit.setText(url)
        self.url_edit.setCursorPosition(0)
        self.copy_btn.setEnabled(True)
        self.open_btn.setEnabled(True)

    def _copy_url(self):
        QApplication.clipboard().setText(self.url_edit.text())
        self._set_status(tr('Link copied.'), 'green')

    def _open_url(self):
        QDesktopServices.openUrl(QUrl(self.url_edit.text()))

    def _on_success(self, token, secret, username):
        stored = (credentials.store(credentials.mw_oauth_slot('token'), token)
                  and credentials.store(credentials.mw_oauth_slot('secret'),
                                        secret))
        if stored:
            self.settings.remove('oauth_token')
            self.settings.remove('oauth_secret')
        else:
            # no keyring backend: same trust level as the old plaintext
            # BotPassword - degrade, do not fail
            self.settings.setValue('oauth_token', token)
            self.settings.setValue('oauth_secret', secret)
        self.settings.setValue('oauth_username', username)
        self.settings.sync()
        self.username = username
        self.accept()

    def _on_failure(self, message):
        self._set_status(message, 'red')
        self.start_btn.setEnabled(True)
        self.show_only_cb.setEnabled(True)

    def _set_status(self, text, color):
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f'color: {color}')

    def reject(self):
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(2000)
        super().reject()


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


class FlowLayout(QLayout):
    """A layout that arranges its items left-to-right and wraps to the next
    line when the width runs out (like word wrapping). Used for button rows so
    they never force a wide minimum width that would push neighbours off-screen.

    Adapted from Qt's official FlowLayout example.
    """

    def __init__(self, parent=None, margin=0, spacing=6):
        super().__init__(parent)
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)
        self._spacing = spacing
        self._items = []

    def addItem(self, item):        # noqa: N802 (Qt override)
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):        # noqa: N802
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):        # noqa: N802
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):  # noqa: N802
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):    # noqa: N802
        return True

    def heightForWidth(self, width):    # noqa: N802
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):    # noqa: N802
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):             # noqa: N802
        return self.minimumSize()

    def minimumSize(self):          # noqa: N802
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def _do_layout(self, rect, test_only):
        x, y = rect.x(), rect.y()
        line_height = 0
        for item in self._items:
            w = item.sizeHint().width()
            h = item.sizeHint().height()
            next_x = x + w + self._spacing
            if next_x - self._spacing > rect.right() and line_height > 0:
                x = rect.x()
                y = y + line_height + self._spacing
                next_x = x + w + self._spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
            x = next_x
            line_height = max(line_height, h)
        return y + line_height - rect.y()
