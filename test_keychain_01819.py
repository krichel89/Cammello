"""Wie oft Cammello den Schluesselbund fragt (0.18.19).

Harald: "Die vierfache Frage nach dem Passwort fuer den Schluesselbund ist
aber immer noch da, bleibt auch nach Neustart des Programms." Ursache waren
am Ende alte Eintraege aus der unsignierten App, deren Zugriffsliste auf ein
Programm zeigte, das es so nicht mehr gab. Der Code hat aber mitgeholfen:

  * die beiden Faecher von VOR 0.14 ('mw-oauth:token' und ':secret')
    wurden bei JEDEM Start gesucht, auch in einer Installation, die sie nie
    hatte - auf macOS ist jede Suche eine eigene Passwortfrage;
  * die Umzugsloeschung wurde nicht geprueft: schlug sie fehl, blieben die
    alten Faecher liegen und wurden fuer immer weiter gesucht;
  * der Status im Einstellungsfenster las OAuth 2 UND OAuth 1, obwohl beide
    Antworten dieselbe Zeile auf dem Schirm ergeben.

Geprueft wird mit einem gefaelschten Schluesselbund, der MITZAEHLT:

  1. ohne Altlasten wird zweimal gesucht - einmal, und nie wieder,
  2. die Merkung ueberlebt den Programmstart,
  3. mit Altlasten wird umgezogen, geloescht und dann gemerkt,
  4. eine FEHLGESCHLAGENE Loeschung wird NICHT gemerkt (sonst waere eine
     echte Anmeldung verloren),
  5. die Statuszeile fragt die 1.0a-Faecher gar nicht mehr (0.18.22),
  6. das Entfernen der Berechtigung raeumt beides weg.
"""
import json
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import Cammello        # the shim; also puts the package on the path
from cammello import credentials

fails = []


def check(name, cond, detail=''):
    print(('PASS' if cond else 'FAIL'), name, detail)
    if not cond:
        fails.append(name)


check('the shim still exposes the package', hasattr(Cammello, 'main'))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QSettings
from cammello.constants import APP_NAME
from cammello import widgets

app = QApplication.instance() or QApplication(sys.argv)


class FakeKeychain:
    """Counts every read, because every read is a password prompt."""

    def __init__(self, store=None, deletable=True):
        self.store = dict(store or {})
        self.reads = []
        self.deleted = []
        self.deletable = deletable

    def load(self, slot):
        self.reads.append(slot)
        return self.store.get(slot)

    def store_(self, slot, secret):
        self.store[slot] = secret
        return True

    def delete(self, slot):
        self.deleted.append(slot)
        if not self.deletable:
            return False          # a locked keychain, a denied prompt
        self.store.pop(slot, None)
        return True


def install(fake):
    credentials.load = fake.load
    credentials.store = fake.store_
    credentials.delete = fake.delete
    credentials.clear_cache = lambda: None


_real = (credentials.load, credentials.store, credentials.delete,
         credentials.clear_cache)


def fresh_settings():
    s = QSettings(APP_NAME, 'Login')
    for key in ('oauth_token', 'oauth_secret', 'oauth_username',
                'oauth2_tokens', widgets.LEGACY_OAUTH_KEY):
        s.remove(key)
    s.sync()
    return s


TOKENS = credentials.mw_oauth_slot('tokens')
TOK = credentials.mw_oauth_slot('token')
SEC = credentials.mw_oauth_slot('secret')

try:
    # ── 1. and 2. nothing stored: asked once, then never again ───────────
    fresh_settings()
    fake = FakeKeychain()
    install(fake)
    widgets.stored_oauth_tokens()
    first = list(fake.reads)
    check('a first run looks for the two legacy slots',
          TOK in first and SEC in first, str(first))

    fake.reads.clear()
    widgets.stored_oauth_tokens()
    check('the next call does not ask for them again',
          TOK not in fake.reads and SEC not in fake.reads, str(fake.reads))
    check('but it still reads the combined slot',
          TOKENS in fake.reads, str(fake.reads))
    check('and the answer is written down, so a restart keeps it',
          widgets._legacy_slots_gone())

    # ── 3. legacy tokens present: migrate, delete, remember ──────────────
    fresh_settings()
    fake = FakeKeychain({TOK: 'T-old', SEC: 'S-old'})
    install(fake)
    got = widgets.stored_oauth_tokens()
    check('the old pair is still found', got == ('T-old', 'S-old'), str(got))
    check('and moved into the combined slot',
          json.loads(fake.store[TOKENS]) == {'token': 'T-old',
                                             'secret': 'S-old'})
    check('the two old slots are deleted',
          TOK in fake.deleted and SEC in fake.deleted)
    check('and that is remembered', widgets._legacy_slots_gone())

    fake.reads.clear()
    got = widgets.stored_oauth_tokens()
    check('the next start reads ONE slot, not three',
          fake.reads == [TOKENS], str(fake.reads))
    check('and still knows who we are', got == ('T-old', 'S-old'))

    # ── 4. a delete that fails must NOT be remembered ────────────────────
    fresh_settings()
    fake = FakeKeychain({TOK: 'T-old', SEC: 'S-old'}, deletable=False)
    install(fake)
    got = widgets.stored_oauth_tokens()
    check('a failed delete still returns the tokens',
          got == ('T-old', 'S-old'))
    check('but it is NOT written down - the slots are still there',
          not widgets._legacy_slots_gone())
    # The migration WRITE succeeded even though the deletes did not, so the
    # combined slot answers from now on and the stale leftovers are never
    # read again - one prompt, not three. They stay in the keychain as
    # clutter, which the log warns about.
    fake.reads.clear()
    got = widgets.stored_oauth_tokens()
    check('the combined slot answers anyway, so still one prompt',
          fake.reads == [TOKENS], str(fake.reads))
    check('and the tokens survive', got == ('T-old', 'S-old'))
    # If the combined slot is ever empty again, the probe has to come back -
    # that is what leaving the flag unset buys.
    fake.store.pop(TOKENS)
    fake.reads.clear()
    widgets.stored_oauth_tokens()
    check('an empty combined slot brings the probe back',
          TOK in fake.reads, str(fake.reads))

    # ── 6. removing the authorization ────────────────────────────────────
    fresh_settings()
    fake = FakeKeychain({TOKENS: '{}', TOK: 'T', SEC: 'S'})
    install(fake)
    widgets.clear_stored_oauth()
    check('clearing removes all three slots',
          set(fake.deleted) >= {TOKENS, TOK, SEC}, str(fake.deleted))
    check('and settles the legacy question', widgets._legacy_slots_gone())

    fresh_settings()
    fake = FakeKeychain({TOKENS: '{}', TOK: 'T', SEC: 'S'}, deletable=False)
    install(fake)
    widgets.clear_stored_oauth()
    check('a clear whose deletes failed leaves the question open',
          not widgets._legacy_slots_gone())
finally:
    (credentials.load, credentials.store, credentials.delete,
     credentials.clear_cache) = _real
    fresh_settings()


# ── 5. an OAuth 2.0 session never touches the 1.0a slots ─────────────────────

import ast

src = open(os.path.join(os.path.dirname(widgets.__file__), 'main_window.py'),
           encoding='utf-8').read()
tree = ast.parse(src)
func = None
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef) and node.name == '_refresh_oauth_status':
        func = node
check('_refresh_oauth_status is still there', func is not None)
body = ast.get_source_segment(src, func) if func else ''
# 0.18.22: the 1.0a path is gone, so the status line does not ask about
# those slots AT ALL any more - which is the strongest form of what this
# check always wanted. A leftover 1.0a pair can no longer sign anything
# in, so counting it as "authorized" would have been a lie.
calls = 0
if func:
    for node in ast.walk(func):
        if isinstance(node, ast.Call) and getattr(node.func, 'id', '') \
                == 'stored_oauth_tokens':
            calls += 1
check('it does not ask for the 1.0a tokens at all any more', calls == 0,
      str(calls))
check('and it reads the 2.0 token instead',
      'stored_oauth2_tokens' in body, body[:0] or 'see source')

print()
print('FAILURES:', ', '.join(fails) if fails else 'none')
sys.exit(1 if fails else 0)
