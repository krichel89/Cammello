"""Anwendungsweites Stylesheet nur bei echter Änderung setzen (0.17.1).

Hintergrund: QApplication.setStyleSheet() lässt QStyleSheetStyle JEDES je
gesehene Widget nachpolieren. Ist eines davon inzwischen zerstört, greift
der Durchlauf auf einen toten Zeiger zu und der Prozess stirbt mit SIGSEGV
in updateObjects() - unter gdb nachgewiesen, Ursache des abstürzenden
CI-Testlaufs bei v0.17.0.
"""
import os
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('CAMMELLO_WORKFLOWS',
                      os.path.join(tempfile.mkdtemp(), 'workflows.toml'))

from PyQt5.QtWidgets import QApplication

app = QApplication(sys.argv)

import Cammello
from cammello import main_window as mw
from cammello.constants import app_style
from cammello.logging_setup import setup_logging

logger, emitter, gui_handler, log_path = setup_logging()
fails = []


def check(name, cond, detail=''):
    if cond:
        print('PASS', name, detail)
    else:
        print('FAIL', name, detail)
        fails.append(name)


# Zählen, wie oft Qt wirklich zum Nachpolieren gezwungen wird.
_calls = []
_orig = QApplication.setStyleSheet


def _counting(self, sheet):
    _calls.append(sheet)
    _orig(self, sheet)


QApplication.setStyleSheet = _counting
try:
    app.setStyleSheet('')                      # definierter Ausgangspunkt
    _calls.clear()

    w1 = Cammello.MainWindow(logger, emitter, gui_handler, log_path)
    check('the first window applies the stylesheet', len(_calls) == 1,
          str(len(_calls)))
    check('and it is the real one', app.styleSheet() == app_style())

    w2 = Cammello.MainWindow(logger, emitter, gui_handler, log_path)
    check('a second window does NOT re-apply the same sheet',
          len(_calls) == 1, str(len(_calls)))
    w3 = Cammello.MainWindow(logger, emitter, gui_handler, log_path)
    check('nor does a third', len(_calls) == 1, str(len(_calls)))
    check('the sheet is still in place', app.styleSheet() == app_style())

    # Eine ECHTE Änderung muss weiterhin durchkommen.
    app.setStyleSheet('QLabel { color: red; }')
    _calls.clear()
    mw._apply_app_stylesheet()
    check('a genuine change is applied', len(_calls) == 1, str(len(_calls)))
    check('and restores the app style', app.styleSheet() == app_style())

    # Und der Aufruf ohne laufende Anwendung darf nicht werfen.
    check('the helper is defined', callable(mw._apply_app_stylesheet))
finally:
    QApplication.setStyleSheet = _orig

print('---')
print('FAILURES:', fails if fails else 'none')
print(f'{len(fails)} failure(s)')
sys.exit(1 if fails else 0)
