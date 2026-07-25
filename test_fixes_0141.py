"""0.14.1: guards for the review fixes.

Covers, in order:
  1. normalize_commons_filename rejects ':', '/', '\\' BEFORE any upload,
     naming each character (the Wikimania badfilename case: target names
     like "<session title>: <n>.JPG" failed 129/129 server-side).
  2. api.MediaWikiApi._explain_badfilename names the offending characters
     and the name MediaWiki would store.
  3. Orientation crop end-to-end: a crop drawn on the UPRIGHT display of an
     orientation-6 JPEG must survive into the rendered copy (it used to cut
     the wrong region), and the copy's orientation tag must be reset.
  4. _exif_upright resets tag 274 and leaves unparsable input alone.
  5. The combined WB+EV LUT matches the two-pass result within rounding and
     is exact for the identity cases.
  6. culling.rename_stem_problem flags Windows-reserved stems and trailing
     dot/space, passes normal names.
  7. The edit store is saved debounced: one pending timer after repeated EV
     steps, flushed on folder change/shutdown paths.

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
    from cammello import sdc, edits, culling
    from cammello.api import MediaWikiApi
    from PIL import Image, ImageOps

    # ── 1. Client-side filename validation ───────────────────────────────
    for ch, label in ((':', 'colon'), ('/', 'slash'), ('\\', 'backslash')):
        try:
            sdc.normalize_commons_filename(f'Session{ch} title 1.jpg',
                                           '/x/src.jpg')
            check(f'illegal {label} rejected', False, 'no ValueError')
        except ValueError as e:
            msg = str(e)
            check(f'illegal {label} rejected', True)
            check(f'{label} named in message',
                  label in msg and repr(ch) in msg, msg[:70])
    # The real-world shape passes only without the colon.
    try:
        sdc.normalize_commons_filename(
            'Behind the Lens – WikiPortraits on a Global Scale 25.JPG',
            '/x/src.JPG')
        check('en-dash replacement accepted', True)
    except ValueError as e:
        check('en-dash replacement accepted', False, str(e))
    # The old general-title check still works.
    try:
        sdc.normalize_commons_filename('a#b.jpg', '/x/src.jpg')
        check('title chars still rejected', False)
    except ValueError:
        check('title chars still rejected', True)

    # ── 2. badfilename explanation ───────────────────────────────────────
    msg = MediaWikiApi._explain_badfilename(
        'WikiAnalyzer v2 & WikiDebate: Open AI Tools 18.JPG',
        'WikiAnalyzer_v2_&_WikiDebate-_Open_AI_Tools_18.JPG')
    check('badfilename names the colon', "':' (colon)" in msg, msg[:80])
    check('badfilename shows stored name',
          'WikiDebate- Open' in msg)
    msg2 = MediaWikiApi._explain_badfilename('Ok name.jpg', 'OK name.jpg')
    check('badfilename fallback wording', 'normalize' in msg2, msg2[:60])

    # ── 3. Orientation crop end-to-end ───────────────────────────────────
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, 'orient6.jpg')
        out = os.path.join(td, 'out.jpg')
        # 600x400 landscape pixels + orientation 6 -> displays 400x600
        # portrait. The corner that lands TOP-LEFT after rotation is the
        # bottom-left of the raw pixels; paint it green.
        img = Image.new('RGB', (600, 400), (30, 30, 30))
        for x in range(150):
            for y in range(250, 400):
                img.putpixel((x, y), (0, 255, 0))
        exif = Image.Exif()
        exif[274] = 6
        exif[306] = '2026:07:24 22:38:42'   # DateTime - must survive
        img.save(src, 'JPEG', exif=exif.tobytes(), quality=95)

        # Crop the top-left corner of the DISPLAYED (upright, 400x600)
        # image, normalized - exactly what CropOverlay hands to edits.
        rec = {'crop': [0.0, 0.0, 0.375, 0.25]}
        res = edits.render_edited(src, rec, out)
        check('orientation render succeeds', res == out)
        with Image.open(out) as r:
            check('orientation tag reset', r.getexif().get(274, 1) == 1,
                  f'tag={r.getexif().get(274, 1)}')
            px = ImageOps.exif_transpose(r).convert('RGB')
            w, h = px.size
            green = sum(1 for x in range(0, w, 3) for y in range(0, h, 3)
                        if px.getpixel((x, y))[1] > 200
                        and px.getpixel((x, y))[0] < 80)
            total = len(range(0, w, 3)) * len(range(0, h, 3))
            ratio = green / total
            check('crop hits the displayed region', ratio > 0.95,
                  f'{ratio:.0%} green, size {px.size}')
            check('crop has the displayed proportions',
                  (w, h) == (150, 150), f'{w}x{h}')
        # EXIF survives (camera metadata was passed through).
        with Image.open(out) as r:
            check('EXIF passed through',
                  r.getexif().get(306) == '2026:07:24 22:38:42',
                  str(dict(r.getexif()))[:60])

    # ── 4. _exif_upright ─────────────────────────────────────────────────
    exif = Image.Exif()
    exif[274] = 8
    fixed = edits._exif_upright(exif.tobytes())
    parsed = Image.Exif()
    parsed.load(fixed)
    check('_exif_upright resets tag', parsed.get(274) == 1)
    check('_exif_upright tolerates junk',
          edits._exif_upright(b'not exif') == b'not exif')
    check('_exif_upright tolerates None', edits._exif_upright(None) is None)

    # ── 5. Combined LUT ──────────────────────────────────────────────────
    base = Image.new('RGB', (16, 16))
    base.putdata([(i * 16 % 256, (i * 7) % 256, (i * 3) % 256)
                  for i in range(256)])
    wb = (1.3, 1.0, 0.8)
    two_pass = edits._apply_ev_image(edits._apply_wb_image(base, wb), 0.5)
    one_pass = edits._apply_wb_ev_image(base, wb, 0.5)
    diff = max(abs(a - b)
               for p1, p2 in zip(two_pass.getdata(), one_pass.getdata())
               for a, b in zip(p1, p2))
    check('combined LUT within rounding of two-pass', diff <= 2,
          f'max diff {diff}')
    check('combined LUT identity', edits._apply_wb_ev_image(base, None, 0.0)
          is base)
    ev_only = edits._apply_wb_ev_image(base, None, 1.0)
    ref = edits._apply_ev_image(base, 1.0)
    check('combined LUT ev-only equals ev pass',
          list(ev_only.getdata()) == list(ref.getdata()))

    # ── 6. rename stem checks ────────────────────────────────────────────
    check('reserved stem flagged',
          culling.rename_stem_problem('CON') == 'reserved')
    check('reserved stem flagged case-insensitively',
          culling.rename_stem_problem('com7') == 'reserved')
    check('trailing dot flagged',
          culling.rename_stem_problem('shot.') == 'trailing')
    check('trailing space flagged',
          culling.rename_stem_problem('shot ') == 'trailing')
    check('normal stem passes',
          culling.rename_stem_problem('Berlinale_2026_014') is None)
    check('inner dots pass',
          culling.rename_stem_problem('a.b') is None)

    # ── 7. Debounced persisting (GUI) ────────────────────────────────────
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import QCoreApplication
    import Cammello  # noqa: F401  (package path side effects)
    from cammello.main_window import MainWindow
    from cammello.logging_setup import setup_logging

    app = QApplication.instance() or QApplication(sys.argv)
    QCoreApplication.setOrganizationName('CammelloTest0141')
    QCoreApplication.setApplicationName('CammelloTest0141')
    logger, emitter, gui_handler, log_path = setup_logging()
    win = MainWindow(logger, emitter, gui_handler, log_path)
    if hasattr(win, '_cull_edits_timer'):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, 'x.jpg')
            Image.new('RGB', (8, 8)).save(p)
            import cammello.edits as ed
            calls = []
            real_save = ed.save_edits
            ed.save_edits = lambda s, e: calls.append(1)
            try:
                ed.set_ev(win._cull_edits, p, 0.5)
                for _ in range(4):
                    win._cull_save_edits_soon()
                check('debounce: no save yet', not calls, str(len(calls)))
                check('debounce: timer pending',
                      win._cull_edits_timer.isActive())
                win._cull_flush_edits()
                check('flush saves exactly once', len(calls) == 1,
                      str(len(calls)))
                check('flush stops the timer',
                      not win._cull_edits_timer.isActive())
            finally:
                ed.save_edits = real_save
                ed.clear_edit(win._cull_edits, p)
        # The guard: folder-open on a window without culling state is a
        # no-op, not an AttributeError.
        class _Bare:
            pass
        try:
            MainWindow._cull_open_folder(_Bare(), '/nonexistent')
            check('open-folder guard degrades to no-op', True)
        except AttributeError as e:
            check('open-folder guard degrades to no-op', False, str(e))
    else:
        print('SKIP debounce checks (culling tab unavailable: no pyexiv2)')

    win.close()

    print('\nFAILURES:', FAILURES if FAILURES else 'none')
    return 1 if FAILURES else 0


if __name__ == '__main__':
    sys.exit(main())
