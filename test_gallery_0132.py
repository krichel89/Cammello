"""0.13.2: gallery updates never destroy an existing page.

Four cases: page with a gallery (insert before the last closing tag), page
without one (append a COMPLETE new block), page that does not exist (create),
and a failed fetch (abort rather than overwrite). Run as a file.
"""
import os
import sys

FAILURES = []


def check(name, cond, detail=''):
    print(('PASS ' if cond else 'FAIL ') + name, detail)
    if not cond:
        FAILURES.append(name)


class _Log:
    def info(self, *a):
        pass

    def debug(self, *a):
        pass

    def warning(self, *a):
        pass

    def error(self, *a, **k):
        pass


class _Resp:
    def __init__(self, status, text=''):
        self.status_code = status
        self.text = text


def make_api(status, text=''):
    """An api object wired to a canned page response, with the write
    captured instead of sent."""
    from cammello.api import MediaWikiApi
    api = MediaWikiApi.__new__(MediaWikiApi)
    api.log = _Log()
    api.api_url = 'https://commons.wikimedia.org/w/api.php'
    api._request = lambda method, desc, **kw: _Resp(status, text)
    written = {}
    api.set_page_content = lambda t, c, cm: written.update(
        page=t, content=c, comment=cm)
    return api, written


def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    entries = [('A.jpg', 'Bild A'), ('B.jpg', 'Bild B')]

    # ── 1. Page with an existing gallery ────────────────────────────────
    page = ('Intro text\n'
            '<gallery mode="packed-hover" heights="240">\n'
            'File:Old.jpg|Old one\n'
            '</gallery>\n'
            '[[Category:Something]]')
    api, written = make_api(200, page)
    api.update_gallery('Gallery page', entries)
    out = written.get('content', '')
    check('the existing entry survives', 'File:Old.jpg|Old one' in out)
    check('both new entries are added',
          'File:A.jpg|Bild A' in out and 'File:B.jpg|Bild B' in out)
    check('new entries go INSIDE the gallery',
          out.index('File:B.jpg') < out.index('</gallery>'))
    check('text above the gallery is kept', out.startswith('Intro text'))
    check('content below the gallery is kept',
          out.rstrip().endswith('[[Category:Something]]'))
    check('no second gallery block is opened',
          out.count('<gallery') == 1 and out.count('</gallery>') == 1)

    # ── 2. Page exists but has NO gallery ───────────────────────────────
    api, written = make_api(200, 'Just prose here.\n[[Category:X]]')
    api.update_gallery('Gallery page', entries)
    out = written.get('content', '')
    check('an OPENING gallery tag is written', '<gallery' in out)
    check('the block is balanced',
          out.count('<gallery') == 1 and out.count('</gallery>') == 1)
    check('the opening tag comes before the entries',
          out.index('<gallery') < out.index('File:A.jpg'))
    check('the entries come before the closing tag',
          out.index('File:B.jpg') < out.index('</gallery>'))
    check('the original prose is kept', out.startswith('Just prose here.'))

    # ── 3. Page does not exist (404) ────────────────────────────────────
    api, written = make_api(404)
    api.update_gallery('Gallery page', entries)
    out = written.get('content', '')
    check('a fresh page gets a complete gallery',
          out.startswith('<gallery') and out.rstrip().endswith('</gallery>'))
    check('with both entries',
          'File:A.jpg|Bild A' in out and 'File:B.jpg|Bild B' in out)

    # ── 4. Fetch failed: abort, never overwrite ─────────────────────────
    for status in (500, 503, 429):
        api, written = make_api(status)
        raised = False
        try:
            api.update_gallery('Gallery page', entries)
        except Exception:
            raised = True
        check(f'HTTP {status} aborts instead of writing',
              raised and written == {}, str(written))

    # A caption with a pipe or newline must not break the wikitext.
    api, written = make_api(404)
    api.update_gallery('Gallery page', [('C.jpg', 'Bad|caption\nsecond line')])
    out = written.get('content', '')
    check('captions cannot inject extra gallery lines',
          out.count('File:') == 1 and '|' in out, repr(out))

    # ── 5. Page title assembly: exactly one slash, never // ─────────────
    from cammello.constants import gallery_page_name
    check('prefix and suffix are joined with one slash',
          gallery_page_name('User:Seewolf', 'Berlinale 2026')
          == 'User:Seewolf/Berlinale 2026')
    check('a trailing slash on the prefix is absorbed',
          gallery_page_name('User:Seewolf/', 'Berlinale 2026')
          == 'User:Seewolf/Berlinale 2026')
    check('a leading slash on the suffix is absorbed',
          gallery_page_name('User:Seewolf', '/Berlinale 2026')
          == 'User:Seewolf/Berlinale 2026')
    check('both slashes at once still give one',
          gallery_page_name('User:Seewolf/', '/Berlinale 2026')
          == 'User:Seewolf/Berlinale 2026')
    check('surrounding whitespace is trimmed',
          gallery_page_name('  User:Seewolf ', ' Berlinale 2026  ')
          == 'User:Seewolf/Berlinale 2026')
    check('spaces around an inner slash do not survive',
          gallery_page_name('User:Seewolf', 'Berlinale / 2026')
          == 'User:Seewolf/Berlinale/2026')
    check('doubled slashes collapse',
          gallery_page_name('User:Seewolf//', '//Berlinale//2026//')
          == 'User:Seewolf/Berlinale/2026')
    check('an empty suffix leaves the prefix alone',
          gallery_page_name('User:Seewolf', '') == 'User:Seewolf'
          and gallery_page_name('User:Seewolf', '   ') == 'User:Seewolf')
    check('a multi-level prefix keeps its own levels',
          gallery_page_name('Commons:Cammello/Galerien', 'Cannes 2026')
          == 'Commons:Cammello/Galerien/Cannes 2026')
    check('nothing usable gives an empty title, not a lone slash',
          gallery_page_name('/', '/') == '' and gallery_page_name('', '') == '')
    messy = [('User:X/', '/A'), ('X//', '//B//'), (' X ', ' / C / ')]
    check('no assembled title ever contains //',
          not any('//' in gallery_page_name(p, s) for p, s in messy))

    print('\n' + ('ALL GALLERY CHECKS PASSED' if not FAILURES
                  else f'FAILURES: {FAILURES}'))
    return 1 if FAILURES else 0


if __name__ == '__main__':
    sys.exit(main())
