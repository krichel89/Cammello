"""0.14.2: guards for the tone preview, the movable panel and the splash.

Covers, in order:
  1. previews.apply_tone: identity when there is nothing to do, correct
     direction for EV and WB, the caller's image is never modified, and the
     numpy path and the pure-Python fallback agree byte for byte.
  2. CullImageView.set_tone: the source image is kept, the displayed pixmap
     carries the correction, and the pipette samples the UNTOUCHED source
     (otherwise a second white balance would be measured on already
     corrected pixels) - also with a crop active.
  3. EditPanel: dragging by the title moves it, the position survives a
     view resize as a fraction, the panel is clamped inside the view,
     double-click resets, and the crop legend appears only while cropping.
  4. The culling tab debounces the tone preview on key repeat but applies
     it immediately on an image change.
  5. splash.build_pixmap paints at the requested device pixel ratio and
     survives missing assets; the bundled logo assets exist.

Run as a file (multiprocessing rule).
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
    from PyQt5.QtGui import QImage
    from PyQt5.QtCore import Qt, QPoint, QEvent
    from PyQt5.QtGui import QMouseEvent
    from PIL import Image

    app = QApplication.instance() or QApplication(sys.argv)
    from cammello import previews, splash, edits
    from cammello.constants import asset_path

    # ── 1. apply_tone ────────────────────────────────────────────────────
    grey = QImage(8, 8, QImage.Format_RGB32)
    grey.fill(0xff808080)
    check('apply_tone identity returns the input',
          previews.apply_tone(grey, None, 0.0) is grey)
    check('apply_tone tolerates None', previews.apply_tone(None) is None)

    up = previews.apply_tone(grey, None, 1.0)
    check('EV +1 brightens', (up.pixel(0, 0) & 0xff) > 0x80,
          hex(up.pixel(0, 0)))
    down = previews.apply_tone(grey, None, -1.0)
    check('EV -1 darkens', (down.pixel(0, 0) & 0xff) < 0x80,
          hex(down.pixel(0, 0)))
    check('the source image is not modified', grey.pixel(0, 0) == 0xff808080,
          hex(grey.pixel(0, 0)))

    c = previews.apply_tone(grey, (1.4, 1.0, 0.7), 0.0).pixel(0, 0)
    r, g, b = (c >> 16) & 255, (c >> 8) & 255, c & 255
    check('WB raises red, lowers blue', r > 128 > b, f'R={r} G={g} B={b}')
    check('WB leaves green pinned', g == 128, str(g))

    # The exposure preview must agree with what the EXPORT produces - one
    # differing rounding step and the screen would lie about the result.
    lut = edits._combined_lut(1.0, 1.0)
    check('preview LUT is the export LUT', lut[128] == (up.pixel(0, 0) & 0xff),
          f'{lut[128]} vs {up.pixel(0, 0) & 0xff}')

    if previews._np is not None:
        real_np = previews._np
        fast = previews.apply_tone(grey, (1.4, 1.0, 0.7), 0.5)
        previews._np = None
        try:
            slow = previews.apply_tone(grey, (1.4, 1.0, 0.7), 0.5)
        finally:
            previews._np = real_np
        same = all(fast.pixel(x, y) == slow.pixel(x, y)
                   for x in range(8) for y in range(8))
        check('numpy path and fallback agree', same)
    else:
        print('SKIP numpy comparison (numpy not installed)')

    # ── 2. The view ──────────────────────────────────────────────────────
    from cammello.culling_view import CullImageView
    view = CullImageView()
    view.resize(400, 300)
    src = QImage(40, 30, QImage.Format_RGB32)
    src.fill(0xff808080)
    view.set_image(src)
    view.set_tone((1.4, 1.0, 0.7), 0.0)
    check('set_tone stores the values', view.tone() == ((1.4, 1.0, 0.7), 0.0),
          str(view.tone()))
    shown = view._item.pixmap().toImage().pixel(0, 0)
    check('the displayed pixmap carries the correction',
          ((shown >> 16) & 255) > 128, hex(shown))
    check('the source image is kept untouched',
          view._source_image.pixel(0, 0) == 0xff808080)

    # The pipette must read the SOURCE, not the corrected display.
    view.fit()
    app.processEvents()
    centre = view.viewport().rect().center()
    sample = view._sample_at(centre)
    check('pipette samples the untouched source', sample == (128, 128, 128),
          str(sample))

    # …and it must still hit the right spot with a crop active: paint a
    # marker into the lower right quarter and crop to it.
    marked = QImage(40, 30, QImage.Format_RGB32)
    marked.fill(0xff808080)
    for x in range(20, 40):
        for y in range(15, 30):
            marked.setPixel(x, y, 0xff2040c0)
    view.set_image(marked)
    view.set_tone(None, 0.0)
    view.set_crop_display((0.5, 0.5, 0.5, 0.5))
    view.fit()
    app.processEvents()
    sample = view._sample_at(view.viewport().rect().center())
    check('pipette maps through an active crop', sample == (32, 64, 192),
          str(sample))

    # ── 3. The panel ─────────────────────────────────────────────────────
    from cammello.edit_panel import EditPanel
    panel = EditPanel(view)
    panel.show()
    panel.place()
    for _ in range(3):      # child geometry is valid only after the layout
        app.processEvents()
    panel.place()
    default_x = panel.x()
    check('panel starts at the top right',
          default_x + panel.width() + panel.MARGIN == view.width()
          and panel.y() == panel.MARGIN,
          f'({panel.x()}, {panel.y()}) w={panel.width()} view={view.width()}')

    def drag(dx, dy):
        start = QPoint(panel.title.geometry().center())
        assert panel._in_drag_zone(start), 'title must be a drag zone'
        panel.mousePressEvent(QMouseEvent(
            QEvent.MouseButtonPress, start, Qt.LeftButton, Qt.LeftButton,
            Qt.NoModifier))
        panel.mouseMoveEvent(QMouseEvent(
            QEvent.MouseMove, QPoint(start.x() + dx, start.y() + dy),
            Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
        panel.mouseReleaseEvent(QMouseEvent(
            QEvent.MouseButtonRelease, QPoint(start.x() + dx, start.y() + dy),
            Qt.LeftButton, Qt.NoButton, Qt.NoModifier))

    drag(-120, 60)
    moved_x, moved_y = panel.x(), panel.y()
    check('dragging the title moves the panel',
          moved_x < default_x and moved_y > panel.MARGIN,
          f'({moved_x}, {moved_y})')

    check('a press on a button does not drag',
          not panel._in_drag_zone(panel.crop_btn.geometry().center()))

    # The remembered position is relative, so a resize keeps it in place.
    rel = panel._rel_pos
    check('the position is remembered as a fraction',
          rel is not None and 0.0 <= rel[0] <= 1.0 and 0.0 <= rel[1] <= 1.0,
          str(rel))
    view.resize(800, 600)
    panel.place()
    check('the panel keeps its relative spot after a resize',
          abs(panel.x() / 800 - rel[0]) < 0.02
          and abs(panel.y() / 600 - rel[1]) < 0.02,
          f'({panel.x()}, {panel.y()})')

    # Clamping: a tiny view must not strand the panel outside itself.
    view.resize(200, 150)
    panel.place()
    check('the panel stays inside a shrunken view',
          0 <= panel.x() <= max(0, 200 - panel.width())
          and 0 <= panel.y() <= max(0, 150 - panel.height()),
          f'({panel.x()}, {panel.y()}) in 200x150')

    view.resize(400, 300)
    panel.reset_position()
    check('reset_position returns to the corner',
          panel._rel_pos is None and panel.y() == panel.MARGIN)

    # Crop legend
    check('crop legend hidden by default', panel.crop_help.isHidden())
    panel.set_cropping(True)
    check('crop legend appears while cropping',
          not panel.crop_help.isHidden()
          and '3:2' in panel.crop_help.text(),
          panel.crop_help.text()[:40])
    panel.set_cropping(False)
    check('crop legend hidden again', panel.crop_help.isHidden())

    # ── 4. Debounce in the tab ───────────────────────────────────────────
    import Cammello  # noqa: F401
    from cammello.logging_setup import setup_logging
    logger, emitter, gui_handler, log_path = setup_logging()
    win = Cammello.MainWindow(logger, emitter, gui_handler, log_path)
    if hasattr(win, '_cull_tone_timer'):
        calls = []
        real_set_tone = win.cull_view.set_tone
        win.cull_view.set_tone = lambda wb, ev: calls.append((wb, ev))
        try:
            win._cull_apply_tone()          # debounced
            check('tone preview is debounced', not calls
                  and win._cull_tone_timer.isActive(), str(calls))
            win._cull_flush_tone()
            check('flush applies the pending tone once', len(calls) == 1,
                  str(len(calls)))
            calls.clear()
            win._cull_apply_tone(immediate=True)
            check('image change applies the tone immediately',
                  len(calls) == 1 and not win._cull_tone_timer.isActive(),
                  str(len(calls)))
        finally:
            win.cull_view.set_tone = real_set_tone
    else:
        print('SKIP debounce checks (culling tab unavailable: no pyexiv2)')
    win.close()

    # ── 5. The splash ────────────────────────────────────────────────────
    check('WikiPortraits asset is bundled',
          os.path.exists(asset_path('wikiportraits.png')))
    check('rounded icon asset is bundled',
          os.path.exists(asset_path('icon_rounded.png')))
    with Image.open(asset_path('icon_rounded.png')) as ic:
        ic = ic.convert('RGBA')
        w, h = ic.size
        corner = ic.getpixel((int(w * 0.10), int(h * 0.10)))[3]
        edge = ic.getpixel((w // 2, int(h * 0.10)))[3]
    check('the rounded icon is transparent in the corners and solid at the '
          'edge midpoint', corner == 0 and edge == 255,
          f'corner alpha={corner}, edge alpha={edge}')

    # 0.14.3: the card must be OPAQUE - a transparent pixmap plus a
    # translucent window left the splash invisible on macOS.
    probe = splash.build_pixmap(1.0).toImage()
    check('the splash card is opaque',
          all(probe.pixelColor(x, y).alpha() == 255
              for x, y in ((2, 2), (splash.WIDTH - 3, 2),
                           (2, splash.HEIGHT - 3),
                           (splash.WIDTH // 2, splash.HEIGHT // 2))))

    pm = splash.build_pixmap(1.0)
    check('splash paints at 1x',
          pm.width() == splash.WIDTH and pm.height() == splash.HEIGHT,
          f'{pm.width()}x{pm.height()}')
    pm2 = splash.build_pixmap(2.0)
    check('splash paints at 2x for retina',
          pm2.width() == splash.WIDTH * 2
          and pm2.devicePixelRatio() == 2.0,
          f'{pm2.width()}px, dpr {pm2.devicePixelRatio()}')

    # The minimum visible time: a fast start used to close the splash
    # before it could be seen at all.
    sp_obj = splash.Splash()
    sp_obj.show()
    app.processEvents()
    from PyQt5.QtWidgets import QWidget
    dummy = QWidget()
    held = sp_obj.finish_after_minimum(dummy, minimum_ms=800)
    check('the splash is held for a minimum time', 0 < held <= 800,
          f'{held} ms')
    check('no translucent-background attribute is set',
          not sp_obj.testAttribute(Qt.WA_TranslucentBackground))
    held2 = sp_obj.finish_after_minimum(dummy, minimum_ms=0)
    check('no wait when the minimum has passed', held2 == 0, str(held2))
    dummy.deleteLater()

    # A missing asset must not break the start screen.
    import cammello.splash as sp
    real_asset = sp.asset_path
    sp.asset_path = lambda name: '/nonexistent/' + name
    try:
        pm3 = sp.build_pixmap(1.0)
        check('splash survives missing assets', not pm3.isNull())
    finally:
        sp.asset_path = real_asset

    print('\nFAILURES:', FAILURES if FAILURES else 'none')
    return 1 if FAILURES else 0


if __name__ == '__main__':
    sys.exit(main())
