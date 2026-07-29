"""Preview delivery: priority promotion and the watchdog (0.15.0).

Covers the two reported symptoms - previews arriving late, or not at all.
Both are checked on the mechanism, not on timing: a test that waits for a
decode would be flaky in CI.
"""
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtWidgets import QApplication

import Cammello
from cammello import previews
from cammello.constants import CULL_RETRIES, CULL_RETRY_MS
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


# ── priority promotion ───────────────────────────────────────────────────────
ld = previews.PreviewLoader()
started = []
ld._pool.start = lambda job, prio=0: started.append((job.key, prio))

ld.request('/nowhere/a.jpg', 'screen', previews.PreviewLoader.P_PREFETCH)
check('a prefetch is queued', len(started) == 1,
      str([p for _k, p in started]))

ld.request('/nowhere/a.jpg', 'screen', previews.PreviewLoader.P_PREFETCH)
check('the same priority is not queued twice', len(started) == 1)

ld.request('/nowhere/a.jpg', 'screen', previews.PreviewLoader.P_CURRENT)
check('a higher priority re-queues the same image', len(started) == 2,
      str([p for _k, p in started]))
check('the second job carries the higher priority',
      started[-1][1] == previews.PreviewLoader.P_CURRENT)

ld.request('/nowhere/a.jpg', 'screen', previews.PreviewLoader.P_PREFETCH)
check('a lower priority afterwards is ignored', len(started) == 2)

check('_inflight remembers the highest priority',
      ld._inflight.get(('/nowhere/a.jpg', 'screen'))
      == previews.PreviewLoader.P_CURRENT)

ld._done('/nowhere/a.jpg', 'screen')
check('_done clears the entry',
      ('/nowhere/a.jpg', 'screen') not in ld._inflight)

ld.new_generation()
check('a generation change clears everything', not ld._inflight)

# ── the watchdog ─────────────────────────────────────────────────────────────
check('the culling view can say whether it holds an image',
      hasattr(w.cull_view, 'has_image'))
check('an empty view reports no image', not w.cull_view.has_image())
check('the retry timer exists and is single-shot',
      w._cull_retry_timer.isSingleShot())
check('the retry budget is bounded', CULL_RETRIES >= 1 and CULL_RETRY_MS > 0,
      f'{CULL_RETRIES} attempts every {CULL_RETRY_MS} ms')
check('failed previews are handled, not just logged',
      hasattr(w, '_cull_on_failed'))


class _Item:
    display_path = '/nowhere/b.jpg'


asked = []
w._cull_visible = [_Item()]
w._cull_index = 0
w._cull_failed_paths = set()
w._cull_retry_left = CULL_RETRIES
w._cull_loader.request = lambda path, level, prio: asked.append((path, prio))

w._cull_retry_current()
check('the watchdog asks again for a blank image', len(asked) == 1,
      str(asked))
check('it asks at the highest priority',
      asked and asked[0][1] == previews.PreviewLoader.P_CURRENT)
check('it spends one attempt', w._cull_retry_left == CULL_RETRIES - 1)

asked.clear()
w._cull_failed_paths.add('/nowhere/b.jpg')
w._cull_retry_current()
check('a file that failed to decode is not retried', not asked)

asked.clear()
w._cull_failed_paths.clear()
w._cull_retry_left = 0
w._cull_retry_current()
check('the retries are bounded', not asked)

print()
print('FAILURES:', ', '.join(fails) if fails else 'none')
sys.exit(1 if fails else 0)
