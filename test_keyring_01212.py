"""0.12.12: no keychain access at application start.

On macOS every keyring read of an unsigned build pops a keychain prompt;
0.12.11 and earlier performed up to four before the user did anything
(BotPassword prefill, OAuth token + secret, backend probe). This guards
the fix: building the main window touches the credentials module NOT AT
ALL; the accesses happen when the BotPassword dialog or the Settings
window opens. Run as a file.
"""
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
FAILURES = []


def check(name, cond, detail=''):
    print(('PASS ' if cond else 'FAIL ') + name, detail)
    if not cond:
        FAILURES.append(name)


def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from PyQt5.QtWidgets import QApplication
    import Cammello
    from cammello import credentials, main_window
    from cammello.logging_setup import setup_logging

    app = QApplication.instance() or QApplication(sys.argv)

    # Count every call that can reach the OS keyring. Patch in BOTH modules:
    # main_window binds the names via its own import.
    counts = {'load': 0, 'load_pw': 0, 'save_pw': 0, 'backend': 0}
    real_load_pw = credentials.load_mediawiki_password

    def counted(name, ret, real=None):
        def f(*a, **k):
            counts[name] += 1
            return real(*a, **k) if real else ret
        return f

    credentials.load = counted('load', None)
    credentials.load_mediawiki_password = counted('load_pw', '',
                                                 real=real_load_pw)
    credentials.save_mediawiki_password = counted('save_pw', None)
    credentials.backend_available = counted('backend', False)

    logger, emitter, gui_handler, log_path = setup_logging()
    win = Cammello.MainWindow(logger, emitter, gui_handler, log_path)
    win.show()
    app.processEvents()

    check('window build touches the keyring ZERO times',
          counts['load'] == 0 and counts['load_pw'] == 0
          and counts['backend'] == 0, str(counts))
    check('password field starts empty and unloaded',
          win.mw_password_edit.text() == ''
          and win._mw_password_loaded is False)

    # Opening the BotPassword dialog is the moment the password loads.
    win._open_botpassword_dialog()
    app.processEvents()
    check('BotPassword dialog triggers exactly one password load',
          counts['load_pw'] == 1 and win._mw_password_loaded is True,
          str(counts))
    win._botpassword_dialog.close()

    # Second open: no second load.
    win._open_botpassword_dialog()
    check('the load happens only once', counts['load_pw'] == 1)
    win._botpassword_dialog.close()

    # Closing the app saves the (now loaded) password - but see below.
    win.close()
    app.processEvents()
    loaded_save = counts['save_pw']
    check('loaded field IS saved on close', loaded_save >= 1)

    # The dangerous case: a window whose field was NEVER loaded must not
    # save (= delete) anything on close.
    counts['save_pw'] = 0
    win2 = Cammello.MainWindow(logger, emitter, gui_handler, log_path)
    win2.show()
    app.processEvents()
    win2.close()
    app.processEvents()
    check('never-loaded field is NOT saved on close (would delete '
          'the stored secret)', counts['save_pw'] == 0, str(counts))

    print('\n' + ('ALL KEYRING CHECKS PASSED' if not FAILURES
                  else f'FAILURES: {FAILURES}'))
    return 1 if FAILURES else 0


if __name__ == '__main__':
    sys.exit(main())
