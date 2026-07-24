"""0.13.1: the on-wiki manual linked from the Help menu, per UI language.

Checks the URL builder (all five languages, plus the fallback), that the
entry exists in the Help menu, that it is translated, and that it carries
the standard help shortcut. Run as a file.
"""
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
FAILURES = []


def check(name, cond, detail=''):
    print(('PASS ' if cond else 'FAIL ') + name, detail)
    if not cond:
        FAILURES.append(name)


def help_menu(win):
    """The Help menu, found by its About entry rather than by title (the
    title is translated)."""
    for act in win.menuBar().actions():
        menu = act.menu()
        if menu and any('_open_about_dialog' in str(a.receivers)
                        or 'Cammello' in a.text() for a in menu.actions()):
            if len(menu.actions()) >= 3:
                return menu
    return None


def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtGui import QKeySequence
    import Cammello
    from cammello.constants import manual_url, MANUAL_LANGUAGES, MANUAL_BASE_URL
    from cammello.i18n import UI_LANGUAGES, set_language, current_language
    from cammello.logging_setup import setup_logging

    app = QApplication.instance() or QApplication(sys.argv)

    # ── The URL builder ─────────────────────────────────────────────────
    check('the manual languages match the UI languages',
          tuple(code for code, _n in UI_LANGUAGES) == MANUAL_LANGUAGES,
          str(MANUAL_LANGUAGES))
    for code, _name in UI_LANGUAGES:
        url = manual_url(code)
        check(f'{code} maps to its own page',
              url == f'{MANUAL_BASE_URL}/{code}', url)
    check('an unknown language falls back to English, not a red link',
          manual_url('pt') == f'{MANUAL_BASE_URL}/en')
    check('None falls back too', manual_url(None).endswith('/en'))
    check('the base page is the documentation page on Commons',
          MANUAL_BASE_URL ==
          'https://commons.wikimedia.org/wiki/Commons:Cammello/documentation',
          MANUAL_BASE_URL)

    # ── The menu entry ──────────────────────────────────────────────────
    logger, emitter, gui_handler, log_path = setup_logging()
    set_language('en')
    win = Cammello.MainWindow(logger, emitter, gui_handler, log_path)
    check('the window has a manual handler', hasattr(win, '_open_manual'))

    menu = help_menu(win)
    check('a Help menu exists', menu is not None)
    if menu:
        texts = [a.text() for a in menu.actions() if a.text()]
        check('the manual is the first Help entry',
              texts and 'manual' in texts[0].lower(), str(texts[:2]))
        entry = [a for a in menu.actions() if 'manual' in a.text().lower()]
        check('it carries the standard help shortcut (F1)',
              entry and entry[0].shortcut() == QKeySequence.HelpContents,
              entry[0].shortcut().toString() if entry else '-')
    win.close()

    # ── Translation: the label changes with the language ────────────────
    seen = {}
    for code, _name in UI_LANGUAGES:
        set_language(code)
        w = Cammello.MainWindow(logger, emitter, gui_handler, log_path)
        m = help_menu(w)
        if m:
            first = [a.text() for a in m.actions() if a.text()][0]
            seen[code] = first
        w.close()
    check('every language has its own label',
          len(set(seen.values())) == len(seen), str(list(seen.values())))
    check('the German label is translated',
          'Handbuch' in seen.get('de', ''), seen.get('de', ''))

    # ── The handler follows the current language ────────────────────────
    for code, _name in UI_LANGUAGES:
        set_language(code)
        check(f'the handler would open the {code} page',
              manual_url(current_language()).endswith('/' + code))
    set_language('en')

    print('\n' + ('ALL MANUAL CHECKS PASSED' if not FAILURES
                  else f'FAILURES: {FAILURES}'))
    return 1 if FAILURES else 0


if __name__ == '__main__':
    sys.exit(main())
