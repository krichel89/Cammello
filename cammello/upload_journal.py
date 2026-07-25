"""Crash-safe journal for an upload batch (0.14.2). NEW MODULE.

The problem it solves: a batch of 200 files dies after 100 - power cut,
crash, closed laptop. Before this, the only way back was to work out by
hand which files had made it and rebuild the table around the rest.

The design mirrors channels.py / edits.py: plain JSON, no Qt, so the logic
is testable on its own. It is NOT in QSettings, though, and that is
deliberate:

  * the journal is written after EVERY file, and QSettings gives no
    guarantee about when a value reaches the disk - which is exactly the
    moment that matters here;
  * a file can be written atomically (write to a temp file in the same
    directory, then os.replace), so a crash mid-write leaves either the
    old journal or the new one, never half of one;
  * it lives next to the log, where it can be inspected after a crash.

Each entry carries the FULL row dict the worker needs, so a resumed run
does not depend on the file table still holding those rows - after a crash
it does not.

Status of an entry:
    pending    not attempted yet
    in_flight  the upload request went out; the outcome is unknown. This is
               the crash window: the file may well be on Commons with the
               journal never having heard about it, which is why a resume
               ASKS Commons about these before re-uploading.
    done       uploaded (post-processing may still have failed; that is
               logged, and does not make the file un-uploaded)
    failed     the upload itself failed; the file is not on Commons
"""
import json
import os
import tempfile
import time

JOURNAL_NAME = 'upload_journal.json'
FORMAT_VERSION = 1

PENDING = 'pending'
IN_FLIGHT = 'in_flight'
DONE = 'done'
FAILED = 'failed'

OPEN_STATES = (PENDING, IN_FLIGHT)


def journal_dir():
    """Same folder as the log file (see logging_setup)."""
    return os.path.join(os.path.expanduser('~'), 'Cammello')


def journal_path():
    return os.path.join(journal_dir(), JOURNAL_NAME)


def _atomic_write(path, data):
    """Write `data` so that a crash can never leave a half journal: a temp
    file in the SAME directory (os.replace is only atomic within one file
    system), flushed and fsync'd, then moved into place."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class Journal:
    """One upload batch. Every state change is written through to disk."""

    def __init__(self, data, path=None):
        self.data = data
        self.path = path or journal_path()

    # -- creation / loading -----------------------------------------------
    @classmethod
    def start(cls, rows, gallery_prefix='', ignore_warnings=False,
              api_url='', username='', path=None):
        data = {
            'format': FORMAT_VERSION,
            'started': time.strftime('%Y-%m-%d %H:%M:%S'),
            'updated': time.strftime('%Y-%m-%d %H:%M:%S'),
            'gallery_prefix': gallery_prefix,
            'ignore_warnings': bool(ignore_warnings),
            'api_url': api_url,
            'username': username,
            'gallery_written': False,
            'entries': [{'row': dict(r), 'status': PENDING, 'target': '',
                         'error': '', 'gallery': None} for r in rows],
        }
        j = cls(data, path)
        j.save()
        return j

    @classmethod
    def load(cls, path=None):
        """-> Journal, or None if there is none or it is unusable. A corrupt
        journal is never a reason to fail the start; it is ignored."""
        path = path or journal_path()
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict) or data.get('format') != FORMAT_VERSION:
            return None
        entries = data.get('entries')
        if not isinstance(entries, list) or not entries:
            return None
        for e in entries:
            if not isinstance(e, dict) or not isinstance(e.get('row'), dict):
                return None
        return cls(data, path)

    # -- state ------------------------------------------------------------
    @property
    def entries(self):
        return self.data['entries']

    def counts(self):
        """-> (done, failed, open, total)."""
        done = sum(1 for e in self.entries if e['status'] == DONE)
        failed = sum(1 for e in self.entries if e['status'] == FAILED)
        openc = sum(1 for e in self.entries if e['status'] in OPEN_STATES)
        return done, failed, openc, len(self.entries)

    def is_resumable(self):
        """True while files remain that were never uploaded. Entries that
        FAILED are not counted: they were attempted and rejected (a bad
        filename, a missing licence), so resuming would only repeat the
        error. They stay in the journal for the report."""
        return any(e['status'] in OPEN_STATES for e in self.entries)

    def open_entries(self):
        return [e for e in self.entries if e['status'] in OPEN_STATES]

    def in_flight_entries(self):
        return [e for e in self.entries if e['status'] == IN_FLIGHT]

    def pending_rows(self):
        """The row dicts a resumed run has to upload, in original order."""
        return [e['row'] for e in self.open_entries()]

    def collected_gallery(self):
        """Gallery entries of files already uploaded whose gallery has not
        been written yet -> {page: [(filename, caption), ...]}."""
        out = {}
        if self.data.get('gallery_written'):
            return out
        for e in self.entries:
            g = e.get('gallery')
            if e['status'] == DONE and g:
                page, filename, caption = g
                if page:
                    out.setdefault(page, []).append((filename, caption))
        return out

    # -- updates ----------------------------------------------------------
    def _index_of(self, row):
        """Find an entry by its row identity (filepath + target name), so
        the caller does not have to track indices across a resume."""
        fp = row.get('filepath')
        target = row.get('target_name')
        for i, e in enumerate(self.entries):
            if (e['row'].get('filepath') == fp
                    and e['row'].get('target_name') == target):
                return i
        return -1

    def mark(self, row, status, target=None, error=None, gallery=None,
             save=True):
        i = self._index_of(row)
        if i < 0:
            return False
        e = self.entries[i]
        e['status'] = status
        if target is not None:
            e['target'] = target
        if error is not None:
            e['error'] = error
        if gallery is not None:
            e['gallery'] = list(gallery)
        if save:
            self.save()
        return True

    def set_gallery_written(self):
        self.data['gallery_written'] = True
        self.save()

    def save(self):
        self.data['updated'] = time.strftime('%Y-%m-%d %H:%M:%S')
        _atomic_write(self.path, self.data)

    def discard(self):
        """Remove the journal - the batch is finished or given up on."""
        try:
            os.unlink(self.path)
        except OSError:
            pass


def load_resumable(path=None):
    """-> Journal with unfinished files, else None. The one call the GUI
    needs at start-up; it touches no network and no keyring."""
    j = Journal.load(path)
    if j is not None and j.is_resumable():
        return j
    if j is not None:
        # Nothing left to do: an old journal from a completed run (or one
        # where everything failed). Clean it up so it stops being offered.
        j.discard()
    return None
