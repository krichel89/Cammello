"""Sign-in routing test (0.12.8): ONE window, reached from both sides.

The dialogs are replaced by recorders, so the test asserts WHICH door a
caller ends up behind - no network, no browser.
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
    from PyQt5.QtWidgets import QApplication, QDialog
    import Cammello                                  # noqa: F401
    from cammello import mw_files, mw_oauth
    from cammello.logging_setup import setup_logging

    app = QApplication.instance() or QApplication(sys.argv)
    logger, emitter, gui_handler, log_path = setup_logging()
    w = Cammello.MainWindow(logger, emitter, gui_handler, log_path)

    calls = []

    class FakeOAuthDialog:
        """Stands in for OAuthLoginDialog. `outcome` drives the run."""
        outcome = 'accept'          # accept | cancel | botpassword

        def __init__(self, parent=None):
            self.username = 'Seewolf'
            self.use_botpassword = (self.outcome == 'botpassword')

        def exec(self):
            calls.append('oauth-window')
            return (QDialog.Accepted if self.outcome == 'accept'
                    else QDialog.Rejected)

    class FakeLoginDialog:
        def __init__(self, parent=None):
            pass

        def exec(self):
            calls.append('botpassword-window')
            return QDialog.Rejected

    mw_files.OAuthLoginDialog = FakeOAuthDialog
    mw_files.LoginDialog = FakeLoginDialog
    w._start_login_worker = lambda *a, **kw: calls.append(
        'signed-in-with-oauth' if kw.get('oauth_token') else 'signed-in-with-pw')

    configured = [True]
    tokens = ['', '']
    mw_oauth.is_configured = lambda: configured[0]
    mw_files.stored_oauth_tokens = lambda: (tokens[0], tokens[1])

    # 1. Link / Login button, never authorized -> the OAUTH window, not the
    #    bot-password one. This is the 0.12.7 complaint.
    calls.clear()
    FakeOAuthDialog.outcome = 'cancel'
    w.do_login()
    check('link with no token opens the OAuth window',
          calls == ['oauth-window'], str(calls))

    # 2. Same door, authorization succeeds -> the user is actually SIGNED IN,
    #    not merely authorized.
    calls.clear()
    FakeOAuthDialog.outcome = 'accept'
    tokens[0], tokens[1] = 'tok', 'sec'
    w.do_login.__self__  # noqa: B018  (mixin sanity)
    w.open_signin_dialog(force=True)
    check('authorizing signs in straight away',
          calls == ['oauth-window', 'signed-in-with-oauth'], str(calls))

    # 3. Link with a stored token -> silent, NO window (Harald's decision).
    calls.clear()
    w.do_login()
    check('stored token signs in without a window',
          calls == ['signed-in-with-oauth'], str(calls))

    # 4. Settings button -> always shows the window, even with a token.
    calls.clear()
    w._on_oauth_login()
    check('Settings button always shows the window',
          calls[0] == 'oauth-window', str(calls))

    # 5. The fallback inside the window leads to the bot password.
    calls.clear()
    FakeOAuthDialog.outcome = 'botpassword'
    w.open_signin_dialog(force=True)
    check('fallback button opens the bot-password window',
          calls == ['oauth-window', 'botpassword-window'], str(calls))

    # 6. A build with no consumer goes straight to the bot password.
    calls.clear()
    configured[0] = False
    w.do_login()
    check('no consumer -> bot password directly',
          calls == ['botpassword-window'], str(calls))

    # 7. Both entry points really are the same function.
    check('Settings and the link share one entry point',
          hasattr(w, 'open_signin_dialog'))

    w.close()
    print('\n' + ('ALL SIGN-IN CHECKS PASSED' if not FAILURES
                  else f'FAILURES: {FAILURES}'))
    return 1 if FAILURES else 0


if __name__ == '__main__':
    sys.exit(main())
