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
# default_on   whether the field is visible in a workflow that says
#              nothing about it. FALSE is for the fields of one special
#              workflow (the music fields): `felder_aus` is an exclusion
#              list, so a newly added field would otherwise appear in
#              EVERY existing workflows.toml, including the ones written
#              before it existed. A default-off field has to be switched
#              on with `felder_an` instead.
FIELDS = [
    ('vorlagen',             'Other templates:',                    True,  True),
    ('basisbeschreibung',    'Base description:',                   True,  True),
    ('autor',                'Author:',                             True,  True),
    ('ersteller',            'Creator (Q-number):',                 True,  True),
    ('quelle',               'Source:',                             True,  True),
    ('genehmigung',          'Permission:',                         True,  True),
    ('lizenz',               'Licence:',                            True,  True),
    ('zeigt',                'Depicts (P180):',                     True,  True),
    ('falls_kein_depicts',   'If no depicts:',                      False, True),
    ('kategorien',           'Categories:',                         True,  True),
    ('entstanden_waehrend',  'Created during (P10408):',            True,  True),
    ('kamerastandort',       'Camera position (wikitext + SDC):',   False, True),
    ('objektstandort',       'Object position (wikitext + SDC):',   False, True),
    ('galerieseite',         'Gallery page:',                       True,  True),
    ('zusatz_wikitext',      'Extra wikitext / comments:',          True,  True),
    # Music workflow (audio uploads). Off unless a workflow asks for them.
    ('kompositionsjahr',     'Year of composition:',                True,  False),
    ('quellvorlage',         'Source template:',                    True,  False),
    ('komponist',            'Composer:',                           True,  False),
    ('aufnehmender',         'Recorded by:',                        True,  False),
    ('aufnahmetechnik',      'Recording technique:',                True,  False),
    ('todesjahr_komponist',  'Composer died:',                      True,  False),
    ('lizenz_komposition',   'Licence of the composition:',         True,  False),
    ('lizenz_aufnahme',      'Licence of the recording:',           True,  False),
    ('andere_versionen',     'Other versions:',                     True,  False),
    ('instrument',           'Instrument:',                         True,  False),
    ('epoche',               'Period:',                             True,  False),
    ('werk',                 'Work (category name):',               True,  False),
    ('land',                 'Country:',                            True,  False),
]

FIELD_NAMES = [name for name, _label, _text, _on in FIELDS]
TEXT_FIELDS = [name for name, _label, text, _on in FIELDS if text]
DEFAULT_OFF = [name for name, _label, _text, on in FIELDS if not on]
_FIELD_LABEL = {name: label for name, label, _t, _on in FIELDS}


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
        'show': [],
        'preset': {},
        'example': {},
    },
    {
        'key': 'buildings',
        'label': 'Buildings and Landscapes',
        'hide': ['entstanden_waehrend'],
        'show': [],
        'preset': {},
        'example': {},
    },
    # 0.18.0: audio uploads. This is the only workflow that switches the
    # music fields ON; everything a photograph needs and a recording does
    # not is hidden. `{{own}}` in the source field would be wrong here by
    # definition - these are other people's recordings - so the preset
    # empties it.
    {
        'key': 'music',
        'label': 'Music and audio',
        'hide': ['entstanden_waehrend', 'kamerastandort', 'objektstandort',
                 'zeigt', 'galerieseite'],
        'show': list(DEFAULT_OFF),
        'preset': {'quelle': ''},
        'example': {
            'komponist': '[[:en:Felix Mendelssohn|Felix Mendelssohn]]',
            'lizenz_komposition': '{{PD-old-auto-expired}}',
            'todesjahr_komponist': '1847',
            'instrument': 'organ',
            'land': 'Germany',
        },
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
        f'#   felder_an   {tr("fields to SHOW that are off by default (marked below)")}',
        '#',
        f'# {tr("Two optional sections per workflow:")}',
        f'#   [workflow.vorbelegung]  {tr("fills the field if it is still empty")}',
        f'#   [workflow.beispiel]     {tr("grey hint only, never uploaded")}',
        '#',
        f'# {tr("Available field names:")}',
    ]
    width = max(len(n) for n in FIELD_NAMES)
    for name, label, takes_text, _on in FIELDS:
        shown = tr(label).rstrip(':')
        note = '' if takes_text else f'  ({tr("hide only")})'
        if not _on:
            note += f'  ({tr("off by default")})'
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
        show = ', '.join(_quote(h) for h in wf.get('show', []))
        lines += [
            '[[workflow]]',
            f'schluessel = {_quote(wf["key"])}',
            f'name       = {_quote(wf["label"])}',
            f'felder_aus = [{hide}]',
            f'felder_an  = [{show}]',
            '',
            '  # [workflow.vorbelegung]',
            '  # vorlagen = "{{Wikiportraits}}"',
            '',
            '  # [workflow.beispiel]',
            '  # autor = "[[User:Seewolf|Harald Krichel]]"',
            '',
        ]
    return '\n'.join(lines)


def render_block(wf):
    """One [[workflow]] block with its real vorbelegung and beispiel.

    0.18.0, for adding a built-in workflow to a file that predates it.
    Deliberately NOT shared with template_text(): the template writes the
    two sections as commented-out hints, because a fresh file is there to
    be read and learned from. Here they carry actual values.

    Dotted keys (vorbelegung.quelle = "") rather than [workflow.vorbelegung]
    sub-tables, so the whole block is self-contained and can be appended
    after any other block without landing inside the wrong table.
    """
    hide = ', '.join(_quote(h) for h in wf['hide'])
    show = ', '.join(_quote(x) for x in wf.get('show', []))
    lines = [
        '[[workflow]]',
        f'schluessel = {_quote(wf["key"])}',
        f'name       = {_quote(wf["label"])}',
        f'felder_aus = [{hide}]',
        f'felder_an  = [{show}]',
    ]
    for name, value in wf.get('preset', {}).items():
        lines.append(f'vorbelegung.{name} = {_quote(value)}')
    for name, value in wf.get('example', {}).items():
        lines.append(f'beispiel.{name} = {_quote(value)}')
    return '\n'.join(lines) + '\n'


def missing_builtins(translate=None):
    """Built-in workflows the user's file does not have, in built-in order.

    Empty when there is no file, when it could not be read, or when it
    could not be parsed - in all three cases load() is already serving the
    built-ins and nothing is missing.
    """
    if LAST_ERROR:
        return []
    target = path()
    if not os.path.exists(target):
        return []
    have = {w['key'] for w in load(translate)}
    return [w for w in BUILTIN if w['key'] not in have]


def append_builtins(keys, translate=None):
    """Append the named built-in workflows to the user's file.

    APPEND ONLY, and a copy of the file is put beside it as
    workflows.toml.bak first. The file belongs to Harald: nothing already
    in it is rewritten, reordered or reformatted, and if this goes wrong
    the previous state is one rename away.

    Returns (path, error). On success error is None; on failure path is
    None and the file has not been touched.
    """
    wanted = [w for w in BUILTIN if w['key'] in set(keys)]
    if not wanted:
        return None, 'nothing to add'
    target = path()
    if not os.path.exists(target):
        return None, 'no workflow file'
    try:
        with open(target, 'r', encoding='utf-8') as fh:
            before = fh.read()
        with open(target + '.bak', 'w', encoding='utf-8') as fh:
            fh.write(before)
        blocks = '\n'.join(render_block(w) for w in wanted)
        sep = '' if before.endswith('\n\n') else \
              ('\n' if before.endswith('\n') else '\n\n')
        with open(target, 'a', encoding='utf-8') as fh:
            fh.write(sep + blocks)
    except OSError as e:
        return None, str(e)
    reload(translate)
    return target, None


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
        show = []
        raw_show = raw.get('felder_an', [])
        if isinstance(raw_show, str):        # a single name without brackets
            raw_show = [raw_show]
        if isinstance(raw_show, list):
            for name in raw_show:
                if name in FIELD_NAMES:
                    show.append(name)
                else:
                    warnings.append(
                        f'{where}: felder_an {name!r} is not a field name')
        else:
            warnings.append(f'{where}: felder_an is not a list')
        seen.add(key)
        out.append({
            'key': key,
            'label': label.strip(),
            'hide': hide,
            'show': show,
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
        entries = [dict(w, hide=list(w['hide']), show=list(w.get('show', [])),
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
