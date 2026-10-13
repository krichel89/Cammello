"""Passed-on workflow files, .cammello (0.18.29).

Core: workflows.d is loaded next to workflows.toml, a file is checked before
it is installed, a clashing key is refused, the same file name is an update.
Window: the dialog shows what will be set and asks, a decline changes
nothing, an accept installs, selects and applies; drops, the command line
and the macOS open event reach the same code.

HOME is redirected, so no real ~/Cammello is touched.
Run headless:  QT_QPA_PLATFORM=offscreen python3 test_workflowfile_01829.py
"""
import os
import plistlib
import shutil
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
_HOME = tempfile.mkdtemp()
os.environ['HOME'] = _HOME
os.environ['USERPROFILE'] = _HOME          # Windows
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from PyQt5.QtCore import QEvent, QMimeData, QPoint, QUrl, Qt
from PyQt5.QtGui import QDropEvent
from PyQt5.QtWidgets import QApplication, QMessageBox

import Cammello
from cammello import main_window, workflows
from cammello import workflow_config as wc
from cammello.logging_setup import setup_logging

app = QApplication(sys.argv)
logger, emitter, gui_handler, log_path = setup_logging()
fails = []
asked = []                      # every dialog the window raised


def check(name, cond, detail=''):
    if cond:
        print('PASS', name, detail)
    else:
        print('FAIL', name, detail)
        fails.append(name)


ANSWER = {'question': QMessageBox.Yes}
QMessageBox.information = staticmethod(lambda *a, **k: asked.append(('i', a)))
QMessageBox.warning = staticmethod(lambda *a, **k: asked.append(('w', a)))
QMessageBox.question = staticmethod(
    lambda *a, **k: (asked.append(('q', a)), ANSWER['question'])[1])

SRC = tempfile.mkdtemp()


def make(name, body):
    p = os.path.join(SRC, name)
    with open(p, 'w', encoding='utf-8') as fh:
        fh.write(body)
    return p


FAIR = '''
# comment
[[workflow]]
schluessel = "fair26"
name = "Test Fair 2026"
felder_aus = ["kamerastandort", "objektstandort"]

  [workflow.setzen]
  vorlagen = "{{WikiPortraits Test Fair 2026}}"
  kategorien = "Test Fair 2026"
  entstanden_waehrend = "Q42"
'''
fair = make('Test_Fair_2026.cammello', FAIR)

# ── 1. the core ─────────────────────────────────────────────────────────────
os.makedirs(os.path.dirname(wc.path()), exist_ok=True)
check('start: only the built-in workflows',
      [w['key'] for w in wc.load()] == [w['key'] for w in wc.BUILTIN])
check('workflows.d sits beside workflows.toml',
      wc.extras_dir() == os.path.join(os.path.dirname(wc.path()),
                                      'workflows.d'))

entries, notes, err = wc.inspect_file(fair)
check('a good file is read', err is None and entries[0]['key'] == 'fair26',
      str(err))
check('its setzen is there',
      entries[0]['set']['entstanden_waehrend'] == 'Q42')

for label, name, body in (
        ('wrong extension', 'x.txt', FAIR),
        ('not TOML', 'broken.cammello', 'this is = = not toml ['),
        ('no workflow block', 'empty.cammello', '# nothing\n'),
        ('too large', 'big.cammello', '#' + 'x' * (wc.MAX_FILE_BYTES + 10)),
):
    e, _n, er = wc.inspect_file(make(name, body))
    check(f'refused: {label}', er and not e, str(er))
bad = os.path.join(SRC, 'binary.cammello')
open(bad, 'wb').write(b'\xff\xfe\x00\x01')
check('refused: not UTF-8', wc.inspect_file(bad)[2] is not None)
check('refused: missing file',
      wc.inspect_file(os.path.join(SRC, 'nope.cammello'))[2] is not None)

check('a harmless name is kept',
      wc.safe_name('/a/b/Berlinale_2027.cammello') == 'Berlinale_2027.cammello')
check('a path trick is cut to the base name',
      wc.safe_name('../../etc/passwd.cammello') == 'passwd.cammello')
check('odd characters are replaced, the extension is always there',
      wc.safe_name('a/b:c*d?.txt') == 'b_c_d_.txt.cammello',
      wc.safe_name('a/b:c*d?.txt'))
check('nothing left of a name still gives a name',
      wc.safe_name('...') == 'workflow.cammello')

check('no conflict for a new key', wc.conflicts_of(entries, fair) == [])
clash = make('Clash.cammello', FAIR.replace('fair26', 'portraits'))
check('a key of a built-in workflow is a conflict',
      wc.conflicts_of(wc.inspect_file(clash)[0], clash) == ['portraits'])

dest, replaced, err = wc.install_file(fair, lambda s: s)
check('installed into workflows.d',
      err is None and dest == os.path.join(wc.extras_dir(),
                                           'Test_Fair_2026.cammello'), str(err))
check('first time is not a replacement', replaced is False)
check('workflows.toml itself was not touched',
      'fair26' not in open(wc.path(), encoding='utf-8').read())
check('the new workflow is loaded', 'fair26' in
      [w['key'] for w in wc.load()])
check('and knows where it came from',
      wc.ORIGINS.get('fair26') == 'Test_Fair_2026.cammello')
check('the file was written without leftovers',
      sorted(os.listdir(wc.extras_dir())) == ['Test_Fair_2026.cammello'])
check('the same file again is an UPDATE, not a conflict',
      wc.conflicts_of(entries, fair) == [])
d2, replaced2, _e = wc.install_file(
    make('Test_Fair_2026.cammello',
         FAIR.replace('Test Fair 2026"\nfelder_aus', 'Test Fair 2026 v2"\nfelder_aus')),
    lambda s: s)
check('the update replaces the old file and is reported',
      replaced2 is True and
      [w['label'] for w in wc.load() if w['key'] == 'fair26']
      == ['Test Fair 2026 v2'])
other = make('Other_Name.cammello', FAIR)
check('the same key from ANOTHER file is a conflict',
      wc.conflicts_of(wc.inspect_file(other)[0], other) == ['fair26'])

# a broken file in the folder is skipped, never fatal
open(os.path.join(wc.extras_dir(), 'Broken.cammello'), 'w').write('[[x')
wc.reload()
check('a broken file in workflows.d does not stop the others',
      'fair26' in [w['key'] for w in wc.load()]
      and any('Broken.cammello' in w for w in wc.LAST_WARNINGS))
os.remove(os.path.join(wc.extras_dir(), 'Broken.cammello'))
# the user's own workflows.toml wins over a loaded file
open(os.path.join(wc.extras_dir(), 'Dup.cammello'), 'w').write(
    FAIR.replace('fair26', 'portraits'))
wc.reload()
check('a loaded file never overrides a key of workflows.toml',
      [w['label'] for w in wc.load() if w['key'] == 'portraits']
      == ['Events/Portraits'])
os.remove(os.path.join(wc.extras_dir(), 'Dup.cammello'))
wc.reload()

txt = wc.preview_text(entries, lambda s: s)
check('the preview names the workflow and the values',
      'Test Fair 2026' in txt and 'Q42' in txt and 'replaces' in txt, txt)
sens = wc.inspect_file(make('Sens.cammello', FAIR.replace(
    '  vorlagen =', '  lizenz = "{{PD}}"\n  vorlagen =')))[0]
check('a licence change is marked in the preview',
      '⚠' in wc.preview_text(sens, lambda s: s))
check('a file that sets nothing says so',
      'sets no field' in wc.preview_text(
          wc.inspect_file(make('Nil.cammello', '[[workflow]]\nschluessel="n"\n'
                               'name="N"\n'))[0], lambda s: s))

shutil.rmtree(wc.extras_dir())
wc.reload()

# ── 2. the window ───────────────────────────────────────────────────────────
w = Cammello.MainWindow(logger, emitter, gui_handler, log_path)
cb = w.workflow_combo
w.other_templates_edit.setText('{{Old}}')
w.base_struct.created_during.setText('Q1')
w._set_field_visible  # exists

ANSWER['question'] = QMessageBox.No
asked.clear()
w._load_workflow_file(fair)
check('declined: one question was asked',
      [a[0] for a in asked] == ['q'], str(asked))
check('the question shows what will be set',
      'Q42' in asked[0][1][2] and 'Test Fair 2026' in asked[0][1][2])
check('declined: nothing installed', not os.path.exists(wc.extras_dir())
      or os.listdir(wc.extras_dir()) == [])
check('declined: dropdown and fields unchanged',
      cb.findData('fair26') < 0 and w.other_templates_edit.text() == '{{Old}}')

ANSWER['question'] = QMessageBox.Yes
asked.clear()
w._load_workflow_file(fair)
check('accepted: installed', os.path.exists(
    os.path.join(wc.extras_dir(), 'Test_Fair_2026.cammello')))
check('it is in the dropdown AND selected',
      cb.findData('fair26') >= 0 and w.current_workflow() == 'fair26')
check('and it was applied at once',
      w.other_templates_edit.text() == '{{WikiPortraits Test Fair 2026}}'
      and w.base_struct.categories.text() == 'Test Fair 2026'
      and w.base_struct.created_during.text() == 'Q42')
check('a replacement is announced in the question next time',
      (asked.clear(), w._load_workflow_file(fair))[0] is None
      and 'replaces the version' in asked[0][1][2])

asked.clear()
w._load_workflow_file(make('Clash2.cammello', FAIR.replace('fair26',
                                                          'portraits')))
check('a key clash: warning, no question',
      [a[0] for a in asked] == ['w'], str(asked))
asked.clear()
w._load_workflow_file(make('Junk.cammello', 'garbage = = ['))
check('a broken file: warning, no question',
      [a[0] for a in asked] == ['w'], str(asked))

# the action bound to the menu passes a bool: must not be taken for a path
asked.clear()
orig_dialog = main_window.QFileDialog.getOpenFileName
main_window.QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: ('', ''))
w._load_workflow_file(False)
main_window.QFileDialog.getOpenFileName = orig_dialog
check('the menu action (bool argument) opens the file dialog, not a load',
      asked == [])
acts = [a for a in w.findChildren(type(w.menuBar().actions()[0]))
        if 'workflow from' in a.text().lower()]
check('the menu entry exists', len(acts) >= 1)

# drop on the window and on the table
mime = QMimeData()
mime.setUrls([QUrl.fromLocalFile(fair)])
check('the window recognises the dropped file',
      w._workflow_paths(mime) == [fair])
mime2 = QMimeData()
mime2.setUrls([QUrl.fromLocalFile(os.path.join(SRC, 'a.jpg'))])
check('a picture is not a workflow', w._workflow_paths(mime2) == [])
check('the window accepts drops', w.acceptDrops())
got = []
w._load_workflow_file_deferred = lambda p: got.append(p)
ev = QDropEvent(QPoint(5, 5), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
w.dropEvent(ev)
check('dropping on the window loads it', got == [fair], str(got))
got.clear()
w.table._on_workflow_dropped = lambda p: got.append(p)
w.table.dropEvent(QDropEvent(QPoint(5, 5), Qt.CopyAction, mime,
                             Qt.LeftButton, Qt.NoModifier))
check('dropping on the file table loads it too, adds no picture',
      got == [fair] and w.table.rowCount() == 0, str(got))
w.close()

# ── 3. start-up and the macOS open event ────────────────────────────────────
check('command line: only .cammello files are ours',
      main_window._workflow_args(['Cammello', '--x', 'a.CAMMELLO', 'b.jpg'])
      == ['a.CAMMELLO'])
check('command line: nothing given', main_window._workflow_args(['Cammello'])
      == [])

flt = main_window._OpenFileFilter()


class QFileOpenEvent:
    """PyQt5 cannot construct the real event; the filter only needs these."""

    def __init__(self, path):
        self._path = path

    def type(self):
        return QEvent.FileOpen

    def file(self):
        return self._path


ev = QFileOpenEvent(fair)
check('the filter takes the open event', flt.eventFilter(None, ev) is True)
check('and keeps it until a handler exists', flt.pending == [fair])
seen = []
flt.handler = seen.append
flt.eventFilter(None, QFileOpenEvent(fair))
app.processEvents()
check('with a handler it forwards', seen == [fair], str(seen))
check('other events are left alone',
      flt.eventFilter(None, QEvent(QEvent.None_)) is False)

w2 = Cammello.MainWindow(logger, emitter, gui_handler, log_path)
ANSWER['question'] = QMessageBox.No
asked.clear()
w2._open_from_system('/x/picture.jpg')
check('the system may hand us anything: only .cammello is opened',
      asked == [])
w2._open_from_system(fair)
check('a .cammello from the system goes through the dialog',
      [a[0] for a in asked] == ['q'])
w2.close()

# ── 4. the bundle declaration and the build ─────────────────────────────────
import make_bundle_types as mbt                              # noqa: E402
info = mbt.declare({'CFBundleName': 'Cammello',
                    'CFBundleDocumentTypes': [
                        {'CFBundleTypeExtensions': ['jpg']}]})
check('the type is declared in both places', mbt.is_declared(info))
check('other document types and keys survive',
      info['CFBundleName'] == 'Cammello' and any(
          d.get('CFBundleTypeExtensions') == ['jpg']
          for d in info['CFBundleDocumentTypes']))
before = plistlib.dumps(info)
check('declaring twice changes nothing more',
      plistlib.dumps(mbt.declare(plistlib.loads(before))) == before)
check('an empty plist is not "declared"', not mbt.is_declared({}))
import subprocess
pl = os.path.join(SRC, 'Info.plist')
plistlib.dump({'CFBundleName': 'X'}, open(pl, 'wb'))
r = subprocess.run([sys.executable, os.path.join(_HERE, 'make_bundle_types.py'),
                    pl], capture_output=True, text=True)
check('the script runs and succeeds',
      r.returncode == 0 and mbt.is_declared(plistlib.load(open(pl, 'rb'))),
      r.stderr)
r = subprocess.run([sys.executable, os.path.join(_HERE, 'make_bundle_types.py')],
                   capture_output=True, text=True)
check('without an argument it fails loudly', r.returncode != 0)

build = open(os.path.join(_HERE, '.github', 'workflows', 'build.yml'),
             encoding='utf-8').read()
i_decl = build.find('make_bundle_types.py')
i_sign = build.find('- name: Codesign app bundle')
check('build.yml calls the script, and BEFORE the code signature',
      0 < i_decl < i_sign)

# ── 5. the example file ─────────────────────────────────────────────────────
ex = os.path.join(_HERE, 'workflows_examples', 'Frankfurter_Buchmesse_2026.cammello')
e, n, er = wc.inspect_file(ex)
check('the Buchmesse example is a valid workflow file', er is None and e,
      str(er))
check('it sets the 2026 edition',
      e and e[0]['set'].get('entstanden_waehrend') == 'Q141663636')
check('and parses without warnings', not n, str(n))

# ── 6. depicts is the first row of the per-file editor ──────────────────────
from cammello import editors
ed = editors.StructuredDescriptionEditor(is_base=False)
ed.resize(500, 600)
ed.show()
app.processEvents()
y = lambda widget: widget.mapTo(ed, QPoint(0, 0)).y()
check('depicts sits ABOVE the captions',
      y(ed.depicts) < y(ed.captions_editor), f'{y(ed.depicts)} / {y(ed.captions_editor)}')
check('"If no depicts" follows it, still above the captions',
      y(ed.depicts) < y(ed.override_combo) < y(ed.captions_editor))
check('the categories stay below the captions',
      y(ed.captions_editor) < y(ed.categories))
check('the caption button is right under depicts',
      0 < y(ed.suggest_captions_btn) - y(ed.depicts) < 80)
ed.close()

print()
print('FAILURES:', fails or 'none')
sys.exit(1 if fails else 0)
