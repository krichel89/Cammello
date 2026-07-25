"""0.14: the floating edit panel (crop, white balance, exposure in sixths),
one keyring prompt instead of four, the remembered start folder, and F2
renaming on disk. Run as a file.
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


class FakeKeyring:
    """Records every read, so prompts can be counted."""
    class errors:
        class PasswordDeleteError(Exception):
            pass

    def __init__(self):
        self.store = {}
        self.reads = []

    def get_password(self, service, slot):
        self.reads.append(slot)
        return self.store.get(slot)

    def set_password(self, service, slot, value):
        self.store[slot] = value

    def delete_password(self, service, slot):
        self.store.pop(slot, None)


def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from PyQt5.QtWidgets import QApplication, QInputDialog
    from PyQt5.QtCore import Qt, QEvent, QSettings
    from PyQt5.QtGui import QKeyEvent
    from PIL import Image
    import Cammello
    from cammello import edits, credentials, channels
    from cammello.edit_panel import EditPanel
    from cammello.constants import remembered_dir, remember_dir
    from cammello.logging_setup import setup_logging

    app = QApplication.instance() or QApplication(sys.argv)

    # ── White balance maths ─────────────────────────────────────────────
    check('exposure steps are sixths of a stop',
          abs(edits.EV_STEP - 1 / 6) < 1e-9)
    check('a neutral sample is not an edit',
          edits.wb_from_neutral(128, 128, 128) is None)
    check('a dark sample is refused', edits.wb_from_neutral(3, 4, 5) is None)
    gains = edits.wb_from_neutral(110, 128, 150)
    check('a blue cast lifts red and lowers blue',
          gains and gains[0] > 1 and gains[2] < 1,
          str([round(g, 3) for g in gains] if gains else None))
    check('green stays the reference', abs(gains[1] - 1.0) < 1e-9)

    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, 'cast.jpg')
        Image.new('RGB', (80, 60), (110, 128, 150)).save(src, quality=95)
        out = os.path.join(tmp, 'out.jpg')
        edits.render_edited(src, {'wb': list(gains)}, out)
        px = Image.open(out).getpixel((40, 30))
        check('rendering neutralises the cast', max(px) - min(px) <= 4, str(px))

    # ── Panel formatting ────────────────────────────────────────────────
    check('EV 0 reads plainly', EditPanel._format_ev(0) == 'EV 0')
    check('a partial stop is shown as sixths',
          EditPanel._format_ev(4 / 6) == 'EV +4/6',
          EditPanel._format_ev(4 / 6))
    check('a full stop drops the fraction',
          EditPanel._format_ev(1.0) == 'EV +1', EditPanel._format_ev(1.0))
    check('negative exposure is signed',
          EditPanel._format_ev(-1 / 6).startswith('EV \u2212'))

    # ── One keyring prompt, not four ────────────────────────────────────
    fake = FakeKeyring()
    real_keyring, real_ok = credentials.keyring, credentials._backend_ok
    real_avail = credentials.backend_available
    credentials.keyring = fake
    credentials.backend_available = lambda: True
    credentials.clear_cache()
    from cammello.widgets import stored_oauth_tokens, store_oauth_tokens
    fake.store['mw-oauth:token'] = 'T'
    fake.store['mw-oauth:secret'] = 'S'
    check('old two-slot installs still work',
          stored_oauth_tokens() == ('T', 'S'))
    check('and are migrated to one entry',
          'mw-oauth:tokens' in fake.store
          and 'mw-oauth:token' not in fake.store)
    credentials.clear_cache()
    fake.reads.clear()
    check('a fresh session reads the keyring once',
          stored_oauth_tokens() == ('T', 'S') and len(fake.reads) == 1,
          str(fake.reads))
    fake.reads.clear()
    stored_oauth_tokens()
    check('a second read in the same session costs nothing',
          fake.reads == [], str(fake.reads))
    credentials.keyring, credentials._backend_ok = real_keyring, real_ok
    credentials.backend_available = real_avail
    credentials.clear_cache()

    # ── Remembered start folder ─────────────────────────────────────────
    s = QSettings('CammelloTest', 'DirMemory')
    s.remove('last_open_dir')
    default = remembered_dir(s)
    check('with nothing remembered a real folder is offered',
          bool(default) and os.path.isdir(default), default)
    with tempfile.TemporaryDirectory() as tmp:
        remember_dir(s, os.path.join(tmp, 'some_file.jpg'))
        check('a file path is remembered as its folder',
              remembered_dir(s) == tmp, remembered_dir(s))
    check('a folder that no longer exists is not offered',
          remembered_dir(s) != tmp)
    s.remove('last_open_dir')

    # ── The panel and the keys in the culling tab ───────────────────────
    logger, emitter, gui_handler, log_path = setup_logging()
    win = Cammello.MainWindow(logger, emitter, gui_handler, log_path)
    win.resize(1100, 780)
    win.show()
    app.processEvents()

    folder = tempfile.mkdtemp()
    Image.new('RGB', (400, 300), (110, 128, 150)).save(
        os.path.join(folder, 'IMG_001.jpg'))
    with open(os.path.join(folder, 'IMG_001.CR3'), 'wb') as fh:
        fh.write(b'\0' * 64)
    with open(os.path.join(folder, 'IMG_001.xmp'), 'w') as fh:
        fh.write('<x/>')
    win._cull_open_folder(folder)
    app.processEvents()
    item = win._cull_visible[0]

    def press(key, mods=Qt.NoModifier):
        win._cull_key(QKeyEvent(QEvent.KeyPress, key, mods))
        app.processEvents()

    panel = win.cull_edit_panel
    check('the edit panel is shown', panel.isVisible())
    check('it sits in the top-right corner',
          panel.x() > win.cull_view.width() / 2 and panel.y() < 60,
          f'x={panel.x()} y={panel.y()}')

    press(Qt.Key_Plus)
    press(Qt.Key_Plus)
    check('+ moves exposure by sixths',
          abs(edits.get_ev(win._cull_edits, item.display_path)
              - 2 * edits.EV_STEP) < 1e-6)
    check('the panel shows the sixths', panel.ev_lbl.text() == 'EV +2/6',
          panel.ev_lbl.text())
    press(Qt.Key_Minus)
    check('- steps back', panel.ev_lbl.text() == 'EV +1/6',
          panel.ev_lbl.text())

    press(Qt.Key_W)
    check('W arms the pipette',
          win.cull_view.pipette_active() and panel.wb_btn.isChecked())
    win._cull_wb_from_pixel(110, 128, 150)
    check('a pick stores the white balance',
          edits.get_wb(win._cull_edits, item.display_path) is not None)
    check('and disarms the pipette', not win.cull_view.pipette_active())
    win._cull_wb_from_pixel(2, 2, 2)
    check('a too-dark pick is refused, keeping the old balance',
          edits.get_wb(win._cull_edits, item.display_path) is not None)

    # Crop is displayed after Enter, full frame while cropping.
    press(Qt.Key_C)
    check('crop mode shows the full frame',
          win.cull_view.crop_display() is None)
    win.cull_view.crop._box.setRect(0.2, 0.2, 0.5, 0.5)
    press(Qt.Key_Return)
    check('after Enter the view shows the crop',
          win.cull_view.crop_display() is not None,
          str(win.cull_view.crop_display()))

    # F2 renames every file of the picture.
    QInputDialog.getText = staticmethod(lambda *a, **k: ('Berlinale_01', True))
    press(Qt.Key_F2)
    names = sorted(os.listdir(folder))
    check('all three files are renamed together',
          names == ['Berlinale_01.CR3', 'Berlinale_01.jpg',
                    'Berlinale_01.xmp'], str(names))
    check('the edits follow the new name',
          edits.get_edit(win._cull_edits, item.display_path) is not None)

    # A name that already exists is refused rather than overwriting.
    Image.new('RGB', (10, 10)).save(os.path.join(folder, 'Taken.jpg'))
    QInputDialog.getText = staticmethod(lambda *a, **k: ('Taken', True))
    from PyQt5.QtWidgets import QMessageBox
    QMessageBox.warning = staticmethod(lambda *a, **k: None)
    press(Qt.Key_F2)
    check('an existing name is refused',
          os.path.exists(os.path.join(folder, 'Berlinale_01.jpg')))

    win.close()
    import shutil
    shutil.rmtree(folder, ignore_errors=True)

    print('\n' + ('ALL EDIT-0140 CHECKS PASSED' if not FAILURES
                  else f'FAILURES: {FAILURES}'))
    return 1 if FAILURES else 0


if __name__ == '__main__':
    sys.exit(main())
