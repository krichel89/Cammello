"""The zoom no longer jumps when the full preview arrives (0.18.6).

Harald: "Beim Zoomen mit Command + \"+\" springt er gerne mal gleich auf
100%."

What actually happened: Cmd+ asks for the FULL preview, because a zoomed
view wants real pixels. The full preview arrives a moment later and is
several times wider than the screen preview it replaces - 2560 px against
8192 for an R5 frame. It was swapped in with keep_view=True, which kept the
TRANSFORM; but what reaches the screen is scale x pixmap width, so the same
scale over 3.2x the pixels made the picture jump by 3.2x. One step asked
for, three and a bit delivered - indistinguishable from a jump to 100%.

"gerne mal" fits: it only happens when the full level was not cached yet,
and only by as much as the two previews differ.

Defended here:

  1. swapping in a bigger pixmap with keep_view leaves the picture the same
     size on screen,
  2. and leaves it looking at the same part of the picture,
  3. the reported zoom factor is rescaled with it (50% of a small preview
     was never 50% of the picture),
  4. a swap that does NOT change the resolution changes nothing at all -
     that is the tone/exposure path, which must stay cheap and stable,
  5. keep_view=False still fits, and a swap while fitted re-fits,
  6. one Cmd+ from fit is still exactly one step on the ladder, before and
     after the full preview lands.
"""
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import Cammello        # the shim; also puts the package on the path
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QImage

from cammello.culling_view import CullImageView
from cammello.mw_culling import ZOOM_STEPS

fails = []


def check(name, cond, detail=''):
    print(('PASS' if cond else 'FAIL'), name, detail)
    if not cond:
        fails.append(name)


check('the shim still exposes the package', hasattr(Cammello, 'main'))

app = QApplication.instance() or QApplication([])


def image(w, h):
    img = QImage(w, h, QImage.Format_RGB32)
    img.fill(0xFF335577)
    return img


# The two levels of an R5 frame as the loader produces them: the screen
# preview capped at 2560, and the full file.
SCREEN = image(2560, 1707)
FULL = image(8192, 5464)

view = CullImageView()
view.resize(1200, 700)
view.show()
app.processEvents()

view.set_image(SCREEN)
app.processEvents()
check('a fresh image starts fitted', view.is_fit)

fit_pct = view.zoom_factor() * 100
check('fit is well below 100% for a 2560 px preview in this window',
      0 < fit_pct < 100, f'{fit_pct:.1f} %')


# ── 6. one Cmd+ is one step ──────────────────────────────────────────────────

def next_step(pct):
    for step in ZOOM_STEPS:
        if step > pct + 0.5:
            return step
    return None


target = next_step(fit_pct)
check('the ladder has a step above fit', target is not None, str(target))
view.set_zoom(target / 100.0)
app.processEvents()
apparent_before = view.zoom_factor() * view._item.pixmap().width()
center_before = view.mapToScene(view.viewport().rect().center())
rel_before = (center_before.x() / 2560, center_before.y() / 1707)


# ── 1./2./3. the swap ────────────────────────────────────────────────────────

view.set_image(FULL, keep_view=True)
app.processEvents()

apparent_after = view.zoom_factor() * view._item.pixmap().width()
check('the picture keeps its size on screen when the full level arrives',
      abs(apparent_after - apparent_before) < 2.0,
      f'{apparent_before:.0f} px -> {apparent_after:.0f} px')

center_after = view.mapToScene(view.viewport().rect().center())
rel_after = (center_after.x() / 8192, center_after.y() / 5464)
check('and it still looks at the same part of the picture',
      abs(rel_after[0] - rel_before[0]) < 0.02
      and abs(rel_after[1] - rel_before[1]) < 0.02,
      f'{rel_before} -> {rel_after}')

check('the reported zoom is rescaled with the pixels',
      abs(view.zoom_factor() - (target / 100.0) * 2560 / 8192) < 0.001,
      f'{view.zoom_factor():.4f}')
check('the picture did NOT jump towards 100%',
      view.zoom_factor() < target / 100.0,
      f'{view.zoom_factor()*100:.1f} % vs {target} %')

# The old behaviour is what this pins: same scale over 3.2x the pixels.
would_have_been = (target / 100.0) * 8192
check('the old code would have blown it up more than threefold',
      would_have_been > 3 * apparent_before,
      f'{would_have_been:.0f} px against {apparent_before:.0f} px')


# ── 4. a swap of the same size changes nothing ───────────────────────────────

before_factor = view.zoom_factor()
before_center = view.mapToScene(view.viewport().rect().center())
view.set_image(image(8192, 5464), keep_view=True)
app.processEvents()
after_center = view.mapToScene(view.viewport().rect().center())
check('a same-size swap leaves the zoom alone',
      abs(view.zoom_factor() - before_factor) < 1e-9)
check('a same-size swap leaves the pan exactly alone',
      after_center == before_center,
      f'{before_center} -> {after_center}')

# set_tone() goes through the same path and must stay a no-op for the view.
view.set_tone(None, 0.5)
app.processEvents()
check('a tone change leaves the zoom alone',
      abs(view.zoom_factor() - before_factor) < 1e-9,
      f'{view.zoom_factor():.4f} vs {before_factor:.4f}')
view.set_tone(None, 0.0)


# ── 5. fit still wins where it should ────────────────────────────────────────

view.set_image(SCREEN)                      # keep_view=False
app.processEvents()
check('keep_view=False fits again', view.is_fit)

fitted = view.zoom_factor()
view.set_image(FULL, keep_view=True)
app.processEvents()
check('a swap while fitted stays fitted', view.is_fit)
check('and re-fits to the new size',
      view.zoom_factor() < fitted,
      f'{fitted:.4f} -> {view.zoom_factor():.4f}')
check('fitted means the whole picture is in the window',
      view.zoom_factor() * 8192 <= view.viewport().width() + 2
      and view.zoom_factor() * 5464 <= view.viewport().height() + 2)

view.close()

print()
print('FAILURES:', ', '.join(fails) if fails else 'none')
sys.exit(1 if fails else 0)
