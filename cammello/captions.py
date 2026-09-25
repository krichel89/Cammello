"""Structured-data caption generation (0.18.24).

Harald: "die caption soll in allen sprachen gleichzeitig verfügbar sein …
die sollen erzeugt werden … wie bei LrMediaWiki2 … eigenständig."

A caption (a Wikibase label on the file's structured data) is built from the
file's own depicts (P180) and created-during (P10408) values, in every
configured language at once, out of the labels Wikidata already holds. This
module is the whole rulebook and is deliberately Qt-free: the network call
lives in wikidata.py, the settings and the dialog in the GUI layer, so every
decision here can be tested without a window and without a network.

Two things the design turns on:

* The **conjunction** ("Fügung") between the person and the event is learned
  per event AND per language, because it is grammatical, not mechanical:
  German "Anna Müller bei der Berlinale" needs "bei der", English "at the",
  and a festival, an award ceremony and a match each inflect differently.
  What is not (yet) learned falls back to the **caseless** form "Name,
  Event", which reads correctly in any language and is never wrong, only
  plainer.

* The caption itself is **plain text** and capped at 250 characters - a
  Wikibase label carries no markup. Interwiki links (`[[:de:Title|Text]]`)
  belong in the description wikitext instead, and are built here from the
  entities' sitelinks but never put into a caption.

The entities this module works on are the NORMALIZED shape that
wikidata.py.fetch_caption_entities returns, so the two never disagree:

    { 'Q42': { 'labels':    {'en': 'Douglas Adams', 'de': '…'},
               'sitelinks':  {'enwiki': 'Douglas Adams', 'dewiki': '…'},
               'human':      True } }
"""
import json
import re

from .constants import CAPTION_MAX_LEN


# ── Reading a normalized entity ─────────────────────────────────────────────

def is_human(entity):
    """True when the entity is instance-of human (P31 = Q5). The fetch layer
    has already resolved this; a missing entity is not a person."""
    return bool(entity and entity.get('human'))


def entity_label(entity, lang, fallbacks=('en', 'de')):
    """The best label for `lang`: the language itself, then the fallbacks,
    then any label the entity has. '' when the entity is missing or bare."""
    if not entity:
        return ''
    labels = entity.get('labels') or {}
    for code in (lang,) + tuple(fallbacks):
        val = (labels.get(code) or '').strip()
        if val:
            return val
    for val in labels.values():
        if (val or '').strip():
            return val.strip()
    return ''


def interwiki_link(entity, prefer_langs):
    """`[[:xx:Title|Display]]` for the first of `prefer_langs` the entity has
    a Wikipedia sitelink in, or '' when it has none. The display text is the
    label in that same language, the title as it stands otherwise."""
    if not entity:
        return ''
    sitelinks = entity.get('sitelinks') or {}
    labels = entity.get('labels') or {}
    for lang in prefer_langs:
        title = (sitelinks.get(f'{lang}wiki') or '').strip()
        if title:
            display = (labels.get(lang) or title).strip()
            # The label is external data; strip the characters that would
            # break out of the [[…|…]] into other wikitext. A MediaWiki title
            # cannot contain these, so the title itself is already safe.
            display = re.sub(r'[\[\]|{}]', '', display).strip() or title
            return f'[[:{lang}:{title}|{display}]]'
    return ''


# ── The subject (who/what the caption is about) ─────────────────────────────

def subject_qids(depicts_qids, entities):
    """The depicts QIDs that carry the caption: the humans among them, or -
    when none is a person - every depicts value, so a caption is still built
    for a picture of a building or an artwork."""
    humans = [q for q in depicts_qids if is_human(entities.get(q))]
    return humans or [q for q in depicts_qids if q]


def subject_name(depicts_qids, entities, lang):
    """The subject as plain text in `lang`: one name, or several joined with
    ', ' when the picture depicts more than one person."""
    names = []
    for qid in subject_qids(depicts_qids, entities):
        label = entity_label(entities.get(qid), lang)
        if label:
            names.append(label)
    return ', '.join(names)


def subject_linked(depicts_qids, entities, lang, prefer_langs):
    """The subject with each name wrapped in an interwiki link where a
    sitelink exists, for the description wikitext. Names without a sitelink
    stay plain, so the text is never broken."""
    parts = []
    for qid in subject_qids(depicts_qids, entities):
        entity = entities.get(qid)
        link = interwiki_link(entity, prefer_langs)
        parts.append(link or entity_label(entity, lang))
    return ', '.join(p for p in parts if p)


# ── The learned conjunction table ("Fügungen"), Qt-free ─────────────────────

class FuegungTable:
    """What connects a name to an event, per event and per language.

    An entry is a pair (conn, form): the connector that follows the name and
    the event's inflected display form. The caption is name + conn + form, so
    "Anna Müller" + " bei der " + "Berlinale". Storing the two apart lets the
    dialog show and correct them; only their concatenation matters to the
    caption, which is why deriving them from an existing caption need not be
    perfect. An entry with both parts empty is no entry at all.
    """

    def __init__(self):
        self._d = {}   # {event_qid: {lang: {'conn': str, 'form': str}}}

    def get(self, event_qid, lang):
        """The (conn, form) pair, or None when nothing is learned."""
        entry = (self._d.get(event_qid) or {}).get(lang)
        if not entry:
            return None
        return (entry.get('conn', ''), entry.get('form', ''))

    def tail(self, event_qid, lang):
        """conn + form, the text that follows the name. '' when unlearned."""
        pair = self.get(event_qid, lang)
        return (pair[0] + pair[1]) if pair else ''

    def learn(self, event_qid, lang, conn, form):
        """Remember (or, when both parts are empty, forget) one conjunction."""
        if not event_qid or not lang:
            return
        conn, form = conn or '', form or ''
        if not conn.strip() and not form.strip():
            if event_qid in self._d:
                self._d[event_qid].pop(lang, None)
                if not self._d[event_qid]:
                    self._d.pop(event_qid, None)
            return
        self._d.setdefault(event_qid, {})[lang] = {'conn': conn, 'form': form}

    def events(self):
        return sorted(self._d)

    def merge_from(self, other, overwrite=False):
        """Copy entries from another table. With overwrite=False (the
        default) only fills gaps, so a value learned from the user's own
        caption never quietly replaces one they set in the dialog."""
        for event_qid in other.events():
            for lang, entry in (other._d.get(event_qid) or {}).items():
                if overwrite or self.get(event_qid, lang) is None:
                    self.learn(event_qid, lang, entry.get('conn', ''),
                               entry.get('form', ''))
        return self

    def to_json(self):
        return json.dumps(self._d, ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, text):
        """Rebuild a table from stored JSON, ignoring anything malformed - a
        corrupt settings value must never stop the feature from working."""
        table = cls()
        try:
            data = json.loads(text) if text else {}
        except (ValueError, TypeError):
            return table
        if not isinstance(data, dict):
            return table
        for event_qid, langs in data.items():
            if not isinstance(langs, dict):
                continue
            for lang, entry in langs.items():
                if isinstance(entry, dict):
                    table.learn(str(event_qid), str(lang),
                                str(entry.get('conn', '')),
                                str(entry.get('form', '')))
        return table


def derive_fuegung(caption, subject, event_label):
    """Read a (conn, form) pair back out of a caption the user already wrote.

    So a shoot where one file was captioned by hand teaches the rest: given
    "Anna Müller bei der Berlinale", the known name "Anna Müller" and the
    bare event label "Berlinale", this returns (" bei der ", "Berlinale").
    Returns None when the caption does not start with the name, when the
    event label is not found in the tail, or when the caption is only the
    caseless "Name, Event" fallback (which is not a conjunction to learn).
    """
    caption = (caption or '').strip()
    subject = (subject or '').strip()
    event_label = (event_label or '').strip()
    if not caption or not subject or not event_label:
        return None
    if not caption.lower().startswith(subject.lower()):
        return None
    tail = caption[len(subject):]
    idx = tail.lower().find(event_label.lower())
    if idx < 0:
        return None
    conn, form = tail[:idx], tail[idx:]
    # The caseless fallback "Name, Event" is not a learned conjunction.
    if (conn.strip() in (',', '')
            and form.strip().lower() == event_label.lower()):
        return None
    return (conn, form)


# ── Building the captions ───────────────────────────────────────────────────

_WIKILINK_RE = re.compile(r'\[\[(?::?[^\]|]*\|)?([^\]|]+)\]\]')


def _plain(text):
    """A caption is a label: no markup. Unwrap any [[link|text]] to its text
    and collapse whitespace, defensively - the inputs are labels already, but
    a learned form could have had a link pasted into it."""
    text = _WIKILINK_RE.sub(r'\1', text or '')
    return re.sub(r'\s+', ' ', text).strip()


def _clamp(text, max_len):
    """Trim to the label limit, on a word boundary when one is near the end
    so a caption is never cut mid-word."""
    if len(text) <= max_len:
        return text
    cut = text[:max_len]
    space = cut.rfind(' ')
    if space >= max_len - 24:      # a boundary close enough to the limit
        cut = cut[:space]
    return cut.rstrip()


def build_caption(subject, event_qid, event_label, lang, table,
                  max_len=CAPTION_MAX_LEN):
    """One plain-text caption for one language.

    name + learned conjunction + event, or the caseless "name, event" when
    the conjunction is not learned, or just the name when there is no event.
    '' when there is neither a subject nor an event.
    """
    subject = _plain(subject)
    event_label = _plain(event_label)
    if not subject and not event_label:
        return ''
    if not event_label:
        caption = subject
    else:
        tail = table.tail(event_qid, lang) if (table and event_qid) else ''
        if tail.strip():
            caption = (subject + tail) if subject else tail.lstrip()
        elif subject:
            caption = f'{subject}, {event_label}'     # caseless fallback
        else:
            caption = event_label
    return _clamp(_plain(caption), max_len)


def derive_table(rows, entities, langs):
    """Learn conjunctions from the captions the user already wrote.

    `rows` is a list of {'depicts': [qid], 'event': qid, 'captions':
    {lang: text}}. A shoot where one file is captioned by hand teaches the
    rest: for every row that has both an event and a caption in a language,
    the (conn, form) is read back and remembered. The first plausible
    reading of each event+language wins; later rows do not overwrite it.
    """
    table = FuegungTable()
    for row in rows:
        event = (row.get('event') or '').strip()
        if not event:
            continue
        depicts = row.get('depicts') or []
        caps = row.get('captions') or {}
        for lang in langs:
            if table.get(event, lang) is not None:
                continue
            cap = (caps.get(lang) or '').strip()
            if not cap:
                continue
            pair = derive_fuegung(
                cap, subject_name(depicts, entities, lang),
                entity_label(entities.get(event), lang))
            if pair:
                table.learn(event, lang, *pair)
    return table


def all_captions(depicts_qids, event_qid, entities, table, langs):
    """{lang: caption} across `langs`, skipping any language that yields no
    text (no label in it and none to fall back to)."""
    out = {}
    for lang in langs:
        subject = subject_name(depicts_qids, entities, lang)
        event_label = (entity_label(entities.get(event_qid), lang)
                       if event_qid else '')
        caption = build_caption(subject, event_qid, event_label, lang, table)
        if caption:
            out[lang] = caption
    return out


def linked_description(depicts_qids, event_qid, entities, table, lang,
                       prefer_langs):
    """The caption for `lang` with the names turned into interwiki links, for
    an Information-template description. The conjunction and the caseless
    fallback are the same as build_caption; only the names are linked."""
    subject_plain = subject_name(depicts_qids, entities, lang)
    subject = subject_linked(depicts_qids, entities, lang, prefer_langs)
    event_label = (entity_label(entities.get(event_qid), lang)
                   if event_qid else '')
    event = event_label
    event_link = interwiki_link(entities.get(event_qid), prefer_langs)
    if not subject_plain and not event_label:
        return ''
    if not event_label:
        return subject
    tail = table.tail(event_qid, lang) if (table and event_qid) else ''
    if tail.strip():
        # Link the event by swapping its bare label inside the learned form
        # for the interwiki link; the connector and inflection stay.
        if event_link:
            tail = tail.replace(event_label, event_link, 1)
        return (subject + tail) if subject else tail.lstrip()
    linked_event = event_link or event
    return f'{subject}, {linked_event}' if subject else linked_event
