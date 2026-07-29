"""GPX matching, the dialog, and network calls off the GUI thread (0.15.0)."""
import os
import sys
import tempfile
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtWidgets import QApplication

import Cammello
from cammello import gpx
from cammello.gpx_dialog import GpxMatchDialog
from cammello.wikidata import fetch_in_background
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


# ── time parsing ─────────────────────────────────────────────────────────────
check('GPX UTC time', gpx.parse_gpx_time('2026-07-20T10:00:00Z') is not None)
check('GPX numeric offset shifts the epoch',
      gpx.parse_gpx_time('2026-07-20T12:00:00+02:00')
      == gpx.parse_gpx_time('2026-07-20T10:00:00Z'))
check('nonsense yields None', gpx.parse_gpx_time('gestern') is None)
check('EXIF colon form and dash form agree',
      gpx.parse_exif_datetime('2026:07:20 12:03:00', 7200)
      == gpx.parse_exif_datetime('2026-07-20 12:03:00', 7200))
check('the offset turns local into UTC',
      gpx.parse_exif_datetime('2026-07-20 12:00:00', 7200)
      == gpx.parse_gpx_time('2026-07-20T10:00:00Z'))

# ── parsing a track ──────────────────────────────────────────────────────────
d = tempfile.mkdtemp()
track = os.path.join(d, 't.gpx')
open(track, 'w').write(
    '<?xml version="1.0"?>'
    '<gpx xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>'
    '<trkpt lat="48.1" lon="9.1"><time>2026-07-20T10:00:00Z</time></trkpt>'
    '<trkpt lat="48.2" lon="9.2"><time>2026-07-20T10:05:00Z</time></trkpt>'
    '<trkpt lat="999" lon="9.9"><time>2026-07-20T10:06:00Z</time></trkpt>'
    '<trkpt lat="48.3" lon="9.3"/>'
    '</trkseg></trk></gpx>')
pts = gpx.parse_gpx(track)
check('valid points are read, invalid and timeless ones skipped',
      len(pts) == 2, f'{len(pts)} points')

broken = os.path.join(d, 'b.gpx')
open(broken, 'w').write('<gpx><trk>')
check('a broken file yields an empty list, not an exception',
      gpx.parse_gpx(broken, log=logger) == [])

# ── matching ─────────────────────────────────────────────────────────────────
res = gpx.match_files(pts, [('/a.jpg', '2026-07-20 12:03:00')], 7200, 300)
check('a photo lands on the nearest point', res['/a.jpg'] == (48.2, 9.2),
      str(res))
res = gpx.match_files(pts, [('/a.jpg', '2026-07-20 12:03:00')], 7200, 60)
check('outside the gap there is no match', res['/a.jpg'] is None)
res = gpx.match_files(pts, [('/a.jpg', '')], 7200, 300)
check('a file without a date gets None', res['/a.jpg'] is None)

# ── the dialog, driven headless ──────────────────────────────────────────────
files = [('/x/one.jpg', '2026-07-20 12:03:00', False),
         ('/x/two.jpg', '2026-07-20 12:04:00', True),
         ('/x/three.jpg', '', False)]
dlg = GpxMatchDialog(files, None, settings=w.settings)
check('the apply button starts disabled', not dlg._ok_btn.isEnabled())
dlg._gpx_edit.setText(track)
dlg._points = gpx.index_points(gpx.parse_gpx(track))
dlg._offset.setValue(120)      # camera at UTC+2
dlg._gap.setValue(5)
dlg._rematch()
check('matching enables the apply button', dlg._ok_btn.isEnabled())
dlg._accept()
check('a file WITH a position is not overwritten by default',
      '/x/two.jpg' not in dlg.results, str(dlg.results))
check('a file without one gets the matched point',
      dlg.results.get('/x/one.jpg') == (48.2, 9.2))
check('a file without a date stays out', '/x/three.jpg' not in dlg.results)
dlg._overwrite.setChecked(True)
dlg._rematch()
dlg._accept()
check('overwrite includes the file with a position',
      '/x/two.jpg' in dlg.results)

# ── fetch_in_background ──────────────────────────────────────────────────────
def _slowly(x):
    time.sleep(0.05)
    return x * 2

result, exc, cancelled = fetch_in_background(None, 'test', _slowly, 21)
check('the background call returns the result',
      result == 42 and exc is None and not cancelled)

def _boom():
    raise RuntimeError('kaputt')

result, exc, cancelled = fetch_in_background(None, 'test', _boom)
check('an exception comes back as a value, not a crash',
      result is None and isinstance(exc, RuntimeError) and not cancelled)

check('the GPX action exists', hasattr(w, '_location_match_gpx'))

print()
print('FAILURES:', ', '.join(fails) if fails else 'none')
sys.exit(1 if fails else 0)
