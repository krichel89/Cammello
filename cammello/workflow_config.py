"""Workflows from an editable text file (0.16.1).

Harald: "Die Konfiguration der Workflows hätte ich gerne in einer einfachen
Textdatei, die ich leicht selbst bearbeiten kann. Sichtbare Felder,
Vorbelegung oder Beispiele. Ebenso die Konfiguration, mit der ich weitere
Workflows hinzufügen kann."

Design decisions:
  * The file lives in the USER directory (~/Cammello/workflows.toml), next
    to the log - NOT in assets/. Everything under assets/ is inside the
    program: a built Mac or Windows Cammello unpacks it fresh on every
    start, so an edit there is gone at the next launch. The user file is
    written once from a template and then never touched again, so it also
    survives every update.
  * TOML, read with the standard library's tomllib (Python 3.11+, which is
    what the build uses) - so this costs no new dependency. It allows
    comments, sections and multi-line strings, which an INI file does not
    do half as comfortably.
  * The field names a workflow may switch are a REGISTRY (FIELDS below),
    and the generated template lists every one of them as a comment. So
    nobody has to read source code to find out what can be switched, and
    the list in the file can never drift from the list in the code.
  * `felder_aus` is an EXCLUSION list: a field not mentioned stays
    visible. A field added in a later Cammello version therefore shows up
    on its own instead of silently disappearing because an old file did
    not know about it.
  * A broken file must never stop Cammello from starting. Parsing errors
    are collected in LAST_ERROR, the built-in defaults take over, and the
    user is told once - the same contract categories.py has for
    meta_categories.txt.
  * A workflow PRESETS, it never locks: `vorbelegung` fills a field that
    is still empty, `beispiel` only sets the grey placeholder and is never
    uploaded.

Qt-free apart from what .constants drags in (QRegExp/QStandardPaths at
import time, no QApplication needed), so plain logic tests can use it.
"""
import os
import tomllib

from .constants import APP_NAME

FILENAME = 'workflows.toml'

# Key of the workflow a fresh installation starts in.
DEFAULT_KEY = 'portraits'

# ── The switchable fields ────────────────────────────────────────────────
# name          the identifier used in the file (bare TOML key: ASCII,
#               no umlauts, so it needs no quoting)
# label         the English UI string of that field - IS the tr() key, so
#               the generated template can name the field the way the
#               running Cammello labels it
# text          whether the field takes text, i.e. whether `vorbelegung`
#               and `beispiel` mean anything for it
FIELDS = [
    ('vorlagen',             'Other templates:',                    True),
    ('basisbeschreibung',    'Base description:',                   True),
    ('autor',                'Author:',                             True),
    ('ersteller',            'Creator (Q-number):',                 True),
    ('quelle',               'Source:',                             True),
    ('genehmigung',          'Permission:',                         True),
    ('lizenz',               'Licence:',                            True),
    ('zeigt',                'Depicts (P180):',                     True),
    ('falls_kein_depicts',   'If no depicts:',                      False),
    ('kategorien',           'Categories:',                         True),
    ('entstanden_waehrend',  'Created during (P10408):',            True),
    ('kamerastandort',       'Camera position (wikitext + SDC):',   False),
    ('objektstandort',       'Object position (wikitext + SDC):',   False),
    ('galerieseite',         'Gallery page:',                       True),
    ('zusatz_wikitext',      'Extra wikitext / comments:',          True),
]

FIELD_NAMES = [name for name, _label, _text in FIELDS]
TEXT_FIELDS = [name for name, _label, text in FIELDS if text]
_FIELD_LABEL = {name: label for name, label, _t in FIELDS}


def label_key_of_field(name):
    """The English UI label (and tr() key) of a registry field."""
    return _FIELD_LABEL.get(name, name)


# ── The built-in defaults ────────────────────────────────────────────────
# These are what a missing or broken file falls back to, and what the
# generated template starts from. They reproduce the two workflows of
# 0.15.0 exactly: Events/Portraits without the object position and the
# gallery page, Buildings and Landscapes without the event.
BUILTIN = [
    {
        'key': 'portraits',
        'label': 'Events/Portraits',
        'hide': ['kamerastandort', 'objektstandort'],
        'preset': {},
        'example': {},
    },
    {
        'key': 'buildings',
        'label': 'Buildings and Landscapes',
        'hide': ['entstanden_waehrend'],
        'preset': {},
        'example': {},
    },
]

LAST_ERROR = None       # human-readable reason the file was not used
LAST_WARNINGS = []      # things that were ignored but did not stop the load
_cache = None


def user_dir():
    """The user's Cammello directory - the one the log file lives in."""
    return os.path.join(os.path.expanduser('~'), APP_NAME)


ENV_OVERRIDE = 'CAMMELLO_WORKFLOWS'


def path():
    """Full path of the workflow file.

    CAMMELLO_WORKFLOWS overrides it with a path of your own. The tests need
    that: without it every test that builds a window would read the
    developer's OWN workflows.toml, so editing it could break tests that
    have nothing to do with workflows. It doubles as a support switch -
    starting Cammello against a fresh file proves whether a problem is in
    the file or in the program.
    """
    override = os.environ.get(ENV_OVERRIDE)
    if override:
        return override
    return os.path.join(user_dir(), FILENAME)


def _quote(value):
    """A TOML basic string. Backslash and quote are the only escapes we
    can produce from our own defaults, but do them properly anyway."""
    out = value.replace('\\', '\\\\').replace('"', '\\"')
    return f'"{out}"'


def template_text(translate=None):
    """The text of a fresh workflow file, including the field list.

    `translate` is an optional tr()-like callable; passing the app's own
    one puts the comments in the user's language. Kept as a parameter
    rather than importing i18n so this module stays usable from tests
    without a language being set up.
    """
    tr = translate or (lambda s: s)
    lines = [
        f'# {APP_NAME} - {tr("Workflows")}',
        '#',
        f'# {tr("This file is yours to edit. Cammello reads it at startup;")}',
        f'# {tr("File > Reload workflows picks up changes without a restart.")}',
        '#',
        f'# {tr("A new workflow is a new [[workflow]] block - nothing else.")}',
        f'# {tr("Lines starting with # are comments.")}',
        '#',
        f'# {tr("Per workflow:")}',
        f'#   schluessel  {tr("internal, never shown, do not change it later")}',
        f'#   name        {tr("what the dropdown shows")}',
        f'#   felder_aus  {tr("fields to HIDE - anything not listed stays visible")}',
        '#',
        f'# {tr("Two optional sections per workflow:")}',
        f'#   [workflow.vorbelegung]  {tr("fills the field if it is still empty")}',
        f'#   [workflow.beispiel]     {tr("grey hint only, never uploaded")}',
        '#',
        f'# {tr("Available field names:")}',
    ]
    width = max(len(n) for n in FIELD_NAMES)
    for name, label, takes_text in FIELDS:
        shown = tr(label).rstrip(':')
        note = '' if takes_text else f'  ({tr("hide only")})'
        lines.append(f'#   {name.ljust(width)}  {shown}{note}')
    lines += [
        '#',
        f'# {tr("Anything Cammello cannot make sense of is listed in the log;")}',
        f'# {tr("a broken file never stops the program - the built-in")}',
        f'# {tr("workflows take over until it parses again.")}',
        '',
    ]
    for wf in BUILTIN:
        hide = ', '.join(_quote(h) for h in wf['hide'])
        lines += [
            '[[workflow]]',
            f'schluessel = {_quote(wf["key"])}',
            f'name       = {_quote(wf["label"])}',
            f'felder_aus = [{hide}]',
            '',
            '  # [workflow.vorbelegung]',
            '  # vorlagen = "{{Wikiportraits}}"',
            '',
            '  # [workflow.beispiel]',
            '  # autor = "[[User:Seewolf|Harald Krichel]]"',
            '',
        ]
    return '\n'.join(lines)


def ensure_file(translate=None):
    """Create the file from the template if it is not there yet.

    Returns the path, or None when it could not be written - a read-only
    home directory is a reason to fall back to the built-ins, not to
    refuse to start.
    """
    target = path()
    if os.path.exists(target):
        return target
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, 'w', encoding='utf-8') as fh:
            fh.write(template_text(translate))
        return target
    except OSError as e:
        global LAST_ERROR
        LAST_ERROR = str(e)
        return None


def _clean_map(raw, where, warnings):
    """A {field: text} section, keeping only known text fields."""
    out = {}
    if raw is None:
        return out
    if not isinstance(raw, dict):
        warnings.append(f'{where}: expected a section, got {type(raw).__name__}')
        return out
    for name, value in raw.items():
        if name not in TEXT_FIELDS:
            known = 'unknown field' if name not in FIELD_NAMES \
                else 'field takes no text'
            warnings.append(f'{where}: {name} ignored ({known})')
            continue
        if not isinstance(value, str):
            warnings.append(f'{where}: {name} ignored (not text)')
            continue
        out[name] = value
    return out


def _parse(data, warnings):
    """Turn parsed TOML into workflow entries. Raises ValueError if there
    is nothing usable at all, so the caller can fall back cleanly."""
    entries = data.get('workflow')
    if not isinstance(entries, list) or not entries:
        raise ValueError('no [[workflow]] block found')
    out = []
    seen = set()
    for i, raw in enumerate(entries, 1):
        where = f'workflow #{i}'
        if not isinstance(raw, dict):
            warnings.append(f'{where}: ignored (not a section)')
            continue
        key = raw.get('schluessel')
        if not isinstance(key, str) or not key.strip():
            warnings.append(f'{where}: ignored (no schluessel)')
            continue
        key = key.strip()
        if key in seen:
            warnings.append(f'{where}: ignored (schluessel {key} used twice)')
            continue
        label = raw.get('name')
        if not isinstance(label, str) or not label.strip():
            label = key
            warnings.append(f'{where}: no name, using the schluessel')
        hide = []
        raw_hide = raw.get('felder_aus', [])
        if isinstance(raw_hide, str):        # a single name without brackets
            raw_hide = [raw_hide]
        if isinstance(raw_hide, list):
            for name in raw_hide:
                if name in FIELD_NAMES:
                    hide.append(name)
                else:
                    warnings.append(
                        f'{where}: felder_aus {name!r} is not a field name')
        else:
            warnings.append(f'{where}: felder_aus is not a list')
        seen.add(key)
        out.append({
            'key': key,
            'label': label.strip(),
            'hide': hide,
            'preset': _clean_map(raw.get('vorbelegung'),
                                 f'{where} vorbelegung', warnings),
            'example': _clean_map(raw.get('beispiel'),
                                  f'{where} beispiel', warnings),
        })
    if not out:
        raise ValueError('no usable workflow in the file')
    return out


def load(translate=None):
    """The workflow entries, from the file if it parses, else built-in.

    Cached; reload() drops the cache. Never raises.
    """
    global _cache, LAST_ERROR, LAST_WARNINGS
    if _cache is not None:
        return _cache
    LAST_ERROR = None
    warnings = []
    target = ensure_file(translate)
    entries = None
    if target:
        try:
            with open(target, 'rb') as fh:      # tomllib wants binary
                data = tomllib.load(fh)
            entries = _parse(data, warnings)
        except tomllib.TOMLDecodeError as e:
            LAST_ERROR = f'{FILENAME}: {e}'
        except (OSError, ValueError) as e:
            LAST_ERROR = f'{FILENAME}: {e}'
    if entries is None:
        entries = [dict(w, hide=list(w['hide']),
                        preset=dict(w['preset']), example=dict(w['example']))
                   for w in BUILTIN]
    LAST_WARNINGS = warnings
    _cache = entries
    return _cache


def reload(translate=None):
    """Drop the cache so an edited file takes effect."""
    global _cache
    _cache = None
    return load(translate)
