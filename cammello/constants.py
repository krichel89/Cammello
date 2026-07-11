"""Cammello constants and shared configuration."""
import sys
import re
from PyQt5.QtCore import QRegExp


__version__ = '0.9.11'
APP_NAME = 'Cammello'

# Maintenance category added to every uploaded file.
TRACKING_CATEGORY = f'Uploaded with {APP_NAME}'
TRACKING_CATEGORY_WIKITEXT = f'[[Category:{TRACKING_CATEGORY}]]'

SD_KEYS = [
    'creator', 'copyright', 'license', 'depicts', 'created_during',
    'gallery_suffix',
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
THUMB_ROW_HEIGHT = 105

# Maximum number of text lines shown in the Wikitext column. The vertical
# header resizes rows to their contents, which for a long effective wikitext
# would grow a row without limit; CappedRowHeightDelegate caps it here. The
# full text stays available in the cell tooltip.
WIKITEXT_MAX_LINES = 12

# Accepted image extensions (used by the file dialog and by drag-and-drop).
IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.gif', '.tif', '.tiff', '.svg', '.webp')

# Highlighted style for the main section headings (Upload settings, Base
# description, Selected file): a bold, colored title badge on the group box.
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
INPUT_STYLE = (
    'QLineEdit, QTextEdit, QPlainTextEdit, QComboBox {'
    ' border: 1px solid #7a8ea6;'
    ' border-radius: 3px;'
    ' padding: 2px 4px;'
    ' background: white;'
    ' color: #1a1a1a;'          # explicit dark text: on macOS dark mode, Qt5
    #                             follows the system (light) text color while
    #                             this stylesheet forces a white background,
    #                             which made fields unreadable (white on white).
    ' }'
    'QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus {'
    ' border: 1px solid #2a6db0;'
    ' }'
)

# Fixed width for QFormLayout labels so labels stay narrow and the input
# fields get the remaining width (approximately a 30:70 split at the typical
# right-panel width).
FORM_LABEL_WIDTH = 165

# Wikidata fields (P170 creator, P6216 copyright, P275 license, P10408
# created-during, P180 depicts) get a light-blue background and a validator
# that only accepts QIDs (Q followed by digits). Single-value fields accept
# one QID; the depicts field accepts a semicolon-separated list of QIDs.
WD_BG = '#e6f2ff'
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
