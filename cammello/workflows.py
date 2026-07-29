"""Workflow definitions (0.15.0).

Design decisions (agreed with Harald, 2026-07-26):
  * A workflow is DATA, not code. Everything that differs between
    "Events/Portraits" and "Buildings and Landscapes" sits in ONE entry
    below, so a third workflow is a new entry - not a change to the UI.
    No editor for these presets in this round; the table is the editor.
  * A workflow presets exactly three things: the wikitext templates and
    base description, the category suggestions, and the structured-data
    statements. IPTC is deliberately NOT switched - the IPTC tab keeps
    its own fields regardless of the selected workflow.
  * A workflow PRESETS, it never locks. Every field it fills stays
    editable, and switching does not overwrite something the user has
    already typed (see apply_to() callers).
  * Which of the two coordinates a workflow OFFERS is part of the entry
    (`object_location`), but the Location column in the file table is
    shown independently of it - it is driven by whether any file
    actually carries coordinates.

No Qt imports in here: the module is usable from plain logic tests, the
same rule channels.py and edits.py follow.
"""

# Key of the workflow a fresh installation starts in.
DEFAULT_KEY = 'portraits'


# One entry per workflow, in the order of the dropdown.
#
#   key              stable identifier; persisted in QSettings, never shown
#   label            English UI string - IS the tr() key (see i18n.py)
#   templates        preset for the "Other templates" field
#   base_description preset for the base description (MediaWiki tab)
#   categories       category suggestions offered for every file
#   sdc              structured-data statements as (property, value) pairs
#   camera_location  offer the camera position   -> {{Location dec}}  / P1259
#   object_location  offer the depicted position -> {{Object location dec}}
#                                                   / P9149
#
# The content of `templates`, `base_description`, `categories` and `sdc`
# is deliberately EMPTY for now: what belongs in the two workflows is
# Harald's call, not a guess of mine. The structure carries them the
# moment he says what they are.
WORKFLOWS = [
    {
        'key': 'portraits',
        'label': 'Events/Portraits',
        'templates': '',
        'base_description': '',
        'categories': [],
        'sdc': [],
        'camera_location': True,
        'object_location': False,
    },
    {
        'key': 'buildings',
        'label': 'Buildings and Landscapes',
        'templates': '',
        'base_description': '',
        'categories': [],
        'sdc': [],
        'camera_location': True,
        'object_location': True,
    },
]

_BY_KEY = {w['key']: w for w in WORKFLOWS}


def all_workflows():
    """The workflow entries in dropdown order."""
    return list(WORKFLOWS)


def keys():
    """The stable workflow keys in dropdown order."""
    return [w['key'] for w in WORKFLOWS]


def by_key(key):
    """The workflow entry for `key`; unknown keys fall back to the default,
    so a stale QSettings value can never leave the app without a workflow."""
    return _BY_KEY.get(key) or _BY_KEY[DEFAULT_KEY]


def label_of(key):
    """The English label (and tr() key) of a workflow."""
    return by_key(key)['label']


def offers_object_location(key):
    """Whether this workflow offers the position of the DEPICTED object
    ({{Object location dec}} / P9149) next to the camera position."""
    return bool(by_key(key)['object_location'])


def offers_camera_location(key):
    """Whether this workflow offers the camera position
    ({{Location dec}} / P1259)."""
    return bool(by_key(key)['camera_location'])
