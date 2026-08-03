"""Workflow definitions (0.16.1).

Design decisions (agreed with Harald, 2026-07-26, extended 2026-07-30):
  * A workflow is DATA, not code. Since 0.16.1 that data lives in a text
    file the user edits himself - see workflow_config for the format, the
    field registry and the error contract. This module is only the lookup
    layer the UI talks to, so callers did not have to change.
  * A workflow presets fields and hides fields. IPTC is deliberately NOT
    switched - the IPTC tab keeps its own fields regardless.
  * A workflow PRESETS, it never locks. `vorbelegung` fills a field only
    while it is still empty, `beispiel` sets nothing but the grey
    placeholder, and switching never overwrites something already typed.
  * Which fields a workflow hides is an EXCLUSION list, so a field that a
    later version adds appears on its own instead of vanishing because an
    old file did not mention it.

No Qt imports in here beyond what .constants pulls in at import time
(QRegExp/QStandardPaths, no QApplication needed): the module stays usable
from plain logic tests, the same rule channels.py and edits.py follow.
"""
from . import workflow_config

# Key of the workflow a fresh installation starts in. Kept as a name for
# the callers that had it; if the user's file has no workflow by this key,
# by_key() falls back to the FIRST entry in the file instead - he is free
# to throw both built-in workflows away and put his own there.
DEFAULT_KEY = workflow_config.DEFAULT_KEY


def all_workflows():
    """The workflow entries in dropdown order.

    Each entry is a dict with 'key', 'label', 'hide', 'preset', 'example'.
    """
    return list(workflow_config.load())


def keys():
    """The stable workflow keys in dropdown order."""
    return [w['key'] for w in all_workflows()]


def default_key():
    """The key a fresh start selects: DEFAULT_KEY if the file offers it,
    otherwise the first workflow in the file."""
    entries = all_workflows()
    for w in entries:
        if w['key'] == DEFAULT_KEY:
            return DEFAULT_KEY
    return entries[0]['key'] if entries else DEFAULT_KEY


def by_key(key):
    """The workflow entry for `key`; unknown keys fall back to the default,
    so a stale QSettings value can never leave the app without a workflow.
    """
    entries = all_workflows()
    for w in entries:
        if w['key'] == key:
            return w
    fallback = default_key()
    for w in entries:
        if w['key'] == fallback:
            return w
    # Only reachable if the file yielded nothing at all, which load()
    # already guards against - but a caller must never get None.
    return {'key': DEFAULT_KEY, 'label': DEFAULT_KEY, 'hide': [],
            'preset': {}, 'example': {}}


def label_of(key):
    """The label shown in the dropdown. For the two built-in workflows this
    is also the tr() key; a workflow the user invented is shown as he
    wrote it, because there is nothing to translate it to."""
    return by_key(key)['label']


def hidden_fields(key):
    """The registry names of the fields this workflow hides."""
    return list(by_key(key)['hide'])


def is_hidden(key, field):
    """Whether `field` is hidden in this workflow."""
    return field in by_key(key)['hide']


def presets_of(key):
    """{field name: text} to fill into still-empty fields."""
    return dict(by_key(key)['preset'])


def examples_of(key):
    """{field name: text} to show as a grey placeholder only."""
    return dict(by_key(key)['example'])


def offers_object_location(key):
    """Whether this workflow offers the position of the DEPICTED object
    ({{Object location dec}} / P9149) next to the camera position."""
    return not is_hidden(key, 'objektstandort')


def offers_camera_location(key):
    """Whether this workflow offers the camera position
    ({{Location dec}} / P1259)."""
    return not is_hidden(key, 'kamerastandort')


def reload(translate=None):
    """Re-read the workflow file (Workflows > Reload)."""
    return workflow_config.reload(translate)
