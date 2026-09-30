"""Link to the tool that creates a NEW Wikidata item for a person (0.18.27).

Harald: "Hier ist ein Tool, um einen neuen Wikidata-Eintrag fuer eine Person
anzulegen. Das sollte bei Cammello im MediaWiki-Tab verlinkt sein. Und zwar
so, dass es sinnvoll ist. Also Link direkt auf Schauspieler etc."

The tool is new-q5 on Toolforge. It takes NO values from the address, only
the list of PROPERTIES its form offers (Harald: "Werte kann man nicht
uebergeben, nur Properties"), e.g.

    https://new-q5.toolforge.org/?property=P345%7CP106%7CP69

So "a link straight to actors" means: the property set that fits an actor
(IMDb ID, occupation, educated at). Each occupation in the menu carries its
own set. The name cannot travel in the address; Cammello puts it on the
clipboard instead, ready to paste into the tool's name field.

The whole table is here, so changing a set is a one-line edit. No Qt in this
module: the builder is testable without a window.
"""
from urllib.parse import quote

NEW_PERSON_URL = 'https://new-q5.toolforge.org/?property={properties}'

# (key, menu label - an i18n key, properties offered in the form).
# Every PID checked on Wikidata (30.09.2026):
#   P106 occupation          P69  educated at         P108 employer
#   P345 IMDb ID             P434 MusicBrainz artist  P1953 Discogs artist
#   P1303 instrument         P412 voice type          P227 GND ID
#   P102 member of pol. party  P39 position held
#   P641 sport               P54  member of sports team
# The actor set is Harald's own example link.
NEW_PERSON_ROLES = [
    ('actor', 'Actor', ('P345', 'P106', 'P69')),
    ('film_director', 'Film director', ('P345', 'P106', 'P69')),
    ('film_producer', 'Film producer', ('P345', 'P106', 'P108')),
    ('screenwriter', 'Screenwriter', ('P345', 'P106', 'P69')),
    ('musician', 'Musician', ('P434', 'P1953', 'P106', 'P1303')),
    ('singer', 'Singer', ('P434', 'P1953', 'P106', 'P412')),
    ('composer', 'Composer', ('P434', 'P1953', 'P106', 'P69')),
    ('writer', 'Writer', ('P227', 'P106', 'P69')),
    ('journalist', 'Journalist', ('P106', 'P108', 'P69')),
    ('politician', 'Politician', ('P106', 'P102', 'P39')),
    ('athlete', 'Athlete', ('P106', 'P641', 'P54')),
    ('other', 'Other person', ('P106',)),
]

_ROLES = {r[0]: r for r in NEW_PERSON_ROLES}


def role(key):
    """(key, label, properties) for a role key; 'other' if unknown."""
    return _ROLES.get(key, _ROLES['other'])


def new_person_url(role_key, template=None):
    """The address that opens the tool with this occupation's properties.

    The list is joined with '|' and URL-encoded (%7C), exactly like the
    tool's own links. Only {properties} is filled; any other brace in the
    template is left as it is.
    """
    props = '|'.join(role(role_key)[2])
    return (template or NEW_PERSON_URL).replace(
        '{properties}', quote(props, safe=''))


def name_from_captions(captions, prefer=('en',), split=None):
    """The person's name from the file's captions, or ''.

    captions  {lang: caption}
    prefer    languages to try first (the UI language, then English)
    split     function that cuts the name off a caption ("X at Y" -> "X");
              the caller passes sdc.extract_name_from_caption

    The tool cannot take the name from the address, so this goes to the
    clipboard - a caption is the only place the name already exists as
    plain text (depicts is exactly what is missing here).
    """
    captions = {k: (v or '').strip() for k, v in (captions or {}).items()}
    order = [c for c in prefer if captions.get(c)]
    order += [c for c in sorted(captions) if captions[c] and c not in order]
    for code in order:
        text = captions[code]
        name = split(text) if split else text
        name = (name or '').strip()
        if name:
            return name
    return ''
