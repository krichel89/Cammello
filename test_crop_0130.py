"""0.13 crop UI: the C-key crop overlay in culling, its persistence via
edits.py, the aspect presets, and the edited folder export. Run as a file.
"""
import os
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
FAILURES = []


def check(name, cond, detail=''):
    print(('PASS ' if cond else 'FAIL ') + name, detail)
    if not cond:
        FAILURES.append(name)


def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import Qt, QEvent
    from PyQt5.QtGui import QKeyEvent
    from PIL import Image
    import Cammello
    from cammello import edits
    from cammello.mw_culling import _FolderCopyWorker
    from cammello.logging_setup import setup_logging

    app = QApplication.instance() or QApplication(sys.argv)
    logger, emitter, gui_handler, log_path = setup_logging()
    win = Cammello.MainWindow(logger, emitter, gui_handler, log_path)
    win.show()
    app.processEvents()

    tmp = tempfile.mkdtemp()
    for i in range(3):
        Image.new('RGB', (400, 300), (120, 120, 120)).save(
            os.path.join(tmp, f'img{i}.jpg'))
    win._cull_open_folder(tmp)
    app.processEvents()
    check('the folder loaded', len(win._cull_visible) == 3)

    def press(key, mods=Qt.NoModifier):
        win._cull_key(QKeyEvent(QEvent.KeyPress, key, mods))
        app.processEvents()

    # Enter and leave crop mode.
    check('not cropping at first', win._cull_cropping is False)
    press(Qt.Key_C)
    check('C enters crop mode',
          win._cull_cropping and win.cull_view.crop.isVisible())
    check('the mode label becomes a crop legend while cropping',
          win.cull_mode_lbl.text().startswith('[crop]')
          or 'crop' in win.cull_mode_lbl.text().lower(),
          win.cull_mode_lbl.text())

    # Commit a box and check it persists and badges.
    win.cull_view.crop._box.setRect(0.2, 0.2, 0.5, 0.5)
    press(Qt.Key_Return)
    item = win._cull_visible[0]
    rec = edits.get_edit(win._cull_edits, item.display_path)
    check('Enter stores the crop',
          rec == {'crop': [0.2, 0.2, 0.5, 0.5]}, str(rec))
    check('crop mode ends after commit', win._cull_cropping is False)
    check('the strip row gets the edit badge',
          win.cull_strip.item(0).data(Qt.UserRole + 4) is True)
    # 0.14.1: persisting is debounced; a real shutdown flushes via
    # _cull_shutdown. Emulate the flush the way the app does on exit.
    win._cull_flush_edits()
    check('the stored edit survives a reload',
          edits.load_edits(win.settings).get(
              edits.norm(item.display_path)) == {'crop': [0.2, 0.2, 0.5, 0.5]})

    # Aspect presets map from the Qt key codes, not the digit values.
    press(Qt.Key_C)
    press(Qt.Key_4)
    check('number key 4 selects the 1:1 aspect',
          win._cull_crop_aspect == 1.0, str(win._cull_crop_aspect))
    press(Qt.Key_1)
    check('number key 1 is free aspect', win._cull_crop_aspect is None)

    # Same key pressed again flips landscape <-> portrait.
    press(Qt.Key_2)
    check('key 2 gives 3:2 landscape first',
          abs(win._cull_crop_aspect - 1.5) < 0.001, str(win._cull_crop_aspect))
    press(Qt.Key_2)
    check('key 2 again flips to 2:3 portrait',
          abs(win._cull_crop_aspect - 2 / 3) < 0.001,
          str(win._cull_crop_aspect))
    press(Qt.Key_3)
    check('a different key starts landscape again',
          abs(win._cull_crop_aspect - 4 / 3) < 0.001
          and win._cull_crop_portrait is False)
    press(Qt.Key_3)
    check('key 3 again gives 3:4 portrait',
          abs(win._cull_crop_aspect - 3 / 4) < 0.001)
    press(Qt.Key_Escape)
    check('Esc leaves crop mode without changing the stored crop',
          win._cull_cropping is False
          and edits.get_edit(win._cull_edits, item.display_path)
          == {'crop': [0.2, 0.2, 0.5, 0.5]})

    # A rating key does NOT fire while cropping (crop swallows 1..6).
    press(Qt.Key_C)
    before = win._cull_visible[0].rating
    press(Qt.Key_3)          # would be "3 stars" outside crop mode
    check('digits do not rate while cropping',
          win._cull_visible[0].rating == before)
    press(Qt.Key_Escape)

    # Shift+C removes the crop.
    press(Qt.Key_C)
    press(Qt.Key_C, Qt.ShiftModifier)
    check('Shift+C removes the crop',
          edits.get_edit(win._cull_edits, item.display_path) is None)
    check('the badge clears with the crop',
          win.cull_strip.item(0).data(Qt.UserRole + 4) is False)

    # Regression: dragging a handle must not raise QRect/QRectF TypeError.
    # _image_rect must be a QRectF so intersected()/contains() downstream
    # never mix integer and float rects (crashed on Harald's PyQt5).
    from PyQt5.QtCore import QRectF
    press(Qt.Key_C)
    overlay = win.cull_view.crop
    rect = overlay._image_rect()
    check('the image rect is a QRectF, not a QRect',
          rect is None or type(rect).__name__ == 'QRectF',
          type(rect).__name__)
    if rect is not None:
        overlay._box = QRectF(0.2, 0.2, 0.5, 0.5)
        crashed = False
        try:
            overlay._resize_handle('tl', overlay._norm_to_px(overlay._box),
                                   20, 15, rect)
        except TypeError:
            crashed = True
        check('resizing by a handle does not raise', not crashed)
    press(Qt.Key_Escape)

    win.close()
    import shutil
    shutil.rmtree(tmp)

    # The folder export renders an edited copy named "<stem>_edit.jpg".
    src_dir = tempfile.mkdtemp()
    dest = tempfile.mkdtemp()
    src = os.path.join(src_dir, 'photo.jpg')
    Image.new('RGB', (400, 300), (120, 120, 120)).save(src)
    em = {}
    edits.set_crop(em, src, (0.25, 0.25, 0.5, 0.5))
    edits.set_ev(em, src, 1.0)
    worker = _FolderCopyWorker([src], dest, logger,
                               {src: edits.get_edit(em, src)})
    worker.run()
    out = os.listdir(dest)
    check('the export writes an _edit copy',
          out == ['photo_edit.jpg'], str(out))
    im = Image.open(os.path.join(dest, out[0]))
    check('the exported copy is cropped', abs(im.size[0] - 200) <= 2)
    check('and carries the exposure change', im.getpixel((100, 75))[0] > 120)

    # A plain file (no edit) exports under its own name.
    src2 = os.path.join(src_dir, 'plain.jpg')
    Image.new('RGB', (100, 100), (90, 90, 90)).save(src2)
    worker2 = _FolderCopyWorker([src2], dest, logger, {})
    worker2.run()
    check('an unedited file keeps its name',
          'plain.jpg' in os.listdir(dest))
    shutil.rmtree(src_dir)
    shutil.rmtree(dest)

    print('\n' + ('ALL CROP CHECKS PASSED' if not FAILURES
                  else f'FAILURES: {FAILURES}'))
    return 1 if FAILURES else 0


if __name__ == '__main__':
    sys.exit(main())
