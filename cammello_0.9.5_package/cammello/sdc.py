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


def extract_structured_data(text):
    """Extract key=value lines from description_all text.
    Lines starting with # are treated as comments and removed.
    Keys are matched case-insensitively (license= and LICENSE= are equivalent)."""
    sd = {}
    # Remove comment lines (starting with #)
    text = re.sub(r'^#[^\n]*\n?', '', text, flags=re.MULTILINE)
    result = text

    # Dynamically extract all caption_XX= lines (any language code)
    for m in re.finditer(r'(?:^|\n)caption_([a-z]{2,3})=([^\n]+)',
                         result, flags=re.IGNORECASE):
        lang = m.group(1).lower()
        val = m.group(2).strip()
        sd['caption_' + lang] = val
    # Remove all matched caption_XX= lines from result
    result = re.sub(r'\ncaption_[a-z]{2,3}=[^\n]+', '', result, flags=re.IGNORECASE)
    result = re.sub(r'^caption_[a-z]{2,3}=[^\n]+\n?', '', result,
                    flags=re.MULTILINE | re.IGNORECASE)

    for key in SD_KEYS:
        # Match at start of string
        m = re.match(rf'^{key}=([^\n]+)', result, flags=re.IGNORECASE)
        if not m:
            # Match after newline
            m = re.search(rf'\n{key}=([^\n]+)', result, flags=re.IGNORECASE)
        if m:
            sd[key] = m.group(1).strip()
            result = re.sub(rf'\n{key}=[^\n]+', '', result, flags=re.IGNORECASE)
            result = re.sub(rf'^{key}=[^\n]+\n?', '', result,
                            flags=re.MULTILINE | re.IGNORECASE)

    return sd, result.strip()


# Keys that look like a structured-data tag when they appear at the start of a line.

_LINT_KEYS_RE = (r'(?:creator|copyright|license|depicts|created_during|'
                 r'gallery_suffix|caption_[a-z]{2,3})')


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
    r'^\s*(?:caption_[a-z]{2,3}|creator|copyright|license|depicts|gallery_suffix)\s*=',
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
