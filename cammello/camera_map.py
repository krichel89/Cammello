"""Camera and lens mapping (0.15.0): EXIF strings -> Wikidata items.

The camera side is DATA FROM WIKIDATA, not guesswork: items carry their
EXIF model string as P2009 (plus P2010 for the make), and
make_camera_map.py regenerates the snapshot in assets/camera_map.json
from that. Only unambiguous mappings are in the file, so a hit here IS
the deliberate "only when the mapping is unique" rule - an EXIF string
that belongs to several items simply is not in the table.

Lenses have no Exif-string property on Wikidata; their section of the
same file is curated by hand and empty until it is filled.

No Qt in here.
"""
import json
import os

_MAP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         'assets', 'camera_map.json')
_cache = None


def _load():
    global _cache
    if _cache is None:
        try:
            with open(_MAP_PATH, encoding='utf-8') as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            data = {}
        _cache = {
            'cameras': {k: v for k, v in
                        (data.get('cameras') or {}).items()
                        if not k.startswith('_')},
            'lenses': {k: v for k, v in
                       (data.get('lenses') or {}).items()
                       if not k.startswith('_')},
        }
    return _cache


def camera_qid(make, model):
    """The Wikidata item for this camera, or None.

    Tried in order: "make\\tmodel" (the key form for models that are only
    unique together with their make), then the bare model. Both lookups
    are EXACT string matches against what the camera wrote - no fuzzy
    matching, that is the whole point.
    """
    if not model:
        return None
    table = _load()['cameras']
    if make:
        hit = table.get(f'{make}\t{model}')
        if hit:
            return hit
    return table.get(model)


def lens_qid(lens_model):
    """The Wikidata item for this lens, or None. Curated list only."""
    if not lens_model:
        return None
    return _load()['lenses'].get(lens_model)


def counts():
    """(cameras, lenses) in the loaded table - for the log line."""
    t = _load()
    return len(t['cameras']), len(t['lenses'])
