"""IPTC metadata support (read/write via pyexiv2) and MediaWiki mapping.

pyexiv2 is an OPTIONAL dependency: if it is missing, available() returns False
and the IPTC tab simply does not appear - the MediaWiki side of Cammello is
not affected in any way. All pyexiv2 access goes through this module.

Design decisions (provisional, agreed defaults - easy to change):
  * Writing goes to COPIES in an export folder by default; writing into the
    original files is possible but must be enabled explicitly per run.
  * The IPTC envelope character set is marked as UTF-8 ('\\x1b%G'), which is
    what stock agencies expect for non-ASCII captions (verified by roundtrip,
    not against agency documentation - their specs are not public).
"""
import os
import re
import shutil

from .constants import *
from . import native_exec

try:
    import pyexiv2
    _PYEXIV2_ERROR = None
except Exception as e:          # ImportError or a broken native library
    pyexiv2 = None
    _PYEXIV2_ERROR = str(e)

# IPTC IIM: envelope character set marker for UTF-8 (ESC % G).
_UTF8_MARKER = '\x1b%G'

# The editable fields, in UI order: (storage key, exiv2 key, label, multi-value)
IPTC_FIELDS = [
    ('object_name',  'Iptc.Application2.ObjectName',    'Title / object name', False),
    ('headline',     'Iptc.Application2.Headline',      'Headline',            False),
    ('caption',      'Iptc.Application2.Caption',       'Caption / description', False),
    ('keywords',     'Iptc.Application2.Keywords',      'Keywords',            True),
    ('byline',       'Iptc.Application2.Byline',        'Creator (by-line)',   False),
    ('copyright',    'Iptc.Application2.Copyright',     'Copyright notice',    False),
    ('credit',       'Iptc.Application2.Credit',        'Credit',              False),
    ('source',       'Iptc.Application2.Source',        'Source',              False),
    ('city',         'Iptc.Application2.City',          'City',                False),
    ('province',     'Iptc.Application2.ProvinceState', 'Province / state',    False),
    ('country',      'Iptc.Application2.CountryName',   'Country',             False),
    ('date_created', 'Iptc.Application2.DateCreated',   'Date created (YYYY-MM-DD)', False),
]

_KEY_TO_EXIV = {k: e for k, e, _l, _m in IPTC_FIELDS}
_MULTI_KEYS = {k for k, _e, _l, m in IPTC_FIELDS if m}

# Values are edited as text; multi-value fields use ';' (',' tolerated on read,
# same convention as the SDC fields).
_SPLIT_RE = re.compile(r'[;,]')


def available():
    """True if pyexiv2 could be imported."""
    return pyexiv2 is not None


def unavailable_reason():
    return _PYEXIV2_ERROR or 'pyexiv2 is not installed'


def split_multi(text):
    return [p.strip() for p in _SPLIT_RE.split(text or '') if p.strip()]


def read_iptc(filepath):
    """Read the supported IPTC fields from a file.

    Returns a dict {storage_key: str}; multi-value fields are joined with '; '.
    Unknown/other IPTC tags in the file are left alone (and untouched on write).
    """
    if pyexiv2 is None:
        raise RuntimeError(unavailable_reason())
    raw = native_exec.run(_read_iptc_raw, filepath)
    out = {}
    for key, exiv_key, _label, multi in IPTC_FIELDS:
        val = raw.get(exiv_key)
        if val is None:
            continue
        if multi:
            if isinstance(val, str):
                val = [val]
            out[key] = '; '.join(v for v in val if v)
        else:
            # exiv2 may hand back a list for repeated single-value tags; take
            # the first and mention nothing - repeats are junk metadata.
            if isinstance(val, list):
                val = val[0] if val else ''
            out[key] = val
    return out


def write_iptc(filepath, data, target_path=None):
    """Write the supported IPTC fields.

    data: {storage_key: str} - empty strings DELETE the tag.
    target_path: if given and different from filepath, the file is COPIED there
    first and the copy is modified; the original is never touched. Returns the
    path that was actually written.
    """
    if pyexiv2 is None:
        raise RuntimeError(unavailable_reason())
    path = filepath
    if target_path and os.path.abspath(target_path) != os.path.abspath(filepath):
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        shutil.copy2(filepath, target_path)
        path = target_path

    payload = {'Iptc.Envelope.CharacterSet': _UTF8_MARKER}
    for key, exiv_key, _label, multi in IPTC_FIELDS:
        if key not in data:
            continue
        val = (data.get(key) or '').strip()
        if not val:
            payload[exiv_key] = None        # pyexiv2: None deletes the tag
        elif multi:
            payload[exiv_key] = split_multi(val)
        else:
            payload[exiv_key] = val

    native_exec.run(_modify_iptc_raw, path, payload)
    return path


def _read_iptc_raw(filepath):
    img = pyexiv2.Image(filepath)
    try:
        return img.read_iptc() or {}
    finally:
        img.close()


def _modify_iptc_raw(path, payload):
    img = pyexiv2.Image(path)
    try:
        img.modify_iptc(payload)
    finally:
        img.close()


# ── MediaWiki -> IPTC mapping ────────────────────────────────────────────────
#
# Conservative on purpose: only fields whose meaning translates without
# guessing. QIDs (creator=Q640 etc.) are NOT resolved to labels here - that
# would need a network call; the by-line comes from the Information |author=
# value instead, which is already plain text.

_CATEGORY_RE = re.compile(r'\[\[Category:([^\]|]+)(?:\|[^\]]*)?\]\]')
# Categories that describe the upload, not the picture.
_MAINTENANCE_CATEGORIES = {'Uploaded with Cammello'}


def mw_to_iptc(merged_description, author='', date='', target_filename='',
               caption_langs=('de', 'en')):
    """Derive IPTC fields from a file's merged description_all text.

    Mapping:
      caption_XX   -> caption (first language found in caption_langs, then any)
      [[Category]] -> keywords (maintenance categories dropped)
      author       -> byline           (Information |author=, plain text)
      date         -> date_created     (leading YYYY-MM-DD of the Date column)
      target file  -> object_name      (filename without extension)
    Deliberately NOT mapped: creator/copyright/license QIDs (labels would need
    a Wikidata lookup), free wikitext (markup, not caption text).
    """
    from .sdc import extract_structured_data
    sd, rest = extract_structured_data(merged_description or '')

    out = {}
    caption = ''
    for lang in caption_langs:
        caption = sd.get(f'caption_{lang}', '')
        if caption:
            break
    if not caption:
        for key in sorted(sd):
            if key.startswith('caption_') and sd[key]:
                caption = sd[key]
                break
    if caption:
        out['caption'] = caption
        out['headline'] = caption

    cats = [c.strip() for c in _CATEGORY_RE.findall(rest or '')
            if c.strip() and c.strip() not in _MAINTENANCE_CATEGORIES]
    if cats:
        out['keywords'] = '; '.join(dict.fromkeys(cats))

    if author:
        out['byline'] = author
    m = re.match(r'(\d{4}-\d{2}-\d{2})', (date or '').strip())
    if m:
        out['date_created'] = m.group(1)
    if target_filename:
        out['object_name'] = os.path.splitext(target_filename)[0]
    return out


def iptc_to_caption_line(iptc_data, lang):
    """IPTC -> MediaWiki: the caption as a description_all line, or ''."""
    caption = (iptc_data.get('caption') or '').strip()
    if not caption or not lang:
        return ''
    return f'caption_{lang}={caption}'
