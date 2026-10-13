#!/usr/bin/env python3
"""Declare the .cammello file type in the macOS app bundle (0.18.29).

    python3 make_bundle_types.py dist/Cammello.app/Contents/Info.plist

Why a separate script: PyInstaller writes the bundle's Info.plist and knows
nothing about document types, and macOS only hands a double-clicked file to
an app that DECLARES the type there. With the declaration, a double click on
Berlinale_2026.cammello starts (or tells) Cammello, which receives it as a
QFileOpenEvent (see _OpenFileFilter in main_window.py).

It runs in the build workflow BEFORE code signing: the plist is part of the
signature, so editing it afterwards would break it.

Idempotent (running it twice changes nothing more) and strict: the exit code
is non-zero when the result does not read back as declared, so a build never
ships an app that silently ignores the file type.
"""
import plistlib
import sys

EXTENSION = 'cammello'
UTI = 'de.krichel.cammello.workflow'
DESCRIPTION = 'Cammello workflow'


def declare(info):
    """Return `info` (a dict from an Info.plist) with the type declared."""
    doc_types = [d for d in info.get('CFBundleDocumentTypes', [])
                 if EXTENSION not in (d.get('CFBundleTypeExtensions') or [])]
    doc_types.append({
        'CFBundleTypeName': DESCRIPTION,
        'CFBundleTypeExtensions': [EXTENSION],
        'CFBundleTypeRole': 'Viewer',
        'LSHandlerRank': 'Owner',
        'LSItemContentTypes': [UTI],
    })
    info['CFBundleDocumentTypes'] = doc_types
    exported = [d for d in info.get('UTExportedTypeDeclarations', [])
                if d.get('UTTypeIdentifier') != UTI]
    exported.append({
        'UTTypeIdentifier': UTI,
        'UTTypeDescription': DESCRIPTION,
        'UTTypeConformsTo': ['public.plain-text'],
        'UTTypeTagSpecification': {
            'public.filename-extension': [EXTENSION],
        },
    })
    info['UTExportedTypeDeclarations'] = exported
    return info


def is_declared(info):
    """Whether `info` carries the declaration, in both places."""
    docs = [d for d in info.get('CFBundleDocumentTypes', [])
            if EXTENSION in (d.get('CFBundleTypeExtensions') or [])
            and UTI in (d.get('LSItemContentTypes') or [])]
    exported = [d for d in info.get('UTExportedTypeDeclarations', [])
                if d.get('UTTypeIdentifier') == UTI]
    return len(docs) == 1 and len(exported) == 1


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    target = argv[1]
    with open(target, 'rb') as fh:
        info = plistlib.load(fh)
    declare(info)
    with open(target, 'wb') as fh:
        plistlib.dump(info, fh)
    with open(target, 'rb') as fh:
        ok = is_declared(plistlib.load(fh))
    if not ok:
        print(f'make_bundle_types: {target} does not carry the declaration',
              file=sys.stderr)
        return 1
    print(f'make_bundle_types: .{EXTENSION} declared in {target}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
