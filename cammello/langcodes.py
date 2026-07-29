"""Language codes with a script or region part (0.15.2).

A user reported that captions in Malay written in Jawi script are
impossible: the code is "ms-Arab", and Cammello answered "Not a valid
code". The old check was `[a-z]{2,3}` plus a `.lower()`, which rejected
the hyphen and would have destroyed the capital of the script tag anyway.

The interesting part is that BOTH spellings are in circulation: ISO 15924
writes script tags in title case ("ms-Arab", as Wiktionary and the Commons
category labels do), while MediaWiki's own site codes are lower case
("ms-arab"). Guessing which one Commons wants for captions would be a coin
flip, so this module does not guess:

  * `normalize()` puts a code into the BCP 47 shape (language lower,
    script title, region upper) - that is what a human expects to see.
  * `looks_valid()` is a pure pattern check, used offline.
  * `fetch_commons_languages()` asks Commons which codes it actually
    accepts for captions (meta=wbcontentlanguages, context "term").
  * `canonical()` matches CASE-INSENSITIVELY against that list and returns
    the spelling COMMONS uses. Whatever the wiki calls it, that is what we
    store - the question of ms-Arab versus ms-arab never has to be
    answered here.

No Qt in here.
"""
import re

import requests

from .constants import WD_USER_AGENT

COMMONS_API = 'https://commons.wikimedia.org/w/api.php'

# language(2-3) [ -script(4) ] [ -region(2 alpha | 3 digit) ]
# Deliberately not full BCP 47: variants and extensions do not appear in
# Wikimedia caption codes, and a looser pattern would accept typing errors.
_CODE_RE = re.compile(
    r'^[A-Za-z]{2,3}(-[A-Za-z]{4})?(-([A-Za-z]{2}|[0-9]{3}))?$')

_cache = {'codes': None}
LAST_ERROR = None


def normalize(code):
    """'MS-arab' -> 'ms-Arab'. Casing per BCP 47; the parts are untouched
    otherwise, so an unknown code keeps its shape."""
    parts = (code or '').strip().replace('_', '-').split('-')
    if not parts or not parts[0]:
        return ''
    out = [parts[0].lower()]
    for p in parts[1:]:
        if len(p) == 4 and p.isalpha():
            out.append(p.capitalize())          # script: Arab, Latn, Hant
        elif len(p) == 2 and p.isalpha():
            out.append(p.upper())               # region: MY, BR
        else:
            out.append(p.lower())
    return '-'.join(out)


def looks_valid(code):
    """Pattern check only - says nothing about whether Commons knows it."""
    return bool(_CODE_RE.match((code or '').strip().replace('_', '-')))


def fetch_commons_languages(timeout=15):
    """The caption language codes Commons accepts. -> set, or None.

    Cached for the session: the list changes on the scale of MediaWiki
    releases, not of uploads. None means the question could not be
    answered - the caller then falls back to the pattern rather than
    refusing a code that may well be fine.
    """
    global LAST_ERROR
    if _cache['codes'] is not None:
        return _cache['codes']
    try:
        r = requests.get(
            COMMONS_API,
            params={'action': 'query', 'meta': 'wbcontentlanguages',
                    'wbclcontext': 'term', 'wbclprop': 'code',
                    'format': 'json', 'formatversion': '2'},
            headers={'User-Agent': WD_USER_AGENT}, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        langs = data.get('query', {}).get('wbcontentlanguages', {})
        if isinstance(langs, dict):
            codes = {str(k) for k in langs}
        else:                                    # formatversion 2 list form
            codes = {str(e.get('code')) for e in langs if e.get('code')}
        codes.discard('None')
        if not codes:
            LAST_ERROR = 'empty language list'
            return None
        _cache['codes'] = codes
        return codes
    except Exception as e:
        LAST_ERROR = str(e)
        return None


def canonical(code, known=None):
    """-> the spelling Commons uses, or None when it does not know the code.

    `known` is the set from fetch_commons_languages(); pass None to have it
    fetched. Matching ignores case, so a user typing "ms-arab" gets back
    whatever Commons calls it - and the other way round.
    """
    wanted = (code or '').strip().replace('_', '-')
    if not wanted:
        return None
    if known is None:
        known = fetch_commons_languages()
    if not known:
        return None
    lowered = {c.lower(): c for c in known}
    return lowered.get(wanted.lower())


def reset_cache():
    """Forget the fetched list (tests, and a retry after a failed fetch)."""
    _cache['codes'] = None
