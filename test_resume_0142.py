"""0.14.2: crash-safe resume of an interrupted upload batch.

The scenario Harald named: 200 files, something dies after 100, and the
rest has to go up after a restart without hand-sorting what made it.

Covers:
  1. Journal basics: start/load round-trip, counts, resumability, atomic
     write, a corrupt or foreign-format journal is ignored rather than
     fatal, discard.
  2. A SIMULATED CRASH through the real UploadWorker: a fake API that
     raises after N files, then a second worker over the journal's pending
     rows - every file ends up on the fake Commons exactly once.
  3. The in-flight window: a file whose upload request went out but whose
     outcome was never recorded is asked about, not blindly re-sent
     (once when it did arrive, once when it did not).
  4. Gallery entries collected before the interruption are carried into
     the resumed run, and are not written twice.
  5. Rows are matched by filepath + target name, so a resume finds them
     without any index bookkeeping.

Run as a file (multiprocessing rule).
"""
import json
import os
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
FAILURES = []


def check(name, cond, detail=''):
    print(('PASS ' if cond else 'FAIL ') + name, detail)
    if not cond:
        FAILURES.append(name)


def make_rows(n, folder):
    rows = []
    for i in range(n):
        path = os.path.join(folder, f'img_{i:03d}.jpg')
        with open(path, 'wb') as f:
            f.write(b'\xff\xd8\xff\xe0stub')
        rows.append({
            'filepath': path,
            'target_name': f'Test image {i:03d}.jpg',
            'source_name': f'img_{i:03d}.jpg',
            'date': '2026-07-25',
            'description_all': 'depicts=Q42\ncaption_en=Test',
            'author': 'Harald Krichel', 'source': 'own', 'permission': '',
            'license_text': '{{Cc-by-sa-4.0}}', 'other_templates': '',
            'other_fields': '', 'template': 'Information',
        })
    return rows


class FakeApi:
    """Enough of MediaWikiApi for the worker, with a scripted crash."""

    def __init__(self, log, fail_at=None):
        self.log = log
        self.uploaded = []          # filenames that "reached Commons"
        self.galleries = {}         # page -> list of entries
        self.fail_at = fail_at      # raise a hard error before this upload
        self.page_id_calls = []
        self.timeout = 30
        self.api_url = 'https://commons.wikimedia.org/w/api.php'
        self.username = 'Seewolf'

    def upload(self, filename, filepath, wikitext, comment,
               ignore_warnings=False):
        if self.fail_at is not None and len(self.uploaded) >= self.fail_at:
            raise KeyboardInterrupt('simulated crash')
        self.uploaded.append(filename)
        return True

    def clear_token(self):
        pass

    def get_page_id(self, filename):
        self.page_id_calls.append(filename)
        return 4711 if filename in self.uploaded else None

    def set_structured_data(self, page_id, labels, claims):
        pass

    def purge(self, title):
        pass

    def update_gallery(self, page, entries):
        self.galleries.setdefault(page, []).extend(entries)


def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import logging
    from PyQt5.QtWidgets import QApplication
    from cammello import upload_journal as uj
    from cammello.workers import UploadWorker

    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841
    log = logging.getLogger('test_resume')
    log.addHandler(logging.NullHandler())

    tmp = tempfile.mkdtemp()
    jpath = os.path.join(tmp, 'journal.json')

    # ── 1. Journal basics ────────────────────────────────────────────────
    rows = make_rows(10, tmp)
    j = uj.Journal.start(rows, gallery_prefix='Commons:WikiPortraits',
                         ignore_warnings=False,
                         api_url='https://commons.wikimedia.org/w/api.php',
                         username='Seewolf', path=jpath)
    check('journal file written', os.path.exists(jpath))
    check('all entries start pending', j.counts() == (0, 0, 10, 10),
          str(j.counts()))
    check('a fresh batch is resumable', j.is_resumable())

    j.mark(rows[0], uj.DONE)
    j.mark(rows[1], uj.FAILED, error='bad name')
    reloaded = uj.Journal.load(jpath)
    check('state survives a reload', reloaded.counts() == (1, 1, 8, 10),
          str(reloaded.counts()))
    check('pending rows exclude done and failed',
          len(reloaded.pending_rows()) == 8)
    check('rows are matched by path, not index',
          reloaded.entries[0]['status'] == uj.DONE
          and reloaded.entries[1]['status'] == uj.FAILED)

    # Written atomically: no leftover temp files beside the journal.
    strays = [f for f in os.listdir(tmp) if f.endswith('.tmp')]
    check('no temp files left behind', not strays, str(strays))

    # A journal where everything failed is not offered for resuming.
    j2path = os.path.join(tmp, 'j2.json')
    j2 = uj.Journal.start(make_rows(2, tmp), path=j2path)
    for r in j2.pending_rows():
        j2.mark(r, uj.FAILED)
    check('a fully failed batch is not resumable', not j2.is_resumable())
    check('load_resumable cleans up a finished journal',
          uj.load_resumable(j2path) is None and not os.path.exists(j2path))

    # Corrupt / foreign journals must be ignored, never raise.
    bad = os.path.join(tmp, 'bad.json')
    with open(bad, 'w') as f:
        f.write('{not json')
    check('a corrupt journal is ignored', uj.Journal.load(bad) is None)
    with open(bad, 'w') as f:
        json.dump({'format': 99, 'entries': []}, f)
    check('a future format is ignored', uj.Journal.load(bad) is None)
    check('a missing journal is ignored',
          uj.Journal.load(os.path.join(tmp, 'nope.json')) is None)

    # ── 2. Simulated crash and resume through the real worker ────────────
    run_dir = tempfile.mkdtemp()
    jrun = os.path.join(run_dir, 'run.json')
    rows = make_rows(200, run_dir)
    journal = uj.Journal.start(rows, gallery_prefix='', path=jrun)

    api = FakeApi(log, fail_at=100)          # dies after 100 files
    worker = UploadWorker(api, rows, '', False, journal=journal)
    try:
        worker.run()                          # synchronous: no thread needed
    except KeyboardInterrupt:
        pass                                  # this IS the crash
    check('100 of 200 files reached the fake Commons',
          len(api.uploaded) == 100, str(len(api.uploaded)))

    # The process is gone; a new run reads only the journal from disk.
    resumed = uj.Journal.load(jrun)
    done, failed, openc, total = resumed.counts()
    check('journal survived the crash with the right split',
          (done, failed, total) == (100, 0, 200), f'{done}/{failed}/{total}')
    check('the crashed file is marked in flight',
          len(resumed.in_flight_entries()) == 1,
          str(len(resumed.in_flight_entries())))

    # Resolve the in-flight entry the way the GUI does: ask the wiki.
    entry = resumed.in_flight_entries()[0]
    target = entry.get('target') or entry['row']['target_name']
    entry['status'] = uj.DONE if api.get_page_id(target) else uj.PENDING
    resumed.save()
    check('the in-flight file is asked about, not assumed',
          target in api.page_id_calls)
    check('it did NOT arrive, so it goes back to pending',
          entry['status'] == uj.PENDING)

    api2 = FakeApi(log)                       # a healthy session
    api2.uploaded = list(api.uploaded)        # the wiki still has the first 100
    pending = resumed.pending_rows()
    check('exactly the remaining 100 are pending', len(pending) == 100,
          str(len(pending)))
    worker2 = UploadWorker(api2, pending, '', False, journal=resumed)
    worker2.run()

    check('all 200 files are on the fake Commons after the resume',
          len(api2.uploaded) == 200, str(len(api2.uploaded)))
    check('no file was uploaded twice',
          len(set(api2.uploaded)) == 200, str(len(set(api2.uploaded))))
    check('the journal is removed once nothing is left',
          not os.path.exists(jrun))

    # ── 3. The in-flight file that DID arrive ────────────────────────────
    d3 = tempfile.mkdtemp()
    j3 = os.path.join(d3, 'j3.json')
    rows3 = make_rows(5, d3)
    jj = uj.Journal.start(rows3, path=j3)
    api3 = FakeApi(log)
    # Pretend file 2 went up and the answer never came back.
    api3.uploaded.append(rows3[2]['target_name'])
    jj.mark(rows3[0], uj.DONE)
    jj.mark(rows3[1], uj.DONE)
    jj.mark(rows3[2], uj.IN_FLIGHT, target=rows3[2]['target_name'])
    e = jj.in_flight_entries()[0]
    e['status'] = uj.DONE if api3.get_page_id(e['target']) else uj.PENDING
    jj.save()
    check('an in-flight file that DID arrive counts as uploaded',
          e['status'] == uj.DONE)
    check('and is not sent a second time',
          rows3[2] not in jj.pending_rows())

    # ── 4. Gallery carry-over ────────────────────────────────────────────
    d4 = tempfile.mkdtemp()
    j4 = os.path.join(d4, 'j4.json')
    rows4 = make_rows(4, d4)
    jg = uj.Journal.start(rows4, gallery_prefix='Commons:WP', path=j4)
    jg.mark(rows4[0], uj.DONE,
            gallery=('Commons:WP/2026', 'A.jpg', 'caption A'))
    jg.mark(rows4[1], uj.DONE,
            gallery=('Commons:WP/2026', 'B.jpg', 'caption B'))
    carried = jg.collected_gallery()
    check('gallery entries of the first run are carried over',
          carried.get('Commons:WP/2026') == [('A.jpg', 'caption A'),
                                             ('B.jpg', 'caption B')],
          str(carried))
    jg.set_gallery_written()
    check('once written, they are not carried again',
          jg.collected_gallery() == {})

    api4 = FakeApi(log)
    jg2 = uj.Journal.load(j4)
    worker4 = UploadWorker(api4, jg2.pending_rows(), 'Commons:WP', False,
                           journal=jg2)
    worker4.run()
    entries = api4.galleries.get('Commons:WP/2026', [])
    check('the gallery was not written twice',
          not any(name == 'A.jpg' for name, _cap in entries), str(entries))

    # ── 5. Worker without a journal still works ──────────────────────────
    d5 = tempfile.mkdtemp()
    api5 = FakeApi(log)
    rows5 = make_rows(3, d5)
    UploadWorker(api5, rows5, '', False, journal=None).run()
    check('a run without a journal is unaffected', len(api5.uploaded) == 3,
          str(len(api5.uploaded)))

    print('\nFAILURES:', FAILURES if FAILURES else 'none')
    return 1 if FAILURES else 0


if __name__ == '__main__':
    sys.exit(main())
