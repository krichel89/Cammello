"""Cammello constants and shared configuration."""
import os
import sys
import re
import threading
from PyQt5.QtCore import QRegExp


__version__ = '0.11.9'

# pyexiv2 is documented as NOT thread-safe ("Not thread safe, because pyexiv2
# uses some global variables in C++", pyexiv2 README). A lock (this used to be
# it) serializes calls but does NOT fix exiv2/XMP's thread-affine global state,
# which still crashed on Windows when pyexiv2 was touched from more than one
# thread. All native imaging work is therefore confined to a single dedicated
# thread instead - see cammello/native_exec.py. This lock is kept only for
# backward compatibility of the import and is no longer used.
PYEXIV2_LOCK = threading.RLock()


def asset_path(name):
    """Absolute path of a bundled asset (cammello/assets/<name>)."""
    return os.path.join(os.path.dirname(__file__), 'assets', name)


APP_NAME = 'Cammello'

# Maintenance category added to every uploaded file.
TRACKING_CATEGORY = f'Uploaded with {APP_NAME}'
TRACKING_CATEGORY_WIKITEXT = f'[[Category:{TRACKING_CATEGORY}]]'

SD_KEYS = [
    'creator', 'copyright', 'license', 'depicts', 'created_during',
    'gallery_suffix', 'depicts_override',
]

PROPERTY_MAP = {
    'creator': 'P170',
    'copyright': 'P6216',
    'license': 'P275',
    'depicts': 'P180',
    'created_during': 'P10408',
}

# Standard width (px) for single-value Wikidata QID fields in the structured
# editor. Keeps QID inputs at a sensible length instead of stretching them
# across the whole panel.
WD_FIELD_WIDTH = 220

# Table preview thumbnails: icon size, column width and the fallback row
# height. 0.9.8 enlarged the icons by 50% (was 96x64 / 104 px / 70 px).
THUMB_W = 144
THUMB_H = 96
THUMB_COL_WIDTH = 156
THUMB_COL_MAX = 2 * THUMB_COL_WIDTH   # column is draggable up to 2x
THUMB_ROW_HEIGHT = 105
# Source pixmaps are rendered at 2x so dragging the column wider does not
# upscale (blur); QIcon scales DOWN cleanly.
THUMB_SRC_W = 2 * THUMB_W
THUMB_SRC_H = 2 * THUMB_H

# Maximum number of text lines shown in the Wikitext column. The vertical
# header resizes rows to their contents, which for a long effective wikitext
# would grow a row without limit; CappedRowHeightDelegate caps it here. The
# full text stays available in the cell tooltip.
WIKITEXT_MAX_LINES = 12

# Accepted image extensions (used by the file dialog and by drag-and-drop).
IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.gif', '.tif', '.tiff', '.svg', '.webp')

# Highlighted style for the main section headings (Upload settings, Base
# description, Selected file): a bold, colored title badge on the group box.
# The About page is deliberately dark in EVERY scheme (it hosts the dark
# logo tile); scoped by objectName so nothing else is affected.
ABOUT_STYLE = (
    'QWidget#aboutPage { background: #16222e; }'
    'QWidget#aboutPage QLabel { color: #e9eff6; background: transparent; }')


def app_style():
    """The ONE application-wide stylesheet: input fields (light/dark
    variant) + the collapsible-group chrome + the About page.

    0.11.0: set on the QApplication instead of the main window, and the
    collapsible groups no longer carry their own setStyleSheet(). Rationale:
    per-widget stylesheets kept producing wrongly rendered child fields on
    macOS (captions/description fields with dark backgrounds inside styled
    group boxes - not reproducible on other platforms). An application-level
    sheet reaches every widget unconditionally; all rules are scoped by
    class/objectName, so the merge is equivalent on platforms that rendered
    correctly before."""
    return current_input_style() + '\n' + GROUP_TITLE_STYLE + '\n' + ABOUT_STYLE


GROUP_TITLE_STYLE = (
    # Collapsible section: arrow tool-button header + framed content.
    'QToolButton#groupTitle {'
    ' font-weight: bold;'
    ' color: white;'
    ' background: #2a6db0;'
    ' border: none;'
    ' border-radius: 4px;'
    ' padding: 3px 10px;'
    ' font-size: 11pt;'
    ' }'
    'QFrame#groupContent {'
    ' border: 1px solid #b9c6d6;'
    ' border-radius: 6px;'
    ' }'
)

# Higher-contrast input fields (applied on the main window and dialogs; the
# rules cascade to all child QLineEdit/QTextEdit/QComboBox widgets, including
# the per-language Information wikitext boxes).
def input_style(dark=False):
    """Stylesheet for input widgets, in a light and a dark variant.

    Up to now the light variant was a constant applied once at build time, so
    switching the color scheme left every input field light - the main reason
    the scheme switch looked broken. _apply_color_scheme() now re-applies the
    matching variant and repolishes the widget tree."""
    if dark:
        bg, fg, border, focus = '#2b2b2b', '#e8e8e8', '#5a6b7d', '#4a9fe0'
    else:
        bg, fg, border, focus = 'white', '#1a1a1a', '#7a8ea6', '#2a6db0'
    return (
        f'QLineEdit, QTextEdit, QPlainTextEdit, QComboBox {{'
        f' border: 1px solid {border};'
        f' border-radius: 3px;'
        f' padding: 2px 4px;'
        f' background: {bg};'
        f' color: {fg};'
        f' }}'
        f'QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,'
        f' QComboBox:focus {{'
        f' border: 1px solid {focus};'
        f' }}'
        # AdjustToContents measures the text only; with a stylesheet the
        # native width logic (arrow/check indicator room) is off.
        f'QComboBox {{ padding-right: 24px; }}'
        f'QComboBox::drop-down {{ width: 20px; }}'
        # The dropdown POPUP is a separate QAbstractItemView and does NOT
        # inherit the rule above (0.9.7 bug class).
        f'QComboBox QAbstractItemView {{'
        f' background: {bg};'
        f' color: {fg};'
        f' selection-background-color: #2a6db0;'
        f' selection-color: white;'
        f' }}'
    )


# Light variant as the module constant (backward compatible); the currently
# active variant is tracked so dialogs built later pick the right one.
INPUT_STYLE = input_style(False)
_CURRENT_INPUT_STYLE = [INPUT_STYLE]
_CURRENT_INPUT_DARK = [False]


def set_current_input_style(dark):
    _CURRENT_INPUT_STYLE[0] = input_style(dark)
    _CURRENT_INPUT_DARK[0] = bool(dark)


def current_input_style():
    return _CURRENT_INPUT_STYLE[0]


def current_style_is_dark():
    """Whether the ACTIVE input style is the dark variant."""
    return _CURRENT_INPUT_DARK[0]


def completer_popup_style():
    """Stylesheet for TOP-LEVEL completer popups (the Wikidata suggestion
    lists). These popups are not children of the main window, so neither the
    window stylesheet nor the repolish pass in _apply_color_scheme reaches
    them - without explicit colors they kept the platform default and were
    unreadable on the dark scheme (light background with light palette
    text). Re-applied every time the popup is about to show, so a scheme
    switch at runtime is picked up."""
    if _CURRENT_INPUT_DARK[0]:
        bg, fg, border = '#2b2b2b', '#e8e8e8', '#5a6b7d'
    else:
        bg, fg, border = 'white', '#1a1a1a', '#7a8ea6'
    return (
        f'QListView {{'
        f' background: {bg};'
        f' color: {fg};'
        f' border: 1px solid {border};'
        f' font-size: 12pt;'
        f' }}'
        f'QListView::item {{ padding: 4px 6px; }}'
        f'QListView::item:selected {{'
        f' background: #2a6db0; color: white; }}'
    )

# Fixed width for QFormLayout labels so labels stay narrow and the input
# fields get the remaining width (approximately a 30:70 split at the typical
# right-panel width).
FORM_LABEL_WIDTH = 165

# Wikidata fields (P170 creator, P6216 copyright, P275 license, P10408
# created-during, P180 depicts) get a light-blue background and a validator
# that only accepts QIDs (Q followed by digits). Single-value fields accept
# one QID; the depicts field accepts a semicolon-separated list of QIDs.
WD_BG = '#e6f2ff'   # unused since 0.11.0 (WD fields are border-only)
_WD_SINGLE_RE = QRegExp(r'^(Q\d+)?$')
_WD_LIST_RE = QRegExp(r'^\s*(Q\d+(\s*[;,]\s*Q\d+)*\s*[;,]?\s*)?$')

# Wikidata entity search (verified: action=wbsearchentities returns a "search"
# array with id/label/description). Public, unauthenticated endpoint.
WD_API_ENDPOINT = 'https://www.wikidata.org/w/api.php'
WD_USER_AGENT = (
    f'{APP_NAME}/{__version__} '
    f'(Python {sys.version_info.major}.{sys.version_info.minor}; PyQt5)'
)
# A single, complete QID.
QID_RE = re.compile(r'^Q\d+$')

# The caption-language dropdown shows FOUR default languages; every other
# ISO code can be typed via the "Other (ISO code)..." entry and is then
# PERSISTED (QSettings key caption_extra_langs) so the dropdown grows with
# the codes the user actually uses. LANGUAGES below stays as the lookup
# table for display names.
CAPTION_BASE_LANGS = ['en', 'de', 'es', 'fr']


def _caption_extra_langs():
    from PyQt5.QtCore import QSettings
    raw = QSettings(APP_NAME, 'Main').value('caption_extra_langs', '') or ''
    return [c for c in raw.split(',') if c.strip()]


def remember_caption_language(code):
    """Persist a freely entered ISO code so future dropdowns include it."""
    from PyQt5.QtCore import QSettings
    s = QSettings(APP_NAME, 'Main')
    extras = _caption_extra_langs()
    if code not in extras and code not in CAPTION_BASE_LANGS:
        extras.append(code)
        s.setValue('caption_extra_langs', ','.join(extras))
        s.sync()


def forget_caption_language(code):
    """Remove a previously remembered ISO code from the persisted list, so it
    stops appearing in the caption-language dropdown. The four base languages
    cannot be removed. No-op if the code was never remembered."""
    from PyQt5.QtCore import QSettings
    s = QSettings(APP_NAME, 'Main')
    extras = _caption_extra_langs()
    if code in extras:
        extras.remove(code)
        s.setValue('caption_extra_langs', ','.join(extras))
        s.sync()


def format_caption_language(code):
    name = dict(LANGUAGES).get(code, '')
    return f'{code} – {name}' if name else code


def caption_language_choices():
    """[(code, display_name)] - the four defaults plus the persisted extras."""
    known = dict(LANGUAGES)
    out = [(c, known.get(c, '')) for c in CAPTION_BASE_LANGS]
    out += [(c, known.get(c, '')) for c in _caption_extra_langs()]
    return out


LANGUAGES = [
    ('en', 'English'), ('de', 'Deutsch'), ('es', 'Español'), ('fr', 'Français'),
    ('it', 'Italiano'), ('ca', 'Català'), ('pt', 'Português'), ('nl', 'Nederlands'),
    ('pl', 'Polski'), ('sv', 'Svenska'), ('ru', 'Русский'), ('uk', 'Українська'),
    ('ja', '日本語'), ('zh', '中文'), ('ar', 'العربية'),
]

# Worked example of a description_all with every option (used as a placeholder).
EXAMPLE_DESCRIPTION_ALL = (
    'caption_en=Harald Krichel at the Berlinale 2026\n'
    'caption_de=Harald Krichel auf der Berlinale 2026\n'
    'creator=Q640\n'
    'copyright=Q73566113\n'
    'license=Q18199165\n'
    'depicts=Q42; Q64\n'
    '# created_during=Q124692383  (e.g. 81st Venice Film Festival)\n'
    'gallery_suffix=Berlinale 2026\n'
    '\n'
    '{{en|1=Harald Krichel at the Berlinale 2026}}\n'
    '[[Category:Harald Krichel]]'
)

# Per-file placeholder: creator / copyright / license / created_during and
# gallery suffix live in the base description and are intentionally omitted.
EXAMPLE_FILE_DESCRIPTION = (
    'caption_en=Harald Krichel at the Berlinale 2026\n'
    'caption_de=Harald Krichel auf der Berlinale 2026\n'
    'depicts=Q640\n'
    '\n'
    '{{en|1=Harald Krichel at the Berlinale 2026}}\n'
    '[[Category:Harald Krichel]]'
)


# Category links ([[Category:Name]]) that can be split out of / rebuilt for the
# structured "Categories" field. The tracking category is added only at upload.
