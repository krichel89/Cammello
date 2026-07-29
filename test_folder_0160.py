"""Verzeichnis-Import, Ziffernautomatik und die naechste freie Sprache (0.16.0).

Deckt Haralds drei Punkte dieser Runde ab:
  1. Die Stellenzahl der Originaldateinummer wird automatisch bestimmt
     (groesste gemeinsame Endziffernfolge, 3-6), die Spinbox ist weg.
  2. Knopf "Verzeichnis oeffnen" im MediaWiki-Modul: nicht rekursiv, nur
     hochladbare Endungen, Fortschritt mit Abbrechen, Warnung ab 1000.
  3. "Add language" waehlt die naechste noch nicht benutzte Sprache.
"""
import os
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PIL import Image
from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QApplication, QMessageBox

import Cammello
from cammello import mw_files
from cammello.constants import (APP_NAME, FOLDER_WARN_COUNT, IMAGE_EXTS,
                                caption_language_choices)
from cammello.editors import CaptionsEditor
from cammello.logging_setup import setup_logging
from cammello.widgets import BulkRenameDialog

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


# ── 1. Ziffernautomatik ──────────────────────────────────────────────────
check('the spin box for the digit count is gone',
      not hasattr(BulkRenameDialog, 'digits_spin'))
check('Canon names give four digits',
      BulkRenameDialog.auto_digits(['IMG_4711', 'IMG_4712']) == 4)
check('Lumix names give six',
      BulkRenameDialog.auto_digits(['P1066330', 'P1066331']) == 6)
check('a mixed selection takes the shorter run - every file must be able '
      'to supply it',
      BulkRenameDialog.auto_digits(['IMG_4711', 'P1066330']) == 4)
check('a name without trailing digits does not drag the count down',
      BulkRenameDialog.auto_digits(['P1066330', 'Scan']) == 6)
check('nothing numbered at all yields 0 (whole number)',
      BulkRenameDialog.auto_digits(['Scan', 'Foto']) == 0)
check('an empty selection does not raise',
      BulkRenameDialog.auto_digits([]) == 0)
check('fewer than three digits is clamped up',
      BulkRenameDialog.auto_digits(['DSC_12']) == BulkRenameDialog.DIGITS_MIN)
check('more than six is clamped down',
      BulkRenameDialog.auto_digits(['X123456789'])
      == BulkRenameDialog.DIGITS_MAX)
check('clamping up does not invent digits',
      BulkRenameDialog.camera_number('DSC_12', 3) == '12')

_dlg = BulkRenameDialog(3, None,
                        sources=['IMG_66330', 'IMG_66331', 'Scan'],
                        exts=['.JPG', '.JPG', '.tif'],
                        dates=['2026-07-29', '2026-07-29', '2026-07-28'])
_dlg.text_edit.setText('testI')
check('the dialog derives the count from the selection', _dlg._digits == 5,
      str(_dlg._digits))
_dlg.scheme_combo.setCurrentIndex(_dlg.scheme_combo.findData('text_orig'))
_names = _dlg.names()
check('Haralds example line still comes out', _names[0] == 'testI-66330',
      _names[0])
check('the file without digits still gets a unique name',
      _names[2] not in _names[:2], str(_names))
check('every scheme entry is a five-tuple now',
      all(len(e) == 5 for e in BulkRenameDialog.SCHEMES),
      str({len(e) for e in BulkRenameDialog.SCHEMES}))
_dlg.scheme_combo.setCurrentIndex(_dlg.scheme_combo.findData('template'))
_dlg.template_edit.setText('{text}-{c}')
check('the free template still knows {c}', _dlg.names()[0] == 'testI-66330',
      _dlg.names()[0])

# ── 2. Verzeichnis oeffnen ───────────────────────────────────────────────
check('the toolbar carries the button', hasattr(w, 'open_folder_btn'))
check('it is labelled for a directory, not a folder',
      'director' in w.open_folder_btn.text().lower()
      or 'verzeichnis' in w.open_folder_btn.text().lower(),
      w.open_folder_btn.text())

_dir = tempfile.mkdtemp()
for _i in range(6):
    Image.new('RGB', (40, 30), (30 * _i, 90, 120)).save(
        os.path.join(_dir, f'IMG_{4710 + _i}.jpg'))
for _junk in ('raw.cr2', 'raw.nef', 'notes.txt', 'sidecar.xmp'):
    open(os.path.join(_dir, _junk), 'wb').write(b'x')
Image.new('RGB', (40, 30)).save(os.path.join(_dir, 'UPPER.JPG'))
os.mkdir(os.path.join(_dir, 'sub'))
Image.new('RGB', (40, 30)).save(os.path.join(_dir, 'sub', 'deep.jpg'))

_found = [os.path.basename(p) for p in w.folder_image_files(_dir)]
check('it reads the top level only, not subdirectories',
      'deep.jpg' not in _found, str(_found))
check('only uploadable extensions come in',
      all(os.path.splitext(f)[1].lower() in IMAGE_EXTS for f in _found),
      str(_found))
check('no RAW: there is no converter, so it could not be uploaded',
      not [f for f in _found if f.lower().endswith(('.cr2', '.nef'))])
check('the extension test is case-insensitive', 'UPPER.JPG' in _found)
check('the result is sorted by name', _found == sorted(_found))
check('a directory that does not exist yields nothing, not an exception',
      w.folder_image_files(os.path.join(_dir, 'nope')) == [])
check('an empty directory yields nothing',
      w.folder_image_files(tempfile.mkdtemp()) == [])

# The chooser is modal - patching it is the only way to click this path.
_orig_chooser = mw_files.QFileDialog.getExistingDirectory
mw_files.QFileDialog.getExistingDirectory = staticmethod(
    lambda *a, **k: _dir)
_orig_question = QMessageBox.question
_orig_information = QMessageBox.information
try:
    w.open_directory()
    check('the directory lands in the table, skipping the culling module',
          w.table.rowCount() == len(_found), str(w.table.rowCount()))
    _rows = w.table.rowCount()
    w.open_directory()
    check('a second run adds nothing - duplicates are recognised',
          w.table.rowCount() == _rows, str(w.table.rowCount()))

    # Cancelling: the rows read so far stay, the rest is not touched.
    while w.table.rowCount():
        w.table.removeRow(0)
    _calls = []

    def _stop_after_two(done, total):
        _calls.append((done, total))
        return done < 2

    _added, _dups, _failed, _cancelled = w._add_paths(
        w.folder_image_files(_dir), progress=_stop_after_two)
    check('cancelling is reported back', _cancelled is True)
    check('the files read before the cancel are kept', _added == 2,
          str(_added))
    check('the table holds exactly those', w.table.rowCount() == 2,
          str(w.table.rowCount()))
    check('the callback saw the total', _calls and _calls[0][1] == len(_found),
          str(_calls[:1]))
    check('without a callback the old three-value result is unchanged',
          len(w._add_paths([])) == 3)

    # The warning is a question box: answering No must not add anything.
    while w.table.rowCount():
        w.table.removeRow(0)
    _asked = []

    def _fake_question(parent, title, text, *a, **k):
        _asked.append(text)
        return QMessageBox.No

    QMessageBox.question = staticmethod(_fake_question)
    _real_count = w.folder_image_files
    w.folder_image_files = lambda folder: ['/nowhere/%d.jpg' % i
                                           for i in range(FOLDER_WARN_COUNT
                                                          + 1)]
    w.open_directory()
    check('above the threshold Cammello asks first', bool(_asked))
    check('the question names the number',
          _asked and str(FOLDER_WARN_COUNT + 1) in _asked[0],
          _asked[0] if _asked else '')
    check('answering No adds nothing', w.table.rowCount() == 0)
    check('the threshold is Haralds thousand', FOLDER_WARN_COUNT == 1000,
          str(FOLDER_WARN_COUNT))
    w.folder_image_files = _real_count

    # An empty directory says so instead of opening a progress dialog.
    _told = []
    QMessageBox.information = staticmethod(
        lambda parent, title, text, *a, **k: _told.append(text))
    mw_files.QFileDialog.getExistingDirectory = staticmethod(
        lambda *a, **k: tempfile.mkdtemp())
    w.open_directory()
    check('an empty directory is reported, not silently ignored', bool(_told))
    check('and still nothing is in the table', w.table.rowCount() == 0)

    # A cancelled chooser must do nothing at all.
    mw_files.QFileDialog.getExistingDirectory = staticmethod(
        lambda *a, **k: '')
    _told.clear()
    w.open_directory()
    check('cancelling the chooser is a no-op', not _told
          and w.table.rowCount() == 0)
finally:
    mw_files.QFileDialog.getExistingDirectory = _orig_chooser
    QMessageBox.question = _orig_question
    QMessageBox.information = _orig_information

# ── 3. Naechste noch nicht benutzte Sprache ──────────────────────────────
_settings = QSettings(APP_NAME, 'Main')
_saved_extras = _settings.value('caption_extra_langs', '')
try:
    _settings.setValue('caption_extra_langs', '')
    _settings.sync()
    _ed = CaptionsEditor()
    check('the editor starts on English', _ed.used_languages() == ['en'],
          str(_ed.used_languages()))
    _offered = [c for c, _n in caption_language_choices()]
    for _expected in _offered[1:]:
        _ed.add_row()
    check('each click takes the next unused language',
          _ed.used_languages() == _offered, str(_ed.used_languages()))
    check('no language was handed out twice',
          len(set(_ed.used_languages())) == len(_ed.used_languages()))
    _ed.add_row()
    check('with everything taken it falls back instead of refusing',
          len(_ed.used_languages()) == len(_offered) + 1,
          str(_ed.used_languages()))
    _ed2 = CaptionsEditor()
    _ed2.add_row('it', 'ciao')
    check('a caller passing a code gets that code',
          _ed2.used_languages()[-1] == 'it', str(_ed2.used_languages()))
    check('next_language skips what a caller already took',
          _ed2.next_language() not in _ed2.used_languages(),
          _ed2.next_language())
    # Removing the last row must not crash and must refill one.
    _ed3 = CaptionsEditor()
    _ed3._remove(_ed3._rows[0])
    check('removing the last row leaves exactly one behind',
          len(_ed3.used_languages()) == 1, str(_ed3.used_languages()))
finally:
    _settings.setValue('caption_extra_langs', _saved_extras or '')
    _settings.sync()

print('---')
print('FAILURES:', fails if fails else 'none')
print(f'{len(fails)} failure(s)')
sys.exit(1 if fails else 0)
