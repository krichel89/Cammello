"""Workflows aus der Textdatei (0.16.1).

Prueft das Format, die Fehlertoleranz und die Wirkung in der Oberflaeche:
sichtbare Felder, Vorbelegung, Beispiele und das Neuladen. Der HOME-Pfad
wird umgebogen, damit kein echtes ~/Cammello/workflows.toml angefasst wird.
"""
import os
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
_HOME = tempfile.mkdtemp()
os.environ['HOME'] = _HOME
os.environ['USERPROFILE'] = _HOME          # Windows

from PyQt5.QtWidgets import QApplication, QMessageBox

import Cammello
from cammello import i18n, workflows
from cammello import workflow_config as wc
from cammello.logging_setup import setup_logging

app = QApplication(sys.argv)
logger, emitter, gui_handler, log_path = setup_logging()

fails = []


def check(name, cond, detail=''):
    if cond:
        print('PASS', name, detail)
    else:
        print('FAIL', name, detail)
        fails.append(name)


def write(text):
    os.makedirs(os.path.dirname(wc.path()), exist_ok=True)
    with open(wc.path(), 'w', encoding='utf-8') as fh:
        fh.write(text)
    return wc.reload()


# ── Ort und Vorlage ──────────────────────────────────────────────────────
check('the file lives in the user directory, not inside the program',
      wc.path().startswith(_HOME) and 'assets' not in wc.path(),
      wc.path())
check('it is created on first load', wc.load() and os.path.exists(wc.path()))
_tpl = open(wc.path(), encoding='utf-8').read()
check('the template lists every field name',
      all(n in _tpl for n in wc.FIELD_NAMES))
check('it names the menu path for reloading',
      'Reload workflows' in _tpl or 'neu laden' in _tpl)
check('the template parses back into the built-in workflows',
      [w['key'] for w in wc.load()] == [w['key'] for w in wc.BUILTIN])
check('a second load does not rewrite the file',
      wc.template_text() == _tpl)

# ── Fehlertoleranz: nichts davon darf Cammello aufhalten ─────────────────
_e = write('[[workflow]\nschluessel = "a"\n')
check('a syntax error falls back to the built-ins',
      [w['key'] for w in _e] == [w['key'] for w in wc.BUILTIN])
check('and names line and column', wc.LAST_ERROR and 'line' in wc.LAST_ERROR,
      str(wc.LAST_ERROR))
_e = write('# nothing but a comment\n')
check('an empty file falls back too',
      [w['key'] for w in _e] == [w['key'] for w in wc.BUILTIN])
check('the reason is recorded', bool(wc.LAST_ERROR))

_e = write('[[workflow]]\nschluessel = "x"\nname = "X"\n'
           'felder_aus = ["gibtsnicht", "galerieseite"]\n')
check('an unknown field name is ignored, the known one kept',
      _e[0]['hide'] == ['galerieseite'], str(_e[0]['hide']))
check('and it is reported as a warning',
      any('gibtsnicht' in w for w in wc.LAST_WARNINGS),
      str(wc.LAST_WARNINGS))
check('a file with one usable workflow is NOT discarded',
      wc.LAST_ERROR is None)

_e = write('[[workflow]]\nschluessel = "y"\nname = "Y"\n'
           '[workflow.vorbelegung]\nkamerastandort = "x"\nautor = "A"\n')
check('presetting a hide-only field is refused',
      _e[0]['preset'] == {'autor': 'A'}, str(_e[0]['preset']))

_e = write('[[workflow]]\nschluessel = "z"\nname = "Z1"\n'
           '[[workflow]]\nschluessel = "z"\nname = "Z2"\n')
check('a repeated schluessel is dropped, not silently merged',
      len(_e) == 1 and _e[0]['label'] == 'Z1', str(_e))

_e = write('[[workflow]]\nschluessel = "s"\nname = "S"\n'
           'felder_aus = "galerieseite"\n')
check('a single field name without brackets is accepted',
      _e[0]['hide'] == ['galerieseite'], str(_e[0]['hide']))

_e = write('[[workflow]]\nschluessel = "n"\n')
check('a workflow without a name falls back to its schluessel',
      _e[0]['label'] == 'n', _e[0]['label'])

# ── Die Ausschlussliste ist eine Ausschlussliste ─────────────────────────
_e = write('[[workflow]]\nschluessel = "leer"\nname = "Leer"\n')
check('a workflow that hides nothing shows everything',
      workflows.hidden_fields('leer') == [])
check('so a field added later is visible without editing the file',
      not workflows.is_hidden('leer', wc.FIELD_NAMES[-1]))

# ── Wirkung in der Oberflaeche ───────────────────────────────────────────
i18n.set_language('de')
w = Cammello.MainWindow(logger, emitter, gui_handler, log_path)
_orig_info = QMessageBox.information
_orig_warn = QMessageBox.warning
_orig_question = QMessageBox.question
QMessageBox.information = staticmethod(lambda *a, **k: None)
QMessageBox.warning = staticmethod(lambda *a, **k: None)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)
try:
    write('''
[[workflow]]
schluessel = "presse"
name = "Pressekonferenz"
felder_aus = ["kamerastandort", "objektstandort", "galerieseite"]

  [workflow.vorbelegung]
  vorlagen = "{{Wikiportraits}}"

  [workflow.beispiel]
  autor = "[[User:Seewolf|Harald Krichel]]"

[[workflow]]
schluessel = "denkmal"
name = "Denkmal"
felder_aus = ["entstanden_waehrend", "zeigt"]
''')
    w.other_templates_edit.clear()
    w.author_edit.clear()
    w._reload_workflows()
    labels = [w.workflow_combo.itemText(i)
              for i in range(w.workflow_combo.count())]
    check('own workflows reach the dropdown without a restart',
          labels == ['Pressekonferenz', 'Denkmal'], str(labels))
    check('a preset fills an empty field',
          w.other_templates_edit.text() == '{{Wikiportraits}}',
          w.other_templates_edit.text())
    check('an example is only a grey hint',
          w.author_edit.placeholderText().startswith('[[User:Seewolf')
          and w.author_edit.text() == '',
          repr(w.author_edit.text()))
    check('a hidden field is really hidden',
          w.base_struct.gallery_suffix.isHidden())
    check('its caption goes with it',
          (w._label_for(w, w.base_struct.gallery_suffix) is None
           or w._label_for(w, w.base_struct.gallery_suffix).isHidden()))

    # A preset must never overwrite typed text.
    w.other_templates_edit.setText('{{Handgetippt}}')
    w.workflow_combo.setCurrentIndex(w.workflow_combo.findData('denkmal'))
    w.workflow_combo.setCurrentIndex(w.workflow_combo.findData('presse'))
    check('switching back does not overwrite what was typed',
          w.other_templates_edit.text() == '{{Handgetippt}}',
          w.other_templates_edit.text())

    w.workflow_combo.setCurrentIndex(w.workflow_combo.findData('denkmal'))
    check('any field can be hidden now, not just the coordinates',
          w.file_struct.depicts.isHidden())
    check('and the event field with it',
          w.base_struct.created_during.isHidden())
    check('the button that fills the event follows the field',
          getattr(w, 'iptc_event_btn', None) is None
          or w.iptc_event_btn.isHidden())

    # Expert mode overrules the workflow, as before.
    expert = getattr(w, 'expert_cb', None)
    if expert is not None:
        expert.setChecked(True)
        w._apply_workflow_visibility()
        check('expert mode shows everything again',
              not w.file_struct.depicts.isHidden())
        expert.setChecked(False)
        w._apply_workflow_visibility()

    # A broken file while running: keep working, say so, do not crash.
    write('[[workflow]\nkaputt\n')
    w._reload_workflows()
    check('a broken file leaves a usable dropdown',
          w.workflow_combo.count() == len(wc.BUILTIN),
          str(w.workflow_combo.count()))
    check('the selected workflow is still a real one',
          w.current_workflow() in [b['key'] for b in wc.BUILTIN],
          w.current_workflow())
finally:
    QMessageBox.information = _orig_info
    QMessageBox.warning = _orig_warn
    QMessageBox.question = _orig_question
    w.close()

print('---')
print('FAILURES:', fails if fails else 'none')
print(f'{len(fails)} failure(s)')
sys.exit(1 if fails else 0)
