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
import logging
import os
import re
import shutil

from .constants import *
from . import native_exec
from . import native_ops

# RAW/DNG extensions exiv2 must never open (its parser has crashed on real
# camera files). Kept in sync with previews._RAW_EXTS by test_iptc.
RAW_EXTS = {'.cr3', '.cr2', '.crw', '.nef', '.nrw', '.arw', '.raf',
            '.rw2', '.orf', '.pef', '.srw', '.dng', '.raw', '.x3f'}

# Minimal valid XMP sidecar (same shape culling.py writes).
XMP_SKELETON = ('<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
                '<x:xmpmeta xmlns:x="adobe:ns:meta/">'
                '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
                '<rdf:Description rdf:about=""/></rdf:RDF></x:xmpmeta>\n'
                '<?xpacket end="w"?>')

# 0.12.9: the main process no longer IMPORTS pyexiv2 - it only checks that
# the module exists. Since 0.12.6 every real exiv2 call runs in the helper
# process (native_exec/native_ops); importing the module here still loaded
# the crash-prone native library into the GUI process, which is exactly what
# that architecture exists to avoid - and it cost ~0.2 s at startup.
# Trade-off, stated honestly: find_spec proves the module is installed, not
# that its native library loads. A broken installation now surfaces at the
# first metadata access (as a helper-process error naming the module)
# instead of at startup. `pyexiv2` stays as a module attribute because
# read_iptc/write_iptc guard on `pyexiv2 is None`; it is truthy when the
# module exists but is NOT the imported module.
import importlib.util as _ilu
if _ilu.find_spec('pyexiv2') is not None:
    pyexiv2 = True              # sentinel: installed; real import is in the child
    _PYEXIV2_ERROR = None
else:
    pyexiv2 = None
    _PYEXIV2_ERROR = 'pyexiv2 is not installed'

# IPTC IIM: envelope character set marker for UTF-8 (ESC % G).
_UTF8_MARKER = '\x1b%G'

# The per-image editable IIM fields, in UI order:
#   (storage key, exiv2 key, label, multi-value)
# Creator / copyright / credit / contact moved to the CONSTANT block below
# (same for every image, edited in Settings); "Source" was dropped.
IPTC_FIELDS = [
    ('object_name',  'Iptc.Application2.ObjectName',    'Title / object name', False),
    ('headline',     'Iptc.Application2.Headline',      'Headline',            False),
    ('caption',      'Iptc.Application2.Caption',       'Caption / description', False),
    ('keywords',     'Iptc.Application2.Keywords',      'Keywords',            True),
    ('city',         'Iptc.Application2.City',          'City',                False),
    ('province',     'Iptc.Application2.ProvinceState', 'Province / state',    False),
    ('country',      'Iptc.Application2.CountryName',   'Country',             False),
    ('date_created', 'Iptc.Application2.DateCreated',   'Date created (YYYY-MM-DD)', False),
]

_KEY_TO_EXIV = {k: e for k, e, _l, _m in IPTC_FIELDS}
_MULTI_KEYS = {k for k, _e, _l, m in IPTC_FIELDS if m}

# XMP-backed per-image fields (not classic IIM):
#   * Person shown -> Xmp.iptcExt.PersonInImage, an unordered array ("bag");
#     ';'-separated in the editor. What Photo Mechanic / Lightroom write.
#   * Event        -> Xmp.iptcExt.Event, a language-alternative text ("langalt");
#     single value. Photo Mechanic's "Event" field; the natural source for the
#     Wikidata "created during" (P10408) statement.
PERSON_KEY = 'person_shown'
PERSON_XMP = 'Xmp.iptcExt.PersonInImage'
EVENT_KEY = 'event'
EVENT_XMP = 'Xmp.iptcExt.Event'

# Fields shown in the per-image editor = IIM fields + the two XMP fields.
EDITOR_FIELDS = IPTC_FIELDS + [
    (PERSON_KEY, PERSON_XMP, 'Person shown', True),
    (EVENT_KEY,  EVENT_XMP,  'Event',        False),
]

# Constant block: creator / rights / contact, identical for every processed
# image, edited in Settings (persisted) - NOT derived from the MediaWiki data.
# (storage key, exiv2 key, label)  -- kinds are set in _FIELD_KIND below.
CONSTANT_FIELDS = [
    ('byline',    'Iptc.Application2.Byline',    'Creator (by-line)'),
    ('copyright', 'Iptc.Application2.Copyright', 'Copyright notice'),
    ('credit',    'Iptc.Application2.Credit',    'Credit'),
    ('ci_email',  'Xmp.iptc.CiEmailWork',        'E-mail'),
    ('ci_tel',    'Xmp.iptc.CiTelWork',          'Phone'),
    ('ci_url',    'Xmp.iptc.CiUrlWork',          'Website'),
    ('ci_street', 'Xmp.iptc.CiAdrExtadr',        'Street'),
    ('ci_city',   'Xmp.iptc.CiAdrCity',          'City'),
    ('ci_pcode',  'Xmp.iptc.CiAdrPcode',         'Postal code'),
    ('ci_ctry',   'Xmp.iptc.CiAdrCtry',          'Country'),
]

# Storage kind per field key, driving how read_iptc / write_iptc handle it:
#   'iim'     - classic IPTC IIM (Iptc.Application2.*), via modify_iptc
#   'iim_multi' - IIM repeatable (keywords)
#   'bag'     - XMP unordered array (person shown)
#   'langalt' - XMP language-alternative text (event)
#   'text'    - XMP simple text (contact fields)
_FIELD_EXIV = {k: e for k, e, *_ in
               (IPTC_FIELDS + CONSTANT_FIELDS
                + [(PERSON_KEY, PERSON_XMP, ''), (EVENT_KEY, EVENT_XMP, '')])}
_FIELD_KIND = {}
for _k, _e, _l, _m in IPTC_FIELDS:
    _FIELD_KIND[_k] = 'iim_multi' if _m else 'iim'
_FIELD_KIND[PERSON_KEY] = 'bag'
_FIELD_KIND[EVENT_KEY] = 'langalt'
for _k, _e, _l in CONSTANT_FIELDS:
    _FIELD_KIND[_k] = 'text' if _e.startswith('Xmp.') else 'iim'

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


def _langalt_text(val):
    """Extract the text from an XMP lang-alt value (dict {'lang=...': text})
    or a plain string; prefer x-default, else the first entry."""
    if val is None:
        return ''
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        for k, v in val.items():
            if 'x-default' in k:
                return v
        return next(iter(val.values()), '')
    if isinstance(val, list):
        return val[0] if val else ''
    return str(val)


def _sidecar_read_xmp(path):
    """Read PersonInImage (bag) and Event (lang-alt) from an .xmp sidecar in
    PURE PYTHON (0.12.6 fix).

    exiv2 crashes on Windows even when merely OPENING a sidecar, so the two
    XMP fields Cammello cares about are parsed from the XML text directly.
    Returns a dict shaped like pyexiv2's read_xmp() for these keys.
    """
    try:
        text = open(path, 'r', encoding='utf-8', errors='replace').read()
    except OSError:
        return {}
    out = {}
    # PersonInImage: an rdf:Bag of rdf:li elements.
    m = re.search(r'<Iptc4xmpExt:PersonInImage>(.*?)</Iptc4xmpExt:PersonInImage>',
                  text, re.S)
    if m:
        names = re.findall(r'<rdf:li[^>]*>(.*?)</rdf:li>', m.group(1), re.S)
        names = [n.strip() for n in names if n.strip()]
        if names:
            out[PERSON_XMP] = names
    # Event: lang-alt (rdf:Alt with xml:lang) or a plain attribute.
    m = re.search(r'<Iptc4xmpExt:Event>(.*?)</Iptc4xmpExt:Event>', text, re.S)
    if m:
        li = re.search(r'<rdf:li[^>]*>(.*?)</rdf:li>', m.group(1), re.S)
        val = (li.group(1) if li else m.group(1)).strip()
        if val:
            out[EVENT_XMP] = {'lang="x-default"': val}
    else:
        m = re.search(r'Iptc4xmpExt:Event\s*=\s*"([^"]*)"', text)
        if m and m.group(1).strip():
            out[EVENT_XMP] = m.group(1).strip()
    return out


def _sidecar_write_xmp(path, payload):
    """Write PersonInImage / Event into an .xmp sidecar in PURE PYTHON.

    Counterpart to _sidecar_read_xmp - same reason: exiv2 crashes on
    sidecars under Windows. Only the two keys Cammello manages are touched;
    everything else in the packet is preserved.
    """
    if os.path.exists(path):
        text = open(path, 'r', encoding='utf-8', errors='replace').read()
    else:
        text = XMP_SKELETON

    if 'xmlns:Iptc4xmpExt=' not in text:
        text = re.sub(
            r'(<rdf:Description\b.*?)(/>|>)',
            lambda m: (m.group(1) +
                       ' xmlns:Iptc4xmpExt="http://iptc.org/std/Iptc4xmpExt/'
                       '2008-02-29/"' + m.group(2)),
            text, count=1, flags=re.S)

    def _drop(tag):
        return re.sub(rf'<Iptc4xmpExt:{tag}>.*?</Iptc4xmpExt:{tag}>', '',
                      text, flags=re.S)

    names = payload.get(PERSON_XMP)
    text = _drop('PersonInImage')
    if names:
        items = ''.join(f'<rdf:li>{n}</rdf:li>' for n in names)
        block = (f'<Iptc4xmpExt:PersonInImage><rdf:Bag>{items}'
                 f'</rdf:Bag></Iptc4xmpExt:PersonInImage>')
        text = _insert_in_description(text, block)

    event = payload.get(EVENT_XMP)
    text = re.sub(r'<Iptc4xmpExt:Event>.*?</Iptc4xmpExt:Event>', '', text,
                  flags=re.S)
    if event:
        val = (list(event.values())[0] if isinstance(event, dict) else event)
        block = (f'<Iptc4xmpExt:Event><rdf:Alt><rdf:li xml:lang="x-default">'
                 f'{val}</rdf:li></rdf:Alt></Iptc4xmpExt:Event>')
        text = _insert_in_description(text, block)

    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


def _insert_in_description(text, block):
    """Put an element inside rdf:Description, converting a self-closing
    <rdf:Description .../> into an open/close pair when needed."""
    m = re.search(r'<rdf:Description\b.*?/>', text, re.S)
    if m:
        opened = m.group(0)[:-2] + '>'
        return text.replace(m.group(0),
                            opened + block + '</rdf:Description>', 1)
    m = re.search(r'(<rdf:Description\b.*?>)', text, re.S)
    if m:
        return text.replace(m.group(1), m.group(1) + block, 1)
    return text


def read_iptc(filepath):
    """Read the editable IPTC fields (IIM + the two XMP fields) from a file.

    Returns a dict {storage_key: str}; multi-value fields are joined with '; '.
    The constant creator/rights/contact block is NOT read here - it lives in
    the app settings, not per image. Unknown tags are left alone.
    """
    if pyexiv2 is None:
        raise RuntimeError(unavailable_reason())
    ext = os.path.splitext(filepath)[1].lower()
    if ext in RAW_EXTS:
        # exiv2 must never open a RAW/DNG (its parser has crashed on real
        # camera files, 0.12.6). For RAW the metadata lives in the .xmp
        # sidecar anyway - read the XMP families from there when present.
        sidecar = os.path.splitext(filepath)[0] + '.xmp'
        raw = {}
        # Pure Python: a sidecar is XML text, and exiv2 has crashed even on
        # opening one (0.12.6). No native library on this path any more.
        xmp = _sidecar_read_xmp(sidecar) if os.path.exists(sidecar) else {}
    else:
        raw = native_exec.run(native_ops.read_iptc_raw, filepath)
        xmp = native_exec.run(native_ops.read_xmp_raw, filepath)
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
            if isinstance(val, list):
                val = val[0] if val else ''
            out[key] = val
    # Person shown (bag) and Event (lang-alt) live in XMP.
    persons = xmp.get(PERSON_XMP)
    if persons is not None:
        names = [persons] if isinstance(persons, str) else list(persons)
        names = [n for n in names if n]
        if names:
            out[PERSON_KEY] = '; '.join(names)
    event = _langalt_text(xmp.get(EVENT_XMP))
    if event:
        out[EVENT_KEY] = event
    return out


def write_iptc(filepath, data, constants=None, target_path=None):
    """Write the editable fields plus the constant creator/rights/contact
    block.

    data: {storage_key: str} for the per-image editor fields (IIM + person +
        event). Empty strings DELETE the tag.
    constants: {storage_key: str} for the CONSTANT_FIELDS (creator, copyright,
        credit, contact) - written to EVERY image. Empty strings delete.
    target_path: if given and different from filepath, the file is COPIED there
        first and the copy is modified; the original is never touched.
    Returns the path that was actually written.
    """
    if pyexiv2 is None:
        raise RuntimeError(unavailable_reason())
    path = filepath
    if target_path and os.path.abspath(target_path) != os.path.abspath(filepath):
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        shutil.copy2(filepath, target_path)
        path = target_path

    merged = dict(data or {})
    if constants:
        merged.update(constants)

    iim_payload = {'Iptc.Envelope.CharacterSet': _UTF8_MARKER}
    xmp_payload = {}
    for key, val in merged.items():
        exiv_key = _FIELD_EXIV.get(key)
        if not exiv_key:
            continue
        kind = _FIELD_KIND.get(key)
        text = (val or '').strip() if isinstance(val, str) else val
        if kind == 'iim':
            iim_payload[exiv_key] = text or None
        elif kind == 'iim_multi':
            iim_payload[exiv_key] = split_multi(text) if text else None
        elif kind == 'bag':
            names = split_multi(text)
            xmp_payload[exiv_key] = names if names else None
        elif kind in ('langalt', 'text'):
            xmp_payload[exiv_key] = text or None

    ext = os.path.splitext(path)[1].lower()
    if ext in RAW_EXTS:
        # RAW is never opened by exiv2 (see read_iptc): the XMP families go
        # into the sidecar (created when missing); the IIM block has no place
        # in a sidecar and is skipped with a log note.
        sidecar = os.path.splitext(path)[0] + '.xmp'
        if not os.path.exists(sidecar):
            with open(sidecar, 'w', encoding='utf-8') as f:
                f.write(XMP_SKELETON)
        if xmp_payload:
            # Pure Python (0.12.6): no exiv2 on sidecars.
            _sidecar_write_xmp(sidecar, xmp_payload)
        skipped = [k for k, v in iim_payload.items()
                   if v is not None and k != 'Iptc.Envelope.CharacterSet']
        if skipped:
            logging.getLogger('Cammello').info(
                'IPTC: %d IIM field(s) not written for RAW %s (sidecars '
                'carry XMP only).', len(skipped), os.path.basename(path))
        return sidecar
    native_exec.run(native_ops.modify_all_raw, path, iim_payload, xmp_payload)
    return path


# ── MediaWiki -> IPTC mapping ────────────────────────────────────────────────
#
# Conservative on purpose: only fields whose meaning translates without
# guessing. QIDs (creator=Q640 etc.) are NOT resolved to labels here - that
# would need a network call; the by-line comes from the Information |author=
# value instead, which is already plain text.

_CATEGORY_RE = re.compile(r'\[\[Category:([^\]|]+)(?:\|[^\]]*)?\]\]')
# Categories that describe the upload, not the picture.
_MAINTENANCE_CATEGORIES = {'Uploaded with Cammello'}


def mw_to_iptc(merged_description, date='', target_filename='',
               caption_langs=('de', 'en')):
    """Derive IPTC fields from a file's merged description_all text.

    Mapping:
      caption_XX   -> caption (first language found in caption_langs, then any)
      [[Category]] -> keywords (maintenance categories dropped)
      date         -> date_created     (leading YYYY-MM-DD of the Date column)
      target file  -> object_name      (filename without extension)
    Deliberately NOT mapped: creator / copyright / credit / contact - those
    are the CONSTANT block (same for every image, edited in Settings), never
    taken from the MediaWiki data. Also not mapped: license QIDs, free
    wikitext.
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


# ── Person shown -> categories / depicts (helpers) ───────────────────────────
# Pure text helpers; the UI in mw_iptc.py adds the interactive Wikidata parts.

def add_category_lines(text, category_names):
    """Append '[[Category:<name>]]' lines to a description, skipping any that
    are already present (case-insensitive on the bare name). Returns the new
    text. `category_names` are bare names (no wrapper)."""
    text = text or ''
    existing = {m.group(1).strip().lower()
                for m in _CATEGORY_RE.finditer(text)}
    additions = []
    for name in category_names:
        name = (name or '').strip()
        if name and name.lower() not in existing:
            additions.append(f'[[Category:{name}]]')
            existing.add(name.lower())
    if not additions:
        return text
    sep = '' if (not text or text.endswith('\n')) else '\n'
    return text + sep + '\n'.join(additions)


def merge_depicts(text, qids):
    """Add QIDs to the file's 'depicts=' line (semicolon-separated), keeping
    order and removing duplicates. Creates the line if absent. Returns the new
    text. `qids` is an iterable of 'Q…' strings."""
    text = text or ''
    lines = text.split('\n')
    idx = next((i for i, l in enumerate(lines)
                if l.strip().lower().startswith('depicts=')), -1)
    current = []
    if idx >= 0:
        current = [q.strip() for q in lines[idx].split('=', 1)[1].split(';')
                   if q.strip()]
    seen = {q.upper() for q in current}
    for q in qids:
        q = (q or '').strip()
        if q and q.upper() not in seen:
            current.append(q)
            seen.add(q.upper())
    if not current:
        return text
    new_line = 'depicts=' + '; '.join(current)
    if idx >= 0:
        lines[idx] = new_line
    else:
        lines.insert(0, new_line)
    return '\n'.join(l for l in lines if l.strip())


def set_created_during(text, qid):
    """Set the 'created_during=<QID>' line in a description (single value:
    replaces an existing line, else inserts one). Returns the new text."""
    qid = (qid or '').strip()
    if not qid:
        return text or ''
    lines = (text or '').split('\n')
    out = [l for l in lines if not l.strip().lower().startswith('created_during=')]
    out.insert(0, f'created_during={qid}')
    return '\n'.join(l for l in out if l.strip())
