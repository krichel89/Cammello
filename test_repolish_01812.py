"""Der Absturz beim Umschalten des Farbschemas (0.18.12).

Gefunden beim zweiten Durchlauf der Testreihe fuer 0.18.12:
test_cullview.py starb mit SIGSEGV, immer an derselben Stelle - der Zeile
nach "settings tab exists", also beim Wechsel auf das dunkle Schema.
Haeufigkeit gemessen: 14 Abstuerze in 33 Laeufen, waehrend derselbe Baum
mit dem alten camera.py 0 von 44 zeigte. Der Ausloeser war also eine
Verschiebung der Speicherlage, nicht der neue Code - der Fehler lag
darunter.

Es ist derselbe Mechanismus, den 0.17.1 schon einmal getroffen hat:
QApplication.setStyleSheet() laesst QStyleSheetStyle jedes Widget
nachpolieren, das es je gesehen hat. 0.17.1 hat aufgehoert, DASSELBE
Blatt zweimal zu setzen. Das reicht nicht: wenn sich das Blatt wirklich
aendert, laeuft dieselbe Runde ueber Widgets, die Python losgelassen hat,
die Qt aber noch nicht geloescht hat - deleteLater() stellt die Loeschung
nur in die Schlange. Vor dem Setzen wird die Schlange jetzt geleert.

Verteidigt wird:

  1. der Aufraeumschritt steht im Quelltext vor setStyleSheet,
  2. gleiches Blatt bleibt gleiches Blatt (die Bremse aus 0.17.1 haelt),
  3. wiederholtes Umschalten mit fallengelassenen Fenstern ueberlebt.
"""
import ast
import gc
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import Cammello        # the shim; also puts the package on the path
from cammello import main_window

fails = []


def check(name, cond, detail=''):
    print(('PASS' if cond else 'FAIL'), name, detail)
    if not cond:
        fails.append(name)


check('the shim still exposes the package', hasattr(Cammello, 'main'))


# ── 1. the order in the source ───────────────────────────────────────────────

path = os.path.join(os.path.dirname(main_window.__file__), 'main_window.py')
src = open(path, encoding='utf-8').read()
tree = ast.parse(src)
func = next((n for n in tree.body if isinstance(n, ast.FunctionDef)
             and n.name == '_apply_app_stylesheet'), None)
check('_apply_app_stylesheet is still a module function', func is not None)

calls = []
for node in ast.walk(func) if func else []:
    if isinstance(node, ast.Call):
        target = node.func
        if isinstance(target, ast.Attribute):
            calls.append(target.attr)
        elif isinstance(target, ast.Name):
            calls.append(target.id)
check('the deferred deletions are flushed',
      'sendPostedEvents' in calls, str(calls))
check('and the cycles are collected first',
      'collect' in calls and calls.index('collect')
      < calls.index('sendPostedEvents'), str(calls))
check('both happen before the sheet is set',
      'setStyleSheet' in calls
      and calls.index('sendPostedEvents') < calls.index('setStyleSheet'),
      str(calls))


# ── 2. and 3. what it does when run ──────────────────────────────────────────

from PyQt5.QtWidgets import QApplication, QLabel, QWidget

app = QApplication.instance() or QApplication(sys.argv)

main_window._apply_app_stylesheet()
first = app.styleSheet()
main_window._apply_app_stylesheet()
check('setting the same sheet again is still a no-op',
      app.styleSheet() == first)

# Widgets Python has dropped but Qt has not deleted yet are exactly what
# the repolish used to walk into. Build some, drop them, switch.
survived = True
try:
    for round_no in range(6):
        holder = QWidget()
        for i in range(30):
            child = QLabel(f'label {i}', holder)
            child.setStyleSheet('color: #808080;')
        holder.deleteLater()
        del holder
        main_window.set_current_input_style(round_no % 2 == 0)
        main_window._apply_app_stylesheet()
    gc.collect()
except Exception as exc:                                  # pragma: no cover
    survived = False
    print('EXCEPTION', repr(exc))
check('repeated switching with dropped widgets survives', survived)

print()
print('FAILURES:', ', '.join(fails) if fails else 'none')
sys.exit(1 if fails else 0)
