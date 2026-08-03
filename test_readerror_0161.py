"""Lokale Lesefehler beim Upload (0.16.1).

Stellt den gemeldeten Nutzerfall nach: eine Datei, die Windows findet und
oeffnet, deren Daten es aber nicht liefert ([Errno 22] Invalid argument).
Vorher war das ein roher Traceback, der den COMMONS-Zielnamen nannte statt
des lokalen Pfades, und die Datei galt als endgueltig gescheitert.
"""
import errno
import os
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('CAMMELLO_WORKFLOWS',
                      os.path.join(tempfile.mkdtemp(), 'workflows.toml'))

from cammello import upload_journal as journal_mod
from cammello.api import (LocalFileError, MediaWikiApi,
                          is_remote_path)

fails = []


def check(name, cond, detail=''):
    if cond:
        print('PASS', name, detail)
    else:
        print('FAIL', name, detail)
        fails.append(name)


_dir = tempfile.mkdtemp()
_good = os.path.join(_dir, 'IMG_1050.JPG')
with open(_good, 'wb') as fh:
    fh.write(b'\xff\xd8\xff' + b'x' * 5000)

# ── check_readable ───────────────────────────────────────────────────────
MediaWikiApi.check_readable(_good)
check('a readable file passes silently', True)

try:
    MediaWikiApi.check_readable(os.path.join(_dir, 'gone.JPG'))
    check('a missing file is refused', False)
except LocalFileError as e:
    check('a missing file raises LocalFileError', True)
    check('and the message names the LOCAL path, not the Commons target',
          'gone.JPG' in str(e) and e.path.endswith('gone.JPG'), str(e))

# The real case: open() works, read() does not. Exactly what the user hit -
# stat and open succeeded, only the data never came.
_real_open = open


def _open_that_cannot_read(path, *a, **k):
    fh = _real_open(path, *a, **k)
    if os.path.basename(path) == 'IMG_1050.JPG':
        class _Broken:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *exc):
                fh.close()
                return False

            def read(self_inner, *args):
                raise OSError(errno.EINVAL, 'Invalid argument')
        return _Broken()
    return fh


import builtins
builtins.open = _open_that_cannot_read
try:
    try:
        MediaWikiApi.check_readable(_good)
        check('a file that opens but cannot be read is caught', False)
    except LocalFileError as e:
        check('a file that opens but cannot be read is caught', True)
        check('the reason is carried through',
              'Invalid argument' in str(e), str(e))
        check('the local path is on the exception object',
              e.path == _good, e.path)
finally:
    builtins.open = _real_open

check('LocalFileError is an Exception, so old handlers still catch it',
      issubclass(LocalFileError, Exception))

# ── Hinweis auf ein Netzlaufwerk - NUR im Fehlerfall ─────────────────────
check('a local path is not called remote', not is_remote_path(_good),
      _good)
# Must never raise: this runs when an upload has ALREADY gone wrong.
for _odd in ('', '   ', 'relative/name.jpg', None):
    try:
        is_remote_path(_odd)
        _ok = True
    except Exception as _e:
        _ok = False
        print('   raised on', repr(_odd), _e)
    check(f'odd input {_odd!r} does not raise', _ok)
if sys.platform == 'win32':
    check('a UNC path counts as remote',
          is_remote_path(r'\\\\server\\share\\IMG.JPG'))
elif sys.platform == 'darwin':
    check('an external volume counts as remote',
          is_remote_path('/Volumes/NAS/IMG.JPG'))
else:
    check('a mounted volume counts as remote',
          is_remote_path('/mnt/nas/IMG.JPG')
          and is_remote_path('/media/usb/IMG.JPG'))

_remote = LocalFileError('/mnt/nas/IMG_1051.JPG', 'Invalid argument')
check('a remote file gets the copy-it-locally hint',
      _remote.remote and 'network' in str(_remote).lower(), str(_remote))
_local = LocalFileError(_good, 'Invalid argument')
check('a local file gets NO hint - it would only mislead',
      not _local.remote and 'network' not in str(_local).lower(),
      str(_local))
check('the hint never replaces the path',
      _remote.path in str(_remote))

# ── Journal: unlesbar ist NICHT endgueltig ───────────────────────────────
check('UNREADABLE is its own status',
      journal_mod.UNREADABLE not in (journal_mod.FAILED, journal_mod.PENDING,
                                     journal_mod.DONE, journal_mod.IN_FLIGHT))
check('and it counts as open, so a resume offers it',
      journal_mod.UNREADABLE in journal_mod.OPEN_STATES)
check('while a real failure still does not',
      journal_mod.FAILED not in journal_mod.OPEN_STATES)

_rows = [{'filepath': os.path.join(_dir, f'IMG_{i}.JPG'),
          'target_name': f'Target ({i:03d}).JPG'} for i in range(1, 4)]
_j = journal_mod.Journal.start(_rows, path=os.path.join(_dir, 'j.json'))
_j.mark(_rows[0], journal_mod.DONE, target='Target (001).JPG')
_j.mark(_rows[1], journal_mod.UNREADABLE, error='cannot read',
        target='Target (002).JPG')
_j.mark(_rows[2], journal_mod.FAILED, error='bad filename',
        target='Target (003).JPG')
check('a run with an unreadable file is resumable', _j.is_resumable())
check('the unreadable one is listed',
      [e['target'] for e in _j.unreadable_entries()] == ['Target (002).JPG'],
      str([e['target'] for e in _j.unreadable_entries()]))
_open_targets = [e['target'] for e in _j.open_entries()]
check('it is among the open entries',
      'Target (002).JPG' in _open_targets, str(_open_targets))
check('the genuinely failed one is NOT retried',
      'Target (003).JPG' not in _open_targets, str(_open_targets))
check('the finished one is not either',
      'Target (001).JPG' not in _open_targets, str(_open_targets))

# A journal holding ONLY failures must not offer a resume.
_j2 = journal_mod.Journal.start(_rows[:1], path=os.path.join(_dir, 'j2.json'))
_j2.mark(_rows[0], journal_mod.FAILED, error='bad filename')
check('a run with only real failures is not resumable',
      not _j2.is_resumable())

# The status survives a round trip through the file.
_j3 = journal_mod.Journal.load(os.path.join(_dir, 'j.json'))
check('the status survives being written and read back',
      _j3 is not None and len(_j3.unreadable_entries()) == 1,
      str(_j3 and [e['status'] for e in _j3.entries]))

print('---')
print('FAILURES:', fails if fails else 'none')
print(f'{len(fails)} failure(s)')
sys.exit(1 if fails else 0)
