"""Structured-data (SDC) and wikitext text helpers (no GUI)."""
import re
import os
import unicodedata
from .constants import *
from . import langcodes


def invalid_qid_problems(label, value, multi=False):
    """Return a list of human-readable problems if value is not valid QID(s).

    Empty value is allowed (returns no problems). For multi=True the value is
    split on ';'/',' and every token must be a QID.
    """
    value = (value or '').strip()
    if not value:
        return []
    problems = []
    if multi:
        tokens = [t.strip() for t in re.split(r'[;,]', value) if t.strip()]
        bad = [t for t in tokens if not QID_RE.match(t)]
        if bad:
            problems.append(f'{label}: not a QID -> ' + ', '.join(bad))
    else:
        if not QID_RE.match(value):
            problems.append(f'{label}: not a QID -> {value}')
    return problems



_SD_LINE_RE = re.compile(r'^\s*([a-z_]+)\s*=\s*')

def _strip_sd_lines(text, keys):
    """Remove `key = value` lines matching any of the given keys.

    Used by the settings restore to migrate creator/copyright/license out of
    an older base_description into the dedicated upload-settings fields.
    """
    keys = set(keys)
    out = []
    for line in (text or '').splitlines():
        m = _SD_LINE_RE.match(line)
        if m and m.group(1) in keys:
            continue
        out.append(line)
    # Strip any leading empty lines the removal may leave behind.
    while out and not out[0].strip():
        out.pop(0)
    return '\n'.join(out)


NAME_SEPARATORS = [' at ', ' bei ', ' à ', ' al ', ' auf ', ' sur ', ' on ', ' sul ']


# Keys whose values are MERGED when they occur more than once (i.e. once in the
# base description and once in the per-file description). Only depicts qualifies:
# workers.py turns a ";"-separated depicts value into several P180 claims. The
# other keys become a single claim each, so a merged "Q640;Q123" would be handed
# to the API as one (invalid) QID; and a merged gallery_suffix would be a
# nonsensical page name. For those, the per-file value wins - see below.
MERGE_KEYS = {'depicts'}


def extract_structured_data(text, logger=None):
    """Extract key=value lines from description_all text.

    Lines starting with # are treated as comments and removed.
    Keys are matched case-insensitively (license= and LICENSE= are equivalent).

    The text handed in is the concatenation of the upload settings, the base
    description and the per-file description, in that order, so a key can occur
    twice. Since 0.9.13:
      - depicts (MERGE_KEYS): all occurrences are merged, deduplicated, order
        preserved -> several P180 claims.
      - every other key, and caption_XX: the LAST occurrence wins, i.e. the
        per-file value overrides the base value. (Up to 0.9.12 the first one won
        for the non-caption keys, so a per-file value was silently dropped while
        captions behaved the other way round.)
    """
    sd = {}
    # Remove comment lines (starting with #)
    text = re.sub(r'^#[^\n]*\n?', '', text, flags=re.MULTILINE)
    result = text

    # Dynamically extract all caption_XX= lines (any language code). Assigning
    # into the dict means the last occurrence wins.
    for m in re.finditer(r'(?:^|\n)alt_(' + _LANG_CODE + r')=([^\n]+)',
                         result, flags=re.IGNORECASE):
        sd['alt_' + langcodes.normalize(m.group(1))] = m.group(2).strip()
    result = re.sub(r'\nalt_' + _LANG_CODE + r'=[^\n]+', '', result,
                    flags=re.IGNORECASE)
    result = re.sub(r'^alt_' + _LANG_CODE + r'=[^\n]+\n?', '', result,
                    flags=re.MULTILINE | re.IGNORECASE)
    for m in re.finditer(r'(?:^|\n)caption_(' + _LANG_CODE + r')=([^\n]+)',
                         result, flags=re.IGNORECASE):
        # Only the LANGUAGE part is case-insensitive; the script tag keeps
        # the spelling it was written with (see langcodes.normalize).
        lang = langcodes.normalize(m.group(1))
        val = m.group(2).strip()
        key = 'caption_' + lang
        if logger and key in sd and sd[key] != val:
            logger.info('%s: per-file value overrides the base value '
                        '("%s" -> "%s").', key, sd[key], val)
        sd[key] = val
    # Remove all matched caption_XX= lines from result
    result = re.sub(r'\ncaption_' + _LANG_CODE + r'=[^\n]+', '', result,
                    flags=re.IGNORECASE)
    result = re.sub(r'^caption_' + _LANG_CODE + r'=[^\n]+\n?', '', result,
                    flags=re.MULTILINE | re.IGNORECASE)

    for key in SD_KEYS:
        values = [v.strip() for v in
                  re.findall(rf'(?:^|\n){key}=([^\n]+)', result,
                             flags=re.IGNORECASE)]
        values = [v for v in values if v]
        if not values:
            continue

        if key in MERGE_KEYS:
            merged, seen = [], set()
            for value in values:
                # ";" is the separator, "," is tolerated for older values.
                for part in re.split(r'[;,]', value):
                    part = part.strip()
                    if part and part not in seen:
                        seen.add(part)
                        merged.append(part)
            sd[key] = '; '.join(merged)
            if logger and len(values) > 1:
                logger.info('%s: base and per-file values merged -> %s',
                            key, sd[key])
        else:
            sd[key] = values[-1]
            if logger and len(values) > 1 and values[0] != values[-1]:
                logger.info('%s: per-file value overrides the base value '
                            '("%s" -> "%s").', key, values[0], values[-1])

        result = re.sub(rf'\n{key}=[^\n]+', '', result, flags=re.IGNORECASE)
        result = re.sub(rf'^{key}=[^\n]+\n?', '', result,
                        flags=re.MULTILINE | re.IGNORECASE)

    return sd, result.strip()


# Keys that look like a structured-data tag when they appear at the start of a line.

# 0.15.2: language codes may carry a SCRIPT and a REGION part - "ms-Arab"
# (Malay in Jawi), "zh-Hant", "pt-BR". The old [a-z]{2,3} silently dropped
# such captions again when the description cell was read back, so widening
# it in the editor alone would have fixed nothing. ONE pattern, used
# everywhere a language code appears, so the six places cannot drift apart.
_LANG_CODE = r'[A-Za-z]{2,3}(?:-[A-Za-z]{4})?(?:-(?:[A-Za-z]{2}|[0-9]{3}))?'

_LINT_KEYS_RE = (r'(?:creator|copyright|license|depicts|depicts_override|'
                 r'created_during|gallery_suffix|caption_' + _LANG_CODE +
                 r'|alt_' + _LANG_CODE + r')')


def set_coordinates_line(text, value):
    """Set (or replace) the coordinates= line in a per-file description.

    Written as a helper rather than by rebuilding the description through the
    editor: filling coordinates for a MULTI-row selection must not disturb
    anything else those rows carry - captions, depicts, free wikitext. An
    empty value removes the line.
    """
    text = text or ''
    stripped = re.sub(r'(?:^|\n)coordinates=[^\n]*', '', text,
                      flags=re.IGNORECASE)
    value = (value or '').strip()
    if not value:
        return stripped.strip()
    if not stripped.strip():
        return f'coordinates={value}'
    return f'coordinates={value}\n' + stripped.strip()


def find_description_issues(text):
    """Scan description_all for likely typos and return human-readable warnings.

    Catches things that would otherwise be silently turned into broken wikitext:
    a key with the wrong separator (creator_Q… instead of creator=Q…), a
    misspelled [[Category:]] link, or a duplicated "Category:" prefix. This only
    reports problems; it does not change the text.
    """
    issues = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        low = line.lower()
        # 1) known key followed by '_' or ':' instead of '='
        m = re.match(rf'^({_LINT_KEYS_RE})[_:]', low)
        if m:
            issues.append(
                f'"{line[:60]}" looks like a "{m.group(1)}=value" tag but uses '
                f'"_"/":" instead of "=". It will be treated as plain text, and '
                f'no structured data will be set for it.')
            continue
        # 2) misspelled category link ([[Cate… but not [[Category:)
        if re.match(r'^\[\[\s*cate', low) and not low.startswith('[[category:'):
            issues.append(
                f'"{line[:60]}" looks like a misspelled category ("[[Category:" '
                f'expected); it will NOT be added as a category.')
            continue
        # 3) duplicated Category: prefix
        if re.match(r'^\[\[\s*category:\s*category:', low):
            issues.append(
                f'"{line[:60]}" has a duplicated "Category:" prefix; the resulting '
                f'category name will be wrong.')
            continue
    return issues



def extract_name_from_caption(caption):
    """Extract person name from caption (everything before 'at', 'bei', etc.)"""
    if not caption:
        return caption
    for sep in NAME_SEPARATORS:
        if sep in caption:
            return caption.split(sep)[0].strip()
    return caption


# ── Names built from the description (0.18.19) ───────────────────────────────
#
# Harald: "Einmal haette ich gerne eine Funktion, die vor dem Hochladen per
# Knopfdruck sinnvolle Dateinamen aus den Beschreibungen erzeugt. Also vor
# allen Dingen Personennamen, eventuell Person bei Veranstaltung plus die
# Nummer aus der Kamera oder wenn nicht sinnvoll vorhanden, eine laufende
# Nummer zur Unterscheidung."
#
# The caption is the source, not the depicts QID: a QID would mean one
# Wikidata round trip per file for a button that is supposed to answer
# instantly, and the caption already carries the name in the language the
# photographer wrote it in. extract_name_from_caption above has been
# splitting captions on " at "/" bei " since the early versions; this is the
# other half of the same split.

# Leading articles are grammar, not part of an event's name: "at THE
# Berlinale 2026". Only a leading article word is dropped, and only when
# something remains after it.
_EVENT_ARTICLES = {
    'the', 'der', 'die', 'das', 'dem', 'den', 'le', 'la', 'les', 'el',
    'los', 'las', 'il', 'lo', 'i', 'gli',
}


def camera_number(source, digits=0):
    """The trailing digits of a source file name, or '' if it has none.

    IMG_4711 -> 4711; DSC00123 -> 00123. With `digits` > 0 only the last
    that many are kept. Cameras put the counter at the END of the name, so
    this is the piece worth keeping - it is what lets someone find the raw
    file again from the Commons name.

    Lives here rather than in the rename dialog since 0.18.19, because the
    naming button needs it too and a second hand-kept copy is exactly the
    _ASSIGN_RE mistake.
    """
    base = str(source or '')
    tail = ''
    for ch in reversed(base):
        if not ch.isdigit():
            break
        tail = ch + tail
    if digits > 0:
        tail = tail[-digits:]
    return tail


def split_caption(caption):
    """(person, event) for one caption. Either half may be ''.

    "Anna Mueller at the Berlinale 2026" -> ("Anna Mueller", "Berlinale 2026")
    "Anna Mueller"                       -> ("Anna Mueller", "")
    """
    text = normalize_title_spacing(caption or '')
    if not text:
        return '', ''
    for sep in NAME_SEPARATORS:
        if sep in text:
            person, event = text.split(sep, 1)
            person, event = person.strip(), event.strip()
            head, _, rest = event.partition(' ')
            if head.lower() in _EVENT_ARTICLES and rest.strip():
                event = rest.strip()
            return person, event
    return text, ''


def pick_caption(fields, languages=()):
    """The caption to build a name from, out of a decompose_fields() dict.

    `languages` is tried in order first (the interface language, then
    English), then any caption_* there is - a photographer who captions only
    in Italian should still get names.
    """
    for code in list(languages) + ['en']:
        value = (fields.get(f'caption_{code}') or '').strip()
        if value:
            return value
    for key in sorted(fields):
        if key.startswith('caption_') and (fields[key] or '').strip():
            return fields[key].strip()
    return ''


def name_from_caption(caption, source_stem='', seq='', with_event=True,
                      digits=0):
    """Build one target filename stem from a caption. '' when there is none.

    Shape: "<person> at <event> <number>", falling back step by step -
    without an event it is "<person> <number>", and the number is the
    camera's own counter when the source name has one, else `seq`.

    The separator between person and event is the ENGLISH " at " whatever
    language the caption is in: the file name is a Commons-wide identifier,
    and Commons is English-titled by convention.
    """
    person, event = split_caption(caption)
    if not person:
        return ''
    parts = [person]
    if with_event and event:
        parts.append('at')
        parts.append(event)
    number = camera_number(source_stem, digits) or str(seq or '').strip()
    if number:
        parts.append(number)
    return normalize_title_spacing(' '.join(parts))



FORBIDDEN_TITLE_CHARS = set('#<>[]|{}')

# ── MediaWiki title normalization (0.18.19) ──────────────────────────────────
#
# Harald: "Der Benutzer sagt, er haette zu viele Leerzeichen oder sowas in den
# Dateinamen gehabt."
#
# MediaWiki does not take a title as given: Title.php::secureAndSplit()
# rewrites it first, and an upload whose name survives that rewrite CHANGED
# answers with a 'badfilename' warning. Until 0.18.18 Cammello only looked
# for ':', '/', '\' and the forbidden title characters, so a name with two
# spaces in it sailed through here and came back as a warning from the
# server - with a message that named no cause, because the server only says
# what it WOULD have stored.
#
# The rules below are not written from memory: they were read off
# pywikibot 11.7.0 (pywikibot/page/_links.py, whose own comment says "This
# code was adapted from Title.php : secureAndSplit()"). Commons itself could
# not be reached from the build sandbox to confirm them live.

# Every one of these collapses to a single plain space, and runs of them
# collapse together: ASCII space, underscore, NO-BREAK SPACE, OGHAM SPACE
# MARK, MONGOLIAN VOWEL SEPARATOR, EN QUAD..HAIR SPACE, LINE/PARAGRAPH
# SEPARATOR, NARROW NO-BREAK SPACE, MEDIUM MATHEMATICAL SPACE, IDEOGRAPHIC
# SPACE. The non-breaking one is the nasty one: it is invisible in the
# table and arrives by copy-and-paste from a press release.
_TITLE_SPACE_RE = re.compile(
    '[ _  ᠎ -     　]+')

# Removed outright rather than replaced (they are zero-width, so replacing
# them with a space would invent one).
_TITLE_DROP = ('‎', '‏')

# Percent sequences and HTML character references are refused by MediaWiki
# because a title containing them cannot be linked to round-trip.
_PERCENT_RE = re.compile('%[0-9A-Fa-f]{2}')
_ENTITY_RE = re.compile('&(?:[A-Za-z0-9\u0080-ÿ]+|#[0-9]+|#x[0-9A-Fa-f]+);')


NAME_CONNECTOR_DEFAULT = ' at '


def name_from_parts(person, event='', source_stem='', seq='',
                    connector=NAME_CONNECTOR_DEFAULT, person_first=True,
                    digits=0):
    """Build one target filename stem from the two halves (0.18.21).

    The older name_from_caption() cut the event out of the caption text,
    which only worked when the caption actually said "at". This takes the
    two halves as they are - the person from the caption, the event from
    the file's own created_during field - and joins them with whatever
    connector the user chose, in whichever order.

    Either half may be empty; with both empty the result is ''. The number
    is the camera's own counter when the source name has one, else `seq`.
    """
    person = normalize_title_spacing(person or '')
    event = normalize_title_spacing(event or '')
    if not person and not event:
        return ''
    if person and event:
        conn = connector if connector is not None else NAME_CONNECTOR_DEFAULT
        head, tail = ((person, event) if person_first else (event, person))
        core = f'{head}{conn}{tail}'
    else:
        core = person or event
    number = camera_number(source_stem, digits) or str(seq or '').strip()
    if number:
        core = f'{core} {number}'
    # NOT normalize_title_spacing: that would eat a connector made only of
    # spaces around a dash into a single space. Only the outer ends are
    # tidied, and the halves were normalized above.
    return core.strip()


def caption_languages(rows):
    """The caption languages present across `rows`, English first.

    `rows` is a list of {lang: text} dicts. Sorted so the list is stable,
    with 'en' pulled to the front because a Commons filename is English by
    convention - it is what the caller preselects.
    """
    found = set()
    for row in rows or []:
        for code, text in (row or {}).items():
            if (text or '').strip():
                found.add(code)
    ordered = sorted(found)
    if 'en' in found:
        ordered.remove('en')
        ordered.insert(0, 'en')
    return ordered


def propose_names(rows, lang='en', connector=NAME_CONNECTOR_DEFAULT,
                  person_first=True, with_event=True, digits=0, start=1):
    """The proposed base names for a whole selection (0.18.21).

    One pure function so the naming button and the rename dialog cannot
    drift apart. `rows` is a list of dicts:
        captions  {lang: text}
        event     the created_during value, '' when there is none
        source    the source file stem, for the camera's own number

    Returns a list as long as `rows`; an entry is '' when that row has no
    caption in any language and is therefore to be left alone.

    Identical names collide on Commons, so every member of a colliding set
    gets the running number - not just the second one, or the numbering
    would look arbitrary.
    """
    rows = list(rows or [])
    width = len(str(start + len(rows) - 1)) if rows else 1
    out = []
    for i, row in enumerate(rows):
        captions = row.get('captions') or {}
        caption = (captions.get(lang) or '').strip()
        if not caption:
            # The chosen language is empty for this row: any caption beats
            # no name at all, English first.
            for code in caption_languages([captions]):
                caption = (captions.get(code) or '').strip()
                if caption:
                    break
        if not caption:
            out.append('')
            continue
        # Only the PERSON half comes out of the caption. The event is the
        # file's own created_during field and nothing else (Harald's
        # decision, 0.18.21): cutting it out of the caption text only ever
        # worked when the caption happened to say "at". A file without that
        # field therefore gets a name without an event, where 0.18.19 would
        # have guessed one.
        person, _event_in_caption = split_caption(caption)
        event = (row.get('event') or '').strip() if with_event else ''
        out.append(name_from_parts(person, event, row.get('source') or '',
                                   str(start + i).zfill(width),
                                   connector=connector,
                                   person_first=person_first,
                                   digits=digits))
    named = [n for n in out if n]
    if len(set(named)) != len(named):
        seen = {}
        for name in named:
            seen[name] = seen.get(name, 0) + 1
        out = [(f'{n} {str(start + i).zfill(width)}'
                if n and seen.get(n, 0) > 1 else n)
               for i, n in enumerate(out)]
    return out


def normalize_title_spacing(name):
    """Apply MediaWiki's own whitespace rules to `name`.

    Separate from the checking half so the rename dialog can build names
    that are already normalized instead of building them and then being
    told they are wrong.
    """
    text = unicodedata.normalize('NFC', name or '')
    for ch in _TITLE_DROP:
        text = text.replace(ch, '')
    return _TITLE_SPACE_RE.sub(' ', text).strip()


def title_changes(name):
    """What MediaWiki would change about `name`, in plain words.

    -> list of strings, empty when the name survives untouched. Used for
    the report the rename button shows and for the upload's error message,
    so both say the same thing.
    """
    out = []
    raw = name or ''
    if raw != unicodedata.normalize('NFC', raw):
        out.append('combining accents are rewritten (NFC)')
    if any(ch in raw for ch in _TITLE_DROP):
        out.append('writing-direction marks are removed')
    if '_' in raw:
        out.append('underscores become spaces')
    body = _TITLE_SPACE_RE.sub(' ', raw)
    if '  ' in raw.replace('_', ' '):
        out.append('repeated spaces collapse into one')
    if raw != raw.strip():
        out.append('leading or trailing spaces are dropped')
    if any(ch in raw for ch in
           '  ᠎       '
           '      　'):
        out.append('non-breaking and typographic spaces become plain spaces')
    stem = os.path.splitext(body.strip())[0]
    if stem and stem[0].islower():
        out.append(f'the first letter is capitalized ("{stem[0]}" → '
                   f'"{stem[0].upper()}")')
    return out

# Characters MediaWiki forbids in FILE names specifically ($wgIllegalFileChars,
# default ':', '/', '\'). They are legal in ordinary page titles - which is why
# they are easy to miss - but an upload silently REPLACES each of them with
# '-' and answers with a 'badfilename' warning. Catching them here, before any
# request, turns 129 cryptic per-file errors into one clear message per row
# (real case: a Wikimania batch named "<session title>: <n>.JPG", 2026-07).
ILLEGAL_FILENAME_CHARS = set(':/\\')

_CHAR_NAMES = {':': 'colon', '/': 'slash', '\\': 'backslash'}


def _describe_chars(chars):
    """"':' (colon), '/' (slash)" - repr plus a human name where we have one."""
    out = []
    for c in sorted(chars):
        name = _CHAR_NAMES.get(c)
        out.append(f'{c!r} ({name})' if name else repr(c))
    return ', '.join(out)


def normalize_commons_filename(target, source_path):
    """Build the target filename for the upload to Commons.

    - strips a leading 'File:'/'Datei:' prefix
    - ensures an (image) extension is present; if missing, the source file's
      extension is appended
    - rejects empty names, overly long names and invalid characters with a
      ValueError (reported by the worker as a meaningful error)

    Returns: the cleaned filename (without 'File:' prefix).
    """
    name = (target or '').strip()

    # Remove namespace prefix (case-insensitive).
    for prefix in ('file:', 'datei:'):
        if name.lower().startswith(prefix):
            name = name[len(prefix):].strip()
            break

    if not name:
        name = os.path.basename(source_path).strip()
    if not name:
        raise ValueError('Empty target filename.')

    # 0.18.19: do MediaWiki's whitespace rewriting HERE instead of letting
    # the server do it and answer with a 'badfilename' warning. These are
    # not errors the user has to fix - "Anna  Mueller.jpg" is obviously
    # meant to be "Anna Mueller.jpg" - so the name is corrected silently
    # and the upload goes through under the name the server would have
    # chosen anyway.
    name = normalize_title_spacing(name)
    if not name:
        raise ValueError('Empty target filename.')

    # Ensure the extension.
    src_ext = os.path.splitext(source_path)[1]
    stem, ext = os.path.splitext(name)
    if ext.lower() not in IMAGE_EXTS:
        if not src_ext:
            raise ValueError('Source file has no extension; please specify an '
                             'extension in the target filename.')
        name = name + src_ext
    elif stem != stem.rstrip():
        # "Anna Mueller .jpg": MediaWiki would keep that space (it is not at
        # the END of the title), so this one is Cammello's own tidy-up, not
        # a server rule. Nobody means it.
        name = stem.rstrip() + ext

    bad_file = sorted({c for c in name if c in ILLEGAL_FILENAME_CHARS})
    if bad_file:
        # Named individually: the whole point is that the user learns WHICH
        # character broke the name (they are legal in local file names on
        # Linux, so the batch looks fine on disk).
        raise ValueError(
            'Illegal character(s) in target filename: '
            + _describe_chars(bad_file)
            + '. MediaWiki forbids these in file names and would silently '
            'replace each with "-". Please rename (e.g. ":" \u2192 " \u2013").'
        )

    bad = sorted({c for c in name if c in FORBIDDEN_TITLE_CHARS or ord(c) < 32})
    if bad:
        raise ValueError(
            'Invalid characters in target filename: '
            + ' '.join(repr(b) for b in bad)
            + ' (not allowed: # < > [ ] | { } and control characters).'
        )

    # The three MediaWiki refuses outright rather than rewriting. Each gets
    # its own message: "invalid title" from the server says nothing about
    # which of them it was.
    if '�' in name:
        raise ValueError('Target filename contains the Unicode replacement '
                         'character - the name was probably read with the '
                         'wrong encoding somewhere.')
    if _PERCENT_RE.search(name):
        raise ValueError(
            'Target filename contains a percent sequence (e.g. "%20"). '
            'MediaWiki refuses these because such a title cannot be linked '
            'to reliably. Please write the character itself.')
    if _ENTITY_RE.search(name):
        raise ValueError(
            'Target filename contains an HTML character reference (e.g. '
            '"&amp;"). MediaWiki refuses these. Please write the character '
            'itself.')
    if '~~~' in name:
        raise ValueError('Target filename contains "~~~", which MediaWiki '
                         'reserves for signatures.')
    stem = os.path.splitext(name)[0]
    if stem in ('.', '..') or stem.startswith(('./', '../')) \
            or '/./' in stem or '/../' in stem \
            or stem.endswith(('/.', '/..')):
        raise ValueError('Target filename looks like a relative path '
                         '("." / ".."), which MediaWiki refuses.')

    # MediaWiki capitalizes the first letter of a title, so doing it here
    # keeps the uploaded name and the requested name identical.
    if name[:1].islower():
        name = name[0].upper() + name[1:]

    if len(name.encode('utf-8')) > 240:
        raise ValueError('Target filename too long (max. ~240 bytes).')

    return name


# ── MediaWiki API ──────────────────────────────────────────────────────────────


# 'depicts is mandatory' can be waived per file with one of these override
# values; when the upload lands in a WikiPortraits context, the matching
# maintenance category is added (requested 2026-07-15).
DEPICTS_OVERRIDES = {
    'no_item': 'WikiPortraits photos needing Wikidata item',
    'not_applicable': 'WikiPortraits photos without identifiable person',
    'unidentified': 'WikiPortraits photos needing identification',
}

# Backwards compatibility: 'no_person' was the internal value for 'Not
# applicable' up to 0.11.0. It was named for people only, but the option
# also covers buildings, landscapes etc. - so the value is now
# 'not_applicable'. Old file descriptions carrying 'no_person' still map to
# the same category.
_OVERRIDE_ALIASES = {'no_person': 'not_applicable'}


def canonical_override(value):
    """Normalize a depicts_override value, mapping legacy aliases."""
    v = (value or '').strip().lower()
    return _OVERRIDE_ALIASES.get(v, v)


def wikiportraits_maintenance_category(sd, context_text):
    """'[[Category:...]]' for the file's depicts override, or None.

    Applied only when the upload is in a WikiPortraits context: the assembled
    categories or templates mention WikiPortraits (a {{WikiPortraits ...}}
    template or a WikiPortraits (sub)category)."""
    override = canonical_override(sd.get('depicts_override'))
    cat = DEPICTS_OVERRIDES.get(override)
    if not cat:
        return None
    if 'wikiportraits' not in (context_text or '').lower():
        return None
    return f'[[Category:{cat}]]'


_CATEGORY_RE = re.compile(r'\[\[\s*Category:\s*([^\]|]+?)\s*\]\]', re.IGNORECASE)


def normalize_category_name(name):
    """Turn a user-entered category into a bare name (no [[Category:]] wrapper)."""
    name = (name or '').strip()
    name = re.sub(r'^\[\[\s*', '', name)
    name = re.sub(r'\s*\]\]$', '', name)
    name = re.sub(r'^\s*Category:\s*', '', name, flags=re.IGNORECASE)
    return name.strip()


def split_categories(text):
    """Return (list_of_bare_category_names, text_without_category_links).

    Lines that consist only of category links are dropped entirely; lines that
    mix category links with other content keep the other content.
    """
    cats = [m.group(1).strip() for m in _CATEGORY_RE.finditer(text or '')]
    kept = []
    for line in (text or '').split('\n'):
        had_cat = bool(_CATEGORY_RE.search(line))
        cleaned = _CATEGORY_RE.sub('', line)
        if had_cat and not cleaned.strip():
            continue  # line was purely category link(s)
        kept.append(cleaned)
    rest = re.sub(r'\n{3,}', '\n\n', '\n'.join(kept)).strip()
    return cats, rest



# 0.18.1: built FROM SD_KEYS instead of repeating them. The list here had
# already drifted - coordinates and object_coordinates were missing, so
# those lines were pulled out as structured data AND left behind as free
# text, and every round trip through the editor duplicated them. The music
# fields would have inherited the same fault the moment they became
# SD_KEYS; test_music_0181 holds the round trip.
_ASSIGN_RE = re.compile(
    r'^\s*(?:caption_' + _LANG_CODE + r'|alt_' + _LANG_CODE + r'|'
    + '|'.join(re.escape(k) for k in SD_KEYS) + r')\s*=',
    re.IGNORECASE)


def leftover_text(text):
    """Return all lines that are NOT key=value assignments. Comment lines (#) and
    wikitext are kept, so comments survive a round-trip through the structured
    editor (they are only stripped at upload time)."""
    return '\n'.join(l for l in text.split('\n') if not _ASSIGN_RE.match(l)).strip()


# {{en|1=...}} / {{de|1=...}} description templates for the Information box.
# NOTE: the non-greedy match stops at the first '}}', so a value containing a
# nested template would be cut short; such lines are left in the extra text.
_LANG_TMPL_RE = re.compile(
    r'\{\{\s*(' + _LANG_CODE + r')\s*\|\s*1\s*=\s*'
    r'((?:[^{}]|\[\[[^\]]*\]\])*?)\s*\}\}',
    re.DOTALL)


def split_lang_templates(text):
    """Extract simple {{lang|1=value}} templates from text.

    Returns (infos, remaining) where infos is {lang: value}. Only templates
    whose value contains no nested template braces are extracted; anything
    else stays in the remaining text untouched.
    """
    infos = {}

    def _take(m):
        infos[m.group(1)] = m.group(2).strip()
        return ''

    remaining = _LANG_TMPL_RE.sub(_take, text or '')
    # Collapse blank lines left behind by removed templates.
    remaining = re.sub(r'\n{3,}', '\n\n', remaining).strip()
    return infos, remaining


# ── Merging the base description with a per-file description ────────────────────
#
# Up to 0.9.12 the two texts were simply concatenated and parsed as one blob,
# with two consequences the user could not see:
#   * for creator/copyright/license/depicts/created_during/gallery_suffix,
#     extract_structured_data() takes the FIRST occurrence, so the base silently
#     won and a per-file value was dropped - while for caption_XX the LAST one
#     wins, so there the file won. Inconsistent.
#   * the preview column assembled the text differently from the upload path.
# merge_descriptions() is now the single source of truth for both.

# Keys where the per-file value replaces the base value.
_OVERRIDE_KEYS = ['creator', 'copyright', 'license', 'created_during']
# Keys only ever taken from the base description.
_BASE_ONLY_KEYS = ['gallery_suffix']
# Keys whose values are merged into one list.
_MERGE_KEYS = ['depicts']


def _split_qids(value):
    """Split a multi-value field. ';' is the separator, ',' is tolerated."""
    return [p.strip() for p in re.split(r'[;,]', value or '') if p.strip()]


def merge_descriptions(base_text, file_text):
    """Combine base and per-file description into one description_all text.

    Rules (agreed with the user):
      * depicts        - base and file are merged, duplicates removed, order kept
      * caption_XX     - the file overrides the base
      * creator, copyright, license, created_during - the file overrides the base
                         (NOT merged: the worker writes these as a single QID per
                         property, so "Q1;Q2" would be an invalid QID)
      * gallery_suffix - base only; a per-file value is ignored
      * free wikitext  - base text first, then the file text

    Returns (merged_text, warnings): warnings are human-readable strings about
    values that were overridden or dropped.
    """
    base_sd, base_rest = extract_structured_data(base_text or '')
    file_sd, file_rest = extract_structured_data(file_text or '')
    warnings = []

    merged = dict(base_sd)

    for key, val in file_sd.items():
        if key in _BASE_ONLY_KEYS:
            if val.strip():
                warnings.append(
                    f'"{key}" belongs in the base description; the per-file '
                    f'value "{val}" is ignored.')
            continue

        if key in _MERGE_KEYS:
            out, seen = [], set()
            for qid in _split_qids(base_sd.get(key, '')) + _split_qids(val):
                if qid not in seen:
                    out.append(qid)
                    seen.add(qid)
            if out:
                merged[key] = '; '.join(out)
            continue

        # caption_XX and the override keys: the file wins.
        old = base_sd.get(key)
        if old is not None and old.strip() != val.strip():
            warnings.append(
                f'"{key}": the per-file value overrides the base '
                f'("{old}" -> "{val}").')
        merged[key] = val

    # Assemble in a stable order: captions (by language), then the SD keys.
    lines = []
    for key in sorted(k for k in merged if k.startswith('caption_')):
        lines.append(f'{key}={merged[key]}')
    for key in SD_KEYS:
        if merged.get(key, '').strip():
            lines.append(f'{key}={merged[key]}')

    parts = []
    if lines:
        parts.append('\n'.join(lines))
    if (base_rest or '').strip():
        parts.append(base_rest.strip())
    if (file_rest or '').strip():
        parts.append(file_rest.strip())
    return '\n'.join(parts), warnings


# ── Field-level diff/apply for the multi-select editor (0.11.0) ───────────────
#
# A file description is decomposed into named FIELDS so the multi-select
# editor can propagate exactly what the user changed and nothing else:
#   * assignment fields:  caption_xx=, depicts=, depicts_override=, ... (key)
#   * info fields:         the {{lang|1=...}} Information templates (info:lang)
#   * 'extra':             the remaining free wikitext (comments etc.)
# Categories are a separate list, replaced only when they change. This covers
# free-text edits (Information templates and expert/extra text), which the
# earlier key=value-only diff missed.

_ANY_ASSIGN_RE = re.compile(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$')


def assignment_map(text):
    """{key_lower: value} of every recognized key=value line (captions
    included). Used by the upload validation."""
    out = {}
    for line in (text or '').splitlines():
        if line.lstrip().startswith('#'):
            continue
        m = _ANY_ASSIGN_RE.match(line)
        if m and _ASSIGN_RE.match(line):
            out[m.group(1).lower()] = m.group(2).strip()
    return out


def decompose_fields(text):
    """(fields, categories) for a description.

    fields maps a field id to its value:
      * '<key>'        a recognized key=value assignment line
      * 'info:<lang>'  a {{lang|1=value}} Information template
      * 'extra'        the remaining free wikitext (only if non-empty)
    categories is the list of bare [[Category:]] names.
    """
    text = text or ''
    cats = split_categories(text)[0]
    fields = assignment_map(text)
    non_assign = _CATEGORY_RE.sub('', leftover_text(text))
    infos, remaining = split_lang_templates(non_assign)
    for lang, val in infos.items():
        fields[f'info:{lang}'] = val
    remaining = '\n'.join(l for l in remaining.splitlines()
                          if not l.lstrip().startswith('#')).strip()
    if remaining:
        fields['extra'] = remaining
    return fields, cats


def diff_fields(old_text, new_text):
    """(changes, categories_or_None): what changed from old to new.

    changes maps field id -> new value, or -> None for a removed field.
    categories is the new list only when it differs, else None.
    """
    old_f, old_c = decompose_fields(old_text)
    new_f, new_c = decompose_fields(new_text)
    changes = {fid: val for fid, val in new_f.items() if old_f.get(fid) != val}
    for fid in old_f:
        if fid not in new_f:
            changes[fid] = None
    cats = (new_c if [c.strip() for c in new_c] != [c.strip() for c in old_c]
            else None)
    return changes, cats


def _render_field(fid, value):
    if fid.startswith('info:'):
        return f'{{{{{fid[5:]}|1={value}}}}}'
    if fid == 'extra':
        return value
    return f'{fid}={value}'


def apply_field_changes(text, changes, categories=None):
    """Apply a field-level diff (from diff_fields) to ANOTHER file.

    Fields not mentioned in changes are preserved verbatim, including this
    file's own captions, info templates and free text. categories (a list)
    replaces all category links when given; None keeps this file's own.
    Re-serialized in the same order the structured editor's assemble() uses,
    so a file edited here and one edited directly look identical.
    """
    merged, own_cats = decompose_fields(text)
    for fid, val in (changes or {}).items():
        if val in (None, ''):
            merged.pop(fid, None)
        else:
            merged[fid] = val
    cats = categories if categories is not None else own_cats

    assign = {k: v for k, v in merged.items()
              if ':' not in k and k != 'extra'}
    infos = {k: v for k, v in merged.items() if k.startswith('info:')}
    cap_keys = sorted(k for k in assign if k.startswith('caption_'))
    other_keys = [k for k in assign if not k.startswith('caption_')]
    lines = [_render_field(k, assign[k]) for k in cap_keys + other_keys]
    body = '\n'.join(lines)
    info_block = '\n'.join(_render_field(k, infos[k]) for k in sorted(infos))
    if info_block:
        body = (body + '\n\n' + info_block).strip()
    if merged.get('extra'):
        body = (body + '\n\n' + merged['extra']).strip()
    cat_block = '\n'.join(f'[[Category:{c.strip()}]]'
                          for c in cats if c and c.strip())
    if cat_block:
        body = (body + '\n' + cat_block).strip()
    return body
