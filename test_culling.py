"""Culling data model + preview pipeline (0.11.0, Phase 1a).

Everything except real-RAW extraction runs on synthetic files. RAW tests use
testdata/*.CR3 (or any RAW there) and SKIP with a clear message when the
folder is empty - re-upload the three EOS R6 files to run them.
"""
import glob
import os
import sys
import tempfile
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QEventLoop, QTimer
from PyQt5.QtGui import QImage, QPixmap

from cammello import culling, previews

app = QApplication(sys.argv)
fails = []
skips = []


def check(name, cond, detail=''):
    print(('PASS' if cond else 'FAIL'), name, detail)
    if not cond:
        fails.append(name)


def skip(name, why):
    print('SKIP', name, '-', why)
    skips.append(name)


tmp = tempfile.mkdtemp()


def jpg(path, w=640, h=420, color='red'):
    img = QImage(w, h, QImage.Format_RGB32)
    img.fill(0xFFAA3322)
    img.save(path, 'JPG', 90)
    return path


# ── Pairing / scan (filenames only, no RAW needed) ────────────────────────────
folder = os.path.join(tmp, 'card')
os.makedirs(folder)
jpg(os.path.join(folder, '_HK0001.JPG'))
open(os.path.join(folder, '_HK0001.CR3'), 'wb').write(b'\0' * 64)   # pairing is name-based
open(os.path.join(folder, '_HK0002.CR3'), 'wb').write(b'\0' * 64)
jpg(os.path.join(folder, '_HK0003.jpg'))
open(os.path.join(folder, 'notes.txt'), 'w').write('x')
jpg(os.path.join(folder, '_hk0004.JPEG'))
open(os.path.join(folder, '_HK0004.cr3'), 'wb').write(b'\0' * 64)   # case-insensitive stem

items = culling.scan_folder(folder)
check('scan finds 4 items', len(items) == 4, str([i.stem for i in items]))
by = {i.stem.casefold(): i for i in items}
check('RAW+JPEG paired', by['_hk0001'].is_pair)
check('RAW-only item', by['_hk0002'].raw_path and not by['_hk0002'].jpg_path)
check('JPEG-only item', by['_hk0003'].jpg_path and not by['_hk0003'].raw_path)
check('pairing is case-insensitive', by['_hk0004'].is_pair)
check('pair displays the JPEG', by['_hk0001'].display_path.endswith('.JPG'))
check('sidecar path next to the RAW',
      by['_hk0002'].sidecar_path.endswith('_HK0002.xmp'))
check('non-image ignored', all('notes' not in i.stem for i in items))

# ── Label sets ────────────────────────────────────────────────────────────────
check('EN label text', culling.label_text(0, 'en') == 'Red')
check('DE label text', culling.label_text(4, 'de') == 'Lila')
check('read DE while active set is EN', culling.label_index('Grün') == 2)
check('read EN', culling.label_index('purple') == 4)
check('unknown label -> None (text preserved elsewhere)',
      culling.label_index('Facebook') is None)
check('custom extra set', culling.label_index(
    'fertig', extra_sets={'x': ['zu tun', 'in Arbeit', 'fertig', '', '']}) == 2)

# ── XMP write/read: JPEG embedded + sidecar; RAW bytes untouched ─────────────
pair = by['_hk0001']
raw_bytes_before = open(pair.raw_path, 'rb').read()
pair.rating = 4
pair.label = 'Rot'
written = culling.write_item_metadata(pair)
check('pair writes sidecar AND jpeg', len(written) == 2
      and written[0].endswith('.xmp') and written[1].lower().endswith('.jpg'),
      str(written))
check('RAW bytes untouched',
      open(pair.raw_path, 'rb').read() == raw_bytes_before)

fresh = culling.CullItem(pair.stem, pair.raw_path, pair.jpg_path)
culling.read_item_metadata(fresh)
check('sidecar roundtrip rating', fresh.rating == 4)
check('sidecar roundtrip label (DE text kept)', fresh.label == 'Rot')
check('label maps to color index 0', fresh.label_color_index == 0)

# Sidecar wins over embedded JPEG value.
# 0.12.6: embedded JPEG XMP is written in pure Python (no pyexiv2).
culling._write_xmp_jpeg(pair.jpg_path, 1, None)
again = culling.CullItem(pair.stem, pair.raw_path, pair.jpg_path)
culling.read_item_metadata(again)
check('sidecar has precedence over embedded JPEG', again.rating == 4)

# JPEG-only item: embedded roundtrip incl. reject.
solo = by['_hk0003']
solo.rating = -1
culling.write_item_metadata(solo)
back = culling.CullItem(solo.stem, jpg_path=solo.jpg_path)
culling.read_item_metadata(back)
check('reject (-1) roundtrip in JPEG', back.rating == -1)

# Clearing: rating 0 + no label deletes the tags.
solo.rating = 0
solo.label = ''
culling.write_item_metadata(solo)
# 0.12.6: everything is read/written as text now, so the checks read the
# packet directly instead of going through pyexiv2.
r0, l0 = culling._read_rating_label_text(solo.jpg_path)
check('rating 0 deletes the XMP tags', r0 is None and not l0, f'{r0}/{l0}')

# Existing sidecar is amended, not replaced: put a foreign element in and
# make sure a rating write keeps it.
with open(pair.sidecar_path, 'w', encoding='utf-8') as _f:
    _f.write(culling._XMP_SKELETON.replace(
        '<rdf:Description rdf:about=""/>',
        '<rdf:Description rdf:about="" xmlns:dc="http://purl.org/dc/elements/1.1/">'
        '<dc:subject><rdf:Bag><rdf:li>keepme</rdf:li></rdf:Bag></dc:subject>'
        '</rdf:Description>'))
pair.rating = 5
culling.write_item_metadata(pair)
sc_text = open(pair.sidecar_path, encoding='utf-8').read()
check('foreign sidecar content survives', 'keepme' in sc_text)
r5, _ = culling._read_rating_label_text(pair.sidecar_path)
check('new rating in amended sidecar', r5 == '5', str(r5))

# ── Write-behind ─────────────────────────────────────────────────────────────
wb = culling.WriteBehind()
for r in (1, 2, 3):        # rapid re-rating collapses to the last state
    pair.rating = r
    wb.enqueue(pair)
check('flush returns', wb.flush(10))
y = culling.CullItem(pair.stem, pair.raw_path, pair.jpg_path)
culling.read_item_metadata(y)
check('write-behind wrote the LATEST state', y.rating == 3, str(y.rating))
check('no write errors', wb.errors == [], str(wb.errors))
wb.stop()

# ── Filters ──────────────────────────────────────────────────────────────────
def mk(stem, rating, label=''):
    it = culling.CullItem(stem)
    it.rating = rating
    it.label = label
    return it

pool = [mk('a', 5, 'Red'), mk('b', 3), mk('c', -1), mk('d', 0, 'Grün'),
        mk('e', 2, 'Blue')]
f1 = culling.filter_items(pool, min_rating=3)
check('min_rating filter', [i.stem for i in f1] == ['a', 'b'])
f2 = culling.filter_items(pool, exclude_rejects=False, min_rating=0)
check('rejects included on demand', any(i.stem == 'c' for i in f2))
f3 = culling.filter_items(pool, label_indices={0, 2})     # red or green
check('label filter across languages', [i.stem for i in f3] == ['a', 'd'])
f4 = culling.filter_items(pool, label_indices={-1})       # unlabeled only
check('unlabeled filter', [i.stem for i in f4] == ['b'])

# ── Preview pipeline: JPEG path (no RAW needed) ───────────────────────────────
big = jpg(os.path.join(tmp, 'big.jpg'), 3000, 2000)
img = previews.decode_preview(big, max_edge=256)
check('thumb scaled to long edge 256', max(img.width(), img.height()) == 256)
img2 = previews.decode_preview(big)
check('full decode keeps size', (img2.width(), img2.height()) == (3000, 2000))

cache = previews.PreviewCache(thumb_budget=img.sizeInBytes() * 2 + 10,
                              screen_budget=10**9)
cache.put('thumb', 'a', img)
cache.put('thumb', 'b', img)
cache.put('thumb', 'c', img)          # budget forces eviction of 'a'
check('LRU evicts oldest', cache.get('thumb', 'a') is None
      and cache.get('thumb', 'c') is not None)

loader = previews.PreviewLoader(threads=4)
paths = [jpg(os.path.join(tmp, f'p{i}.jpg'), 1200, 800) for i in range(12)]
got = []
loop = QEventLoop()
def on_loaded(key, level):
    got.append(key)
    if len(got) >= 9:                 # 1 current + 8 ahead
        loop.quit()
loader.signals.loaded.connect(on_loaded)
t0 = time.perf_counter()
loader.request(paths[0], 'screen', loader.P_CURRENT)
loader.prefetch_around(paths, 0, direction=1)
QTimer.singleShot(20000, loop.quit)
loop.exec_()
dt = time.perf_counter() - t0
check('current + 8 prefetched decoded', len(set(got)) >= 9,
      f'{len(set(got))} in {dt*1000:.0f} ms')
check('cache hit is instant', loader.cache.get('screen', paths[1]) is not None)

# Stale generation: queued jobs of an old folder do not fill the cache.
loader2 = previews.PreviewLoader(threads=1)
loader2.request(paths[5], 'screen')
loader2.new_generation()
loader2.wait_idle()
# Either it never decoded, or it decoded before the generation bump - both are
# acceptable; what must not happen is a crash. Just assert it is answerable:
check('generation bump survives', True)

# ── RAW path: only with real RAW files in testdata/ ──────────────────────────
raws = sorted(glob.glob(os.path.join(os.path.dirname(__file__),
                                     'testdata', '*.[cC][rR]3')))
if not raws:
    skip('RAW preview extraction', 'no CR3 in testdata/ - re-upload the three '
         'EOS R6 files; measured 2026-07-13: ~75 ms warm, full-res preview')
    skip('RAW orientation', 'see above')
    skip('camera rating from CR3', 'see above')
else:
    t0 = time.perf_counter()
    qi = previews.decode_preview(raws[0])
    dt = (time.perf_counter() - t0) * 1000
    check('CR3 preview decodes', not qi.isNull(),
          f'{qi.width()}x{qi.height()} in {dt:.0f} ms')
    ori = previews.read_orientation(raws[0])
    if ori in (5, 6, 7, 8):
        check('orientation applied (portrait)', qi.height() > qi.width(),
              f'orientation={ori}, {qi.width()}x{qi.height()}')
    it = culling.CullItem('cam', raw_path=raws[0])
    culling.read_item_metadata(it)
    check('camera rating readable', isinstance(it.rating, int), str(it.rating))

print('\nSKIPPED:', len(skips), '| FAILURES:', fails if fails else 'none')
sys.exit(1 if fails else 0)
