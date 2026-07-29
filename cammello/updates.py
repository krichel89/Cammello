"""Check for newer releases (0.15.2).

Asks the GitHub releases API of the repository and compares the newest
release with the running version.

On the stable/experimental split
--------------------------------
Harald's rule (0.16.0, correcting the first attempt): the digit BEHIND
THE FIRST DOT decides - the MINOR number, not the last one. ODD minor =
test version, EVEN minor = working version. So the whole 0.15.x line is
testing and 0.16.x is a working line; a version's patch number says
nothing about it.

The first implementation looked at the LAST digit, which made 0.15.2 a
"stable" build inside what is really a test line. Harald's version is the
better one anyway: a whole line stays one kind of thing, instead of the
character flipping with every patch release.

Releases from before the rule (0.14.3, 0.15.x …) were numbered without it
and are not meaningfully classified by it - only "is this newer" matters
for them.

No Qt in here.
"""
import re

import requests

from .constants import WD_USER_AGENT

RELEASES_API = 'https://api.github.com/repos/krichel89/Cammello/releases'
# Where to send the user when a release has no page of its own.
RELEASES_PAGE = 'https://github.com/krichel89/Cammello/releases'

LAST_ERROR = None


def parse_version(text):
    """'v0.15.2' -> (0, 15, 2). Unparsable -> None."""
    m = re.search(r'(\d+)\.(\d+)\.(\d+)', str(text or ''))
    if not m:
        return None
    return tuple(int(g) for g in m.groups())


def is_stable(version):
    """EVEN minor number = working version, ODD = test version.

    The minor is the digit behind the first dot: 0.16.0 works, 0.15.2 is
    testing. `version` may be a tuple or a string.
    """
    if isinstance(version, str):
        version = parse_version(version)
    if not version or len(version) < 2:
        return None
    return version[1] % 2 == 0


def is_newer(candidate, current):
    """Whether `candidate` is a later version than `current`."""
    a = parse_version(candidate) if isinstance(candidate, str) else candidate
    b = parse_version(current) if isinstance(current, str) else current
    if not a or not b:
        return False
    return a > b


def fetch_releases(timeout=15, per_page=10):
    """The published releases, newest first. -> [(version_tuple, tag, url)].

    Drafts and anything unparsable are dropped. Returns None on any
    failure - an update check that cannot reach the network is a
    non-event, not an error to shout about.
    """
    global LAST_ERROR
    try:
        r = requests.get(
            RELEASES_API, params={'per_page': per_page},
            headers={'User-Agent': WD_USER_AGENT,
                     'Accept': 'application/vnd.github+json'},
            timeout=timeout)
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, list):
            LAST_ERROR = str(data)[:200]
            return None
        out = []
        for rel in data:
            if rel.get('draft'):
                continue
            v = parse_version(rel.get('tag_name'))
            if v:
                out.append((v, rel.get('tag_name'), rel.get('html_url') or ''))
        out.sort(reverse=True)
        return out
    except Exception as e:
        LAST_ERROR = str(e)
        return None


def newest_relevant(releases, current, stable_only=True):
    """The newest release worth mentioning. -> (version, tag, url) or None.

    With stable_only the experimental ones are skipped - unless the
    running version is itself experimental, in which case the user has
    already opted into that world and hiding newer experimental builds
    from them would be unhelpful.
    """
    cur = parse_version(current) if isinstance(current, str) else current
    if not releases or not cur:
        return None
    running_experimental = is_stable(cur) is False
    for version, tag, url in releases:
        if not is_newer(version, cur):
            continue
        if stable_only and not running_experimental and not is_stable(version):
            continue
        return (version, tag, url)
    return None


def format_version(version):
    return '.'.join(str(p) for p in version)
