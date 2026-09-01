"""Moving a whole RAW/JPEG group out of the culling folder (0.18.2).

Harald: "Beim Culling möchte ich das ganze RAW/JPG Paar mit sidecar
verschieben können."

The point of the feature is the word GANZE. "Save to…" may honour the pair
selector, because a copy leaves the original where it is. A move may not:
carrying off only the JPEG leaves a RAW behind and an .xmp describing a
file that is no longer next to it.

What is defended here:

  1. group_paths() takes RAW, JPEG and sidecar - and nothing twice,
  2. move_collisions() names what is already in the target,
  3. the worker actually moves: the source is gone, the target is there,
  4. an existing target file is never overwritten (checked at the worker
     level too, not only in the dialog),
  5. a move does NOT render an edited copy - the original travels,
  6. cancelling stops between files and leaves the rest alone.
"""
import os
import shutil
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import Cammello        # the shim; also puts the package on the path
from cammello import culling
from cammello.mw_culling import _FolderCopyWorker

fails = []


def check(name, cond, detail=''):
    print(('PASS' if cond else 'FAIL'), name, detail)
    if not cond:
        fails.append(name)


check('the shim still exposes the package', hasattr(Cammello, 'main'))


class Item:
    """The three attributes group_paths reads off a strip entry."""
    def __init__(self, raw=None, jpg=None, sidecar=None, display=None):
        self.raw_path = raw
        self.jpg_path = jpg
        self.sidecar_path = sidecar
        self.display_path = display or jpg or raw


# ── group_paths ──────────────────────────────────────────────────────────
pair = Item(raw='/f/A.CR2', jpg='/f/A.JPG', sidecar='/f/A.xmp')
check('a pair gives RAW, JPEG and sidecar',
      culling.group_paths(pair) == ['/f/A.CR2', '/f/A.JPG', '/f/A.xmp'],
      str(culling.group_paths(pair)))

single = Item(jpg='/f/B.JPG')
check('a lone JPEG gives just itself',
      culling.group_paths(single) == ['/f/B.JPG'],
      str(culling.group_paths(single)))

raw_only = Item(raw='/f/C.NEF', sidecar='/f/C.xmp', display='/f/C.NEF')
check('a RAW without a JPEG keeps its sidecar, and itself only once',
      culling.group_paths(raw_only) == ['/f/C.NEF', '/f/C.xmp'],
      str(culling.group_paths(raw_only)))

check('an entry with nothing on it gives an empty list',
      culling.group_paths(Item()) == [])

# ── move_collisions ──────────────────────────────────────────────────────
src = tempfile.mkdtemp()
dst = tempfile.mkdtemp()
for name in ('A.CR2', 'A.JPG', 'A.xmp'):
    with open(os.path.join(src, name), 'w', encoding='utf-8') as fh:
        fh.write(name)
paths = [os.path.join(src, n) for n in ('A.CR2', 'A.JPG', 'A.xmp')]

check('an empty target has no collisions',
      culling.move_collisions(paths, dst) == [])
with open(os.path.join(dst, 'A.JPG'), 'w', encoding='utf-8') as fh:
    fh.write('older')
check('a name already there is reported',
      culling.move_collisions(paths, dst) == ['A.JPG'],
      str(culling.move_collisions(paths, dst)))
os.remove(os.path.join(dst, 'A.JPG'))


# ── The worker moves ─────────────────────────────────────────────────────
class Log:
    def info(self, *a, **k):
        pass

    def error(self, *a, **k):
        pass

    def warning(self, *a, **k):
        pass


worker = _FolderCopyWorker(paths, dst, Log(), move=True)
worker.run()                      # run() directly - no thread, no event loop
check('every file arrived',
      all(os.path.exists(os.path.join(dst, n))
          for n in ('A.CR2', 'A.JPG', 'A.xmp')))
check('and none is left behind',
      not any(os.path.exists(p) for p in paths))
check('the worker reports what it moved', sorted(worker.moved) == sorted(paths))

# ── An existing target file is never overwritten ─────────────────────────
src2 = tempfile.mkdtemp()
keep = os.path.join(src2, 'A.JPG')
with open(keep, 'w', encoding='utf-8') as fh:
    fh.write('newer')
worker2 = _FolderCopyWorker([keep], dst, Log(), move=True)
worker2.run()
with open(os.path.join(dst, 'A.JPG'), encoding='utf-8') as fh:
    check('the file in the target folder is untouched', fh.read() == 'A.JPG')
check('and the source still exists - nothing was destroyed',
      os.path.exists(keep))
check('the skipped file is not reported as moved', worker2.moved == [])

# ── A move does not render an edited copy ────────────────────────────────
# edit_map is what "Save to…" uses to export a rendered "<stem>_edit.jpg".
# On a move that would leave the original behind under a different name and
# Harald would lose the RAW's partner, so the map is ignored.
src3 = tempfile.mkdtemp()
dst3 = tempfile.mkdtemp()
edited = os.path.join(src3, 'D.JPG')
with open(edited, 'w', encoding='utf-8') as fh:
    fh.write('original bytes')
worker3 = _FolderCopyWorker([edited], dst3, Log(),
                            edit_map={edited: {'ev': 1.0}}, move=True)
worker3.run()
check('the original name arrives, not an _edit.jpg',
      os.path.exists(os.path.join(dst3, 'D.JPG'))
      and not os.path.exists(os.path.join(dst3, 'D_edit.jpg')),
      str(sorted(os.listdir(dst3))))
with open(os.path.join(dst3, 'D.JPG'), encoding='utf-8') as fh:
    check('with the original bytes', fh.read() == 'original bytes')

# ── Cancelling ───────────────────────────────────────────────────────────
src4 = tempfile.mkdtemp()
dst4 = tempfile.mkdtemp()
many = []
for i in range(4):
    p = os.path.join(src4, f'E{i}.JPG')
    with open(p, 'w', encoding='utf-8') as fh:
        fh.write(str(i))
    many.append(p)
worker4 = _FolderCopyWorker(many, dst4, Log(), move=True)
worker4.cancel()
worker4.run()
check('a cancel before the first file moves nothing',
      os.listdir(dst4) == [] and all(os.path.exists(p) for p in many),
      str(os.listdir(dst4)))

for d in (src, dst, src2, src3, dst3, src4, dst4):
    shutil.rmtree(d, ignore_errors=True)

print()
print('FAILURES:', ', '.join(fails) if fails else 'none')
sys.exit(1 if fails else 0)
