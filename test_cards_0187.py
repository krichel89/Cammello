"""Hidden dot files, subfolders, and opening a card by itself (0.18.7).

Harald: "cammello findet da immer noch einige versteckte Dateien, die der
Finder nicht findet, mit Punkt am Anfang. Außerdem hätte ich gerne das neu
eingesteckte SD Karte sofort geöffnet wird, gegebenenfalls auch mit allen
Unterverzeichnissen."

The dot files are macOS AppleDouble companions: a card that has been in a
Mac carries "._IMG_0001.CR3" beside every "IMG_0001.CR3", plus .Trashes and
.Spotlight-V100. They have picture extensions, and "._IMG_0001" is a
different stem from "IMG_0001", so they used to arrive as extra entries -
one unreadable ghost per real picture.

Defended here:

  1. a leading dot is skipped, whatever the extension,
  2. a hidden FOLDER is not descended into either,
  3. the scan report counts them, so the log says why the numbers moved,
  4. recursive scanning finds pictures in subfolders,
  5. and does NOT merge IMG_0001 from two DCIM folders into one entry -
     that would hide a picture,
  6. flat scanning is unchanged, and is still the default,
  7. a volume counts as a card only when it has a DCIM folder,
  8. only volumes that APPEAR count as new, and the folder handed over is
     the DCIM folder.
"""
import os
import shutil
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import Cammello        # the shim; also puts the package on the path
from cammello import camera, culling

fails = []


def check(name, cond, detail=''):
    print(('PASS' if cond else 'FAIL'), name, detail)
    if not cond:
        fails.append(name)


check('the shim still exposes the package', hasattr(Cammello, 'main'))


def touch(*parts):
    path = os.path.join(*parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('x')
    return path


# ── A card as macOS leaves it ────────────────────────────────────────────────

card = tempfile.mkdtemp()
dcim = os.path.join(card, 'DCIM')
for n in (1, 2, 3):
    touch(dcim, '100EOSR5', f'IMG_{n:04d}.CR3')
    touch(dcim, '100EOSR5', f'IMG_{n:04d}.JPG')
    touch(dcim, '100EOSR5', f'._IMG_{n:04d}.CR3')      # AppleDouble
    touch(dcim, '100EOSR5', f'._IMG_{n:04d}.JPG')
touch(dcim, '101EOSR5', 'IMG_0001.CR3')                # same number again
touch(dcim, '101EOSR5', 'IMG_0009.CR3')
touch(card, '.Trashes', 'IMG_7777.JPG')                # hidden folder
touch(card, '.Spotlight-V100', 'store.db')
touch(dcim, '100EOSR5', '.DS_Store')
touch(card, 'MISC', 'GPS.LOG')


# ── 1./2./3. hidden ──────────────────────────────────────────────────────────

check('a leading dot is hidden', culling.is_hidden_name('._IMG_0001.CR3'))
check('a hidden folder name too', culling.is_hidden_name('.Trashes'))
check('an ordinary name is not', not culling.is_hidden_name('IMG_0001.CR3'))

flat = os.path.join(dcim, '100EOSR5')
report = {}
items = culling.scan_folder(flat, report)
check('the AppleDouble ghosts are gone',
      [i.stem for i in items] == ['IMG_0001', 'IMG_0002', 'IMG_0003'],
      str([i.stem for i in items]))
check('every entry has both halves of its pair',
      all(i.raw_path and i.jpg_path for i in items))
check('the report counts the hidden names', report['hidden'] == 7,
      str(report['hidden']))
check('the report line says so',
      'hidden (leading dot)' in culling.scan_report_text(report))
check('no hidden file was counted as a picture',
      report['accepted'] == 6, str(report['accepted']))


# ── 4./5./6. subfolders ──────────────────────────────────────────────────────

report2 = {}
deep = culling.scan_folder(dcim, report2, recursive=True)
check('recursive finds both DCIM folders', len(deep) == 5,
      str([i.stem for i in deep]))
folders = {os.path.basename(os.path.dirname(i.raw_path)) for i in deep}
check('from 100EOSR5 and 101EOSR5', folders == {'100EOSR5', '101EOSR5'},
      str(folders))

same_number = [i for i in deep if i.stem == 'IMG_0001']
check('IMG_0001 exists twice and is NOT merged', len(same_number) == 2,
      str(len(same_number)))
check('the two IMG_0001 entries point at different files',
      same_number[0].raw_path != same_number[1].raw_path)
check('the one with a JPEG partner kept it',
      sorted(bool(i.jpg_path) for i in same_number) == [False, True])

check('the hidden folder was never descended into',
      not any('Trashes' in (i.jpg_path or '') for i in deep))

flat_dcim = culling.scan_folder(dcim)
check('flat scanning is unchanged: DCIM itself holds no pictures',
      flat_dcim == [], str(flat_dcim))
check('and flat is still the default',
      culling.scan_folder(flat) == culling.scan_folder(flat, None, False)
      or [i.stem for i in culling.scan_folder(flat)]
      == [i.stem for i in culling.scan_folder(flat, None, False)])


# ── 7./8. the card watch ─────────────────────────────────────────────────────

check('a volume with DCIM is a card', camera.card_folder(card) == dcim,
      str(camera.card_folder(card)))

not_a_card = tempfile.mkdtemp()
touch(not_a_card, 'notes.txt')
check('a plain stick is not a card',
      camera.card_folder(not_a_card) is None)
check('an unreadable path is not a card either',
      camera.card_folder(os.path.join(card, 'nope')) is None)

check('only volumes that appeared count',
      camera.new_cards({card}, {card}) == [])
check('a card that turns up is reported with its DCIM folder',
      camera.new_cards({not_a_card}, {not_a_card, card}) == [dcim],
      str(camera.new_cards({not_a_card}, {not_a_card, card})))
check('a stick that turns up is not reported',
      camera.new_cards({card}, {card, not_a_card}) == [])
check('a volume that disappears is not reported',
      camera.new_cards({card, not_a_card}, {not_a_card}) == [])

roots = camera.volume_roots()
check('this platform names its mount roots (or uses drive letters)',
      isinstance(roots, list))
check('listing volumes never raises',
      isinstance(camera.list_volumes(), set))

for d in (card, not_a_card):
    shutil.rmtree(d, ignore_errors=True)

print()
print('FAILURES:', ', '.join(fails) if fails else 'none')
sys.exit(1 if fails else 0)
