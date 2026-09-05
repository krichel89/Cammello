"""Die Kameratreiber im gebauten Paket (0.18.12).

Harald: "keine treiber im Bundle" - die gebaute App meldete beim Zugriff
auf die Karte "[-4] Fehler beim Laden einer Bibliothek".

Was dahintersteckt: libgphoto2 bindet seine Treiber nicht ein, es oeffnet
sie zur Laufzeit aus den Verzeichnissen in CAMLIBS und IOLIBS.
gphoto2/__init__.py setzt beide relativ zu sich selbst, ABER NUR WENN DIE
VERZEICHNISSE EXISTIEREN (im Wheel nachgelesen, nicht erinnert). Im
.app-Paket existierten sie nicht: PyInstaller haelt jede .so fuer ein
Binary und verschiebt sie aus dem Paketbaum. Also blieben die Variablen
leer, libgphoto2 suchte an den einkompilierten Pfaden des Wheel-Bauers und
antwortete -4.

Verteidigt wird hier, was ohne Kamera und ohne macOS pruefbar ist:

  1. find_driver_dirs() findet den Baum an der erwarteten Stelle,
  2. auch dann, wenn der Bundler ihn woanders hingelegt hat,
  3. ein leeres Verzeichnis gilt nicht als Treiberverzeichnis,
  4. prepare_driver_env() setzt die Variablen und laesst eine gueltige
     Vorgabe aus der Umgebung in Ruhe,
  5. das Setzen passiert beim Import des Moduls, nicht spaeter - sonst
     liest gphoto2 die Variablen zu frueh,
  6. driver_report() sagt, ob ptp2 da ist (der Treiber fuer die Canons),
  7. Fehler -4 wird zu einem Satz, der sagt, was zu tun ist, statt zu
     "[-4] Error loading a library",
  8. dieser Satz steht in allen fuenf Sprachen in der Tabelle,
  9. build.yml legt die Verzeichnisse ausdruecklich ins Paket und bricht
     ab, wenn ptp2 danach fehlt.
"""
import ast
import os
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import Cammello        # the shim; also puts the package on the path
from cammello import camera

fails = []


def check(name, cond, detail=''):
    print(('PASS' if cond else 'FAIL'), name, detail)
    if not cond:
        fails.append(name)


def make_tree(root, middle, leaf, files=('ptp2.so', 'canon.so')):
    path = os.path.join(root, *middle, leaf) if middle else \
        os.path.join(root, leaf)
    os.makedirs(path, exist_ok=True)
    for name in files:
        open(os.path.join(path, name), 'w').close()
    return path


check('the shim still exposes the package', hasattr(Cammello, 'main'))

tmp = tempfile.mkdtemp(prefix='cammello-driver-')


# ── 1. the expected layout ───────────────────────────────────────────────────

root = os.path.join(tmp, 'bundle')
cam_dir = make_tree(root, ('gphoto2', 'libgphoto2'), 'camlibs')
io_dir = make_tree(root, ('gphoto2', 'libgphoto2'), 'iolibs',
                   ('libusb1.so',))
found = camera.find_driver_dirs([root])
check('camlibs found where the package expects it',
      found.get('CAMLIBS') == cam_dir, found.get('CAMLIBS', ''))
check('iolibs found where the package expects it',
      found.get('IOLIBS') == io_dir, found.get('IOLIBS', ''))


# ── 2. and wherever the bundler happened to put it ───────────────────────────

odd = os.path.join(tmp, 'odd')
odd_cam = make_tree(odd, ('Contents', 'Resources', 'libgphoto2'), 'camlibs')
odd_io = make_tree(odd, ('Contents', 'Resources', 'libgphoto2'), 'iolibs',
                   ('libusb1.so',))
found = camera.find_driver_dirs([odd])
check('a relocated tree is still found',
      found.get('CAMLIBS') == odd_cam and found.get('IOLIBS') == odd_io,
      str(found))


# ── 3. an empty directory is not a driver directory ──────────────────────────

hollow = os.path.join(tmp, 'hollow')
os.makedirs(os.path.join(hollow, 'gphoto2', 'libgphoto2', 'camlibs'))
os.makedirs(os.path.join(hollow, 'gphoto2', 'libgphoto2', 'iolibs'))
check('an empty camlibs directory is refused',
      camera.find_driver_dirs([hollow]) == {})


# ── 4. what lands in the environment ─────────────────────────────────────────

keep = {k: os.environ.get(k) for k in camera.DRIVER_ENV}
try:
    for key in camera.DRIVER_ENV:
        os.environ.pop(key, None)
    frozen_before = getattr(sys, 'frozen', False)
    sys.frozen = True                     # pretend to be the built app
    sys._MEIPASS = root
    changed = camera.prepare_driver_env()
    check('CAMLIBS is set for the frozen app',
          os.environ.get('CAMLIBS') == cam_dir, os.environ.get('CAMLIBS', ''))
    check('IOLIBS is set for the frozen app',
          os.environ.get('IOLIBS') == io_dir, os.environ.get('IOLIBS', ''))
    check('the change is reported back', set(changed) == {'CAMLIBS', 'IOLIBS'})

    # A usable value already in the environment wins - a system install or
    # Harald's venv must not be overruled by anything guessed here.
    system_cam = make_tree(tmp, ('system',), 'camlibs')
    system_io = make_tree(tmp, ('system',), 'iolibs', ('libusb1.so',))
    os.environ['CAMLIBS'] = system_cam
    os.environ['IOLIBS'] = system_io
    camera.prepare_driver_env()
    check('an existing usable CAMLIBS is left alone',
          os.environ.get('CAMLIBS') == system_cam)

    # A value pointing nowhere is not usable, so it gets replaced.
    os.environ['CAMLIBS'] = os.path.join(tmp, 'gone')
    os.environ['IOLIBS'] = os.path.join(tmp, 'gone-too')
    camera.prepare_driver_env()
    check('a dangling CAMLIBS is replaced',
          os.environ.get('CAMLIBS') == cam_dir, os.environ.get('CAMLIBS', ''))

    # ── 6. the report ────────────────────────────────────────────────────
    report = camera.driver_report()
    check('the report names ptp2 as present',
          any('ptp2 present' in line for line in report), str(report))
    os.environ['CAMLIBS'] = make_tree(tmp, ('noptp',), 'camlibs',
                                      ('canon.so',))
    check('the report shouts when ptp2 is missing',
          any('PTP2 MISSING' in line for line in camera.driver_report()))
finally:
    for key, value in keep.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    if not frozen_before:
        del sys.frozen
    if hasattr(sys, '_MEIPASS'):
        del sys._MEIPASS


# ── 5. the call sits at import time, before gphoto2 is imported ──────────────

src = open(os.path.join(os.path.dirname(camera.__file__), 'camera.py'),
           encoding='utf-8').read()
tree = ast.parse(src)
top_level_calls = [n.value.func.id for n in tree.body
                   if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
                   and isinstance(n.value.func, ast.Name)]
check('prepare_driver_env runs at import time',
      'prepare_driver_env' in top_level_calls, str(top_level_calls))
prepare_line = src.index('prepare_driver_env()\n\n\n# \u2500\u2500 Backend')
gp_import_line = src.index('import gphoto2 as gp')
check('and before the first real gphoto2 import',
      prepare_line < gp_import_line)


# ── 7. error -4 becomes an instruction ───────────────────────────────────────

class FakeError(Exception):
    def __init__(self, code, string):
        Exception.__init__(self, '[%d] %s' % (code, string))
        self.code = code
        self.string = string


class FakeGp:
    """Only the names the backend touches. The real values were read off
    gphoto2 2.6.4, not remembered: GP_ERROR_LIBRARY is -4."""
    GPhoto2Error = FakeError
    GP_ERROR_LIBRARY = -4
    GP_ERROR_MODEL_NOT_FOUND = -105

    class Camera:
        @staticmethod
        def autodetect():
            raise FakeError(-4, 'Error loading a library')


backend = camera.GPhoto2Backend.__new__(camera.GPhoto2Backend)
backend._gp = FakeGp
backend._camera = None

translated = backend._fail(FakeError(-4, 'Error loading a library'))
check('minus four becomes the driver message',
      isinstance(translated, camera.CameraError)
      and str(translated) == camera.DRIVER_LOAD_FAILED, str(translated)[:60])
check('the driver message says how to clear the quarantine flag',
      'com.apple.quarantine' in camera.DRIVER_LOAD_FAILED)
check('minus 105 still says the camera did not answer',
      'No camera answered' in str(backend._fail(FakeError(-105, 'x'))))

raised = None
try:
    backend.list_devices()
except camera.CameraError as exc:
    raised = exc
except Exception as exc:                                  # pragma: no cover
    raised = exc
check('list_devices no longer leaks the raw gphoto2 error',
      isinstance(raised, camera.CameraError), repr(raised)[:70])
check('and it leaks no bracketed error code either',
      raised is not None and '[-4]' not in str(raised))

# connect() used to build the port list OUTSIDE the try - that is how the
# bare string reached the dialog. The whole body is guarded now.
connect_src = src[src.index('    def connect(self, device=None):'):]
connect_src = connect_src[:connect_src.index('\n    def ')]
check('the port list is built inside the try in connect()',
      connect_src.index('try:') < connect_src.index('PortInfoList()'))


# ── 8. five languages ────────────────────────────────────────────────────────

from cammello.i18n import TRANSLATIONS
entry = TRANSLATIONS.get(camera.DRIVER_LOAD_FAILED)
check('the driver message is a translation key', entry is not None)
check('in all five languages',
      bool(entry) and set(entry) == {'de', 'es', 'fr', 'it'}
      and all(entry.values()), sorted(entry or {}))


# ── 9. the build carries the drivers and checks that it did ──────────────────

here = os.path.dirname(os.path.abspath(__file__))
build_path = os.path.join(here, '.github', 'workflows', 'build.yml')
if os.path.isfile(build_path):
    build = open(build_path, encoding='utf-8').read()
    check('build.yml adds camlibs to the bundle',
          'gphoto2/libgphoto2/$sub' in build)
    check('build.yml collects camlibs, iolibs and locale',
          'for sub in camlibs iolibs locale' in build)
    check('build.yml fails the build when ptp2 is missing',
          "name 'ptp2.so'" in build and 'exit 1' in build)
else:                                            # pragma: no cover
    print('SKIP build.yml checks - not in this tree')

print()
print('FAILURES:', ', '.join(fails) if fails else 'none')
sys.exit(1 if fails else 0)
