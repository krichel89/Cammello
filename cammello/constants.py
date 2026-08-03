"""Cammello constants and shared configuration."""
import os
import sys
import re
import threading
from PyQt5.QtCore import QRegExp, QStandardPaths


__version__ = '0.16.1'

# On-wiki manual (0.13). The pages are manually maintained /xx subpages, one
# per UI language - the same five codes as i18n.UI_LANGUAGES, so the current
# language maps straight onto a page. Unknown codes fall back to English.
MANUAL_BASE_URL = 'https://commons.wikimedia.org/wiki/Commons:Cammello/documentation'

# Mirrors i18n.UI_LANGUAGES; kept as a literal here so constants.py stays
# free of imports from i18n (which would be circular).
MANUAL_LANGUAGES = ('en', 'de', 'es', 'fr', 'it')


def manual_url(lang):
    """URL of the manual page for a UI language code.

    Only the five languages that actually have a page are used; anything
    else falls back to English rather than linking to a red link.
    """
    code = lang if lang in MANUAL_LANGUAGES else 'en'
    return f'{MANUAL_BASE_URL}/{code}'


LAST_DIR_KEY = 'last_open_dir'


def remembered_dir(settings):
    """Where a file/folder dialog should start (0.14).

    The folder last opened, if it still exists - otherwise the system's
    Pictures folder, which is where photographs live. Falls back to the home
    directory on systems that report no Pictures location.
    """
    last = settings.value(LAST_DIR_KEY, '', type=str) if settings else ''
    if last and os.path.isdir(last):
        return last
    # The system names a Pictures location even where no such folder was
    # ever created, so it has to be checked like any other path.
    pics = QStandardPaths.writableLocation(QStandardPaths.PicturesLocation)
    if pics and os.path.isdir(pics):
        return pics
    return os.path.expanduser('~')


def remember_dir(settings, path):
    """Store the folder a dialog ended up in. `path` may be a file."""
    if not settings or not path:
        return
    folder = path if os.path.isdir(path) else os.path.dirname(path)
    if folder and os.path.isdir(folder):
        settings.setValue(LAST_DIR_KEY, folder)
        settings.sync()


def gallery_page_name(prefix, suffix):
    """Join a gallery prefix and suffix into ONE clean wiki page title.

    The user types the two halves separately and should never have to think
    about the separator, so this puts in exactly one slash between them and
    tolerates whatever they typed around it:

        'User:Seewolf'  + 'Berlinale 2026'   -> User:Seewolf/Berlinale 2026
        'User:Seewolf/' + '/Berlinale 2026'  -> User:Seewolf/Berlinale 2026
        ' User:Seewolf' + 'Berlinale // 26'  -> User:Seewolf/Berlinale/26

    Every slash-separated segment is trimmed and empty ones are dropped, so
    doubled slashes, stray leading or trailing ones and spaces around a
    slash can never reach Commons as part of the title. Returns '' when
    nothing usable is left.
    """
    segments = []
    for part in (prefix, suffix):
        for segment in (part or '').split('/'):
            segment = segment.strip()
            if segment:
                segments.append(segment)
    return '/'.join(segments)

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
    # 0.12.15: camera position as "lat, lon" in decimal degrees. Unlike the
    # keys above this is not a QID - it becomes {{Location dec}} in the
    # wikitext and a globe-coordinate claim (P1259) in the structured data.
    'coordinates',
    # 0.15.0: position of the DEPICTED object, kept apart from the camera
    # position above. Becomes {{Object location dec}} in the wikitext and a
    # P9149 claim in the structured data.
    'object_coordinates',
]

# Licence presets for the dropdowns (0.12.14). Each row pairs the WIKITEXT
# template with the Wikidata item for the same licence, so the two halves
# cannot drift apart: picking a licence in one field offers to set the other.
#
# The Q-numbers were verified against wikidata.org, not recalled:
#   Q18199165  Creative Commons Attribution-ShareAlike 4.0 International
#   Q20007257  Creative Commons Attribution 4.0 International
#   Q6938433   Creative Commons CC0 License
LICENSE_PRESETS = [
    # (label, wikitext template, P275 item)
    ('CC0 1.0',       '{{Cc-zero}}',       'Q6938433'),
    ('CC BY 4.0',     '{{Cc-by-4.0}}',     'Q20007257'),
    ('CC BY-SA 4.0',  '{{Cc-by-sa-4.0}}',  'Q18199165'),
]

# Copyright status (P6216) presets.
#   Q73566113  work available with a Creative Commons license  (default)
#   Q50423863  copyrighted
#   Q19652     public domain
# Q73566113 and Q19652 were checked on Commons by Harald (20.07.2026) after
# my own lookup could not confirm them; Q50423863 is verified on wikidata.org.
COPYRIGHT_PRESETS = [
    ('work available with a Creative Commons license', 'Q73566113'),
    ('copyrighted', 'Q50423863'),
    ('public domain', 'Q19652'),
]

# Alt text (0.15.2). P11265 "alt text", verified on wikidata.org
# (29.07.2026). Monolingual, so it is stored per language as alt_<code>=
# lines, exactly like the captions next to it. NOT in PROPERTY_MAP: the
# key carries the language, so the worker handles it by prefix.
ALT_TEXT_PROPERTY = 'P11265'

PROPERTY_MAP = {
    'creator': 'P170',
    'copyright': 'P6216',
    'license': 'P275',
    'depicts': 'P180',
    'created_during': 'P10408',
    # P1259 "coordinates of the point of view" = where the CAMERA stood,
    # which is what EXIF GPS records.
    'coordinates': 'P1259',
    # P9149 "coordinates of depicted place" = where the pictured thing
    # stands. Verified on wikidata.org (28.07.2026), not recalled - an
    # earlier note in this file guessed P625, which is the general-purpose
    # coordinate property and NOT the one Commons uses for this.
    'object_coordinates': 'P9149',
}

# Source of file (P7482), added automatically at upload (0.15.0). Only the
# ONE case that is unambiguous: the source field says "own work", so the
# file is an original creation by the uploader. Anything else (a Flickr
# import, a scan, a third-party file) needs a judgement Cammello cannot
# make, and stays for the user or a bot. Both items verified on
# wikidata.org (28.07.2026).
SOURCE_PROPERTY = 'P7482'
SOURCE_OWN_WORK = 'Q66458942'          # original creation by uploader

# The source templates that mean "own work". Matched case-insensitively
# against the whole source field with the braces stripped; anything else
# yields no statement at all.
OWN_WORK_TEMPLATES = ('own', 'own work', 'self-photographed',
                      'own photograph')

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

# Above this many files in one folder, "Open folder" asks first (0.16.0,
# Harald's number). Nothing breaks beyond it - but a thumbnail costs about
# 0.21 MB of memory at THUMB_SRC_W x THUMB_SRC_H RGBA, so a thousand files
# are roughly 210 MB plus the decoding time, and that is worth a question.
FOLDER_WARN_COUNT = 1000

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
    return (current_input_style() + '\n'
            + group_title_style(current_style_is_dark()) + '\n'
            + BUTTON_STYLE + '\n'
            + ABOUT_STYLE + '\n'
            # Disabled menu items (context-sensitive greying, 0.12.6/0.12.7):
            # this rule alone was NOT enough on Windows - the native
            # "windowsvista" style draws menu items itself and ignores the
            # stylesheet colour, which is why the greying worked on macOS
            # but not on Harald's Windows dark mode. The stylesheet stays
            # (it is what makes it work under Fusion), and main_window
            # additionally forces Fusion + explicit Disabled palette roles
            # on Windows - see _apply_color_scheme.
            'QMenu::item:disabled { color: #888; }'
            'QMenu::item:disabled:selected { color: #888;'
            ' background: transparent; }')


def group_title_style(dark=False):
    """Chrome for a collapsible section header, per colour scheme.

    0.12.7 flattened the loud blue badge; 0.12.8 walks part of that back -
    it had become "too small and too low in contrast" (Harald). What
    changed: a much stronger accent colour, and one that is picked for the
    ACTIVE scheme instead of being a single literal. A mid blue that reads
    well on white is nearly invisible on the dark background, which is half
    of where the contrast complaint came from. The size lives in
    widgets.CollapsibleGroupBox (relative to the app font, so it scales).
    """
    if dark:
        # White (Harald, 0.12.8): maximum contrast on the dark background,
        # and it stops the headings competing with the blue accents used for
        # links and selections.
        colour, hover, rule = '#ffffff', '#ffffff', 'rgba(255, 255, 255, 0.45)'
    else:
        # The light-scheme counterpart of "white" is near-black, not white:
        # white on a light background would be invisible. Same idea - a
        # neutral, maximal-contrast heading rather than a coloured one.
        colour, hover, rule = '#1a1a1a', '#000000', 'rgba(26, 26, 26, 0.35)'
    return (
        'QToolButton#groupTitle {'
        ' font-weight: bold;'
        f' color: {colour};'
        ' background: transparent;'
        ' border: none;'
        f' border-bottom: 2px solid {rule};'
        ' border-radius: 0px;'
        ' padding: 3px 2px 4px 2px;'
        ' }'
        'QToolButton#groupTitle:hover {'
        f' color: {hover};'
        ' }'
        'QFrame#groupContent {'
        ' border: 1px solid #b9c6d6;'
        ' border-radius: 6px;'
        ' }'
    )


# Light variant as a module constant (backwards compatible import).
GROUP_TITLE_STYLE = group_title_style(False)

# ── Buttons: ONE look everywhere (0.12.7) ────────────────────────────────────
# Harald: "the buttons are inconsistent, in the MediaWiki module they look
# different from the Culling module - the MediaWiki style is the better one."
# The difference came from the widget CLASS, not from any intent: the
# MediaWiki bar uses QPushButtons (bordered, padded), the Culling bar mixes
# in flat auto-raise QToolButtons. Rather than restyle them one by one, the
# button chrome now lives HERE and covers both classes, so a button looks the
# same wherever it is built.
#
# Two escapes from the common look, both by dynamic property:
#   cammelloPrimary  - the accent action of a page (green Upload button)
#   cammelloSwatch   - the colour-filter squares, which ARE their colour
BUTTON_STYLE = (
    'QPushButton, QToolButton {'
    ' border: 1px solid palette(mid);'
    ' border-radius: 4px;'
    ' padding: 2px 10px;'
    ' background: palette(button);'
    ' color: palette(button-text);'
    ' }'
    'QPushButton:hover, QToolButton:hover {'
    ' border-color: #2a6db0;'
    ' }'
    'QPushButton:pressed, QToolButton:pressed,'
    ' QPushButton:checked, QToolButton:checked {'
    ' background: #2a6db0;'
    ' color: white;'
    ' }'
    'QPushButton:disabled, QToolButton:disabled {'
    ' color: palette(mid);'
    ' }'
    # The accent action (Upload). Was an inline stylesheet on the widget.
    'QPushButton[cammelloPrimary="true"] {'
    ' font-weight: bold;'
    ' background: #22aa77;'
    ' color: white;'
    ' border: 1px solid #1b8b60;'
    ' padding: 2px 12px;'
    ' }'
    'QPushButton[cammelloPrimary="true"]:hover { background: #26c088; }'
    'QPushButton[cammelloPrimary="true"]:pressed { background: #1b8b60; }'
    'QPushButton[cammelloPrimary="true"]:disabled {'
    ' background: palette(button); color: palette(mid);'
    ' border: 1px solid palette(mid);'
    ' }'
    # Fixed-size square buttons (the star filter): the common horizontal
    # padding would push their glyph out of a 22x22 box.
    'QPushButton[cammelloCompact="true"], QToolButton[cammelloCompact="true"] {'
    ' padding: 0; }'
    # Colour swatches keep their own fill (set per widget); only the frame
    # and the checked marker are unified here.
    'QToolButton[cammelloSwatch="true"] {'
    ' border: 1px solid #444; border-radius: 4px; padding: 0;'
    ' }'
    'QToolButton[cammelloSwatch="true"]:checked {'
    ' border: 2px solid #fff;'
    ' }'
)

# ── Global UI font size (0.12.7) ─────────────────────────────────────────────
# Harald: "the font size could be a bit bigger." Done ONCE on the
# QApplication font instead of in stylesheets, so every widget - including
# menus, dialogs and the ones built later - scales together and the relative
# proportions stay intact. Point size, not pixels: that is what respects the
# platform's own scaling.
UI_FONT_POINT_DELTA = 1
_BASE_FONT_POINT = [None]


def apply_ui_font(app, delta=UI_FONT_POINT_DELTA):
    """Enlarge the application font by `delta` points (idempotent).

    The ORIGINAL point size is remembered on the first call, so repeated
    calls (settings changes, a second window) never stack the increase.
    """
    font = app.font()
    if _BASE_FONT_POINT[0] is None:
        _BASE_FONT_POINT[0] = (font.pointSizeF() if font.pointSizeF() > 0
                               else float(font.pointSize()))
    base = _BASE_FONT_POINT[0]
    if base is None or base <= 0:
        return          # pixel-sized font: leave it alone rather than guess
    font.setPointSizeF(base + delta)
    app.setFont(font)

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
        # Slim toolbar controls (see widgets.slim_toolbar): Qt refuses to draw
        # a widget below its minimumSizeHint, so the compact toolbars only
        # work once min-height is explicitly zeroed here. Styling them also
        # switches them to the stylesheet box model, which keeps the native
        # macOS button bezel from painting over the next control.
        f'QPushButton[cammelloSlim="true"], QToolButton[cammelloSlim="true"],'
        f' QComboBox[cammelloSlim="true"], QCheckBox[cammelloSlim="true"],'
        f' QLabel[cammelloSlim="true"] {{'
        f' min-height: 0; padding: 1px 8px; margin: 0;'
        f' }}'
        f'QPushButton[cammelloSlim="true"], QToolButton[cammelloSlim="true"] {{'
        f' border: 1px solid {border}; border-radius: 4px;'
        f' }}'
        f'QPushButton[cammelloSlim="true"]:pressed,'
        f' QToolButton[cammelloSlim="true"]:pressed {{'
        f' background: #2a6db0; color: white;'
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


# Culling background (0.15.0, Harald: "Background im Übersichtsmodus und im
# Grid mittelgrau"). A true middle grey, not the theme colour: a photograph
# is judged against a neutral surround, and black made the single-image view
# read darker than it is. One constant so the image view and the thumbnail
# strip cannot drift apart.
CULL_BG = '#808080'          # kept as the neutral reference value

# 0.15.0 (Harald): "im Darkmode etwas dunkler, im Light Mode etwas heller".
# A surround that is lighter than the desktop in a dark theme, or darker in a
# light one, fights the rest of the window - and a photograph is judged
# against what surrounds it.
CULL_BG_DARK = '#6E6E6E'
CULL_BG_LIGHT = '#9A9A9A'


def cull_bg(dark):
    """The culling surround for the active colour scheme."""
    return CULL_BG_DARK if dark else CULL_BG_LIGHT


# Preview watchdog (0.15.0). A request can be lost without any signal: the
# job is cancelled by a folder change, the cache entry is evicted between
# "loaded" and the handler, or the signal arrives while another image is
# current. Nothing used to ask again, so the view stayed blank. These bound
# the retry so an unreadable file cannot spin.
CULL_RETRY_MS = 1200
CULL_RETRIES = 3
