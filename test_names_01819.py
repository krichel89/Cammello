"""Dateinamen: Leerzeichen-Fehler und Namen aus den Beschreibungen (0.18.19).

Harald: "Benutzer hatte wieder Probleme mit Dateinamen beim Hochladen. […]
Der Benutzer sagt allerdings, er haette zu viele Leerzeichen oder sowas in
den Dateinamen gehabt." Und: "Einmal haette ich gerne eine Funktion, die
vor dem Hochladen per Knopfdruck sinnvolle Dateinamen aus den
Beschreibungen erzeugt."

Der Fehler: MediaWiki nimmt einen Titel nicht so, wie er kommt -
Title.php::secureAndSplit() schreibt ihn um, und ein Upload, dessen Name
diese Umschreibung VERAENDERT ueberlebt, antwortet mit der Warnung
'badfilename'. Cammello hat bis 0.18.18 nur ':', '/', '\\' und die
verbotenen Titelzeichen geprueft; zwei Leerzeichen hintereinander gingen
glatt durch und kamen als Warnung vom Server zurueck - mit einer Meldung,
die die Ursache nicht nennt, weil der Server nur sagt, was er STATTDESSEN
gespeichert haette.

Die Regeln sind nicht aus dem Gedaechtnis geschrieben, sondern an
pywikibot 11.7.0 abgelesen (pywikibot/page/_links.py, dessen eigener
Kommentar sagt: "adapted from Title.php : secureAndSplit()"). Commons
selbst war aus der Sandbox nicht erreichbar.

Geprueft wird:

  1. mehrfache Leerzeichen, Unterstriche und Unicode-Leerzeichen werden
     zusammengefasst,
  2. Randfaelle: Richtungsmarken, NFC, Leerzeichen vor der Endung,
  3. der erste Buchstabe wird gross geschrieben, wie MediaWiki es tut,
  4. was MediaWiki ABWEIST (%XX, HTML-Entitaeten, ~~~, ./..) ergibt eine
     Meldung, die das Zeichen nennt,
  5. was frueher schon geprueft wurde, wird weiter geprueft,
  6. title_changes() sagt in Worten, was sich aendern wuerde,
  7. die badfilename-Meldung nennt jetzt auch die Leerzeichen,
  8. aus einer Bildunterschrift werden Person und Veranstaltung,
  9. daraus ein Dateiname, mit Kameranummer oder laufender Nummer,
 10. die Kameranummer steht nur noch an EINER Stelle im Quelltext,
 11. die beiden neuen Schemata im Umbenennen-Dialog,
 12. der Knopf und sein Vorschaufenster.
"""
import ast
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import Cammello        # the shim; also puts the package on the path
from cammello import sdc

fails = []


def check(name, cond, detail=''):
    print(('PASS' if cond else 'FAIL'), name, detail)
    if not cond:
        fails.append(name)


check('the shim still exposes the package', hasattr(Cammello, 'main'))

SRC = '/tmp/IMG_4711.jpg'


def norm(name):
    return sdc.normalize_commons_filename(name, SRC)


def _refused(name):
    """True when normalize_commons_filename rejects `name`."""
    try:
        norm(name)
        return False
    except ValueError:
        return True


# ── 1. the bug Harald reported ───────────────────────────────────────────────

check('two spaces become one',
      norm('Anna  Mueller.jpg') == 'Anna Mueller.jpg',
      norm('Anna  Mueller.jpg'))
check('a whole row of them too',
      norm('Anna   Mueller    at   Berlinale.jpg')
      == 'Anna Mueller at Berlinale.jpg')
check('underscores are spaces to MediaWiki',
      norm('Anna_Mueller_2026.jpg') == 'Anna Mueller 2026.jpg')
check('a non-breaking space is a space',
      norm('Anna Mueller 2026.jpg') == 'Anna Mueller 2026.jpg')
check('and so are the typographic ones',
      norm('Anna Mueller　X.jpg') == 'Anna Mueller X.jpg')
check('leading and trailing spaces go',
      norm('   Anna Mueller.jpg   ') == 'Anna Mueller.jpg')


# ── 2. the edges ─────────────────────────────────────────────────────────────

check('writing-direction marks are removed',
      norm('Anna‎Mueller.jpg') == 'AnnaMueller.jpg',
      norm('Anna‎Mueller.jpg'))
check('accents are composed (NFC), so the name matches the server',
      norm('Anna Müller.jpg') == 'Anna Müller.jpg')
check('a space before the extension is dropped',
      norm('Anna Mueller .jpg') == 'Anna Mueller.jpg')


# ── 3. first letter ──────────────────────────────────────────────────────────

check('the first letter is capitalized, as MediaWiki does',
      norm('anna mueller.jpg') == 'Anna mueller.jpg',
      norm('anna mueller.jpg'))
check('but only the first - the rest is left alone',
      norm('von Trier at Cannes.jpg') == 'Von Trier at Cannes.jpg')
check('a name starting with a digit is untouched',
      norm('2026 Berlinale.jpg') == '2026 Berlinale.jpg')


# ── 4. what MediaWiki refuses outright ───────────────────────────────────────

for bad, word in (('Foo%20Bar.jpg', 'percent'),
                  ('Tom &amp; Jerry.jpg', 'HTML'),
                  ('Sig ~~~ here.jpg', '~~~')):
    raised = None
    try:
        norm(bad)
    except ValueError as exc:
        raised = str(exc)
    check(f'{word} is refused with a reason',
          raised is not None and word.lower() in raised.lower(),
          (raised or 'not refused')[:60])

check('the replacement character is refused', _refused('Anna �.jpg'))
# An empty target means "use the source name" - and that name goes through
# the same rules, so an underscore in IMG_4711.jpg no longer earns a
# badfilename warning for a row nobody ever typed into.
check('a name of only whitespace falls back to the source name',
      norm('   ') == 'IMG 4711.jpg', norm('   '))


# ── 5. the old checks still hold ─────────────────────────────────────────────

check('a colon is still refused', _refused('Panel: the future.jpg'))
check('a pipe is still refused', _refused('Anna | Mueller.jpg'))
check('an over-long name is still refused', _refused('A' * 300 + '.jpg'))
check('the File: prefix is still stripped',
      norm('File:Anna Mueller.jpg') == 'Anna Mueller.jpg')
check('a missing extension still comes from the source',
      norm('Anna Mueller') == 'Anna Mueller.jpg')


# ── 6. saying what would change ──────────────────────────────────────────────

changes = sdc.title_changes('anna  Mueller_x .jpg')
check('title_changes names the repeated spaces',
      any('repeated spaces' in c for c in changes), str(changes))
check('and the underscores', any('underscore' in c for c in changes))
check('and the capital letter', any('capitalized' in c for c in changes))
check('a clean name produces no complaints',
      sdc.title_changes('Anna Mueller 4711.jpg') == [])


# ── 7. the upload error message ──────────────────────────────────────────────

from cammello.api import MediaWikiApi

msg = MediaWikiApi._explain_badfilename('Anna  Mueller.jpg',
                                        'Anna Mueller.jpg')
check('badfilename now names the spaces',
      'repeated spaces' in msg, msg[:70])
msg_colon = MediaWikiApi._explain_badfilename('A: B.jpg', 'A- B.jpg')
check('and still names a colon first',
      'colon' in msg_colon, msg_colon[:50])


# ── 8. and 9. names out of captions ──────────────────────────────────────────

check('a caption splits into person and event',
      sdc.split_caption('Anna Mueller at the Berlinale 2026')
      == ('Anna Mueller', 'Berlinale 2026'),
      str(sdc.split_caption('Anna Mueller at the Berlinale 2026')))
check('the German separator works too',
      sdc.split_caption('Anna Mueller bei der Berlinale 2026')
      == ('Anna Mueller', 'Berlinale 2026'))
check('a caption without a separator is all person',
      sdc.split_caption('Anna Mueller') == ('Anna Mueller', ''))
check('an article is only dropped when something follows it',
      sdc.split_caption('Anna Mueller at the') == ('Anna Mueller', 'the'))
check('an empty caption gives nothing', sdc.split_caption('') == ('', ''))

check('the name carries person, event and the camera number',
      sdc.name_from_caption('Anna Mueller at the Berlinale 2026',
                            'IMG_4711')
      == 'Anna Mueller at Berlinale 2026 4711',
      sdc.name_from_caption('Anna Mueller at the Berlinale 2026', 'IMG_4711'))
check('without an event it is person plus number',
      sdc.name_from_caption('Anna Mueller', 'DSC00123')
      == 'Anna Mueller 00123')
check('the event can be left out on purpose',
      sdc.name_from_caption('Anna Mueller at the Berlinale', 'IMG_4711',
                            with_event=False) == 'Anna Mueller 4711')
check('a source without a number falls back to the running one',
      sdc.name_from_caption('Anna Mueller', 'scan', seq='007')
      == 'Anna Mueller 007')
check('no caption, no name',
      sdc.name_from_caption('', 'IMG_4711') == '')
check('the built name is already normalized',
      sdc.name_from_caption('Anna   Mueller  at  the  Berlinale', 'IMG_4711')
      == 'Anna Mueller at Berlinale 4711')
check('the separator in the file name is English whatever the caption was',
      ' at ' in sdc.name_from_caption('Anna Mueller bei der Berlinale',
                                      'IMG_4711'))

check('a caption is picked by language, English as the fallback',
      sdc.pick_caption({'caption_en': 'A at B', 'caption_de': 'A bei B'},
                       ['de']) == 'A bei B')
check('and any caption beats none',
      sdc.pick_caption({'caption_it': 'Luca Rossi'}, ['de']) == 'Luca Rossi')
check('no captions at all gives nothing',
      sdc.pick_caption({'depicts': 'Q1'}, ['de']) == '')


# ── 10. one implementation of the camera number ──────────────────────────────

src = open(os.path.join(os.path.dirname(sdc.__file__), 'widgets.py'),
           encoding='utf-8').read()
tree = ast.parse(src)
own = [n for n in ast.walk(tree)
       if isinstance(n, ast.FunctionDef) and n.name == 'camera_number']
check('widgets.py no longer keeps its own camera_number', not own,
      f'{len(own)} definition(s)')
check('it delegates to the sdc one', 'sdc.camera_number' in src)

from cammello.widgets import BulkRenameDialog
check('and the old name still works',
      BulkRenameDialog.camera_number('IMG_4711') == '4711')
check('digits still clamp', BulkRenameDialog.camera_number('DSC00123', 3)
      == '123')
check('auto_digits still works', BulkRenameDialog.auto_digits(
    ['IMG_4711', 'IMG_4712']) == 4)


# ── 11. and 12. the dialog and the button ────────────────────────────────────

from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import QSettings
from cammello.constants import APP_NAME
from cammello.main_window import setup_logging
from cammello.widgets import NamesFromDescriptionDialog

app = QApplication.instance() or QApplication(sys.argv)

dlg = BulkRenameDialog(
    3, None, sources=['IMG_4711', 'IMG_4712', 'IMG_4713'],
    exts=['.jpg'] * 3, dates=['2026-02-14'] * 3,
    captions=['Anna Mueller at the Berlinale 2026',
              'Anna Mueller at the Berlinale 2026', ''])
for key, want in (('caption_person_event', 'Anna Mueller at Berlinale 2026'),
                  ('caption_person', 'Anna Mueller')):
    idx = dlg.scheme_combo.findData(key)
    check(f'the {key} scheme exists', idx >= 0)
    dlg.scheme_combo.setCurrentIndex(idx)
    names = dlg.names()
    check(f'{key} builds from the caption', names[0].startswith(want),
          names[0])
    check(f'{key} keeps the camera number', names[0].endswith('4711'),
          names[0])
    check(f'{key} leaves a caption-less row its own name',
          names[2] == 'IMG_4713', names[2])
dlg.deleteLater()

from PyQt5.QtWidgets import QTableWidget

preview = NamesFromDescriptionDialog(
    [('IMG_4711.jpg', 'Anna Mueller at Berlinale 2026 4711.jpg'),
     ('IMG_4712.jpg', '')], 1, None)
tbl = preview.findChild(QTableWidget)
check('the preview shows a table', tbl is not None)
check('with one row per file', tbl is not None and tbl.rowCount() == 2)
check('the old name on the left',
      tbl is not None and tbl.item(0, 0).text() == 'IMG_4711.jpg')
check('the new one on the right',
      tbl is not None
      and tbl.item(0, 1).text() == 'Anna Mueller at Berlinale 2026 4711.jpg')
check('and a row without a caption says so',
      tbl is not None and 'caption' in tbl.item(1, 1).text().lower())
preview.deleteLater()

# The button and the wiring on the window.
_ts = QSettings(APP_NAME, 'Main')
_ts.setValue('feature_culling', True)
_ts.sync()
logger, emitter, gui_handler, log_path = setup_logging()
import logging as _logging
for _h in logger.handlers:
    if isinstance(_h, _logging.StreamHandler) and not hasattr(_h,
                                                              'baseFilename'):
        _h.setLevel(_logging.CRITICAL)
QMessageBox.information = staticmethod(lambda *a, **k: None)

w = Cammello.MainWindow(logger, emitter, gui_handler, log_path)
check('the toolbar has the naming button', hasattr(w, 'names_btn'))
check('it is an icon, not a label',
      w.names_btn.text() == '' and not w.names_btn.icon().isNull())
check('its tooltip carries the wording',
      'descriptions' in w.names_btn.toolTip().lower()
      or 'beschreibungen' in w.names_btn.toolTip().lower(),
      w.names_btn.toolTip()[:40])
check('and the action exists', hasattr(w, '_names_from_descriptions'))
check('as does the caption helper', hasattr(w, '_row_caption'))

mw = os.path.join(os.path.dirname(sdc.__file__), 'menus.py')
check('it is in the menu too',
      '_names_from_descriptions' in open(mw, encoding='utf-8').read())

print()
print('FAILURES:', ', '.join(fails) if fails else 'none')
sys.exit(1 if fails else 0)
