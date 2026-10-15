"""[workflow.statements] (0.18.33): fixed SDC claims per workflow.

Defended here:
  1. statement_claims(): Q-ID lists give item claims, other text ONE string
     claim, a property already produced elsewhere is skipped, junk is dropped,
  2. the TOML parser keeps good entries, warns about bad ones, accepts lists,
  3. render_block() / preview_text() carry the statements (the preview is the
     only confirmation before a .cammello file goes into every upload),
  4. workflows.statements(key) hands them to the upload,
  5. the worker really sends them in the SDC call - and lets the dialog's own
     depicts win over a statement for P180.
"""
import os
import sys
import tempfile
import tomllib

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QEventLoop, QTimer

from cammello import workflow_config as wc
from cammello import workflows
from cammello.sdc import statement_claims
from cammello.workers import UploadWorker
from cammello.logging_setup import setup_logging

app = QApplication(sys.argv)
logger, emitter, gui_handler, log_path = setup_logging()
fails = []


def check(name, cond, detail=''):
    print(('PASS' if cond else 'FAIL'), name, detail)
    if not cond:
        fails.append(name)


# 1 ── pure function ────────────────────────────────────────────────────────
c = statement_claims({'P1': 'Q5', 'P2': 'Q1; Q2;Q1', 'P3': 'https://x.org/a;b',
                      'P4': '  ', 'bad': 'Q1', 'P5': 'Q6'}, taken={'P5'})
check('single item', ('P1', 'Q5') in c, str(c))
check('several items, duplicates dropped',
      [v for p, v in c if p == 'P2'] == ['Q1', 'Q2'], str(c))
check('text with ";" stays ONE string',
      [v for p, v in c if p == 'P3'] == [('string', 'https://x.org/a;b')])
check('blank, bad property and taken property are skipped',
      {p for p, _ in c} == {'P1', 'P2', 'P3'}, str(c))
check('None is harmless', statement_claims(None) == [])

# 2 ── parser ───────────────────────────────────────────────────────────────
tmp = tempfile.mkdtemp()
target = os.path.join(tmp, 'workflows.toml')
TEXT = '''[[workflow]]
key = "evt"
name = "Event"
hide_fields = []
[workflow.statements]
P1435 = "Q123"
p180 = ["Q1", "Q2"]
P856 = "https://example.org/x"
foo = "Q1"
P99 = 5
P98 = ""
'''
old = os.environ.get(wc.ENV_OVERRIDE)
os.environ[wc.ENV_OVERRIDE] = target
try:
    with open(target, 'w', encoding='utf-8') as fh:
        fh.write(TEXT)
    wc._cache = None
    wc.LAST_ERROR = None
    entries = wc.load()
    st = entries[0]['statements']
    check('file parsed', wc.LAST_ERROR is None, str(wc.LAST_ERROR))
    check('good statements kept, property upper-cased',
          st == {'P1435': 'Q123', 'P180': 'Q1; Q2',
                 'P856': 'https://example.org/x'}, str(st))
    warn = ' | '.join(wc.LAST_WARNINGS)
    check('bad ones are reported', 'foo' in warn and 'P99' in warn
          and 'P98' in warn, warn)
    check('workflows.statements(key)',
          workflows.statements('evt')['P1435'] == 'Q123')
    check('unknown key never raises',
          isinstance(workflows.statements('nope'), dict))

    # 3 ── export / preview ─────────────────────────────────────────────────
    block = wc.render_block(entries[0])
    back = tomllib.loads(block)['workflow'][0]
    check('render_block round-trips', wc._clean_statements(
        back['statements'], 'x', []) == st, block)
    prev = wc.preview_text(entries)
    check('preview shows every statement in full',
          'P1435 = Q123' in prev and 'P856 = https://example.org/x' in prev,
          prev)
    # the built-ins and the generated template carry the new section
    check('built-ins have the key',
          all('statements' in w for w in wc.BUILTIN))
    check('template mentions the section',
          '[workflow.statements]' in wc.template_text())
finally:
    if old is None:
        os.environ.pop(wc.ENV_OVERRIDE, None)
    else:
        os.environ[wc.ENV_OVERRIDE] = old
    wc._cache = None


# 5 ── the worker ───────────────────────────────────────────────────────────
class FakeApi:
    log = logger
    timeout = 5

    def __init__(self):
        self.sdc = []

    def upload(self, *a, **kw):
        pass

    def clear_token(self):
        pass

    def get_page_id(self, filename):
        return 7

    def set_structured_data(self, page_id, labels, claims):
        self.sdc.append((labels, list(claims)))

    def purge(self, *a, **kw):
        pass

    def update_gallery(self, page, entries):
        pass


def run(statements, desc):
    api = FakeApi()
    row = {'filepath': '/tmp/none.jpg', 'target_name': 'X.jpg',
           'source_name': 'x.jpg', 'date': '', 'description_all': desc,
           'author': '', 'source': '', 'permission': '', 'license_text': '',
           'other_templates': '', 'other_fields': '', 'template': 'Information'}
    w = UploadWorker(api, [row], '', False, statements=statements)
    loop = QEventLoop()
    w.finished.connect(lambda s: loop.quit())
    QTimer.singleShot(15000, loop.quit)
    w.start()
    loop.exec_()
    w.wait(3000)
    return api.sdc


sdc = run({'P1435': 'Q123', 'P180': 'Q999', 'P856': 'https://e.org'},
          'caption_en=Test\ndepicts=Q640')
claims = sdc[0][1] if sdc else []
check('one SDC call', len(sdc) == 1, str(sdc))
check('statement item claim sent', ('P1435', 'Q123') in claims, str(claims))
check('statement string claim sent',
      ('P856', ('string', 'https://e.org')) in claims, str(claims))
check('the dialog depicts wins over a P180 statement',
      [v for p, v in claims if p == 'P180'] == ['Q640'], str(claims))
check('no statements, no extra claims',
      [p for p, _ in (run(None, 'caption_en=T')[0][1])] == [])

print('\nFAILURES:', fails if fails else 'none')
sys.stdout.flush()
os._exit(1 if fails else 0)
