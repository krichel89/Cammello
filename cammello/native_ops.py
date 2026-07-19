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
"""
try:
    import pyexiv2
except Exception:                       # pragma: no cover - optional dep
    pyexiv2 = None


def _require():
    if pyexiv2 is None:
        raise RuntimeError('pyexiv2 is not available in the helper process')


def read_iptc_raw(path):
    _require()
    img = pyexiv2.Image(path)
    try:
        return img.read_iptc() or {}
    finally:
        img.close()


def read_xmp_raw(path):
    _require()
    img = pyexiv2.Image(path)
    try:
        return img.read_xmp() or {}
    finally:
        img.close()


def write_xmp_raw(path, payload):
    _require()
    img = pyexiv2.Image(path)
    try:
        img.modify_xmp(payload)
    finally:
        img.close()


def modify_all_raw(path, iim_payload, xmp_payload):
    """One open for both families - IIM and XMP - like iptc.write_iptc
    always did."""
    _require()
    img = pyexiv2.Image(path)
    try:
        if iim_payload:
            img.modify_iptc(iim_payload)
        if xmp_payload:
            img.modify_xmp(xmp_payload)
    finally:
        img.close()
