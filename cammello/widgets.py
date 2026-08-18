"""Small custom widgets (grip, collapsible group, drop table, delegates, login)."""
import json
import logging
import os
import urllib.parse
from PyQt5.QtWidgets import (QWidget, QLabel, QLineEdit, QPushButton,
                             QToolButton, QFrame, QHeaderView,
                             QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
                             QTextEdit, QDialog, QDialogButtonBox, QCheckBox,
                             QTableWidget, QTableWidgetItem, QStyledItemDelegate,
                             QAbstractItemView, QProgressBar, QComboBox,
                             QApplication, QLayout, QSizePolicy, QSpinBox)
from PyQt5.QtCore import (Qt, QEvent, pyqtSignal, QUrl, QSize, QSettings,
                          QObject, QRect, QPoint)
from PyQt5.QtGui import QDesktopServices, QPixmap, QIcon
from .constants import *
from .i18n import tr
from .sdc import *
from . import credentials
from . import channels
from . import filters
# The colour-label swatches must match the culling module's exactly -
# same colours, same order - so one swatch means one thing app-wide.
from .culling import LABEL_COLORS as LABEL_COLORS_UI


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


# ── Bulk rename dialog (F2 with several rows selected) ────────────────────────


class BulkRenameDialog(QDialog):
    """Bulk rename for the target Commons filenames, in the shape macOS
    Photos and Lightroom use (0.16.0, Harald): you PICK A SCHEME instead of
    writing a template with placeholders.

    The schemes are a table (SCHEMES) - a new one is an entry, not a
    rewrite. Each says which inputs it needs, so the custom text and the
    start number enable themselves only where they mean something; the rest
    stay greyed out the way Photos greys "Anfangsnummer".

    How many trailing digits of the original file name are used is NOT a
    setting any more (0.16.0, Harald: "die Stellenzahl automatisch, im
    Bereich 3-6"). It is derived from the selection - see auto_digits.

    The free template survives as the last entry for anyone who wants
    {name}, {c}, {n}, {date} in an order no scheme offers.

    Extensions are NOT part of a name; the caller re-appends each row's own.
    The example line shows them anyway, because that is what the user will
    see in the table afterwards.
    """

    # key -> (label, builder, needs_text, needs_start)
    # builder(ctx) -> str, with ctx carrying everything a scheme may use.
    SCHEMES = [
        ('text_orig', 'Custom name - original file number',
         lambda c: f"{c['text']}-{c['cam'] or c['seq']}", True, False),
        ('text_seq', 'Custom name - sequence',
         lambda c: f"{c['text']}-{c['seq']}", True, True),
        ('text_xofy', 'Custom name (x of y)',
         lambda c: f"{c['text']} ({c['index']} of {c['total']})",
         True, False),
        ('orig', 'Original file name',
         lambda c: c['name'] or c['seq'], False, False),
        ('orig_seq', 'Original file name - sequence',
         lambda c: f"{c['name']}-{c['seq']}" if c['name'] else c['seq'],
         False, True),
        ('date_orig', 'Date - original file name',
         lambda c: '-'.join(p for p in (c['date'], c['name'] or c['seq'])
                            if p), False, False),
        ('date_text_seq', 'Date - custom name - sequence',
         lambda c: '-'.join(p for p in (c['date'], c['text'], c['seq'])
                            if p), True, True),
        ('template', 'Custom template\u2026', None, False, True),
    ]

    # Apple's own range for a camera counter: fewer than 3 digits is not a
    # counter any more, more than 6 no camera writes. Harald: Lumix counts
    # with 6, Canon always with 4.
    DIGITS_MIN = 3
    DIGITS_MAX = 6

    def __init__(self, count, parent=None, sources=None, exts=None,
                 dates=None):
        super().__init__(parent)
        self.setWindowTitle(tr('Rename {count} files').format(count=count))
        self.setMinimumWidth(520)
        self._count = count
        # Per-row source data, same order as the names this returns.
        self._sources = list(sources or [])
        self._exts = list(exts or [])
        self._dates = list(dates or [])
        # Derived once from the selection, not asked for (0.16.0).
        self._digits = self.auto_digits(self._sources)
        self.settings = QSettings(APP_NAME, 'BulkRename')

        form = QFormLayout(self)

        self.scheme_combo = QComboBox()
        for key, label, _b, _t, _s in self.SCHEMES:
            self.scheme_combo.addItem(tr(label), key)
        want = self.settings.value('scheme', 'text_seq')
        idx = self.scheme_combo.findData(want)
        self.scheme_combo.setCurrentIndex(idx if idx >= 0 else 0)
        form.addRow(tr('File naming:'), self.scheme_combo)

        self.text_edit = QLineEdit(self.settings.value('text', '') or '')
        self.text_edit.setPlaceholderText(
            tr('e.g.') + ' Berlinale 2026 Press Conference')
        form.addRow(tr('Custom text:'), self.text_edit)

        self.start_spin = QSpinBox()
        self.start_spin.setRange(0, 999999)
        self.start_spin.setValue(int(self.settings.value('start', 1)))
        form.addRow(tr('Start number:'), self.start_spin)

        self.template_edit = QLineEdit(self.settings.value('template', '')
                                       or '')
        self.template_edit.setPlaceholderText('{date} {text} {c}')
        self.template_edit.setToolTip(tr(
            'Free template. {n} running number, {c} original file number, '
            '{name}\noriginal file name, {text} the custom text above, '
            '{date} the capture date.'))
        self.template_row_label = QLabel(tr('Template:'))
        form.addRow(self.template_row_label, self.template_edit)

        self.preview_lbl = QLabel()
        self.preview_lbl.setWordWrap(True)
        self.preview_lbl.setStyleSheet('color: gray;')
        form.addRow(tr('Example:'), self.preview_lbl)

        self.scheme_combo.currentIndexChanged.connect(self._update_enabled)
        for w in (self.text_edit, self.template_edit):
            w.textChanged.connect(self._update_preview)
        self.start_spin.valueChanged.connect(self._update_preview)
        self._update_enabled()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok |
                                   QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    # ── scheme plumbing ──────────────────────────────────────────────────
    def _scheme(self):
        key = self.scheme_combo.currentData()
        for entry in self.SCHEMES:
            if entry[0] == key:
                return entry
        return self.SCHEMES[0]

    def _update_enabled(self):
        """Grey out what the chosen scheme does not use - the same courtesy
        Photos does with its start number."""
        key, _label, _b, needs_text, needs_start = self._scheme()
        is_template = key == 'template'
        self.text_edit.setEnabled(needs_text or is_template)
        self.start_spin.setEnabled(needs_start)
        self.template_edit.setVisible(is_template)
        self.template_row_label.setVisible(is_template)
        self._update_preview()

    @classmethod
    def auto_digits(cls, sources):
        """How many trailing digits to take from the original file names.

        The LARGEST COMMON RUN: every file has to be able to supply the
        digits, so the length of the shortest trailing digit run in the
        selection decides, clamped to DIGITS_MIN..DIGITS_MAX. Names with no
        trailing digits at all are left out of the vote - they can supply
        nothing and fall back to the running number anyway; letting them
        count would drag a set of six-digit Lumix names down to three.

        Returns 0 ("take the whole number") when nothing in the selection
        ends in a digit.
        """
        runs = [len(cls.camera_number(s)) for s in (sources or [])]
        runs = [r for r in runs if r]
        if not runs:
            return 0
        return max(cls.DIGITS_MIN, min(cls.DIGITS_MAX, min(runs)))

    @staticmethod
    def camera_number(source, digits=0):
        """The trailing digits of a source file name, or '' if it has none.

        IMG_4711 -> 4711; DSC00123 -> 00123. With `digits` > 0 only the
        last that many are kept. Cameras put the counter at the END of the
        name, so this is the piece worth keeping - it is what lets someone
        find the raw file again from the Commons name.
        """
        base = str(source or '')
        tail = ''
        for ch in reversed(base):
            if not ch.isdigit():
                break
            tail = ch + tail
        if digits > 0:
            tail = tail[-digits:]
        return tail

    def _context(self, i):
        start = self.start_spin.value()
        width = len(str(start + self._count - 1))
        name = self._sources[i] if i < len(self._sources) else ''
        date = self._dates[i] if i < len(self._dates) else ''
        return {
            'seq': str(start + i).zfill(width),
            'index': str(i + 1),
            'total': str(self._count),
            'name': name,
            'cam': self.camera_number(name, self._digits),
            'date': (date or '')[:10],
            'text': self.text_edit.text().strip(),
        }

    def names(self):
        """The final base names (without extension), one per selected row."""
        key, _label, builder, _t, _s = self._scheme()
        out = []
        for i in range(self._count):
            ctx = self._context(i)
            if key == 'template':
                tpl = self.template_edit.text().strip() or '{text} {n}'
                name = (tpl.replace('{n}', ctx['seq'])
                        .replace('{c}', ctx['cam'] or ctx['seq'])
                        .replace('{name}', ctx['name'])
                        .replace('{date}', ctx['date'])
                        .replace('{text}', ctx['text']))
            else:
                name = builder(ctx)
            out.append(' '.join(name.split()).strip(' -') or ctx['seq'])
        # Identical target names collide on Commons, so a scheme that did
        # not separate them gets the running number appended - to ALL of
        # them, otherwise the numbering would look arbitrary.
        if len(set(out)) != len(out):
            out = [f'{n} {self._context(i)["seq"]}'
                   for i, n in enumerate(out)]
        return out

    def _update_preview(self):
        names = self.names()
        if not names:
            self.preview_lbl.setText('')
            return
        first = names[0] + (self._exts[0] if self._exts else '')
        if self._count > 1:
            last = names[-1] + (self._exts[-1] if len(self._exts) ==
                                self._count else '')
            self.preview_lbl.setText(f'{first}  \u2026  {last}')
        else:
            self.preview_lbl.setText(first)

    def _on_accept(self):
        key, _label, _b, needs_text, _s = self._scheme()
        if needs_text and not self.text_edit.text().strip():
            self.text_edit.setFocus()
            return
        if key == 'template' and not self.template_edit.text().strip():
            self.template_edit.setFocus()
            return
        self.settings.setValue('scheme', key)
        self.settings.setValue('text', self.text_edit.text().strip())
        self.settings.setValue('template', self.template_edit.text().strip())
        self.settings.setValue('start', self.start_spin.value())
        self.accept()


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
#
# 0.12.7 - what the manual path is actually for
# --------------------------------------------
# Harald's report: the automatic loopback return works; the manual path does
# not. After clicking "Allow" on Meta the browser showed
# ERR_CONNECTION_REFUSED on 127.0.0.1 - i.e. the wiki DID redirect to the
# registered callback (it ignored the "oob" request) and nothing was
# listening there. So the wiki never showed a code to type: the verifier was
# in the browser's ADDRESS BAR the whole time, on the error page.
#
# Hence the manual field now accepts the whole pasted URL and digs the
# verifier out of it. A bare code still works, so nothing is lost for
# consumers where oob does behave.


def verifier_from_input(text):
    """Extract the OAuth verifier from what the user pasted.

    Accepts a full callback URL (`http://127.0.0.1:8127/cammello/?oauth_
    token=...&oauth_verifier=...`), a bare query string, or the plain code.
    Returns '' if nothing usable is in there.
    """
    text = (text or '').strip().strip('"\'')
    if not text:
        return ''
    # A URL or a query string: read the parameter rather than guessing by
    # position - the order of query parameters is not guaranteed.
    if 'oauth_verifier=' in text:
        query = text.split('?', 1)[1] if '?' in text else text
        query = query.split('#', 1)[0]
        params = urllib.parse.parse_qs(query, keep_blank_values=False)
        values = params.get('oauth_verifier') or []
        if values:
            return values[0].strip()
        return ''
    if '://' in text or text.startswith('127.0.0.1') or '/' in text:
        # Looks like a URL but carries no verifier - do not hand the whole
        # address to the token exchange, it would fail with a confusing
        # server error.
        return ''
    return text
# Storage glue lives here (UI layer): access token/secret go to the OS
# keyring (credentials.mw_oauth_slot); when no keyring backend exists they
# fall back to QSettings 'Login' - same trust level as the old plaintext
# BotPassword, so the app keeps working everywhere.

def store_oauth2_tokens(access, refresh):
    """OAuth 2.0: write the CURRENT pair as one keyring entry. -> bool.

    Called after every refresh too - the server rotates the refresh token,
    so persisting the response pair is what keeps the sign-in alive."""
    blob = json.dumps({'access': access, 'refresh': refresh})
    if credentials.store(credentials.mw_oauth2_slot(), blob):
        return True
    s = QSettings(APP_NAME, 'Login')
    s.setValue('oauth2_tokens', blob)          # no-backend fallback
    return False


def stored_oauth2_tokens():
    """-> (access, refresh), ('', '') when not authorized."""
    blob = credentials.load(credentials.mw_oauth2_slot())
    if not blob:
        blob = QSettings(APP_NAME, 'Login').value('oauth2_tokens', '')
    if blob:
        try:
            data = json.loads(blob)
            return data.get('access', '') or '', data.get('refresh', '') or ''
        except ValueError:
            pass
    return '', ''


def clear_stored_oauth2():
    credentials.delete(credentials.mw_oauth2_slot())
    credentials.clear_cache()
    s = QSettings(APP_NAME, 'Login')
    s.remove('oauth2_tokens')
    s.sync()


def store_oauth_tokens(token, secret):
    """Write both halves as ONE keyring entry. -> bool success."""
    blob = json.dumps({'token': token, 'secret': secret})
    return credentials.store(credentials.mw_oauth_slot('tokens'), blob)


def stored_oauth_tokens():
    """-> (access_token, access_secret), ('', '') if not authorized.

    0.14: both halves live in ONE keyring entry, so this costs a single
    prompt instead of two. Installations from before that still have the two
    separate slots; they are read once and migrated.
    """
    blob = credentials.load(credentials.mw_oauth_slot('tokens'))
    if blob:
        try:
            data = json.loads(blob)
            if data.get('token') and data.get('secret'):
                return data['token'], data['secret']
        except ValueError:
            pass                    # corrupt entry: fall through and rebuild
    tok = credentials.load(credentials.mw_oauth_slot('token'))
    sec = credentials.load(credentials.mw_oauth_slot('secret'))
    if tok and sec:
        # Migrate to the combined entry, then drop the old slots so the next
        # start only ever touches one.
        if store_oauth_tokens(tok, sec):
            credentials.delete(credentials.mw_oauth_slot('token'))
            credentials.delete(credentials.mw_oauth_slot('secret'))
        return tok, sec
    s = QSettings(APP_NAME, 'Login')
    return (s.value('oauth_token', '') or '',
            s.value('oauth_secret', '') or '')


def clear_stored_oauth():
    """Remove the authorization locally (keyring + QSettings fallback).

    The server-side grant stays until the user revokes it on
    Special:OAuthManageMyGrants - worth mentioning in the docs."""
    credentials.delete(credentials.mw_oauth_slot('tokens'))
    credentials.delete(credentials.mw_oauth_slot('token'))
    credentials.delete(credentials.mw_oauth_slot('secret'))
    credentials.clear_cache()
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
    starts UNCHECKED every time (0.12.8) - see below.

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
        # 0.12.8: this window is now THE sign-in place, reached from the
        # MediaWiki page and from Settings alike. The bot password is the
        # fallback inside it, so there is no second door with a different
        # room behind it. The caller checks this flag after exec().
        self.use_botpassword = False
        # 0.12.7: the authorization flow used to log NOTHING - Harald's log
        # of a failed sign-in contained not one line about it, so the cause
        # could not be told from the outside. Every station now leaves a
        # trace. No secrets are logged: the request token is not written,
        # only whether one arrived.
        self._log = logging.getLogger('Cammello')

        v = QVBoxLayout(self)
        intro = QLabel(tr(
            'Cammello asks Wikimedia for permission to upload and edit on '
            'Commons in your name. No password is entered in Cammello. '
            'Open the link in any browser on this computer where you are '
            'signed in to Wikimedia - a second browser works too; Cammello '
            'receives the confirmation automatically.'))
        intro.setWordWrap(True)
        v.addWidget(intro)

        # 0.17.0: OAuth 2.0 (PKCE) is the DEFAULT way in for this test
        # series; this box switches back to the proven 1.0a signing path.
        # Deliberately not persisted - an exception switch like the two
        # below (the 0.12.8 lesson).
        self.oauth1_cb = QCheckBox(
            tr('Use the classic authorization (OAuth 1.0a)'))
        self.oauth1_cb.setChecked(False)
        v.addWidget(self.oauth1_cb)

        self.show_only_cb = QCheckBox(
            tr('Show the link only - do not open the default browser'))
        # 0.12.8 (Harald): BOTH boxes start unchecked, every time. They
        # used to remember their last state, so one manual sign-in left the
        # dialog in manual mode for good - the normal one-click path stayed
        # hidden behind a box the user had ticked once, days earlier. These
        # are exception switches: the default has to be the normal way in,
        # and choosing the exception has to be a deliberate act each time.
        self.show_only_cb.setChecked(False)
        v.addWidget(self.show_only_cb)

        # oob mode: no loopback callback - after "Allow" the wiki shows a
        # code the user pastes below. Works with any consumer/status.
        self.oob_cb = QCheckBox(
            tr('Confirm manually (use if the automatic confirmation does '
               'not work - a code or the address from the browser)'))
        self.oob_cb.setChecked(False)
        v.addWidget(self.oob_cb)

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

        # oob only: revealed once the authorize URL is shown, so the user can
        # paste the code the wiki displays after "Allow".
        self.verifier_row = QWidget()
        vr = QHBoxLayout(self.verifier_row)
        vr.setContentsMargins(0, 0, 0, 0)
        vr.addWidget(QLabel(tr('Confirmation code or URL:')))
        self.verifier_edit = QLineEdit()
        self.verifier_edit.setPlaceholderText(
            tr('paste the code - or the whole address from the browser'))
        self.verifier_edit.setToolTip(tr(
            'If the browser shows a code after "Allow", paste it here. If it '
            'instead jumps to a 127.0.0.1 address - even one that fails to '
            'load - copy that entire address from the address bar and paste '
            'it here; Cammello reads the confirmation out of it.'))
        self.verifier_edit.returnPressed.connect(self._finish_paste)
        vr.addWidget(self.verifier_edit, 1)
        self.finish_btn = QPushButton(tr('Finish'))
        self.finish_btn.clicked.connect(self._finish_paste)
        vr.addWidget(self.finish_btn)
        self.verifier_row.setVisible(False)
        v.addWidget(self.verifier_row)

        self.status_label = QLabel('')
        self.status_label.setWordWrap(True)
        v.addWidget(self.status_label)

        # Fallback, deliberately small and at the bottom: OAuth is the way
        # in, the bot password is what remains when a consumer is blocked or
        # unavailable.
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.botpassword_btn = QPushButton(tr('Sign in with a bot password…'))
        self.botpassword_btn.setToolTip(
            tr('Fallback: sign in with a bot password instead of the '
               'browser authorization.'))
        self.botpassword_btn.clicked.connect(self._choose_botpassword)
        buttons.addButton(self.botpassword_btn, QDialogButtonBox.ActionRole)
        buttons.rejected.connect(self.reject)
        v.addWidget(buttons)

        # oob request token/secret, kept between the two phases.
        self._oob_tokens = None
        # 0.12.7: in manual mode a loopback server usually runs as well
        # (see mw_oauth.begin_oob). The watcher completes the sign-in on its
        # own if the browser redirect arrives; the user pasting something is
        # the fallback, not the only way. Whichever finishes first wins.
        self._watcher = None
        self._manual_server = None

    # ── worker plumbing ──────────────────────────────────────────────────

    def _start(self):
        # Deliberately NOT persisted (0.12.8): see the constructor. The two
        # old keys are dropped so a later re-read cannot resurrect a state
        # the user set once and forgot.
        self.settings.remove('oauth_show_only')
        self.settings.remove('oauth_oob')
        self.settings.sync()
        self.start_btn.setEnabled(False)
        self.show_only_cb.setEnabled(False)
        self.oob_cb.setEnabled(False)
        self._log.info('OAuth sign-in started (mode: %s, browser opened '
                       'automatically: %s).',
                       'manual' if self.oob_cb.isChecked() else 'loopback',
                       'no' if self.show_only_cb.isChecked() else 'yes')
        if not self.oauth1_cb.isChecked():
            self._start_oauth2()
            return
        if self.oob_cb.isChecked():
            self._start_oob()
            return
        from .mw_oauth import OAuthAuthorizeWorker
        self._set_status(tr('Waiting for authorization in the browser…'),
                         'orange')
        self._worker = OAuthAuthorizeWorker(
            auto_open=not self.show_only_cb.isChecked(), parent=self)
        self._worker.authorize_url_ready.connect(self._on_url)
        self._worker.succeeded.connect(self._on_success)
        self._worker.failed.connect(self._on_failure)
        self._worker.start()

    # ── OAuth 2.0 (PKCE) flow ────────────────────────────────────────────

    def _start_oauth2(self):
        from . import mw_oauth2
        self._set_status(tr('Waiting for authorization in the browser…'),
                         'orange')
        self._worker = mw_oauth2.OAuth2AuthorizeWorker(parent=self)
        self._worker.ready.connect(self._on_oauth2_url)
        self._worker.succeeded.connect(self._on_oauth2_success)
        self._worker.failed.connect(self._on_failure)
        self._worker.start()

    def _on_oauth2_url(self, url):
        self._on_url(url)
        if not self.show_only_cb.isChecked():
            QDesktopServices.openUrl(QUrl(url))
        # The paste field of the manual flow doubles as the fallback here:
        # if the loopback catch fails, the code sits in the address bar and
        # pasting the whole URL works (code_from_input).
        self.verifier_row.setVisible(True)
        self.verifier_edit.setPlaceholderText(
            tr('If nothing happens: paste the address bar line here'))

    def _finish_oauth2_paste(self):
        worker = self._worker
        if worker is not None and hasattr(worker, 'finish_with_code'):
            if not worker.finish_with_code(self.verifier_edit.text()):
                self._set_status(tr('No authorization code found in the '
                                    'pasted text.'), 'red')

    def _on_oauth2_success(self, access, refresh, username):
        self._log.info('OAuth 2.0: authorization completed for user '
                       '"%s".', username)
        store_oauth2_tokens(access, refresh)
        self.settings.setValue('oauth_username', username)
        self.settings.sync()
        self.username = username
        self.accept()

    # ── oob (manual code) flow ───────────────────────────────────────────

    def _start_oob(self):
        from .mw_oauth import OAuthOOBBeginWorker
        self._set_status(tr('Requesting an authorization link…'), 'orange')
        self._worker = OAuthOOBBeginWorker(parent=self)
        self._worker.ready.connect(self._on_oob_ready)
        self._worker.failed.connect(self._on_failure)
        self._worker.start()

    def _on_oob_ready(self, request_token, request_secret, url,
                      loopback_active=False):
        self._log.info('OAuth manual: request token received (loopback '
                       'server running: %s).',
                       'yes' if loopback_active else 'no')
        self._oob_tokens = (request_token, request_secret)
        self._on_url(url)
        if not self.show_only_cb.isChecked():
            QDesktopServices.openUrl(QUrl(url))
        self.verifier_row.setVisible(True)
        self.verifier_edit.setFocus()
        if loopback_active:
            from .mw_oauth import OAuthCallbackWatchWorker
            self._manual_server = getattr(self._worker, 'server', None)
            if self._manual_server is not None:
                self._watcher = OAuthCallbackWatchWorker(
                    self._manual_server, request_token, request_secret,
                    parent=self)
                self._watcher.succeeded.connect(self._on_success)
                self._watcher.expired.connect(self._on_watch_expired)
                self._watcher.start()
            self._set_status(tr('Open the link and click "Allow". If the '
                                'browser returns on its own you are done. '
                                'Otherwise paste the code shown - or the '
                                'whole 127.0.0.1 address from the browser, '
                                'even if the page failed to load.'),
                             'orange')
        else:
            self._set_status(tr('Open the link and click "Allow". Then paste '
                                'either the code shown, or - if the browser '
                                'jumps to a 127.0.0.1 address, even a failing '
                                'one - that whole address, and press Finish.'),
                             'orange')

    def _on_watch_expired(self, message):
        # NOT an error path: the manual field is still there, and the user
        # may be halfway through pasting. Log it and stay open.
        self._log.info('OAuth manual: automatic return did not happen (%s); '
                       'the manual entry stays available.', message)

    def _finish_paste(self):
        """Route the pasted text to whichever flow is running."""
        if not self.oauth1_cb.isChecked():
            self._finish_oauth2_paste()
        else:
            self._finish_oob()

    def _finish_oob(self):
        if self._oob_tokens is None:
            return
        from .mw_oauth import OAuthOOBFinishWorker
        raw = self.verifier_edit.text().strip()
        code = verifier_from_input(raw)
        if not code:
            self._log.warning(
                'OAuth manual: no usable verifier in the pasted text '
                '(%d characters, looks like a URL: %s).',
                len(raw), 'yes' if '://' in raw else 'no')
            self._set_status(
                tr('No confirmation found in what was pasted. Paste either '
                   'the code or the complete 127.0.0.1 address from the '
                   'browser.'), 'red')
            return
        if code != raw:
            self._log.info('OAuth manual: verifier extracted from a pasted '
                           'URL.')
        self.finish_btn.setEnabled(False)
        self.verifier_edit.setEnabled(False)
        self._set_status(tr('Completing sign-in…'), 'orange')
        rt, rs = self._oob_tokens
        self._worker = OAuthOOBFinishWorker(rt, rs, code, parent=self)
        self._worker.succeeded.connect(self._on_success)
        self._worker.failed.connect(self._on_oob_finish_failed)
        self._worker.start()

    def _on_oob_finish_failed(self, message):
        self._log.warning('OAuth manual: exchanging the confirmation '
                          'failed: %s', message)
        # keep the verifier field so the user can correct the code
        self.finish_btn.setEnabled(True)
        self.verifier_edit.setEnabled(True)
        self._set_status(message, 'red')

    def _on_url(self, url):
        self._log.info('OAuth: authorization link ready (%s).',
                       url.split('?', 1)[0] if url else '-')
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
        self._log.info('OAuth: authorization completed for user "%s".',
                       username)
        self._stop_watcher()
        stored = store_oauth_tokens(token, secret)
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
        self._log.warning('OAuth: authorization failed: %s', message)
        self._set_status(message, 'red')
        self.start_btn.setEnabled(True)
        self.show_only_cb.setEnabled(True)
        self.oob_cb.setEnabled(True)

    def _set_status(self, text, color):
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f'color: {color}')

    def _choose_botpassword(self):
        """Leave for the bot-password path; the caller reads the flag."""
        self._log.info('OAuth: user chose the bot-password fallback.')
        self.use_botpassword = True
        self.reject()

    def _stop_watcher(self):
        """Stop the loopback watcher and release the port (idempotent)."""
        if self._watcher is not None:
            self._watcher.cancel()
            self._watcher.wait(2000)
            self._watcher = None
        if self._manual_server is not None:
            self._manual_server.close()
            self._manual_server = None

    def reject(self):
        if self._worker is not None and self._worker.isRunning():
            self._log.info('OAuth: sign-in cancelled by the user.')
            cancel = getattr(self._worker, 'cancel', None)
            if callable(cancel):
                cancel()
            self._worker.wait(2000)
        # The port must not stay bound after a cancelled sign-in, or the
        # next attempt cannot bind it.
        self._stop_watcher()
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



class NoWheelComboBox(QComboBox):
    """A combo box that IGNORES the mouse wheel (0.12.8).

    Inside a scrollable form, Qt's default is a trap: the wheel over a combo
    changes its VALUE instead of scrolling the page. Harald hit the worst
    version of it - the caption-language combos carry two ACTION entries
    ("Other (ISO code)…", "Remove saved language…"), so scrolling the
    MediaWiki page with the touchpad kept landing on one and popping up the
    ISO-code dialog.

    Ignoring the event lets it fall through to the scroll area, which is
    what the gesture meant. The value can still be changed by clicking,
    by keyboard, and by the wheel once the popup is OPEN - only the
    accidental path is closed.
    """

    def wheelEvent(self, event):
        event.ignore()


class PresetComboBox(NoWheelComboBox):
    """An editable combo that behaves like the QLineEdit it replaces.

    Built for the license and copyright-status fields (0.12.14): the values
    are a short, well-known set, but they are Q-numbers and template names
    that nobody recites from memory. The DROPDOWN shows readable entries
    ("CC BY-SA 4.0 (Q18199165)"); picking one puts the bare VALUE in the
    field, so everything downstream - settings, description export, upload -
    keeps seeing exactly the same string as before. Typing something else
    stays possible: unusual licenses must not become unreachable.

    The QLineEdit surface below (text/setText/textChanged/placeholder) is
    what makes this a drop-in replacement; several modules and the settings
    mirror talk to these fields as if they were line edits.
    """

    textChanged = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        self.activated.connect(self._apply_choice)
        self.lineEdit().textChanged.connect(self.textChanged)

    def add_choice(self, label, value):
        """Add one dropdown entry: readable label, bare value behind it."""
        self.addItem(f'{label} ({value})', value)

    def _apply_choice(self, index):
        value = self.itemData(index)
        if value is not None:
            self.setEditText(value)

    # ── QLineEdit-compatible surface ────────────────────────────────────
    def text(self):
        return self.currentText()

    def setText(self, text):
        self.setEditText(text)

    def placeholderText(self):
        return self.lineEdit().placeholderText()

    def setPlaceholderText(self, text):
        self.lineEdit().setPlaceholderText(text)

    def echoMode(self):
        return self.lineEdit().echoMode()

    def setEchoMode(self, mode):
        self.lineEdit().setEchoMode(mode)


def mirror_preset_combo(primary):
    """A second PresetComboBox with the same entries, kept in sync.

    mirror_line_edit would hand back a plain QLineEdit - the Settings page
    would then show a text box where the module shows a dropdown.
    """
    m = PresetComboBox()
    for i in range(primary.count()):
        m.addItem(primary.itemText(i), primary.itemData(i))
    m.setEditText(primary.text())
    m.setPlaceholderText(primary.placeholderText())
    link_line_edits(primary, m)
    return m


class CollapsibleGroupBox(QWidget):
    """A section with a simple collapse arrow.

    The header is a checkable QToolButton showing an arrow (down = expanded,
    right = collapsed) plus the section title; clicking it toggles the framed
    content widget. Keeps the isCheckable/setChecked/isChecked/title interface
    of the previous QGroupBox-based version.

    0.12.8: the arrow is a TEXT glyph, not QToolButton.setArrowType. The
    style-drawn arrow is tiny and grey - Harald asked for something more
    noticeable - and its size is decided by the platform style, so there is
    no reliable way to enlarge it. A glyph in the button text scales with
    the heading font and takes the heading's accent colour, which makes it
    visible in both colour schemes for free. title() still returns the
    plain title; the glyph never enters it.
    """

    # Heading size relative to the UI font. History, because it was tuned by
    # eye: 1.25 was too loud, 1.0 too quiet - Harald asked for the step in
    # between, so 1.125. Keep it a factor, never a pt value: the UI font is
    # adjustable (0.12.7) and the headings must follow it.
    TITLE_FONT_FACTOR = 1.125
    ARROW_EXPANDED = '▼'
    ARROW_COLLAPSED = '▶'

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self._btn = QToolButton(self)
        self._btn.setObjectName('groupTitle')
        self._title = title
        self._btn.setCheckable(True)
        self._btn.setChecked(True)
        self._btn.setArrowType(Qt.NoArrow)
        self._btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self._apply_title(True)
        self._btn.setCursor(Qt.PointingHandCursor)
        # Size: a touch above the body text (TITLE_FONT_FACTOR), together
        # with the weight and the accent colour from
        # constants.group_title_style. Rounded to a whole point so the
        # heading does not land on a fractional size that the platform
        # renders at an unpredictable weight.
        f = self._btn.font()
        base = f.pointSizeF() if f.pointSizeF() > 0 else f.pointSize()
        if base > 0 and self.TITLE_FONT_FACTOR != 1.0:
            f.setPointSizeF(round(base * self.TITLE_FONT_FACTOR))
        f.setBold(True)
        self._btn.setFont(f)

        self.content = QFrame(self)
        self.content.setObjectName('groupContent')

        # 0.15.0: the red missing-fields dot is its own label NEXT TO the
        # title button - QToolButton text is single-colour, so a coloured
        # dot inside the title itself is impossible without an icon file.
        self._dot = QLabel(self.ATTENTION_DOT, self)
        self._dot.setStyleSheet('color:#d03030;')
        self._dot.setToolTip(tr('Strongly recommended fields in this '
                                'section are still empty.'))
        self._dot.hide()

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(4)
        head.addWidget(self._btn)
        head.addWidget(self._dot)
        head.addStretch()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 4, 0, 4)
        outer.setSpacing(4)
        outer.addLayout(head)
        outer.addWidget(self.content)

        self._btn.toggled.connect(self._on_toggled)

    # 0.15.0 (Harald): a red dot on the heading when a strongly recommended
    # field inside is still empty - so the group can START COLLAPSED
    # without hiding that something is missing. A text glyph for the same
    # reason the arrow is one (0.12.8): it scales with the heading font.
    ATTENTION_DOT = '●'

    def _apply_title(self, expanded):
        arrow = self.ARROW_EXPANDED if expanded else self.ARROW_COLLAPSED
        self._btn.setText(f'{arrow}  {self._title}')

    def set_attention(self, on):
        """Show or clear the red missing-fields dot beside the heading."""
        self._dot.setVisible(bool(on))

    def attention(self):
        # isHidden, not isVisible: inside a non-current module page
        # isVisible() answers False for everything (known Qt trap).
        return not self._dot.isHidden()

    def _on_toggled(self, expanded):
        self.content.setVisible(expanded)
        self._apply_title(expanded)

    # Interface compatibility with the previous QGroupBox-based version.
    def title(self):
        """The plain title, WITHOUT the arrow glyph."""
        return self._title

    def setTitle(self, title):
        self._title = title
        self._apply_title(self._btn.isChecked())

    def setToolTip(self, text):
        """Explain the SECTION - set on the header button as well.

        Qt propagates an unhandled tooltip event to the parent, so setting
        it on the group alone would usually work; but the header is the
        thing a reader points at, and an explicit tooltip there also
        survives if the button ever gets one of its own.
        """
        super().setToolTip(text)
        self._btn.setToolTip(text)

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
        elif lbl is not None:
            # A composite label (e.g. caption + "Suggest" button, see
            # _label_with_button): pin it to the same column width so the
            # 30:70 ratio holds for those rows too.
            lbl.setFixedWidth(label_width)



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
                 on_rename=None, parent=None):
        super().__init__(rows, cols, parent)
        self._on_files_dropped = on_files_dropped
        self._logger = logger
        # F2 = rename (Lightroom habit): one selected row edits its target
        # filename inline, several open the bulk-rename dialog. The callback
        # lives in MainWindow; None keeps Qt's default F2 (edit current cell).
        self._on_rename = on_rename
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

    def keyPressEvent(self, event):
        # F2 = rename, before Qt's default (edit whatever cell is current):
        # the callback decides between inline single rename and bulk dialog.
        if (self._on_rename is not None and event.key() == Qt.Key_F2
                and not event.modifiers()):
            event.accept()
            self._on_rename()
            return
        super().keyPressEvent(event)

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

    def __init__(self, parent=None, margin=0, spacing=8):
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
            # Use the LARGER of sizeHint and minimumSize: a squeezed row used
            # to hand a button less width than it paints, which made the
            # neighbours visually overlap (0.12.5).
            size = item.sizeHint().expandedTo(item.minimumSize())
            w, h = size.width(), size.height()
            next_x = x + w + self._spacing
            if next_x - self._spacing > rect.right() and line_height > 0:
                x = rect.x()
                y = y + line_height + self._spacing
                next_x = x + w + self._spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), size))
            x = next_x
            line_height = max(line_height, h)
        return y + line_height - rect.y()


# ── Toolbar helpers (0.12.4) ─────────────────────────────────────────────────

TOOLBAR_HEIGHT = 24        # compact control height for the tab toolbars


TOOLBAR_SEPARATOR_NAME = 'cammelloToolbarSeparator'


def toolbar_separator():
    """Thin vertical rule that sets a toolbar cluster apart from its
    neighbours (used around the culling filter block).

    Tagged by objectName rather than by type: QLabel inherits QFrame, so a
    type check would also catch every caption in the row."""
    line = QFrame()
    line.setObjectName(TOOLBAR_SEPARATOR_NAME)
    line.setFrameShape(QFrame.VLine)
    line.setFrameShadow(QFrame.Sunken)
    line.setFixedHeight(TOOLBAR_HEIGHT)
    return line


def slim_toolbar(layout, height=TOOLBAR_HEIGHT):
    """Make a toolbar row as short as it can be.

    setMaximumHeight alone does NOT work: a Qt widget never shrinks below its
    minimumSizeHint (29 px for a plain button, more with the native macOS
    bezel), so the cap was silently ignored and the row stayed tall. The
    controls are therefore tagged with the dynamic property `cammelloSlim`,
    which the application stylesheet answers with `min-height: 0` and tight
    padding - only then does a fixed height actually take effect, and the
    stylesheet box model also stops the native bezel from painting over the
    neighbouring control.

    Fixed-size widgets (the colour swatches) and separators are left alone.
    """
    layout.setContentsMargins(0, 0, 0, 2)
    layout.setSpacing(6)
    for i in range(layout.count()):
        w = layout.itemAt(i).widget()
        if w is None or w.objectName() == TOOLBAR_SEPARATOR_NAME:
            continue                      # already fixed to the row height
        if w.minimumWidth() == w.maximumWidth() and w.minimumWidth() > 0:
            continue                      # fixed-size swatch: leave as is
        w.setProperty('cammelloSlim', True)
        w.setFixedHeight(height)


class ModuleStrip(QWidget):
    """Lightroom-style module picker (0.12.6): a flat, right-aligned row of
    text buttons above the pages - Culling · MediaWiki · IPTC · FTP/Flickr.

    Deliberately NOT the Qt tab bar: that widget is visually heavy and cannot
    look like Lightroom's module strip on any platform. This is a plain row
    of flat checkable buttons, kept in sync with the (bar-hidden) QTabWidget
    in both directions. Only the pages IN the tab widget appear here - the
    dialog pages (Settings/Log/About) never show up.
    """

    def __init__(self, tabs, parent=None):
        super().__init__(parent)
        self._tabs = tabs
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(8, 4, 12, 2)
        self._lay.setSpacing(2)
        self._lay.addStretch(1)               # pushes the modules RIGHT
        self._buttons = []
        tabs.currentChanged.connect(self._sync)
        # The strip is created BEFORE the pages are added (it must sit above
        # the tab widget in the layout), so the buttons are built later via
        # rebuild(), once every addTab has run.

    def rebuild(self):
        """(Re)build the module buttons from the tab widget's CURRENT pages.
        Called once after the pages exist; safe to call again."""
        while self._lay.count() > 1:          # keep the leading stretch
            item = self._lay.takeAt(1)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._buttons = []
        tabs = self._tabs
        for i in range(tabs.count()):
            if i:
                sep = QLabel('·')
                sep.setStyleSheet('color: #888; padding: 0 4px;')
                self._lay.addWidget(sep)
            b = QPushButton(tabs.tabText(i))
            b.setFlat(True)
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)      # keyboard stays with the page
            # 0.12.7: EVERY title is bold, permanently; active vs inactive is
            # a COLOUR difference only.
            #
            # 0.12.6 made only the active title bold and widened the button by
            # a measured bold text width - Harald still saw clipped titles.
            # Measuring is the wrong tool here: the drawn width depends on
            # padding, platform painter and font hinting, so any computed
            # margin is a guess that can be too small. With a constant weight
            # the width simply never changes when switching modules, and the
            # bug cannot come back.
            #
            # The colours come from the PALETTE, not from literals: hard-coded
            # white would be invisible in light mode. Active = the normal text
            # colour (white in dark mode, near-black in light mode), inactive =
            # the disabled text colour, which is exactly the platform's own
            # "muted" grey.
            bold = b.font()
            bold.setBold(True)
            b.setFont(bold)
            b.setProperty('cammelloModule', True)
            # palette(mid) is the platform's muted grey; palette(window-text)
            # the normal foreground. Both are real stylesheet colour roles -
            # the Disabled palette GROUP is not addressable from a style
            # sheet, so it must not be used here.
            b.setStyleSheet(
                'QPushButton { border: none; padding: 2px 10px;'
                ' background: transparent; min-width: 0;'
                ' color: palette(mid); }'
                'QPushButton:checked { color: palette(window-text);'
                ' background: transparent; border: none; }'
                'QPushButton:hover { color: palette(window-text);'
                ' background: transparent; border: none; }'
                'QPushButton:pressed { background: transparent;'
                ' border: none; }')
            b.clicked.connect(lambda _c, idx=i: tabs.setCurrentIndex(idx))
            self._lay.addWidget(b)
            self._buttons.append(b)
        self._sync(tabs.currentIndex())

    def _sync(self, index):
        for i, b in enumerate(self._buttons):
            b.setChecked(i == index)


class FilterBar(QWidget):
    """Stars, colour swatches and channel dots for the upload list (0.16.1).

    Harald: "im Kopf der Bilderspalte noch Filtermoeglichkeiten nach
    Sternen, Farben und Kanaelen ... Sterne als und, farben als oder, wie
    Lightroom."

    Deliberately built to LOOK AND FEEL like the culling toolbar's filter
    cluster, down to the ★/☆ toggle and the swatch styling: the same gesture
    should mean the same thing in both modules. What differs is the effect -
    the culling bar hides what does not match, this one drives the
    SELECTION and leaves everything visible but greyed (Harald: "Die Filter
    sollen die Auswahl steuern, nicht gewaehlte Bilder werden leicht
    gegraut").

    Emits `changed` with a filters.FileFilter whenever the user touches
    anything. The widget owns no file list - the module that embeds it
    decides what to do with the filter.
    """

    changed = pyqtSignal(object)

    def __init__(self, parent=None, with_channels=True):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)
        self._min_rating = 0

        row.addWidget(QLabel(tr('Filter:')))

        # ── Stars: a threshold, exactly like the culling bar ─────────────
        self.star_btns = []
        for n in range(1, filters.MAX_STARS + 1):
            b = QToolButton()
            b.setText('☆')
            b.setCheckable(True)
            b.setAutoRaise(True)
            b.setFixedSize(22, 22)
            b.setProperty('cammelloCompact', True)
            b.setToolTip(tr('Select images with {n} stars or more '
                            '(click again to switch it off).').format(n=n))
            b.clicked.connect(lambda _c, n=n: self._on_star(n))
            self.star_btns.append(b)
            row.addWidget(b)

        # ── Colours: OR ──────────────────────────────────────────────────
        row.addSpacing(8)
        self.color_btns = []
        swatches = list(LABEL_COLORS_UI) + ['#888']       # last = no label
        for i, col in enumerate(swatches):
            b = QToolButton()
            b.setCheckable(True)
            b.setFixedSize(20, 20)
            b.setProperty('cammelloSwatch', True)
            b.setProperty('cammelloCompact', True)
            # Repeating the :checked variant is required - see the same
            # comment in mw_culling: the generic "checked = blue" rule would
            # otherwise paint the swatch blue.
            b.setStyleSheet(f'QToolButton, QToolButton:checked,'
                            f' QToolButton:hover, QToolButton:pressed'
                            f' {{background:{col};}}')
            b.setToolTip(tr('no label') if i == len(swatches) - 1
                         else tr('colour {n}').format(n=i + 1))
            b.clicked.connect(self._emit)
            self.color_btns.append(b)
            row.addWidget(b)

        # ── Channels: OR ─────────────────────────────────────────────────
        self.channel_btns = []
        if with_channels:
            row.addSpacing(8)
            for key, col, tip in (
                    (channels.MARK_COMMONS, channels.COLOR_COMMONS,
                     tr('Marked for Commons (CC)')),
                    (channels.MARK_COMMERCIAL, channels.COLOR_COMMERCIAL,
                     tr('Marked for commercial use')),
                    (filters.NO_CHANNEL, '#888', tr('No channel mark'))):
                b = QToolButton()
                b.setCheckable(True)
                b.setFixedSize(20, 20)
                b.setProperty('cammelloSwatch', True)
                b.setProperty('cammelloCompact', True)
                b.setStyleSheet(f'QToolButton, QToolButton:checked,'
                                f' QToolButton:hover, QToolButton:pressed'
                                f' {{background:{col};'
                                f' border-radius:10px;}}')
                b.setToolTip(tip)
                b.setProperty('cammelloChannelKey', key)
                b.clicked.connect(self._emit)
                self.channel_btns.append(b)
                row.addWidget(b)

        row.addSpacing(8)
        self.clear_btn = QToolButton()
        self.clear_btn.setText('\u2715')
        self.clear_btn.setAutoRaise(True)
        self.clear_btn.setFixedSize(22, 22)
        self.clear_btn.setProperty('cammelloCompact', True)
        self.clear_btn.setToolTip(tr('Switch the filter off'))
        self.clear_btn.clicked.connect(self.clear)
        row.addWidget(self.clear_btn)
        row.addStretch(1)

        self._update_stars()

    # ── Reading the state ────────────────────────────────────────────────
    def current_filter(self):
        """The FileFilter the buttons currently describe."""
        colors = set()
        for i, b in enumerate(self.color_btns):
            if not b.isChecked():
                continue
            colors.add(filters.NO_COLOR if i == len(self.color_btns) - 1
                       else i)
        chans = {b.property('cammelloChannelKey')
                 for b in self.channel_btns if b.isChecked()}
        return filters.FileFilter(self._min_rating, colors, chans)

    # ── Reacting ─────────────────────────────────────────────────────────
    def _on_star(self, stars):
        """Clicking the star that is already the threshold switches it off -
        the same gesture as the culling bar."""
        self._min_rating = 0 if stars == self._min_rating else stars
        self._update_stars()
        self._emit()

    def _update_stars(self):
        for i, b in enumerate(self.star_btns, start=1):
            active = i <= self._min_rating
            b.setChecked(active)
            b.setText('★' if active else '☆')

    def clear(self):
        self._min_rating = 0
        self._update_stars()
        for b in self.color_btns + self.channel_btns:
            b.setChecked(False)
        self._emit()

    def _emit(self):
        self.changed.emit(self.current_filter())
