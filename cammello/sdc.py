"""Structured-data (SDC) and wikitext text helpers (no GUI)."""
import re
import os
from .constants import *


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
    for m in re.finditer(r'(?:^|\n)caption_([a-z]{2,3})=([^\n]+)',
                         result, flags=re.IGNORECASE):
        lang = m.group(1).lower()
        val = m.group(2).strip()
        key = 'caption_' + lang
        if logger and key in sd and sd[key] != val:
            logger.info('%s: per-file value overrides the base value '
                        '("%s" -> "%s").', key, sd[key], val)
        sd[key] = val
    # Remove all matched caption_XX= lines from result
    result = re.sub(r'\ncaption_[a-z]{2,3}=[^\n]+', '', result, flags=re.IGNORECASE)
    result = re.sub(r'^caption_[a-z]{2,3}=[^\n]+\n?', '', result,
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

_LINT_KEYS_RE = (r'(?:creator|copyright|license|depicts|depicts_override|'
                 r'created_during|gallery_suffix|caption_[a-z]{2,3})')


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



FORBIDDEN_TITLE_CHARS = set('#<>[]|{}')


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

    # Ensure the extension.
    src_ext = os.path.splitext(source_path)[1]
    _, ext = os.path.splitext(name)
    if ext.lower() not in IMAGE_EXTS:
        if not src_ext:
            raise ValueError('Source file has no extension; please specify an '
                             'extension in the target filename.')
        name = name + src_ext

    bad = sorted({c for c in name if c in FORBIDDEN_TITLE_CHARS or ord(c) < 32})
    if bad:
        raise ValueError(
            'Invalid characters in target filename: '
            + ' '.join(repr(b) for b in bad)
            + ' (not allowed: # < > [ ] | { } and control characters).'
        )

    if len(name.encode('utf-8')) > 240:
        raise ValueError('Target filename too long (max. ~240 bytes).')

    return name


# ── MediaWiki API ──────────────────────────────────────────────────────────────


# 'depicts is mandatory' can be waived per file with one of these override
# values; when the upload lands in a WikiPortraits context, the matching
# maintenance category is added (requested 2026-07-15).
DEPICTS_OVERRIDES = {
    'no_item': 'WikiPortraits photos needing Wikidata item',
    'no_person': 'WikiPortraits photos without identifiable person',
    'unidentified': 'WikiPortraits photos needing identification',
}


def wikiportraits_maintenance_category(sd, context_text):
    """'[[Category:...]]' for the file's depicts override, or None.

    Applied only when the upload is in a WikiPortraits context: the assembled
    categories or templates mention WikiPortraits (a {{WikiPortraits ...}}
    template or a WikiPortraits (sub)category)."""
    override = (sd.get('depicts_override') or '').strip().lower()
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



_ASSIGN_RE = re.compile(
    r'^\s*(?:caption_[a-z]{2,3}|creator|copyright|license|depicts|'
    r'depicts_override|created_during|gallery_suffix)\s*=',
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
    r'\{\{\s*([a-z]{2,3})\s*\|\s*1\s*=\s*((?:[^{}]|\[\[[^\]]*\]\])*?)\s*\}\}',
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
