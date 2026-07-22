"""Leaf functions executed in the metadata HELPER PROCESS (0.12.6).

This module is imported by the spawned helper process (see native_exec), so
it must stay LIGHT: pyexiv2 and the standard library only - no Qt, no other
Cammello modules. Every function here is top-level (picklable by reference)
and returns plain picklable data.

Why a separate process at all: exiv2 error paths have crashed the whole
application on Windows with access violations that no try/except can catch
(observed 2026-07-18 on a Canon DNG with a corrupt maker note, and once on a
sidecar write). pyexiv2 also documents itself as not thread safe due to C++
globals. Running every exiv2 call in a dedicated helper process turns any
such crash into a catchable error: the helper dies, Cammello survives.

0.12.9: pyexiv2 is imported LAZILY, inside _require(). The GUI process also
imports this module - iptc.py needs the function objects to hand to the
executor (pickled by reference) - and a top-level import therefore loaded
the crash-prone native library into exactly the process the whole
architecture keeps it out of. The functions only ever RUN in the helper, so
the import now happens there, on first use.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:                       # never true at runtime
    # Bundlers (py2app, PyInstaller) build their module graph from bytecode
    # imports. The real import below lives inside _require() and stays lazy;
    # this dead-but-compiled import guarantees pyexiv2 is still PACKAGED.
    # (`if False:` would not work - CPython folds it away entirely.)
    import pyexiv2                      # noqa: F401

_PYEXIV2 = None
_PYEXIV2_ERROR = None


def _require():
    """Import pyexiv2 on first use (in the helper process) and return it."""
    global _PYEXIV2, _PYEXIV2_ERROR
    if _PYEXIV2 is None and _PYEXIV2_ERROR is None:
        try:
            import pyexiv2
            _PYEXIV2 = pyexiv2
        except Exception as e:          # pragma: no cover - optional dep
            _PYEXIV2_ERROR = str(e)
    if _PYEXIV2 is None:
        raise RuntimeError('pyexiv2 is not available in the helper process: '
                           + (_PYEXIV2_ERROR or 'unknown import error'))
    return _PYEXIV2


def read_iptc_raw(path):
    px = _require()
    img = px.Image(path)
    try:
        return img.read_iptc() or {}
    finally:
        img.close()


def read_xmp_raw(path):
    px = _require()
    img = px.Image(path)
    try:
        return img.read_xmp() or {}
    finally:
        img.close()


def write_xmp_raw(path, payload):
    px = _require()
    img = px.Image(path)
    try:
        img.modify_xmp(payload)
    finally:
        img.close()


def modify_all_raw(path, iim_payload, xmp_payload):
    """One open for both families - IIM and XMP - like iptc.write_iptc
    always did."""
    px = _require()
    img = px.Image(path)
    try:
        if iim_payload:
            img.modify_iptc(iim_payload)
        if xmp_payload:
            img.modify_xmp(xmp_payload)
    finally:
        img.close()
