"""Location data: reading, storing, and the workflow-dependent UI (0.15.0)."""
import os
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtWidgets import QApplication, QMessageBox

import Cammello
from cammello import geo, workflows
from cammello.constants import SD_KEYS, PROPERTY_MAP
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


# ── parsing ──────────────────────────────────────────────────────────────────
check('decimal pair', geo.parse_pair('48.775846, 9.182932')
      == (48.775846, 9.182932))
check('German decimal commas', geo.parse_pair('48,775846 9,182932')
      == (48.775846, 9.182932))
check('semicolon separator', geo.parse_pair('48.775846; 9.182932')
      == (48.775846, 9.182932))
check('nonsense is rejected', geo.parse_pair('Unsinn') is None)
check('out-of-range is rejected', geo.parse_pair('200, 9') is None)
check('the output always uses a point',
      geo.format_pair((48.775846, 9.182932)) == '48.775846, 9.182932')

check('XMP degrees/minutes with hemisphere',
      abs(geo.parse_xmp_coordinate('48,46.5507N') - 48.775845) < 1e-5)
check('XMP degrees/minutes/seconds',
      abs(geo.parse_xmp_coordinate('9,10,58.5E') - 9.182917) < 1e-5)
check('a southern value turns negative',
      geo.parse_xmp_coordinate('33,52.1S') < 0)

# ── reading a real sidecar ───────────────────────────────────────────────────
tmp = tempfile.mkdtemp()
img = os.path.join(tmp, 'DSC_0001.CR3')
open(img, 'wb').write(b'not a real raw')
open(os.path.join(tmp, 'DSC_0001.xmp'), 'w', encoding='utf-8').write(
    '<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF><rdf:Description '
    'exif:GPSLatitude="48,46.5507N" exif:GPSLongitude="9,10,58.5E"/>'
    '</rdf:RDF></x:xmpmeta>')
check('the sidecar next to a RAW is found',
      geo.sidecar_path(img) is not None)
hit = geo.read_camera_position(img, log=logger)
check('the camera position comes out of the sidecar',
      hit is not None and hit[1] == geo.SRC_SIDECAR, str(hit))
check('and it is the right one',
      hit is not None and abs(hit[0][0] - 48.775845) < 1e-5)

# ── storage ──────────────────────────────────────────────────────────────────
store = {}
check('setting a camera position reports a change',
      geo.set_position(store, img, 'camera', (48.1, 9.1), geo.SRC_EXIF))
check('setting the same value again does not',
      not geo.set_position(store, img, 'camera', (48.1, 9.1), geo.SRC_EXIF))
check('the object position is kept apart',
      geo.set_position(store, img, 'object', (48.2, 9.2), geo.SRC_USER))
rec = geo.get_location(store, img)
check('both positions survive',
      rec.get('camera') == [48.1, 9.1] and rec.get('object') == [48.2, 9.2],
      str(rec))
check('the source is remembered', rec.get('object_src') == geo.SRC_USER)
check('the column shows both, one under the other',
      geo.column_text(rec).count('\n') == 1, repr(geo.column_text(rec)))
check('has_any finds it', geo.has_any(store, [img]))
geo.set_position(store, img, 'camera', None)
geo.set_position(store, img, 'object', None)
check('clearing both removes the record', not geo.has_any(store, [img]))
check('an invalid pair is refused',
      not geo.set_position(store, img, 'camera', (91.0, 0.0)))

# ── the table column ─────────────────────────────────────────────────────────
check('the table has a Location column', hasattr(w, 'COL_LOCATION'))
check('Wikitext and Status stayed last',
      w.COL_LOCATION < w.COL_EFFECTIVE < w.COL_STATUS)
check('the header row has as many entries as columns',
      len(w.COLS) == w.table.columnCount(), f'{len(w.COLS)} / {w.table.columnCount()}')

# ── workflow-dependent visibility ────────────────────────────────────────────
# isVisible()/isVisibleTo() answer False for EVERYTHING inside a tab page
# that is not the current one - a trap this project has hit before. What is
# being checked here is whether the widget was hidden ON PURPOSE, and that
# is isHidden().
# The three batch actions moved into their own Location menu (Harald's
# call: as buttons the labels had no room).
_loc_menu_texts = []
for a in w.menuBar().actions():
    if 'Location' in a.text():
        _loc_menu_texts = [x.text() for x in a.menu().actions()
                           if not x.isSeparator()]
check('there is a Location menu', bool(_loc_menu_texts),
      str(_loc_menu_texts))
check('it carries the three actions', len(_loc_menu_texts) == 3)
cb = w.workflow_combo
cb.setCurrentIndex(cb.findData('buildings'))
check('Buildings shows the coordinate rows',
      not w.file_struct._coords_row_widget.isHidden())
if hasattr(w, 'iptc_event_btn'):
    check('Buildings hides the Event transfer', w.iptc_event_btn.isHidden())
cb.setCurrentIndex(cb.findData('portraits'))
check('Portraits hides the coordinate rows',
      w.file_struct._coords_row_widget.isHidden())
if hasattr(w, 'iptc_event_btn'):
    check('Portraits shows the Event transfer',
          not w.iptc_event_btn.isHidden())

# ── the two buttons ──────────────────────────────────────────────────────────
check('reading is offered', hasattr(w, '_location_read_selected'))
check('clearing everything is offered', hasattr(w, '_location_clear_all'))
check('the object coordinate field exists',
      w.file_struct.object_coordinates is not None)
check('the base editor has no object coordinate',
      w.base_struct.object_coordinates is None)
check('object coordinates are a known structured key',
      'object_coordinates' in SD_KEYS)
check('and map to P9149', PROPERTY_MAP.get('object_coordinates') == 'P9149')
check('the camera coordinate still maps to P1259',
      PROPERTY_MAP.get('coordinates') == 'P1259')
check('the workflow is now called Buildings and Landscapes',
      workflows.label_of('buildings') == 'Buildings and Landscapes')
# Clearing asks first; the question is MODAL, so it is answered here.
_asked = []
_real_q = QMessageBox.question
QMessageBox.question = lambda *a, **k: (_asked.append(1), QMessageBox.Yes)[1]
try:
    w._location_clear_all()
    check('an empty list is not worth a question', not _asked)
    w.table.insertRow(0)
    from PyQt5.QtWidgets import QTableWidgetItem
    w.table.setItem(0, w.COL_DESC, QTableWidgetItem('coordinates=48.1, 9.1'))
    w.table.setItem(0, w.COL_LOCATION, QTableWidgetItem('48.1, 9.1'))
    w._location_clear_all()
    check('clearing a filled list asks first', len(_asked) == 1)
    check('and the coordinate is gone afterwards',
          'coordinates=' not in w.table.item(0, w.COL_DESC).text(),
          repr(w.table.item(0, w.COL_DESC).text()))
    check('the Location column follows',
          w.table.item(0, w.COL_LOCATION).text() == '')
finally:
    QMessageBox.question = _real_q

print()
print('FAILURES:', ', '.join(fails) if fails else 'none')
sys.exit(1 if fails else 0)
