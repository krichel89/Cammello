"""Language codes with script parts, alt text, workflow clearing and the
update check (0.15.2)."""
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtWidgets import QApplication, QMessageBox, QTableWidgetItem

import Cammello
from cammello import langcodes, sdc, updates
from cammello.constants import ALT_TEXT_PROPERTY
from cammello.logging_setup import setup_logging

app = QApplication(sys.argv)
logger, emitter, gui_handler, log_path = setup_logging()
w = Cammello.MainWindow(logger, emitter, gui_handler, log_path)

fails = []


def check(name, cond, detail=''):
    if cond:
        print('PASS', name, detail)
    else:
        print('FAIL', name, detail)
        fails.append(name)


# ── language codes ───────────────────────────────────────────────────────────
check('the reported code is valid now', langcodes.looks_valid('ms-Arab'))
check('BCP 47 casing is restored',
      langcodes.normalize('MS-ARAB') == 'ms-Arab',
      langcodes.normalize('MS-ARAB'))
check('an underscore is accepted as a separator',
      langcodes.normalize('ms_arab') == 'ms-Arab')
check('a region part stays upper case',
      langcodes.normalize('pt-br') == 'pt-BR')
check('a plain code is untouched', langcodes.normalize('de') == 'de')
check('nonsense is still refused', not langcodes.looks_valid('toolongcode'))
check('a trailing hyphen is refused', not langcodes.looks_valid('de-'))

known = {'de', 'ms-arab', 'zh-Hant'}
check('the wiki spelling wins over the typed one',
      langcodes.canonical('ms-Arab', known) == 'ms-arab',
      str(langcodes.canonical('ms-Arab', known)))
check('and the other way round too',
      langcodes.canonical('zh-hant', known) == 'zh-Hant')
check('an unknown code is reported as unknown',
      langcodes.canonical('xx-Yyyy', known) is None)

# ── the whole chain through the description cell ─────────────────────────────
text = ('Ein Gebaeude.\n'
        'caption_de=Bild\n'
        'caption_ms-Arab=Rumah\n'
        'alt_de=Ein Haus mit rotem Dach\n'
        'alt_ms-Arab=Alt in Jawi\n'
        'creator=Q1\n')
sd, rest = sdc.extract_structured_data(text)
check('a caption with a script code survives the round trip',
      sd.get('caption_ms-Arab') == 'Rumah', str(sd.get('caption_ms-Arab')))
check('alt text is picked up per language',
      sd.get('alt_de') == 'Ein Haus mit rotem Dach'
      and sd.get('alt_ms-Arab') == 'Alt in Jawi')
check('and both are stripped from the leftover text',
      rest.strip() == 'Ein Gebaeude.', repr(rest))

tmpl, _extra = sdc.split_lang_templates(
    '{{de|1=Ein Haus}} {{ms-Arab|1=Rumah}}')
check('lang templates accept a script code too',
      tmpl.get('ms-Arab') == 'Rumah', str(tmpl))

# ── alt text in the editor ───────────────────────────────────────────────────
ce = w.file_struct.captions_editor
ce.set_language_data({'de': 'Bild'}, {}, {'de': 'Ein Haus'})
check('the editor shows the alt text', ce.get_alts() == {'de': 'Ein Haus'},
      str(ce.get_alts()))
check('captions and alt text stay apart',
      ce.get_captions() == {'de': 'Bild'})
assembled = w.file_struct.assemble()
check('assemble writes an alt_ line', 'alt_de=Ein Haus' in assembled,
      assembled.splitlines()[:4])
check('the property is the verified one', ALT_TEXT_PROPERTY == 'P11265')

# ── update check ─────────────────────────────────────────────────────────────
check('an even final digit is stable', updates.is_stable('0.15.2'))
check('an odd one is experimental', updates.is_stable('0.15.3') is False)
check('versions compare numerically, not as text',
      updates.is_newer('0.15.10', '0.15.9'))
check('an unparsable tag is not newer than anything',
      not updates.is_newer('latest', '0.15.2'))

rel = [((0, 16, 0), 'v0.16.0', 'u1'), ((0, 15, 3), 'v0.15.3', 'u2'),
       ((0, 15, 2), 'v0.15.2', 'u3')]
check('a stable user is offered the stable release',
      updates.newest_relevant(rel, '0.15.1', True)[1] == 'v0.16.0')
check('the current version yields nothing',
      updates.newest_relevant(rel, '0.16.0', True) is None)
check('with stable_only off the experimental one can win',
      updates.newest_relevant([((0, 15, 3), 'v0.15.3', 'u')], '0.15.2',
                              False)[1] == 'v0.15.3')
check('but with it on it is skipped',
      updates.newest_relevant([((0, 15, 3), 'v0.15.3', 'u')], '0.15.2',
                              True) is None)
check('an experimental user hears about experimental ones',
      updates.newest_relevant([((0, 15, 5), 'v0.15.5', 'u')], '0.15.3',
                              True)[1] == 'v0.15.5')
check('the settings offer both switches',
      hasattr(w, 'update_check_cb') and hasattr(w, 'update_stable_cb'))
check('there is a Help menu action', hasattr(w, '_check_for_updates'))

# ── clearing on a workflow switch ────────────────────────────────────────────
_asked = []
_orig_q = QMessageBox.question
QMessageBox.question = lambda *a, **k: (_asked.append(a), QMessageBox.Yes)[1]
# The expert checkbox is PERSISTED, so a test that leaves it on poisons
# every later test run in the same profile - which is exactly what it did
# once. Remember it here and put it back in the finally.
_expert_before = w.expert_cb.isChecked()
try:
    w.table.setRowCount(1)
    w.table.setItem(0, w.COL_FILENAME, QTableWidgetItem('a.jpg'))
    # The description cell is where per-file values live; without it
    # _row_sd_set has nowhere to write.
    w.table.setItem(0, w.COL_DESC, QTableWidgetItem(''))
    cb = w.workflow_combo
    cb.setCurrentIndex(cb.findData('buildings'))
    w.expert_cb.setChecked(False)
    w._row_sd_set(0, 'object_coordinates', '48.1, 9.1')
    _asked.clear()
    w._clear_hidden_workflow_fields('portraits')
    check('a filled hidden field triggers the question', len(_asked) == 1)
    check('and Yes clears it',
          not (w._row_sd_get(0, 'object_coordinates') or '').strip())
    _asked.clear()
    w._clear_hidden_workflow_fields('portraits')
    check('with nothing filled there is no question', not _asked)
    w._row_sd_set(0, 'object_coordinates', '48.1, 9.1')
    w.expert_cb.setChecked(True)
    _asked.clear()
    w._clear_hidden_workflow_fields('portraits')
    check('expert mode hides nothing, so it asks nothing', not _asked)
    check('and the value is kept',
          (w._row_sd_get(0, 'object_coordinates') or '').strip() != '')
finally:
    QMessageBox.question = _orig_q
    w.expert_cb.setChecked(_expert_before)

# ── version bookkeeping ──────────────────────────────────────────────────────
from cammello.constants import __version__
root = os.path.dirname(os.path.dirname(langcodes.__file__))
rel_sh = open(os.path.join(root, 'release.sh'), encoding='utf-8').read()
check('release.sh matches constants.py',
      f'VERSION="{__version__}"' in rel_sh, __version__)
notes = 'notes_' + __version__.replace('.', '') + '.md'
check('and points at notes that exist',
      f'NOTES_FILE="{notes}"' in rel_sh
      and os.path.exists(os.path.join(root, notes)), notes)
check('this release is a stable number', updates.is_stable(__version__),
      __version__)

# ── the four corrections from Harald's review (0.15.2) ───────────────────────
from cammello.editors import StructuredDescriptionEditor
from cammello import workflows

base_ed = StructuredDescriptionEditor(is_base=True)
check('the base editor has no alt rows',
      base_ed.captions_editor.is_base
      and base_ed.captions_editor.get_alts() == {})
base_ed.captions_editor.set_language_data({'de': 'x'}, {}, {'de': 'y'})
check('and it refuses to hand out alt text even when asked',
      base_ed.captions_editor.get_alts() == {},
      str(base_ed.captions_editor.get_alts()))
check('the per-file editor still has them',
      not w.file_struct.captions_editor.is_base)

check('the workflow is named Events/Portraits',
      workflows.by_key('portraits')['label'] == 'Events/Portraits',
      workflows.by_key('portraits')['label'])
_labels = [w.workflow_combo.itemText(i)
           for i in range(w.workflow_combo.count())]
check('and the dropdown shows it', any('Portr' in t for t in _labels),
      str(_labels))

# The depicts dot must stay away when the override says so.
w.table.setRowCount(1)
w.table.setItem(0, w.COL_FILENAME, QTableWidgetItem('a.jpg'))
w.table.setItem(0, w.COL_DESC, QTableWidgetItem(''))
w.table.selectRow(0)
_struct = w.file_struct
_struct.depicts.setText('')
_struct.override_combo.setCurrentIndex(0)          # '' = depicts required
w._refresh_file_marks()
_dl = w._label_for(_struct, _struct.depicts)
check('empty depicts is marked when nothing is overridden',
      _dl is not None and _dl.text().startswith('\u25cf'),
      _dl.text() if _dl else 'no label')
_i = _struct.override_combo.findData('not_applicable')
_struct.override_combo.setCurrentIndex(_i)
w._refresh_file_marks()
check('but NOT once it is deselected below',
      _dl is not None and not _dl.text().startswith('\u25cf'),
      _dl.text() if _dl else 'no label')
_struct.override_combo.setCurrentIndex(0)

check('the gallery is one field on the base editor',
      base_ed.gallery_suffix is not None
      and w.file_struct.gallery_suffix is None)

print()
print('FAILURES:', ', '.join(fails) if fails else 'none')
sys.exit(1 if fails else 0)
