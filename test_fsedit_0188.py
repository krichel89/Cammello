"""No editing in fullscreen, and the zoom travels (0.18.8).

Harald: "no edit in Full view, but keep the zoom level while switching"

Fullscreen shows the picture and nothing else. The edit panel is not on
screen there, so crop, white balance and exposure would be changed blind -
and the keys that do it (C, W, plain +/-) sit right next to the rating keys
that fullscreen exists for. Ratings, labels, navigation and zoom keep
working; only the things that change PIXELS are off.

The zoom half is what the zoom is FOR while culling: stepping through a
burst at 100% to see which frame is sharp. It is carried as an ON-SCREEN
WIDTH, not as a scale factor, for the same reason as in 0.18.6 - a factor
only means something against the pixmap it applies to, and the two preview
levels of one picture differ by about three.

Defended here:

  1. the lock answers to fullscreen and nothing else,
  2. crop, pipette, exposure, undo and reset are all refused while it is up,
  3. and none of them changed anything on the way out,
  4. ratings still work in fullscreen - that is what it is for,
  5. the edit panel is not floating over the fullscreen picture,
  6. a crop in progress is cancelled, not committed, when fullscreen starts,
  7. stepping to the next picture keeps the on-screen size and the spot,
  8. a fitted view stays fitted across the step (nothing sticky is kept),
  9. entering fullscreen refits a fitted view but leaves a zoomed one alone.
"""
import os
import shutil
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import Cammello        # the shim; also puts the package on the path
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QSettings, QEventLoop, QTimer
from PyQt5.QtGui import QImage

from cammello import edits
from cammello.constants import APP_NAME
from cammello.culling_view import CullImageView

_ts = QSettings(APP_NAME, 'Main')
_ts.setValue('feature_culling', True)
_ts.sync()

fails = []


def check(name, cond, detail=''):
    print(('PASS' if cond else 'FAIL'), name, detail)
    if not cond:
        fails.append(name)


check('the shim still exposes the package', hasattr(Cammello, 'main'))

app = QApplication.instance() or QApplication([])


def spin(ms=150):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec_()


# ── 7./8. the zoom carried on its own ────────────────────────────────────────

view = CullImageView()
view.resize(1200, 700)
view.show()
app.processEvents()

A = QImage(2560, 1707, QImage.Format_RGB32)
A.fill(0xFF224466)
B = QImage(2560, 1707, QImage.Format_RGB32)
B.fill(0xFF664422)

view.set_image(A)
app.processEvents()
check('a fitted view reports no apparent width',
      view.apparent_width() == 0.0, str(view.apparent_width()))

view.set_zoom(1.0)
app.processEvents()
width = view.apparent_width()
rel = view.relative_center()
check('a zoomed view reports its on-screen width', width == 2560.0, str(width))

view.set_image(B)                 # a plain image change fits
app.processEvents()
check('the next picture starts fitted', view.is_fit)
view.set_apparent_width(width, rel)
app.processEvents()
check('restoring puts it back at the same on-screen size',
      abs(view.apparent_width() - width) < 2.0,
      f'{width} -> {view.apparent_width()}')
after = view.relative_center()
check('and at the same spot in the picture',
      abs(after[0] - rel[0]) < 0.02 and abs(after[1] - rel[1]) < 0.02,
      f'{rel} -> {after}')

# A picture whose preview is a different size still lands at the same size.
C = QImage(8192, 5464, QImage.Format_RGB32)
C.fill(0xFF446622)
view.set_image(C)
app.processEvents()
view.set_apparent_width(width, rel)
app.processEvents()
check('a differently sized preview lands at the same on-screen size',
      abs(view.apparent_width() - width) < 2.0,
      f'{view.apparent_width()}')

check('restoring 0 does nothing', (view.set_apparent_width(0) is None))
view.close()


# ── the window half ──────────────────────────────────────────────────────────

from cammello.logging_setup import setup_logging          # noqa: E402
import logging                                            # noqa: E402

logger, emitter, gui_handler, log_path = setup_logging()
for h in logger.handlers:
    h.setLevel(logging.CRITICAL)

folder = tempfile.mkdtemp()
for i in range(4):
    img = QImage(1200, 800, QImage.Format_RGB32)
    img.fill(0xFF335599 + i * 16)
    img.save(os.path.join(folder, f'IMG_{i:04d}.JPG'), 'JPG', 88)

w = Cammello.MainWindow(logger, emitter, gui_handler, log_path)
w.resize(1200, 800)
w.show()
w.tabs.setCurrentWidget(w._cull_tab_widget)
app.processEvents()
w._cull_open_folder(folder)
app.processEvents()
spin()

check('four pictures are open', len(w._cull_visible) == 4,
      str(len(w._cull_visible)))
w._cull_show_index(0)
app.processEvents()
spin()

path = w._cull_visible[0].display_path


# ── 1./2./3. the lock ────────────────────────────────────────────────────────

check('nothing is locked in the loupe', not w._cull_edits_locked())

w._cull_toggle_fullscreen()
app.processEvents()
check('fullscreen is up', w._cull_fs is not None)
check('and the lock is on', w._cull_edits_locked())

before = dict(edits.get_edit(w._cull_edits, path) or {})

w._cull_toggle_crop()
check('crop is refused in fullscreen',
      not getattr(w, '_cull_cropping', False))
w._cull_set_pipette(True)
check('the pipette is refused in fullscreen',
      not w.cull_view.pipette_active())
w._cull_step_ev(1)
check('exposure is refused in fullscreen',
      edits.get_ev(w._cull_edits, path) == before.get('ev', 0.0),
      str(edits.get_ev(w._cull_edits, path)))
w._cull_reset_edits()
w._cull_undo_edit()
after_edits = dict(edits.get_edit(w._cull_edits, path) or {})
check('nothing was edited while fullscreen was up', after_edits == before,
      f'{before} -> {after_edits}')

# ── 4./5. what fullscreen is for still works ─────────────────────────────────

w._cull_set_rating(3)
app.processEvents()
check('ratings still work in fullscreen',
      w._cull_visible[0].rating == 3 or w._cull_visible[1].rating == 3,
      str([i.rating for i in w._cull_visible]))
check('the edit panel is not floating over the picture',
      not w.cull_edit_panel.isVisible())

w._cull_toggle_fullscreen()
app.processEvents()
check('back out of fullscreen', w._cull_fs is None)
check('and the lock is off again', not w._cull_edits_locked())
# The rating above auto-advanced, so come back to the picture under test.
w._cull_show_index(0)
app.processEvents()
spin()
w._cull_step_ev(1)
check('exposure works again outside fullscreen',
      abs(edits.get_ev(w._cull_edits, path)) > 0,
      str(edits.get_ev(w._cull_edits, path)))
w._cull_reset_edits()


# ── 6. a crop in progress ────────────────────────────────────────────────────

w._cull_toggle_crop()
check('crop mode starts outside fullscreen',
      getattr(w, '_cull_cropping', False))
w._cull_toggle_fullscreen()
app.processEvents()
check('going fullscreen ends the crop',
      not getattr(w, '_cull_cropping', False))
check('and did not commit one',
      'crop' not in (edits.get_edit(w._cull_edits, path) or {}),
      str(edits.get_edit(w._cull_edits, path)))


# ── 9. zoom across the fullscreen switch ─────────────────────────────────────

check('still fullscreen for the zoom check', w._cull_fs is not None)
w.cull_view.set_zoom(0.8)
app.processEvents()
zoomed = w.cull_view.zoom_factor()
w._cull_toggle_fullscreen()
app.processEvents()
check('leaving fullscreen keeps a zoomed view zoomed',
      not w.cull_view.is_fit
      and abs(w.cull_view.zoom_factor() - zoomed) < 1e-6,
      f'{zoomed} -> {w.cull_view.zoom_factor()}')

w.cull_view.fit()
app.processEvents()
w._cull_toggle_fullscreen()
app.processEvents()
check('a fitted view is refitted to the fullscreen window',
      w.cull_view.is_fit)
w._cull_toggle_fullscreen()
app.processEvents()


# ── 7. through the window: stepping while zoomed ─────────────────────────────

w._cull_show_index(0)
app.processEvents()
spin()
w.cull_view.set_zoom(1.0)
app.processEvents()
width = w.cull_view.apparent_width()
check('zoomed in on the first picture', width > 0, str(width))
w._cull_step(+1)
app.processEvents()
spin(250)
check('the next picture kept the on-screen size',
      abs(w.cull_view.apparent_width() - width) < 3.0,
      f'{width} -> {w.cull_view.apparent_width()}')
check('and the picture is actually on screen', w.cull_view.has_image())

w.cull_view.fit()
app.processEvents()
w._cull_step(+1)
app.processEvents()
spin(250)
check('a fitted view stays fitted across a step', w.cull_view.is_fit)
check('nothing sticky is left over',
      getattr(w, '_cull_sticky', None) is None)

w._cull_shutdown()
shutil.rmtree(folder, ignore_errors=True)

print()
print('FAILURES:', ', '.join(fails) if fails else 'none')
sys.exit(1 if fails else 0)
