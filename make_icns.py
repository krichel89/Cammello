#!/usr/bin/env python3
"""Build the rounded macOS icon set from cammello/assets/icon.png (0.14.3).

Why this exists as a separate script: the same rounding lives in the
GitHub Actions workflow, and that only ever runs in CI. If the .app is
built anywhere else - locally with py2app or PyInstaller, or by hand -
the workflow never touches it and the icon stays square. Run this once,
and the .icns is ready for whatever does the packaging.

    python3 make_icns.py

Writes:
    cammello/assets/icon.icns          the icon set for the .app bundle
    cammello/assets/icon_rounded.png   1024 px, used by the splash/About

macOS does NOT round app icons itself: the artwork has to carry the shape.
Apple's grid puts the rounded body at 824 of 1024 px, and its outline is a
SUPERELLIPSE (|x|^n + |y|^n = 1, n ~ 5), not a rounded rectangle - a plain
corner radius reads subtly wrong next to system icons.

Needs Pillow. `iconutil` and `sips` are macOS tools; on other systems the
PNG is still written and the .icns step is skipped with a note.
"""
import os
import shutil
import subprocess
import sys

try:
    from PIL import Image, ImageDraw
except ImportError:
    sys.exit('Pillow is required: pip install pillow')

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'cammello', 'assets', 'icon.png')
OUT_PNG = os.path.join(HERE, 'cammello', 'assets', 'icon_rounded.png')
OUT_ICNS = os.path.join(HERE, 'cammello', 'assets', 'icon.icns')
ICONSET = os.path.join(HERE, 'icon.iconset')

SIZE, CONTENT = 1024, 824


def squircle(size, n=5.0, ss=8):
    """The mask, drawn oversampled and scaled down - that is what
    antialiases the curve."""
    big = size * ss
    m = Image.new('L', (big, big), 0)
    d = ImageDraw.Draw(m)
    a = big / 2.0
    for y in range(big):
        dy = abs((y + 0.5 - a) / a) ** n
        if dy >= 1.0:
            continue
        dx = (1.0 - dy) ** (1.0 / n)
        d.line([(a - dx * a, y), (a + dx * a, y)], fill=255)
    return m.resize((size, size), Image.LANCZOS)


def main():
    if not os.path.exists(SRC):
        sys.exit(f'Source artwork not found: {SRC}')
    src = Image.open(SRC).convert('RGBA')
    if min(src.size) < CONTENT:
        print(f'Note: the source is {src.size[0]}x{src.size[1]} px and will '
              f'be scaled up to {CONTENT}. Large icon sizes stay slightly '
              f'soft; a bigger original would fix that.')

    art = src.resize((CONTENT, CONTENT), Image.LANCZOS)
    art.putalpha(squircle(CONTENT))
    canvas = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
    off = (SIZE - CONTENT) // 2
    canvas.paste(art, (off, off), art)
    canvas.save(OUT_PNG)
    print(f'Wrote {OUT_PNG}')

    if sys.platform != 'darwin' or not shutil.which('iconutil'):
        print('Not on macOS (or iconutil missing) - skipping the .icns step.')
        return 0

    # The set needs every size from 16 to 1024, or the Finder sidebar and
    # the "Get Info" panel fall back to a generic icon.
    if os.path.isdir(ICONSET):
        shutil.rmtree(ICONSET)
    os.makedirs(ICONSET)
    for size in (16, 32, 64, 128, 256, 512):
        for scale, suffix in ((1, ''), (2, '@2x')):
            px = size * scale
            canvas.resize((px, px), Image.LANCZOS).save(
                os.path.join(ICONSET, f'icon_{size}x{size}{suffix}.png'))
    subprocess.run(['iconutil', '-c', 'icns', ICONSET, '-o', OUT_ICNS],
                   check=True)
    shutil.rmtree(ICONSET)
    print(f'Wrote {OUT_ICNS}')
    print('\nIf the old icon sticks around after rebuilding the app, macOS '
          'is caching it:\n'
          '    touch <path to>/Cammello.app && killall Dock\n'
          'Moving the bundle to a different folder also clears it.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
