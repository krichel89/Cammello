"""Adding built-in workflows to an existing workflow file (0.18.0).

Harald ran 0.18.0 and the music workflow was not in the dropdown: his
~/Cammello/workflows.toml predates it, and load() reads the file OR the
built-ins - it never merges them. So a built-in added later is invisible
to everybody who already has a file.

What is defended here:

  1. missing_builtins() finds exactly what the file lacks, and finds
     nothing when there is no file (the built-ins are already in use),
  2. append_builtins() APPENDS - the existing text survives byte for
     byte, including comments and hand edits,
  3. a backup is written before the file is touched,
  4. what comes out is valid TOML and parses back into a working
     workflow, music fields and all,
  5. a failed write leaves the file alone and reports the reason.

The dialog itself is not tested here - it needs a window. This is the
half that decides and writes.
"""
import os
import sys
import tempfile
import tomllib

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import Cammello        # the shim; also puts the package on the path
from cammello import workflow_config as wc

fails = []


def check(name, cond, detail=''):
    print(('PASS' if cond else 'FAIL'), name, detail)
    if not cond:
        fails.append(name)


check('the shim still exposes the package', hasattr(Cammello, 'main'))

# A file the way Harald's looks: written before the music workflow, with
# a comment and a hand edit in it.
OLD = '''# meine eigene Datei - Finger weg
[[workflow]]
schluessel = "portraits"
name       = "Events/Portraits"
felder_aus = ["kamerastandort", "objektstandort"]
vorbelegung.vorlagen = "{{Wikiportraits}}"

[[workflow]]
schluessel = "buildings"
name       = "Gebäude und Landschaften"
felder_aus = ["entstanden_waehrend"]
'''

keep = os.environ.get(wc.ENV_OVERRIDE)
tmp = tempfile.mkdtemp()
target = os.path.join(tmp, 'workflows.toml')


def fresh(text=OLD):
    with open(target, 'w', encoding='utf-8') as fh:
        fh.write(text)
    wc._cache = None
    wc.LAST_ERROR = None


try:
    os.environ[wc.ENV_OVERRIDE] = target

    # ── What is missing ──────────────────────────────────────────────────
    fresh()
    missing = wc.missing_builtins()
    check('only the music workflow is missing',
          [w['key'] for w in missing] == ['music'],
          str([w['key'] for w in missing]))

    os.remove(target)
    wc._cache = None
    check('no file means nothing is missing (built-ins are in use)',
          wc.missing_builtins() == [])

    # A file that does not parse: load() falls back to the built-ins, so
    # again nothing is missing - offering to append to a broken file would
    # be the worst possible moment to write to it.
    fresh('[[workflow]\nkaputt')
    wc.load()
    check('a broken file is left alone', wc.missing_builtins() == [])

    # ── Appending ────────────────────────────────────────────────────────
    fresh()
    path, error = wc.append_builtins(['music'])
    check('append reports success', path == target and error is None,
          str(error))

    with open(target, encoding='utf-8') as fh:
        after = fh.read()
    check('every byte of the old file is still there', after.startswith(OLD))
    check('the comment survived', '# meine eigene Datei' in after)
    check('the hand-edited German label survived',
          'Gebäude und Landschaften' in after)
    check('a backup was written', os.path.exists(target + '.bak'))
    with open(target + '.bak', encoding='utf-8') as fh:
        check('the backup holds the previous text', fh.read() == OLD)

    # ── What was appended actually works ────────────────────────────────
    with open(target, 'rb') as fh:
        data = tomllib.load(fh)
    check('the result is valid TOML with three workflows',
          len(data['workflow']) == 3, str(len(data.get('workflow', []))))

    wc._cache = None
    entries = wc.load()
    check('the music workflow is loaded from the file now',
          [w['key'] for w in entries] == ['portraits', 'buildings', 'music'],
          str([w['key'] for w in entries]))
    m = [w for w in entries if w['key'] == 'music'][0]
    check('all thirteen music fields are switched on',
          sorted(m['show']) == sorted(wc.DEFAULT_OFF), str(len(m['show'])))
    check('the preset came along', m['preset'] == {'quelle': ''},
          str(m['preset']))
    check('the example came along', m['example'].get('instrument') == 'organ')
    check('nothing is missing any more', wc.missing_builtins() == [])

    # Appending twice must not double the block - the caller asks
    # missing_builtins() first, but a second run should still be harmless
    # to reason about, so the guard is checked explicitly.
    check('a workflow that is already there is reported as not missing',
          'music' not in [w['key'] for w in wc.missing_builtins()])

    # ── Separator handling ───────────────────────────────────────────────
    fresh(OLD.rstrip('\n'))           # file without a trailing newline
    wc.append_builtins(['music'])
    with open(target, 'rb') as fh:
        check('a file without a trailing newline still parses',
              len(tomllib.load(fh)['workflow']) == 3)

    # ── Failure paths ────────────────────────────────────────────────────
    fresh()
    path, error = wc.append_builtins([])
    check('asking for nothing changes nothing', path is None and error)
    with open(target, encoding='utf-8') as fh:
        check('and the file is untouched', fh.read() == OLD)

    os.remove(target)
    wc._cache = None
    path, error = wc.append_builtins(['music'])
    check('appending to a file that is not there fails cleanly',
          path is None and error == 'no workflow file', str(error))

    # A directory where the file should be: open() fails, and the failure
    # has to come back as a message rather than as a traceback out of the
    # startup path.
    os.mkdir(target)
    wc._cache = None
    path, error = wc.append_builtins(['music'])
    check('an unwritable target fails cleanly, no exception',
          path is None and error and error != 'no workflow file', str(error))
    os.rmdir(target)

finally:
    if keep is None:
        os.environ.pop(wc.ENV_OVERRIDE, None)
    else:
        os.environ[wc.ENV_OVERRIDE] = keep
    wc._cache = None
    wc.LAST_ERROR = None

print()
print('FAILURES:', ', '.join(fails) if fails else 'none')
sys.exit(1 if fails else 0)
