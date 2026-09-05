"""Nur die ausgewaehlten Bilder von der Kamera holen (0.18.13).

Harald: "Ich moechte aber von der Kamera nur die ausgewaehlten Bilder
kopieren, wie von der SD-Karte." Bisher fragte "Von Kamera…" nach einem
Ordner und kopierte dann alles.

Neu: die Karte wird erst gelesen, dann zeigt _CameraPickDialog, was drauf
ist - Name, Ordner, Aufnahmezeit, Groesse, je Zeile ein Haken. Keine
Vorschaubilder, mit Absicht: jede Vorschau waere ein Weg ueber das Kabel,
und wie lange das bei 800 Bildern dauert, war hier nicht messbar.

Geprueft wird ohne Kamera und ohne Kabel:

  1. die Tagesgrenze liegt um 4 Uhr, nicht um Mitternacht,
  2. die Tageszaehlung sortiert und zaehlt richtig,
  3. die Kurzfilter treffen die richtigen Dateien,
  4. der Dialog haelt Haken, Zielordner und Zaehlung zusammen,
  5. was schon im Zielordner liegt, ist abgehakt und bleibt es,
  6. der Kopier-Worker nimmt eine fertige Liste und liest die Karte dann
     NICHT noch einmal,
  7. ohne Liste bleibt es beim alten Verhalten (0.18.3),
  8. der Zielordner hat sein eigenes Gedaechtnis, getrennt vom zuletzt
     geoeffneten Ordner.
"""
import os
import sys
import tempfile
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import Cammello        # the shim; also puts the package on the path
from cammello import camera, culling

fails = []


def check(name, cond, detail=''):
    print(('PASS' if cond else 'FAIL'), name, detail)
    if not cond:
        fails.append(name)


check('the shim still exposes the package', hasattr(Cammello, 'main'))


def stamp(y, mo, d, h, mi=0):
    return int(time.mktime((y, mo, d, h, mi, 0, 0, 0, -1)))


# ── 1. and 2. sessions, not calendar days ────────────────────────────────────

late = stamp(2026, 2, 14, 1, 30)      # 01:30, still the gala of the 13th
early = stamp(2026, 2, 14, 9, 0)      # the next morning
check('a frame after midnight belongs to the evening before',
      culling.session_day(late) == '2026-02-13', culling.session_day(late))
check('a frame in the morning belongs to its own day',
      culling.session_day(early) == '2026-02-14', culling.session_day(early))
check('midnight would have split them',
      culling.session_day(late, start_hour=0) == '2026-02-14')
check('no timestamp, no day', culling.session_day(0) == '')

files = [
    camera.CameraFile('/store/DCIM/100EOSR5', 'IMG_0001.CR3', 45_000_000,
                      late),
    camera.CameraFile('/store/DCIM/100EOSR5', 'IMG_0001.JPG', 8_000_000,
                      late),
    camera.CameraFile('/store/DCIM/101EOSR5', 'IMG_0002.CR3', 46_000_000,
                      early),
    camera.CameraFile('/store/DCIM/101EOSR5', 'IMG_0003.CR3', 44_000_000, 0),
]
check('the days come out oldest first, undated last',
      camera.camera_day_counts(files)
      == [('2026-02-13', 2), ('2026-02-14', 1), ('', 1)],
      str(camera.camera_day_counts(files)))


# ── 3. the quick filters ─────────────────────────────────────────────────────

check('RAW only leaves the JPEG behind',
      [f.name for f in camera.filter_files(files, camera.KIND_RAW)]
      == ['IMG_0001.CR3', 'IMG_0002.CR3', 'IMG_0003.CR3'])
check('JPEG only takes the one JPEG',
      [f.name for f in camera.filter_files(files, camera.KIND_JPEG)]
      == ['IMG_0001.JPG'])
check('one day takes the pair of that evening',
      [f.name for f in camera.filter_files(files, day='2026-02-13')]
      == ['IMG_0001.CR3', 'IMG_0001.JPG'])
check('day and kind together',
      [f.name for f in camera.filter_files(files, camera.KIND_RAW,
                                           '2026-02-13')]
      == ['IMG_0001.CR3'])


# ── 4. to 7. the dialog and the worker ───────────────────────────────────────

from PyQt5.QtWidgets import QApplication
from cammello.mw_culling import (_CameraPickDialog, _CameraImportWorker,
                                 _CameraListWorker)

app = QApplication.instance() or QApplication(sys.argv)
dest = tempfile.mkdtemp(prefix='cammello-import-')

dlg = _CameraPickDialog(None, files, dest)
check('every frame is offered', dlg.list.count() == 4)
check('everything starts ticked', len(dlg.selected_files()) == 4)
check('the size of the selection is shown',
      '143' in dlg.status.text() or 'MB' in dlg.status.text()
      or 'GB' in dlg.status.text(), dlg.status.text())

dlg._tick_kind(camera.KIND_RAW)
check('RAW only ticks three',
      [f.name for f in dlg.selected_files()]
      == ['IMG_0001.CR3', 'IMG_0002.CR3', 'IMG_0003.CR3'])

dlg.day_combo.setCurrentIndex(1)          # 2026-02-13
check('picking a day ticks that evening',
      [f.name for f in dlg.selected_files()]
      == ['IMG_0001.CR3', 'IMG_0001.JPG'],
      str([f.name for f in dlg.selected_files()]))
check('but the whole card stays visible', dlg.list.count() == 4)

dlg._tick_none()
check('none means none', dlg.selected_files() == [])
check('and OK is refused with an empty selection',
      not dlg._ok_btn.isEnabled())

# ── 5. what is already in the destination ────────────────────────────────
with open(os.path.join(dest, 'IMG_0001.CR3'), 'wb') as fh:
    fh.write(b'x' * 45_000_000)
dlg._dest_changed(dest)
names = [f.name for f in dlg.selected_files()]
check('a file already in the folder is not offered again',
      'IMG_0001.CR3' not in names, str(names))
dlg._tick_kind(camera.KIND_ALL)
check('and a filter does not tick it back on',
      'IMG_0001.CR3' not in [f.name for f in dlg.selected_files()])
check('the row says why',
      any('already' in dlg.list.item(i).text()
          or 'schon' in dlg.list.item(i).text()
          for i in range(dlg.list.count())))
dlg.deleteLater()


# ── 6. and 7. the worker takes the chosen list ───────────────────────────────

class FakeBackend:
    def __init__(self):
        self.listed = 0
        self.downloaded = []

    def connect(self, device):
        pass

    def list_files(self, progress=None):
        self.listed += 1
        return files

    def download(self, cfile, target):
        self.downloaded.append(cfile.name)
        with open(target, 'wb') as fh:
            fh.write(b'')

    def close(self):
        pass


class FakeLog:
    def info(self, *a, **k):
        pass
    warning = error = info


made = []
real_make = camera.make_backend
camera.make_backend = lambda *a, **k: made[-1]
try:
    dest2 = tempfile.mkdtemp(prefix='cammello-import2-')
    made.append(FakeBackend())
    chosen = [files[0], files[2]]
    worker = _CameraImportWorker(None, dest2, FakeLog(), files=chosen)
    worker.run()
    check('only the chosen frames are fetched',
          made[-1].downloaded == ['IMG_0001.CR3', 'IMG_0002.CR3'],
          str(made[-1].downloaded))
    check('and the card is not walked a second time',
          made[-1].listed == 0, str(made[-1].listed))

    dest3 = tempfile.mkdtemp(prefix='cammello-import3-')
    made.append(FakeBackend())
    worker = _CameraImportWorker(None, dest3, FakeLog())
    worker.run()
    check('without a list it still copies the whole card (0.18.3)',
          made[-1].listed == 1 and len(made[-1].downloaded) == 4,
          str(made[-1].downloaded))

    made.append(FakeBackend())
    lister = _CameraListWorker(None, FakeLog())
    lister.run()
    check('the listing worker reads the card once',
          made[-1].listed == 1 and len(lister.files) == 4)
finally:
    camera.make_backend = real_make


# ── 8. the destination has its own memory ────────────────────────────────────

from cammello.constants import (camera_dest_dir, remember_camera_dest,
                                remembered_dir, remember_dir,
                                CAMERA_DEST_KEY, LAST_DIR_KEY)


class FakeSettings:
    # NOT a dict subclass: an empty dict is falsy, and remember_dir() bails
    # out on a falsy settings object - the fake would have tested nothing.
    def __init__(self):
        self.store = {}

    def value(self, key, default='', type=str):
        return self.store.get(key, default)

    def setValue(self, key, value):
        self.store[key] = value

    def sync(self):
        pass


settings = FakeSettings()
card = tempfile.mkdtemp(prefix='cammello-card-')
remember_dir(settings, card)              # the card just opened
remember_camera_dest(settings, dest)
check('the two folders are stored under different keys',
      settings.store[LAST_DIR_KEY] == card
      and settings.store[CAMERA_DEST_KEY] == dest, str(settings.store))
check('the import does not suggest the card it came from',
      camera_dest_dir(settings) == dest
      and remembered_dir(settings) == card)

print()
print('FAILURES:', ', '.join(fails) if fails else 'none')
sys.exit(1 if fails else 0)
