"""Vorschaubilder von der Kamera, und Fehler -53 (0.18.17).

Harald: "Ich brauche die Vorschaubilder, auch wenn es sehr langsam ist."
Und, vom Mac: "Konnte das USB-Gerät nicht beanspruchen."

Beides haengt zusammen: PTP erlaubt EINE Sitzung. Die Vorschauen halten
die Verbindung, solange das Auswahlfenster offen ist, also muss sie weg
sein, bevor kopiert wird - sonst ist der zweite Verbindungsversuch genau
der Fehler -53, ueber den Harald gestolpert ist.

Geprueft wird ohne Kamera, mit einer Attrappe:

  1. preview() holt die eingebettete Vorschau, nicht das ganze Bild,
  2. eine fehlende Vorschau ist leer, kein Fehler,
  3. der Worker holt SICHTBARE Zeilen zuerst,
  4. er holt keine Zeile zweimal,
  5. eine kaputte Vorschau haelt den Lauf nicht auf,
  6. stop() beendet ihn und schliesst die Verbindung,
  7. -53 wird EINMAL wiederholt und dann uebersetzt,
  8. die Uebersetzung nennt den killall-Befehl, in fuenf Sprachen.
"""
import os
import sys
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import Cammello        # the shim; also puts the package on the path
from cammello import camera

fails = []


def check(name, cond, detail=''):
    print(('PASS' if cond else 'FAIL'), name, detail)
    if not cond:
        fails.append(name)


check('the shim still exposes the package', hasattr(Cammello, 'main'))


# ── a stand-in for the gphoto2 module ────────────────────────────────────────

class FakeError(Exception):
    def __init__(self, code, string='x'):
        Exception.__init__(self, '[%d] %s' % (code, string))
        self.code = code
        self.string = string


class FakeCameraFile:
    def __init__(self, data):
        self._data = data

    def get_data_and_size(self):
        return memoryview(self._data)


class FakeCam:
    """Records what type was asked for, so PREVIEW vs NORMAL is provable."""

    def __init__(self, previews=None, fail_codes=None):
        self.asked = []
        self.previews = previews or {}
        self.fail_codes = fail_codes or {}
        self.exited = 0

    def file_get(self, folder, name, ftype):
        self.asked.append((name, ftype))
        if name in self.fail_codes:
            raise FakeError(self.fail_codes[name])
        return FakeCameraFile(self.previews.get(name, b'JPEGDATA'))

    def exit(self):
        self.exited += 1


class FakeGp:
    GPhoto2Error = FakeError
    GP_FILE_TYPE_PREVIEW = 0
    GP_FILE_TYPE_NORMAL = 1
    GP_ERROR_LIBRARY = -4
    GP_ERROR_MODEL_NOT_FOUND = -105
    GP_ERROR_IO_USB_CLAIM = -53
    GP_ERROR_NOT_SUPPORTED = -6
    GP_ERROR_FILE_NOT_FOUND = -108


def make_backend(cam):
    backend = camera.GPhoto2Backend.__new__(camera.GPhoto2Backend)
    backend._gp = FakeGp
    backend._camera = cam
    backend._last_code = 0
    return backend


files = [camera.CameraFile('/store/DCIM/100EOSR5', f'IMG_{i:04d}.CR3',
                           45_000_000, 1771000000 + i)
         for i in range(6)]

cam = FakeCam()
backend = make_backend(cam)
data = backend.preview(files[0])
check('the preview is fetched', data == b'JPEGDATA', str(data))
check('and it asks for the PREVIEW, not the whole raw',
      cam.asked == [('IMG_0000.CR3', FakeGp.GP_FILE_TYPE_PREVIEW)],
      str(cam.asked))

cam2 = FakeCam(fail_codes={'IMG_0001.CR3': FakeGp.GP_ERROR_NOT_SUPPORTED})
check('a camera without a preview gives nothing, not an error',
      make_backend(cam2).preview(files[1]) == b'')

cam3 = FakeCam(fail_codes={'IMG_0002.CR3': FakeGp.GP_ERROR_IO_USB_CLAIM})
raised = None
try:
    make_backend(cam3).preview(files[2])
except camera.CameraError as exc:
    raised = exc
check('a real error still comes through translated',
      raised is not None and str(raised) == camera.USB_CLAIMED,
      str(raised)[:50])


# ── 7. the retry on -53 ──────────────────────────────────────────────────────

class ClaimingGp(FakeGp):
    """Busy on the first init, free on the second - the macOS helper."""
    tries = 0

    class Camera:
        def __init__(self):
            pass

        def init(self):
            ClaimingGp.tries += 1
            if ClaimingGp.tries == 1:
                raise FakeError(-53, 'Could not claim the USB device')


backend = camera.GPhoto2Backend.__new__(camera.GPhoto2Backend)
backend._gp = ClaimingGp
backend._camera = None
backend._last_code = 0
saved_wait = camera.CLAIM_RETRY_WAIT
camera.CLAIM_RETRY_WAIT = 0.01
t0 = time.monotonic()
backend.connect(None)
camera.CLAIM_RETRY_WAIT = saved_wait
check('a busy camera is tried a second time', ClaimingGp.tries == 2,
      str(ClaimingGp.tries))
check('and then it is open', backend._camera is not None)


class AlwaysClaimed(FakeGp):
    class Camera:
        def init(self):
            raise FakeError(-53, 'Could not claim the USB device')


backend = camera.GPhoto2Backend.__new__(camera.GPhoto2Backend)
backend._gp = AlwaysClaimed
backend._camera = None
backend._last_code = 0
camera.CLAIM_RETRY_WAIT = 0.01
raised = None
try:
    backend.connect(None)
except camera.CameraError as exc:
    raised = exc
camera.CLAIM_RETRY_WAIT = saved_wait
check('a camera that stays busy is explained, not dumped raw',
      raised is not None and str(raised) == camera.USB_CLAIMED)
check('and the explanation says what to do',
      'killall ptpcamerad' in camera.USB_CLAIMED
      and 'Lightroom' in camera.USB_CLAIMED)

from cammello.i18n import TRANSLATIONS
entry = TRANSLATIONS.get(camera.USB_CLAIMED)
check('in five languages', bool(entry) and set(entry) == {'de', 'es', 'fr',
                                                          'it'})
check('and the command survives translation',
      all('killall ptpcamerad' in v for v in (entry or {}).values()))


# ── 3. to 6. the worker ──────────────────────────────────────────────────────

from PyQt5.QtWidgets import QApplication
from cammello.mw_culling import _CameraThumbWorker

app = QApplication.instance() or QApplication(sys.argv)


class FakeLog:
    def info(self, *a, **k):
        pass
    warning = error = info


class RecordingBackend:
    def __init__(self, bad=()):
        self.order = []
        self.closed = 0
        self.bad = set(bad)

    def connect(self, device):
        pass

    def preview(self, cfile):
        self.order.append(cfile.name)
        if cfile.name in self.bad:
            raise camera.CameraError('no preview')
        return b'JPEGDATA'

    def close(self):
        self.closed += 1


many = [camera.CameraFile('/store', f'IMG_{i:04d}.CR3', 1000, 0)
        for i in range(20)]
rec = RecordingBackend(bad={'IMG_0000.CR3'})
saved_make = camera.make_backend
camera.make_backend = lambda *a, **k: rec
try:
    worker = _CameraThumbWorker(None, many, FakeLog())
    got = []
    worker.thumb.connect(lambda i, d: got.append(i))
    worker.want([10, 11, 12])          # "these are on screen"
    worker.run()                        # in this thread, deterministically
finally:
    camera.make_backend = saved_make

check('the rows on screen are fetched first',
      rec.order[:3] == ['IMG_0010.CR3', 'IMG_0011.CR3', 'IMG_0012.CR3'],
      str(rec.order[:4]))
check('and the rest follows', len(rec.order) == 20)
check('nothing is fetched twice', len(set(rec.order)) == 20)
check('a failed preview does not stop the run',
      len(got) == 19 and 0 not in got, str(len(got)))
check('the connection is closed at the end', rec.closed == 1)

rec2 = RecordingBackend()
camera.make_backend = lambda *a, **k: rec2
try:
    worker = _CameraThumbWorker(None, many, FakeLog())
    worker.stop()                       # stopped before it starts
    worker.run()
finally:
    camera.make_backend = saved_make
check('stop() means no fetching at all', rec2.order == [])
check('but the connection is closed even then', rec2.closed == 1)

print()
print('FAILURES:', ', '.join(fails) if fails else 'none')
sys.exit(1 if fails else 0)
