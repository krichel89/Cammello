"""Content versus meta categories (0.15.1).

Harald: "Jede Datei sollte mindestens eine inhaltliche Kategorie bekommen,
Metakategorien zählen nicht." A category that says who took the picture,
which project it belongs to or which tool uploaded it does not describe
what is IN the picture, and a file carrying only those is effectively
uncategorised.

The patterns live in assets/meta_categories.txt, a plain text file Harald
edits without touching any source. Deliberately not a regular expression
list: "Photographs by *" is something you can write down correctly at
half past eleven at night, `^Photographs by .*$` is not.

No Qt in here.
"""
import os

_PATTERNS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              'assets', 'meta_categories.txt')
_cache = None
LAST_ERROR = None


def _load():
    """The patterns, lower-cased. Cached; reload_patterns() clears it."""
    global _cache, LAST_ERROR
    if _cache is None:
        pats = []
        try:
            with open(_PATTERNS_PATH, encoding='utf-8') as fh:
                for line in fh:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        pats.append(line.lower())
        except OSError as e:
            # A missing list must not break the app: without patterns
            # nothing counts as meta, which errs towards NOT nagging.
            LAST_ERROR = str(e)
        _cache = pats
    return _cache


def reload_patterns():
    """Drop the cache so an edited file takes effect (used by the tests and
    reachable from the log if the list is ever wrong)."""
    global _cache
    _cache = None
    return _load()


def _normalize(name):
    name = (name or '').strip()
    if name.lower().startswith('category:'):
        name = name.split(':', 1)[1].strip()
    return name.lower()


def _matches(name, pattern):
    """Glob-light: '*' at either end, otherwise an exact match."""
    starts = pattern.startswith('*')
    ends = pattern.endswith('*')
    core = pattern.strip('*')
    if not core:
        return False
    if starts and ends:
        return core in name
    if ends:
        return name.startswith(core)
    if starts:
        return name.endswith(core)
    return name == core


def is_meta(name):
    """Whether this category name is a meta category."""
    norm = _normalize(name)
    if not norm:
        return False
    return any(_matches(norm, p) for p in _load())


def split(names):
    """-> (content, meta) for a list of category names."""
    content, meta = [], []
    for n in names:
        if not (n or '').strip():
            continue
        (meta if is_meta(n) else content).append(n)
    return content, meta


def has_content_category(names):
    """Whether at least one of these says what is IN the picture."""
    content, _meta = split(names)
    return bool(content)


def parse_field(text):
    """The Categories field ('A; B; C') -> a list of names."""
    if not text:
        return []
    return [p.strip() for p in str(text).split(';') if p.strip()]


def count_patterns():
    return len(_load())
