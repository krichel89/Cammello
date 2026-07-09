"""Cammello constants and shared configuration."""
import sys
import re
from PyQt5.QtCore import QRegExp


__version__ = '0.9.5'
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

# Accepted image extensions (used by the file dialog and by drag-and-drop).
IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.gif', '.tif', '.tiff', '.svg', '.webp')

# Highlighted style for the main section headings (Upload settings, Base
# description, Selected file): a bold, colored title badge on the group box.
GROUP_TITLE_STYLE = (
    'QGroupBox {'
    ' font-weight: bold;'
    ' border: 1px solid #b9c6d6;'
    ' border-radius: 6px;'
    ' margin-top: 12px;'
    ' padding-top: 8px;'
    ' }'
    'QGroupBox::title {'
    ' subcontrol-origin: margin;'
    ' subcontrol-position: top left;'
    ' left: 10px;'
    ' padding: 2px 10px;'
    ' color: white;'
    ' background: #2a6db0;'
    ' border-radius: 4px;'
    ' font-size: 11pt;'
    ' }'
)

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
