"""Wikitext for audio uploads (music workflow).

Harald, 2026-08-13: uploads of THIRD-PARTY recordings. Two things make an
audio file description different from a photograph, and both are why this
module exists instead of a few more branches in workers.py:

  * The author line carries ROLES, not one person. A recording has a
    composer and somebody who recorded it, and neither of them is the
    uploader. Harald: "Urheber dürfte selten der Uploader sein."
  * The licence part is a LIST of two blocks, one per rights layer.

The layout below reproduces Harald's Mendelssohn page character for
character (organ sonata op. 65 no. 5, recorded by Wolfram Syré). That page
is the specification; test_music_0180.py holds it verbatim and compares.

Deliberately kept as PURE FUNCTIONS with no Qt, no network and no logging,
the same rule workflows.py and edits.py follow: everything in here can be
tested without building a window, and the one thing that does need the
network - asking Commons which of the generated categories exist - stays
outside in the worker.

Where this differs from the photograph generator in workers.py, it does so
on purpose, and only for this workflow. The photograph path is untouched:

  * a `=={{int:filedesc}}==` heading above {{Information}} (the photo path
    has none),
  * `=={{int:license-header}}==` without the spaces the photo path writes,
  * field order description, date, source, author, permission,
    other versions - source BEFORE author,
  * empty |permission= and |other versions= are kept rather than dropped,
  * |other versions=, which is a different {{Information}} parameter from
    the |other fields= the photo path uses.
"""
import re

# The registry names this module reads out of an upload row. mw_upload
# puts them there, workflow_config lists them, and test_music_0180 checks
# that the three lists agree - a field added in one place and forgotten in
# another is exactly the kind of silent gap this catches.
FIELDS = [
    'kompositionsjahr',
    'quellvorlage',
    'komponist',
    'aufnehmender',
    'aufnahmetechnik',
    'todesjahr_komponist',
    'lizenz_komposition',
    'lizenz_aufnahme',
    'andere_versionen',
    'instrument',
    'epoche',
    'werk',
    'land',
]

# Role words of the author line. English on purpose: they are wikitext
# going to Commons, not UI, and Commons file pages are English by
# default. Once Harald's own template exists these become its parameters
# and the wording moves there.
ROLE_COMPOSITION = 'composition'
ROLE_RECORDING = 'recording'

# [[:en:Target|Text]] or [[:en:Target]] - the leading colon form Commons
# requires for interwiki links on file pages.
_LINK = re.compile(r'\[\[:?(?:[a-z][a-z\w-]*:)?([^|\]]+)(?:\|[^\]]*)?\]\]')


def plain_name(wikitext):
    """The bare name inside a wikitext link, for building category names.

    '[[:en:Felix Mendelssohn|Felix Mendelssohn Bartoldy]]' -> 'Felix
    Mendelssohn'. The LINK TARGET is taken, not the visible text: Commons
    category names follow the article title, and the visible text is
    frequently a fuller or differently spelled form (Harald's page says
    "Felix Mendelssohn Bartoldy" but the category is "Felix Mendelssohn").

    Text without a link is returned as it stands. This is a guess by
    construction - a link to a German article does not have to match the
    English category name - which is why every generated category is
    checked against Commons before it is used; see category_candidates.
    """
    text = (wikitext or '').strip()
    m = _LINK.search(text)
    if m:
        return m.group(1).strip()
    return text


def author_line(values):
    """The |author= value: one line per role.

        composition: [[:en:Felix Mendelssohn|Felix Mendelssohn Bartoldy]]
        recording (using a [[:en:Hauptwerk|Hauptwerk]] digital organ): …

    A role with no name is left out entirely rather than written as an
    empty line - a dangling "recording:" would be worse than nothing.
    """
    parts = []
    composer = (values.get('komponist') or '').strip()
    recordist = (values.get('aufnehmender') or '').strip()
    technique = (values.get('aufnahmetechnik') or '').strip()
    if composer:
        parts.append(f'{ROLE_COMPOSITION}: {composer}')
    if recordist:
        role = ROLE_RECORDING
        if technique:
            role = f'{ROLE_RECORDING} ({technique})'
        parts.append(f'{role}: {recordist}')
    return '\n'.join(parts)


def source_line(values):
    """The |source= value: the link, with the source template stuck
    directly onto it - no separating space, as on Harald's page."""
    return (values.get('quelle') or '').strip() \
        + (values.get('quellvorlage') or '').strip()


def with_deathyear(template, year):
    """Put |deathyear= into a licence template that has no year yet.

    Harald's page carries {{PD-old-auto-expired|deathyear=1847}}, and the
    year is a field of its own here because it also has nothing to do with
    which template is chosen. ONE rule, so there is nothing to guess:

      * no year given, or the text already mentions deathyear= -> the text
        is used unchanged,
      * otherwise |deathyear=YYYY is inserted before the closing braces.

    Anything that is not a single {{…}} call is left alone; somebody who
    writes his own wikitext there means it. "Single" is counted, not
    assumed: '{{A}} and {{B}}' starts with braces and ends with braces
    too, and an early version of this happily put the death year into
    {{B}} - test_music_0180 caught it.
    """
    text = (template or '').strip()
    year = str(year or '').strip()
    if not text or not year or 'deathyear' in text:
        return text
    if not (text.startswith('{{') and text.endswith('}}')
            and text.count('{{') == 1 and text.count('}}') == 1):
        return text
    return text[:-2] + f'|deathyear={year}' + '}}'


def license_block(values):
    """The licence section: one bullet per rights layer.

        *composition:
        {{PD-old-auto-expired|deathyear=1847}}
        *performance:
        {{Wolfram Syré-permission}}

    A layer without a licence is dropped. If neither is filled the caller
    gets '' and leaves the whole section out - a heading over nothing
    would be an empty promise of a permission.
    """
    composition = with_deathyear(values.get('lizenz_komposition'),
                                 values.get('todesjahr_komponist'))
    recording = (values.get('lizenz_aufnahme') or '').strip()
    lines = []
    if composition:
        lines += [f'*{ROLE_COMPOSITION}:', composition]
    if recording:
        lines += ['*performance:', recording]
    return '\n'.join(lines)


# The category patterns, read off Harald's seven. {composer} and
# {recordist} are plain names (see plain_name), the rest are fields.
CATEGORY_PATTERNS = [
    'Audio files of {instrument} music recorded by {recordist}',
    'Audio files of music of {country}',
    'Audio files of music by {composer}',
    'Audio files of {epoch} music recorded by {recordist}',
    'Audio files of music by {composer} recorded by {recordist}',
    '{work}',
    'Audio files of {form}',
]


def category_candidates(values, form='sonatas'):
    """Category names this recording could belong in, in Harald's order.

    A pattern whose fields are not all filled is skipped - it would
    produce "Audio files of music of " and a red link on every file.

    These are CANDIDATES. Whether a category exists is not decidable here
    (see plain_name); the worker asks Commons and drops what does not
    exist, the same "no sitelink means no link" rule LrMediaWiki2 follows.
    Better one category short than a red link on every upload.
    """
    data = {
        'instrument': (values.get('instrument') or '').strip(),
        'country': (values.get('land') or '').strip(),
        'epoch': (values.get('epoche') or '').strip(),
        'work': (values.get('werk') or '').strip(),
        'form': (form or '').strip(),
        'composer': plain_name(values.get('komponist')),
        'recordist': plain_name(values.get('aufnehmender')),
    }
    out = []
    for pattern in CATEGORY_PATTERNS:
        needed = re.findall(r'\{(\w+)\}', pattern)
        if not all(data.get(n) for n in needed):
            continue
        name = pattern.format(**data)
        if name not in out:
            out.append(name)
    return out


def information_block(values, description):
    """The {{Information}} call, in the order Harald's page has it.

    |permission= and |other versions= are written even when empty. The
    photograph path drops empty fields; here they stay, because an audio
    file page that shows the empty rows is what he has on Commons today
    and the point of this workflow is to reproduce it.
    """
    lines = [
        '{{Information',
        f'|description={description}',
        f"|date={(values.get('kompositionsjahr') or '').strip()}",
        f'|source={source_line(values)}',
        f'|author={author_line(values)}',
        f"|permission={(values.get('genehmigung') or '').strip()}",
        f"|other versions={(values.get('andere_versionen') or '').strip()}",
        '}}',
    ]
    return '\n'.join(lines)


def build_wikitext(values, description, categories=(), extra_templates=''):
    """The whole file page.

    `description` arrives ready-made from the caller (language wrapper and
    all, exactly as the photograph path passes it), `categories` are the
    ones that survived the existence check plus whatever the description
    carried. Nothing here goes to the network.
    """
    parts = ['=={{int:filedesc}}==\n' + information_block(values, description)]
    if extra_templates:
        parts.append(extra_templates)
    licences = license_block(values)
    if licences:
        parts.append('=={{int:license-header}}==\n' + licences)
    cats = [c for c in categories if c]
    if cats:
        parts.append('\n'.join(cats))
    return '\n\n'.join(parts)
