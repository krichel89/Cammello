"""Functional smoke test for the 0.12.7 changes (run as a FILE, main guard:
native_exec uses multiprocessing).

Covers: verifier parsing, rating clamping, the module strip, the reject
default, the unified button chrome and the UI font helper.
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
    from PyQt5.QtWidgets import QApplication, QTabWidget, QWidget
    from PyQt5.QtGui import QFontMetrics
    from cammello import constants, culling
    from cammello.widgets import verifier_from_input, ModuleStrip
    from cammello.mw_culling import rating_marks

    # ── 1. OAuth: what the manual field accepts ──────────────────────────
    url = ('http://127.0.0.1:8127/cammello/?oauth_verifier=abc123'
           '&oauth_token=tok')
    check('verifier from full callback URL',
          verifier_from_input(url) == 'abc123', verifier_from_input(url))
    check('verifier when the token comes first',
          verifier_from_input(
              'http://127.0.0.1:8127/cammello/?oauth_token=t&'
              'oauth_verifier=xyz') == 'xyz')
    check('verifier from a bare query string',
          verifier_from_input('oauth_token=t&oauth_verifier=q9') == 'q9')
    check('bare code still works',
          verifier_from_input('  plaincode  ') == 'plaincode')
    check('URL without a verifier yields nothing',
          verifier_from_input('http://127.0.0.1:8127/cammello/?x=1') == '')
    check('empty input yields nothing', verifier_from_input('') == '')
    check('fragment after the verifier is stripped',
          verifier_from_input(
              'http://127.0.0.1:8127/c/?oauth_verifier=v1#frag') == 'v1')

    # ── 2. Ratings can never paint an endless row ────────────────────────
    check('rating 3 -> three stars', rating_marks(3) == '★★★')
    check('rating -1 -> reject glyph', rating_marks(-1) == '✕')
    check('absurd rating clamped to five', rating_marks(4711) == '★★★★★',
          rating_marks(4711))
    check('negative junk clamped to reject', rating_marks(-99) == '✕')
    check('non-numeric rating is harmless', rating_marks('x') == '')
    check('empty stars pad to five',
          rating_marks(2, empty=True) == '★★☆☆☆')

    # A sidecar claiming a bogus rating must not reach the UI unclamped.
    with tempfile.TemporaryDirectory() as tmp:
        jpg = os.path.join(tmp, 'IMG_9999.JPG')
        xmp = os.path.join(tmp, 'IMG_9999.xmp')
        open(jpg, 'wb').write(b'\xff\xd8\xff\xd9')
        open(xmp, 'w', encoding='utf-8').write(
            '<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF '
            'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
            '<rdf:Description rdf:about="" '
            'xmlns:xmp="http://ns.adobe.com/xap/1.0/" '
            'xmp:Rating="250"/></rdf:RDF></x:xmpmeta>')
        raw = os.path.join(tmp, 'IMG_9999.CR3')
        open(raw, 'wb').write(b'\x00')
        item = culling.CullItem('IMG_9999', raw_path=raw, jpg_path=jpg)
        culling.read_item_metadata(item)
        check('bogus XMP rating clamped on read', item.rating == 5,
              str(item.rating))
        check('clamped value renders as five stars',
              rating_marks(item.rating) == '★★★★★')

    # ── 3. Rejects: visible unless a filter says otherwise ───────────────
    def mk(stem, rating):
        it = culling.CullItem(stem, jpg_path=f'/tmp/{stem}.jpg')
        it.rating = rating
        return it
    pool = [mk('a', 0), mk('b', 3), mk('r', -1)]
    default = culling.filter_items(pool, min_rating=0, exclude_rejects=False)
    check('reject visible with no filter',
          any(i.rating == -1 for i in default), str(len(default)))
    hidden = culling.filter_items(pool, min_rating=0, exclude_rejects=True)
    check('reject hidden when asked', all(i.rating != -1 for i in hidden))
    starred = culling.filter_items(pool, min_rating=3, exclude_rejects=False)
    check('reject drops out of an active star filter',
          [i.stem for i in starred] == ['b'], str([i.stem for i in starred]))

    # ── 4. Module strip: constant width, no clipping ─────────────────────
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyleSheet(constants.app_style())
    tabs = QTabWidget()
    for title in ('Culling', 'MediaWiki', 'IPTC', 'FTP/Flickr'):
        tabs.addTab(QWidget(), title)
    strip = ModuleStrip(tabs)
    strip.rebuild()
    strip.show()
    app.processEvents()
    check('one button per tab', len(strip._buttons) == 4,
          str(len(strip._buttons)))
    check('every title is bold', all(b.font().bold() for b in strip._buttons))
    widths_before = [b.width() for b in strip._buttons]
    tabs.setCurrentIndex(2)
    app.processEvents()
    check('strip follows the tab widget',
          strip._buttons[2].isChecked() and not strip._buttons[0].isChecked())
    check('widths do not change when switching module',
          [b.width() for b in strip._buttons] == widths_before,
          f'{widths_before} -> {[b.width() for b in strip._buttons]}')
    for b in strip._buttons:
        fm = QFontMetrics(b.font())
        check(f'title "{b.text()}" fits',
              b.width() >= fm.horizontalAdvance(b.text()),
              f'{b.width()} >= {fm.horizontalAdvance(b.text())}')

    # ── 5. Styling lives in one place ────────────────────────────────────
    sheet = constants.app_style()
    check('button chrome is in the app stylesheet',
          'cammelloPrimary' in sheet and 'QPushButton, QToolButton' in sheet)
    check('section headings are no longer a filled badge',
          'background: transparent' in constants.GROUP_TITLE_STYLE
          and 'font-size: 11pt' not in constants.GROUP_TITLE_STYLE)
    check('disabled menu rule survived', 'QMenu::item:disabled' in sheet)

    # ── 6. UI font: bigger, and idempotent ───────────────────────────────
    base = app.font().pointSizeF()
    constants.apply_ui_font(app)
    once = app.font().pointSizeF()
    constants.apply_ui_font(app)
    twice = app.font().pointSizeF()
    check('font grew', once > base, f'{base} -> {once}')
    check('applying twice does not stack', once == twice,
          f'{once} vs {twice}')

    print('\n' + ('ALL SMOKE CHECKS PASSED'
                  if not FAILURES else f'FAILURES: {FAILURES}'))
    return 1 if FAILURES else 0


if __name__ == '__main__':
    sys.exit(main())
