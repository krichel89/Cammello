"""Channel marks (0.12.1): keep CC-licensed Commons material and commercial
stock material apart WITHOUT removing files from any list.

A file can carry one mark:
    MARK_COMMONS     - released for Commons under a free license
    MARK_COMMERCIAL  - meant for commercial outlets (FTP agencies / Flickr)

The mark is a colour code in the file lists (green = Commons, orange =
commercial). In the OTHER channel's list the file stays visible but is
grayed out (disabled) and excluded from that channel's upload - so a
CC-released file cannot slip to a stock agency and a commercial file cannot
slip onto Commons. Unmarked files behave exactly as before; marking is the
opt-in.

Marks persist across sessions in QSettings ('Channels' scope) as one JSON
object keyed by the normalized absolute path (same normalization as the
duplicate check in mw_files: normcase for case-insensitive Windows paths;
symlinks/hardlinks are NOT resolved).

No Qt imports here beyond nothing at all - the module stays usable from
plain logic tests; the QSettings object is passed in by the caller.
"""
import json
import os

MARK_COMMONS = 'commons'
MARK_COMMERCIAL = 'commercial'

# Colour code shown in the lists (foreground of the file name). Deliberately
# NOT one of culling.LABEL_COLORS (['#d33','#dc3','#3a3','#36c','#93c'] =
# the 1-5 colour labels): a channel mark must never be confusable with a
# rating colour, so teal is used instead of the obvious green.
COLOR_COMMONS = '#0e8a94'      # teal - free/CC, home channel = MediaWiki tab
COLOR_COMMERCIAL = '#d07000'   # orange - commercial, home = FTP/Flickr tab

_SETTINGS_KEY = 'marks'


def norm(path):
    """Normalized absolute path used as the mark key (matches
    MWFilesMixin._norm_path)."""
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def load_marks(settings):
    """-> {normalized_path: mark} from the given QSettings; unknown mark
    values (future versions, manual edits) are dropped instead of crashing."""
    raw = settings.value(_SETTINGS_KEY, '') or ''
    try:
        data = json.loads(raw) if raw else {}
    except ValueError:
        return {}
    if not isinstance(data, dict):
        return {}
    valid = (MARK_COMMONS, MARK_COMMERCIAL)
    return {str(k): v for k, v in data.items() if v in valid}


def save_marks(settings, marks):
    settings.setValue(_SETTINGS_KEY, json.dumps(marks, ensure_ascii=False))
    settings.sync()


def set_mark(marks, paths, mark):
    """Set (mark in MARK_*) or clear (mark=None) the mark for the given
    paths in the marks dict, in place. Returns the number of changes."""
    changed = 0
    for p in paths:
        key = norm(p)
        if mark is None:
            if key in marks:
                del marks[key]
                changed += 1
        elif marks.get(key) != mark:
            marks[key] = mark
            changed += 1
    return changed
