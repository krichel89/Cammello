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
  * `hide_fields` (0.18.29: `felder_aus`) is an EXCLUSION list: a field not mentioned stays
    visible. A field added in a later Cammello version therefore shows up
    on its own instead of silently disappearing because an old file did
    not know about it.
  * A broken file must never stop Cammello from starting. Parsing errors
    are collected in LAST_ERROR, the built-in defaults take over, and the
    user is told once - the same contract categories.py has for
    meta_categories.txt.
  * A workflow PRESETS, it never locks: `prefill` (`vorbelegung`) fills a field that
    is still empty, `example` (`beispiel`) only sets the grey placeholder and is never
    uploaded.
  * 0.18.29: `set` (`setzen`) is the third kind - it REPLACES the field, filled or
    not, when the workflow is picked in the dropdown. That is what an event
    needs (templates, categories, "created during" of ONE event): a fill-
    if-empty rule would keep last year's event the moment anything stood
    there. Only a pick by the user applies it - never the start-up restore
    and never "Reload workflows".

  * 0.18.29: workflows can be PASSED ON as small text files with the
    extension .cammello (same TOML, one or more [[workflow]] blocks).
    Loading one copies it into ~/Cammello/workflows.d/ - the user's own
    workflows.toml is never touched, a newer version of the same file
    replaces the older one, and removing a workflow is deleting the file.
    Everything in such a file is DATA: field names from the registry and
    plain text, nothing is executed.

  * 0.18.30: the parameters are ENGLISH (key, name, hide_fields,
    show_fields, [workflow.prefill|set|example], field names like
    `templates`, `categories`, `created_during`). The German spelling of
    0.18.29 and earlier is still read - nothing a user or a recipient has
    on disk stops working.

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
    ('captions_basis',       'Captions (all files):',               False, True),
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

# 0.18.30 (Harald): the parameters in a workflow file are ENGLISH. The names
# above stay the internal identifiers (and the old German spelling in a
# file keeps working); this table is the spelling the template, the
# generated blocks and the documentation use. Either spelling is read.
ENGLISH_NAMES = {
    'vorlagen': 'templates',
    'basisbeschreibung': 'base_description',
    'captions_basis': 'base_captions',
    'autor': 'author',
    'ersteller': 'creator',
    'quelle': 'source',
    'genehmigung': 'permission',
    'lizenz': 'license',
    'zeigt': 'depicts',
    'falls_kein_depicts': 'if_no_depicts',
    'kategorien': 'categories',
    'entstanden_waehrend': 'created_during',
    'kamerastandort': 'camera_position',
    'objektstandort': 'object_position',
    'galerieseite': 'gallery_page',
    'zusatz_wikitext': 'extra_wikitext',
    'kompositionsjahr': 'composition_year',
    'quellvorlage': 'source_template',
    'komponist': 'composer',
    'aufnehmender': 'recorded_by',
    'aufnahmetechnik': 'recording_technique',
    'todesjahr_komponist': 'composer_died',
    'lizenz_komposition': 'composition_license',
    'lizenz_aufnahme': 'recording_license',
    'andere_versionen': 'other_versions',
    'instrument': 'instrument',
    'epoche': 'period',
    'werk': 'work',
    'land': 'country',
}
# The keys of a [[workflow]] block and its three sections: English first,
# the pre-0.18.30 German spelling second.
BLOCK_KEYS = (('key', 'schluessel'), ('name', 'name'),
              ('hide_fields', 'felder_aus'), ('show_fields', 'felder_an'),
              ('prefill', 'vorbelegung'), ('set', 'setzen'),
              ('example', 'beispiel'))

FIELD_NAMES = [name for name, _label, _text, _on in FIELDS]
TEXT_FIELDS = [name for name, _label, text, _on in FIELDS if text]
DEFAULT_OFF = [name for name, _label, _text, on in FIELDS if not on]
_TO_INTERNAL = {en: de for de, en in ENGLISH_NAMES.items()}
_FIELD_LABEL = {name: label for name, label, _t, _on in FIELDS}


def field_name(name):
    """The internal field name for either spelling, or None if unknown."""
    if name in FIELD_NAMES:
        return name
    return _TO_INTERNAL.get(name) if isinstance(name, str) else None


def external_name(name):
    """The English spelling of an internal field name (what a file shows)."""
    return ENGLISH_NAMES.get(name, name)


def _pick(raw, english, german):
    """A block key by its English name, else by the old German one."""
    return raw[english] if english in raw else raw.get(german)


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
        'hide': ['kamerastandort', 'objektstandort', 'captions_basis'],
        'show': [],
        'preset': {},
        'set': {},
        'example': {},
    },
    {
        'key': 'buildings',
        'label': 'Buildings and Landscapes',
        'hide': ['entstanden_waehrend'],
        'show': [],
        'preset': {},
        'set': {},
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
        'set': {},
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

# Passed-on workflow files (0.18.29).
EXT = '.cammello'
DIRNAME = 'workflows.d'
MAX_FILE_BYTES = 64 * 1024      # a workflow is a few lines; this is generous
# Fields whose change a recipient should SEE before accepting a file: they
# end up in the description of every upload.
SENSITIVE_FIELDS = ('lizenz', 'autor', 'ersteller', 'quelle', 'genehmigung')
ORIGINS = {}    # key -> file name in workflows.d, for those entries


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
        f'#   key          {tr("internal, never shown, do not change it later")}',
        f'#   name         {tr("what the dropdown shows")}',
        f'#   hide_fields  {tr("fields to HIDE - anything not listed stays visible")}',
        f'#   show_fields  {tr("fields to SHOW that are off by default (marked below)")}',
        '#',
        f'# {tr("Three optional sections per workflow:")}',
        f'#   [workflow.prefill]  {tr("fills the field if it is still empty")}',
        f'#   [workflow.set]      {tr("REPLACES the field when you pick the workflow, even if filled")}',
        f'#   [workflow.example]  {tr("grey hint only, never uploaded")}',
        '#',
        f'# {tr("Files written before version 0.18.30 use German names (schluessel, felder_aus, vorbelegung, ...); they are still read.")}',
        '#',
        f'# {tr("Available field names:")}',
    ]
    width = max(len(external_name(n)) for n in FIELD_NAMES)
    for name, label, takes_text, _on in FIELDS:
        shown = tr(label).rstrip(':')
        note = '' if takes_text else f'  ({tr("hide only")})'
        if not _on:
            note += f'  ({tr("off by default")})'
        lines.append(f'#   {external_name(name).ljust(width)}  {shown}{note}')
    lines += [
        '#',
        f'# {tr("Workflows you load from a .cammello file are kept in the folder workflows.d next to this file.")}',
        '#',
        f'# {tr("Anything Cammello cannot make sense of is listed in the log;")}',
        f'# {tr("a broken file never stops the program - the built-in")}',
        f'# {tr("workflows take over until it parses again.")}',
        '',
    ]
    for wf in BUILTIN:
        hide = ', '.join(_quote(external_name(h)) for h in wf['hide'])
        show = ', '.join(_quote(external_name(h))
                         for h in wf.get('show', []))
        lines += [
            '[[workflow]]',
            f'key         = {_quote(wf["key"])}',
            f'name        = {_quote(wf["label"])}',
            f'hide_fields = [{hide}]',
            f'show_fields = [{show}]',
            '',
            '  # [workflow.prefill]',
            '  # templates = "{{Wikiportraits}}"',
            '',
            '  # [workflow.set]',
            '  # templates = "{{WikiPortraits Event 2026}}"',
            '  # categories = "Event 2026; Another category"',
            '  # created_during = "Q12345678"',
            '',
            '  # [workflow.example]',
            '  # author = "[[User:Seewolf|Harald Krichel]]"',
            '',
        ]
    return '\n'.join(lines)


def render_block(wf):
    """One [[workflow]] block with its real prefill and example.

    0.18.0, for adding a built-in workflow to a file that predates it.
    Deliberately NOT shared with template_text(): the template writes the
    two sections as commented-out hints, because a fresh file is there to
    be read and learned from. Here they carry actual values.

    Dotted keys (prefill.source = "") rather than [workflow.prefill]
    sub-tables, so the whole block is self-contained and can be appended
    after any other block without landing inside the wrong table.
    """
    hide = ', '.join(_quote(external_name(h)) for h in wf['hide'])
    show = ', '.join(_quote(external_name(x)) for x in wf.get('show', []))
    lines = [
        '[[workflow]]',
        f'key         = {_quote(wf["key"])}',
        f'name        = {_quote(wf["label"])}',
        f'hide_fields = [{hide}]',
        f'show_fields = [{show}]',
    ]
    for name, value in wf.get('preset', {}).items():
        lines.append(f'prefill.{external_name(name)} = {_quote(value)}')
    for name, value in wf.get('set', {}).items():
        lines.append(f'set.{external_name(name)} = {_quote(value)}')
    for name, value in wf.get('example', {}).items():
        lines.append(f'example.{external_name(name)} = {_quote(value)}')
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
    for given, value in raw.items():
        name = field_name(given)
        if name not in TEXT_FIELDS:
            known = 'unknown field' if name is None \
                else 'field takes no text'
            warnings.append(f'{where}: {given} ignored ({known})')
            continue
        if not isinstance(value, str):
            warnings.append(f'{where}: {given} ignored (not text)')
            continue
        out[name] = value
    return out


def _field_list(raw, option, where, warnings):
    """A list of field names (either spelling) -> internal names."""
    if raw is None:
        return []
    if isinstance(raw, str):                 # a single name without brackets
        raw = [raw]
    if not isinstance(raw, list):
        warnings.append(f'{where}: {option} is not a list')
        return []
    out = []
    for given in raw:
        name = field_name(given)
        if name is None:
            warnings.append(f'{where}: {option} {given!r} is not a field name')
        elif name not in out:
            out.append(name)
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
        key = _pick(raw, 'key', 'schluessel')
        if not isinstance(key, str) or not key.strip():
            warnings.append(f'{where}: ignored (no key)')
            continue
        key = key.strip()
        if key in seen:
            warnings.append(f'{where}: ignored (key {key} used twice)')
            continue
        label = raw.get('name')
        if not isinstance(label, str) or not label.strip():
            label = key
            warnings.append(f'{where}: no name, using the key')
        hide = _field_list(_pick(raw, 'hide_fields', 'felder_aus'),
                           'hide_fields', where, warnings)
        show = _field_list(_pick(raw, 'show_fields', 'felder_an'),
                           'show_fields', where, warnings)
        seen.add(key)
        out.append({
            'key': key,
            'label': label.strip(),
            'hide': hide,
            'show': show,
            'preset': _clean_map(_pick(raw, 'prefill', 'vorbelegung'),
                                 f'{where} prefill', warnings),
            'set': _clean_map(_pick(raw, 'set', 'setzen'),
                              f'{where} set', warnings),
            'example': _clean_map(_pick(raw, 'example', 'beispiel'),
                                  f'{where} example', warnings),
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
                        preset=dict(w['preset']), example=dict(w['example']),
                        set=dict(w.get('set', {})))
                   for w in BUILTIN]
    _load_extras(entries, warnings)
    LAST_WARNINGS = warnings
    _cache = entries
    return _cache


def reload(translate=None):
    """Drop the cache so an edited file takes effect."""
    global _cache
    _cache = None
    return load(translate)


# ── Passed-on workflow files (.cammello, 0.18.29) ────────────────────────

def extras_dir():
    """Where loaded .cammello files live: workflows.d beside workflows.toml
    (so CAMMELLO_WORKFLOWS moves it along - the tests rely on that)."""
    return os.path.join(os.path.dirname(path()), DIRNAME)


def _parse_bytes(raw, where):
    """(entries, warnings, error) from the bytes of one .cammello file."""
    warnings = []
    if len(raw) > MAX_FILE_BYTES:
        return [], warnings, f'{where}: file is too large'
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        return [], warnings, f'{where}: not a UTF-8 text file'
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        return [], warnings, f'{where}: {e}'
    try:
        entries = _parse(data, warnings)
    except ValueError as e:
        return [], warnings, f'{where}: {e}'
    return entries, warnings, None


def _load_extras(entries, warnings):
    """Append the workflows of workflows.d to `entries`, in file-name order.

    A key that is already taken (by workflows.toml, a built-in or an
    earlier file) is ignored with a warning - the user's own file wins.
    Never raises: a broken file is reported and skipped.
    """
    ORIGINS.clear()
    folder = extras_dir()
    try:
        names = sorted(n for n in os.listdir(folder)
                       if n.lower().endswith(EXT))
    except OSError:
        return
    taken = {w['key'] for w in entries}
    for name in names:
        try:
            with open(os.path.join(folder, name), 'rb') as fh:
                raw = fh.read(MAX_FILE_BYTES + 1)
        except OSError as e:
            warnings.append(f'{name}: {e}')
            continue
        found, file_warnings, error = _parse_bytes(raw, name)
        warnings += [f'{name}: {w}' for w in file_warnings]
        if error:
            warnings.append(error)
            continue
        for wf in found:
            if wf['key'] in taken:
                warnings.append(f'{name}: ignored (key {wf["key"]} '
                                f'is already in use)')
                continue
            taken.add(wf['key'])
            ORIGINS[wf['key']] = name
            entries.append(wf)


_WINDOWS_RESERVED = {'CON', 'PRN', 'AUX', 'NUL'} | {
    f'{p}{n}' for p in ('COM', 'LPT') for n in range(1, 10)}


def safe_name(src):
    """The file name a loaded file is stored under: the base name only,
    harmless characters, always ending in .cammello."""
    base = os.path.basename(src or '')
    stem = base[:-len(EXT)] if base.lower().endswith(EXT) else base
    stem = ''.join(c if (c.isalnum() or c in ' ._-()') else '_'
                   for c in stem).strip(' .')[:80].strip(' .')
    # Windows device names (CON, NUL, COM1 ...) are reserved with ANY
    # extension; a file called CON.cammello must not be opened for writing.
    if stem.split('.')[0].upper() in _WINDOWS_RESERVED:
        stem = '_' + stem
    return (stem or 'workflow') + EXT


def inspect_file(src):
    """Check a .cammello file WITHOUT installing it.

    Returns (entries, warnings, error); on error entries is empty. Only the
    extension, the size, UTF-8, TOML and the workflow blocks are checked -
    the same rules the loader applies, so what passes here will load.
    """
    name = os.path.basename(src or '')
    if not name.lower().endswith(EXT):
        return [], [], f'{name}: a workflow file ends in {EXT}'
    try:
        with open(src, 'rb') as fh:
            raw = fh.read(MAX_FILE_BYTES + 1)
    except OSError as e:
        return [], [], f'{name}: {e}'
    return _parse_bytes(raw, name)


def conflicts_of(entries, src):
    """Keys of `entries` that are already taken by something ELSE.

    "Else" = workflows.toml, a built-in, or a different file in
    workflows.d. The same file name is an update, not a conflict.
    """
    mine = safe_name(src)
    load()                      # makes ORIGINS current
    taken = {w['key'] for w in load()}
    return [w['key'] for w in entries
            if w['key'] in taken and ORIGINS.get(w['key']) != mine]


def install_file(src, translate=None):
    """Copy a checked .cammello file into workflows.d and reload.

    Returns (destination, replaced, error). Written to a temporary name
    and moved into place, so a half-written file is never read. An
    existing file of the same name is replaced - that is how a corrected
    version reaches people.
    """
    dest = os.path.join(extras_dir(), safe_name(src))
    replaced = os.path.exists(dest)
    tmp = dest + '.part'
    try:
        with open(src, 'rb') as fh:
            raw = fh.read(MAX_FILE_BYTES + 1)
        # The file is read AGAIN here, after the user confirmed a preview of
        # the first reading. Check the bytes that are about to be stored, so
        # a file swapped in between (or one that outgrew the limit) is never
        # written.
        _entries, _notes, error = _parse_bytes(raw, os.path.basename(src))
        if error:
            return None, False, error
        os.makedirs(extras_dir(), exist_ok=True)
        with open(tmp, 'wb') as fh:
            fh.write(raw)
        os.replace(tmp, dest)
    except OSError as e:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return None, False, str(e)
    reload(translate)
    return dest, replaced, None


def preview_text(entries, translate=None):
    """What loading would change, for the confirmation: per workflow its
    name, the fields it REPLACES and the fields it FILLS, with the values,
    and the fields it hides or shows.

    Values are shown IN FULL, never cut off: the confirmation is the only
    thing between a file from anywhere and every later upload, and a
    preview that ends in "..." could hide the part that matters (a second
    template, another licence). Line breaks become " | ".
    Fields that end up in every upload's description are marked.
    """
    tr = translate or (lambda s: s)
    lines = []

    def shown(name):
        return tr(label_key_of_field(name)).rstrip(':')

    def value(text):
        return ' | '.join(p.strip() for p in text.splitlines() if p.strip())

    for wf in entries:
        lines.append(f'■ {wf["label"]}')
        for heading, mapping in ((tr('replaces'), wf.get('set', {})),
                                 (tr('fills if empty'), wf.get('preset', {}))):
            for name, text in mapping.items():
                mark = '  ⚠' if name in SENSITIVE_FIELDS else ''
                lines.append(f'    {heading}: {shown(name)} = '
                             f'{value(text) or "(empty)"}{mark}')
        for heading, names in ((tr('hides'), wf.get('hide', [])),
                               (tr('shows'), wf.get('show', []))):
            if names:
                lines.append(f'    {heading}: '
                             + ', '.join(shown(n) for n in names))
        if not (wf.get('set') or wf.get('preset')
                or wf.get('hide') or wf.get('show')):
            lines.append(f'    {tr("sets no field")}')
    return '\n'.join(lines)
