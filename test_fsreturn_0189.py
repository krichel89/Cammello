"""Coming back to fullscreen from another program (0.18.9).

Harald, on macOS: "wenn ich auf dem Mac vom Vollbild in ein anderes Programm
wechsle und dann wieder zurück, erhalte ich eine ganz komische Ansicht".

The fullscreen is a SEPARATE, borderless top-level window (_CullTab), and
the image view is reparented into it. That leaves the main window standing
there with a hole in its splitter where the picture used to be. When macOS
brings the application back it raises the MAIN window, not the borderless
one - and that hole is the "komische Ansicht".

Two answers, because one of them cannot be tested here and the other can:

  * on every activation the fullscreen window is put back in front, whole,
  * and the hole is filled with a label that says where the picture went,
    so even a moment of seeing the main window makes sense.

Defended here:

  1. entering fullscreen hooks the activation signal, leaving unhooks it,
  2. the hook is not left behind by shutdown either,
  3. the splitter is not left with a hole - a placeholder stands in it,
  4. and the placeholder is gone again afterwards, with the view back in
     slot 0 where the splitter sizes expect it,
  5. re-asserting restores fullscreen when the window came back as an
     ordinary one,
  6. re-asserting when no fullscreen is up does nothing at all,
  7. the picture survives the round trip: same zoom, same image.
"""
import os
import shutil
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import Cammello        # the shim; also puts the package on the path
from PyQt5.QtWidgets import QApplication, QLabel
from PyQt5.QtCore import Qt, QSettings, QEventLoop, QTimer
from PyQt5.QtGui import QImage

from cammello.constants import APP_NAME

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


from cammello.logging_setup import setup_logging          # noqa: E402
import logging                                            # noqa: E402

logger, emitter, gui_handler, log_path = setup_logging()
for h in logger.handlers:
    h.setLevel(logging.CRITICAL)

folder = tempfile.mkdtemp()
for i in range(3):
    img = QImage(1200, 800, QImage.Format_RGB32)
    img.fill(0xFF335599 + i * 24)
    img.save(os.path.join(folder, f'IMG_{i:04d}.JPG'), 'JPG', 88)

w = Cammello.MainWindow(logger, emitter, gui_handler, log_path)
w.resize(1200, 800)
w.show()
w.tabs.setCurrentWidget(w._cull_tab_widget)
app.processEvents()
w._cull_open_folder(folder)
app.processEvents()
spin()
w._cull_show_index(0)
app.processEvents()
spin()


# ── 6. the safe no-op ────────────────────────────────────────────────────────

check('no fullscreen up to begin with', w._cull_fs is None)
w._cull_fs_reassert()
check('re-asserting without fullscreen does nothing', w._cull_fs is None)
w._cull_fs_app_state(Qt.ApplicationActive)
check('and the state handler is safe too', w._cull_fs is None)


# ── 1./3. entering ───────────────────────────────────────────────────────────

check('the hook is not set yet', not getattr(w, '_cull_fs_hooked', False))
w._cull_toggle_fullscreen()
app.processEvents()
check('fullscreen is up', w._cull_fs is not None)
check('the activation hook is set', w._cull_fs_hooked is True)

check('the view really moved into the fullscreen window',
      w.cull_view.window() is w._cull_fs)
ph = getattr(w, '_cull_fs_ph', None)
check('a placeholder stands in the splitter', isinstance(ph, QLabel))
check('and it sits where the view was', w._cull_split.widget(0) is ph)
check('the splitter has no empty slot',
      w._cull_split.count() >= 2, str(w._cull_split.count()))
check('the placeholder says how to get out',
      'F' in ph.text() and ('Esc' in ph.text() or 'Échap' in ph.text()),
      ph.text().replace('\n', ' / '))


# ── 5./7. the round trip ─────────────────────────────────────────────────────

w.cull_view.set_zoom(0.7)
app.processEvents()
zoom_before = w.cull_view.zoom_factor()
index_before = w._cull_index

# What macOS does on the way back: the fullscreen window is no longer
# fullscreen and no longer in front.
w._cull_fs.showNormal()
app.processEvents()
check('the window came back as an ordinary one',
      not w._cull_fs.isFullScreen())

w._cull_fs_app_state(Qt.ApplicationActive)
spin()                              # the handler defers by one event loop turn
check('activation puts fullscreen back', w._cull_fs.isFullScreen())
check('the same picture is still shown', w._cull_index == index_before)
check('and at the same zoom',
      abs(w.cull_view.zoom_factor() - zoom_before) < 1e-6,
      f'{zoom_before} -> {w.cull_view.zoom_factor()}')
check('the view is still in the fullscreen window',
      w.cull_view.window() is w._cull_fs)

# Deactivation must not do anything by itself.
w._cull_fs_app_state(Qt.ApplicationInactive)
spin(50)
check('going away does not disturb the fullscreen', w._cull_fs is not None)


# ── 1./4. leaving ────────────────────────────────────────────────────────────

w._cull_toggle_fullscreen()
app.processEvents()
check('out of fullscreen', w._cull_fs is None)
check('the hook is released', not w._cull_fs_hooked)
check('the placeholder is gone', getattr(w, '_cull_fs_ph', None) is None)
check('the view is back in slot 0 of the splitter',
      w._cull_split.widget(0) is w.cull_view)
check('and back in the main window', w.cull_view.window() is w)

# A stray activation after leaving must be harmless.
w._cull_fs_app_state(Qt.ApplicationActive)
spin(50)
check('a late activation after leaving changes nothing',
      w._cull_fs is None and w._cull_split.widget(0) is w.cull_view)


# ── 2. shutdown ──────────────────────────────────────────────────────────────

w._cull_toggle_fullscreen()
app.processEvents()
check('fullscreen up again', w._cull_fs is not None and w._cull_fs_hooked)
w._cull_shutdown()
check('shutdown releases the hook', not w._cull_fs_hooked)

shutil.rmtree(folder, ignore_errors=True)

print()
print('FAILURES:', ', '.join(fails) if fails else 'none')
sys.exit(1 if fails else 0)
