"""Import straight from a camera whose card the system does not mount
(0.18.3).

Why this exists: Canon bodies (Harald's R5 and R6, and every EOS since the
DSLR days) speak PTP over USB, not USB Mass Storage. The card therefore
never appears as a volume in Finder or as a drive letter in Explorer, and
`culling.scan_folder()` has no path to list. Lightroom does not work on the
card either - it talks PTP and COPIES to disk on import. This module is the
same idea, and it is meant as the BACKUP for a missing card reader, not as
the everyday path: PTP transfer is markedly slower than a CFexpress reader.

Deliberate shape:

  * No Qt in here, like channels.py and edits.py - the planning logic is
    plain-logic testable, and the thread lives in mw_culling.py next to
    _FolderCopyWorker.
  * Everything downstream (pyexiv2, rawpy previews, edits.py, sidecars, F2)
    needs real local paths, so the import COPIES into a folder and the
    culling module then opens that folder. Nothing else in the app learns
    about cameras.
  * Backends are picked per platform. libgphoto2 has never been ported to
    Windows (upstream issue #279), so Windows needs the Windows Portable
    Devices API instead - a separate backend, see WpdBackend below.
  * Nothing in the target folder is ever overwritten. A name that is
    already there with the same size counts as "already imported" and is
    skipped, which is what makes an interrupted import resumable. A name
    that is there with a DIFFERENT size is reported as a conflict and left
    alone (two cards can both hold IMG_0001.CR3).
"""

import logging
import os
import sys
import time
from importlib.util import find_spec

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - dead at runtime, alive in the bytecode
    # 0.12.10 lesson: a purely lazy import is invisible to the frozen-build
    # analyser, and the bundle then ships without the package. `if False:`
    # would not do - CPython folds it away. native_ops.py uses the same
    # trick for pyexiv2.
    import gphoto2
    # The assignment is not decoration: it is what keeps the pyflakes
    # baseline at zero new findings while the import stays in the bytecode.
    _BUNDLER_KEEPS = gphoto2


BACKEND_GPHOTO2 = 'gphoto2'
BACKEND_WPD = 'wpd'

# Extensions worth pulling off a card. Kept in step with culling.py rather
# than duplicated by hand - a second hand-kept list of the same names is
# exactly what went wrong in sdc._ASSIGN_RE.
try:  # pragma: no cover - trivial
    from .culling import (RAW_EXTENSIONS, JPEG_EXTENSIONS,
                          session_day, day_counts)
except ImportError:  # pragma: no cover - direct import in plain tests
    from culling import (RAW_EXTENSIONS, JPEG_EXTENSIONS,
                         session_day, day_counts)

# Sidecars do not exist on a camera card, but a card written by a tethering
# tool may carry them, and audio/video from the same card is worth having.
EXTRA_EXTENSIONS = {'.xmp', '.wav', '.mp4', '.mov', '.crm'}


class CameraError(Exception):
    """Anything the import cannot recover from. The message is shown to the
    user, so it must say what to do, not just what failed."""


class CameraDevice:
    """One camera the backend can see."""

    def __init__(self, name, addr, backend):
        self.name = name
        self.addr = addr          # gphoto2 port ('usb:001,005') or WPD id
        self.backend = backend

    def __repr__(self):
        return f'CameraDevice({self.name!r}, {self.addr!r})'

    def __eq__(self, other):
        return (isinstance(other, CameraDevice)
                and (self.name, self.addr) == (other.name, other.addr))


class CameraFile:
    """One file on the card. `folder` is the camera-side folder
    ('/store_00020001/DCIM/100EOSR5'), never a local path."""

    def __init__(self, folder, name, size=0, mtime=0):
        self.folder = folder
        self.name = name
        self.size = int(size or 0)
        self.mtime = int(mtime or 0)

    @property
    def key(self):
        """Case-insensitive name, the way scan_folder pairs stems."""
        return self.name.casefold()

    def __repr__(self):
        return f'CameraFile({self.folder!r}, {self.name!r}, {self.size})'


# ── Driver libraries inside a frozen bundle (0.18.12) ────────────────────────
#
# What went wrong in 0.18.3: libgphoto2 does not link its drivers, it opens
# them at run time from the directories named in CAMLIBS and IOLIBS.
# gphoto2/__init__.py sets both relative to its own file - BUT ONLY IF THE
# DIRECTORIES EXIST. In the built .app they did not: PyInstaller treats
# every .so as a binary and relocates it, so `--collect-all gphoto2` alone
# does not reproduce gphoto2/libgphoto2/camlibs/ inside the bundle. The
# variables therefore stayed unset, libgphoto2 fell back to the paths
# compiled into the wheel on the build machine, found nothing loadable, and
# answered -4 "Error loading a library".
#
# Two fixes, on purpose: build.yml now copies the three directories in
# explicitly, and this code looks for them at start-up wherever the bundler
# put them. Either one alone would do; together they survive the next
# PyInstaller release changing its layout again.

DRIVER_ENV = ('CAMLIBS', 'IOLIBS')
_DRIVER_SUFFIXES = ('.so', '.dylib')


def _holds_libraries(path):
    """A directory that actually contains loadable driver files."""
    try:
        return any(name.endswith(_DRIVER_SUFFIXES) for name in os.listdir(path))
    except OSError:
        return False


def bundle_roots():
    """Places a frozen build may keep the libgphoto2 tree.

    On macOS PyInstaller splits the bundle into Contents/Frameworks (where
    _MEIPASS points) and Contents/Resources, and which of the two holds a
    real file rather than a symlink has changed between releases. Both are
    checked, plus the plain directory next to the executable for Linux.
    """
    roots = []
    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        roots.append(meipass)
        contents = os.path.dirname(meipass)
        for sibling in ('Resources', 'Frameworks'):
            roots.append(os.path.join(contents, sibling))
    try:
        roots.append(os.path.dirname(os.path.abspath(sys.executable)))
    except (OSError, TypeError):        # pragma: no cover - defensive
        pass
    seen = []
    for root in roots:
        if root and root not in seen:
            seen.append(root)
    return seen


def find_driver_dirs(roots=None):
    """Locate {'CAMLIBS': …, 'IOLIBS': …} in a bundle, as far as they exist.

    Layout first, search second: the expected relative paths are tried
    directly, and only if that fails does it walk the bundle (shallow, and
    only for the two directory names) - a full walk of a 400 MB bundle at
    every start would be a poor trade.
    """
    wanted_dirs = {'CAMLIBS': 'camlibs', 'IOLIBS': 'iolibs'}
    found = {}
    roots = bundle_roots() if roots is None else list(roots)
    for root in roots:
        for key, leaf in wanted_dirs.items():
            if key in found:
                continue
            for middle in (os.path.join('gphoto2', 'libgphoto2'),
                           'libgphoto2', ''):
                candidate = os.path.join(root, middle, leaf)
                if os.path.isdir(candidate) and _holds_libraries(candidate):
                    found[key] = candidate
                    break
    if len(found) == len(wanted_dirs):
        return found
    for root in roots:
        for base, dirs, _files in os.walk(root):
            if base[len(root):].count(os.sep) > 4:
                dirs[:] = []
                continue
            for key, leaf in wanted_dirs.items():
                if key in found or leaf not in dirs:
                    continue
                candidate = os.path.join(base, leaf)
                if _holds_libraries(candidate):
                    found[key] = candidate
            if len(found) == len(wanted_dirs):
                return found
    return found


def prepare_driver_env(force=False):
    """Point libgphoto2 at the bundled drivers. Returns what was set.

    A value already in the environment is left alone when it names a usable
    directory - a system install or a developer's venv must keep winning
    over anything guessed here.
    """
    settled = {}
    for key in DRIVER_ENV:
        current = os.environ.get(key)
        if not force and current and os.path.isdir(current) \
                and _holds_libraries(current):
            settled[key] = current
    if len(settled) == len(DRIVER_ENV):
        return {}
    if not getattr(sys, 'frozen', False) and not force:
        return {}
    changed = {}
    for key, path in find_driver_dirs().items():
        if key in settled:
            continue
        os.environ[key] = path
        changed[key] = path
    if changed:
        logging.getLogger('Cammello').info(
            'Camera drivers found in the bundle: %s',
            ', '.join(f'{k}={v}' for k, v in sorted(changed.items())))
    return changed


def driver_report():
    """One line per driver directory, for the log and for bug reports."""
    lines = []
    for key in DRIVER_ENV:
        path = os.environ.get(key)
        if not path:
            lines.append(f'{key}: not set')
        elif not os.path.isdir(path):
            lines.append(f'{key}: {path} (missing)')
        else:
            try:
                libs = [n for n in os.listdir(path)
                        if n.endswith(_DRIVER_SUFFIXES)]
            except OSError as exc:
                lines.append(f'{key}: {path} (unreadable: {exc})')
                continue
            note = ''
            if key == 'CAMLIBS':
                has_ptp = any(n.startswith('ptp2.') for n in libs)
                note = ', ptp2 present' if has_ptp else ', PTP2 MISSING'
            lines.append(f'{key}: {path} ({len(libs)} libraries{note})')
    return lines


# The message a user sees for gphoto2 error -4. English on purpose - the
# caller translates it, and it is a table key, so it must stay one literal.
DRIVER_LOAD_FAILED = (
    'The camera drivers could not be loaded. On macOS this is usually the '
    'quarantine flag on a downloaded app; a Terminal command clears it: '
    'xattr -dr com.apple.quarantine /Applications/Cammello.app - then start '
    'Cammello again. A card reader works in the meantime.')


# Prepared at import time so it happens before anything imports gphoto2:
# the package reads CAMLIBS/IOLIBS while it is being imported, and setting
# them afterwards would be too late.
prepare_driver_env()


# ── Backend availability ─────────────────────────────────────────────────────

def platform_backend():
    """Which backend this operating system needs. Windows gets WPD because
    libgphoto2 does not exist there; everything else gets gphoto2."""
    return BACKEND_WPD if sys.platform.startswith('win') else BACKEND_GPHOTO2


def backend_available(name=None):
    name = name or platform_backend()
    if name == BACKEND_GPHOTO2:
        return find_spec('gphoto2') is not None
    return False


def backend_problem(name=None):
    """One sentence saying why the import cannot run, or None when it can.
    English on purpose - the caller translates."""
    name = name or platform_backend()
    if name == BACKEND_WPD:
        return ('Importing straight from a camera is not available on '
                'Windows yet. Use a card reader for now.')
    if not backend_available(name):
        return ('The gphoto2 module is missing, so no camera can be '
                'reached. Install it with: pip install gphoto2')
    return None


def make_backend(name=None):
    name = name or platform_backend()
    problem = backend_problem(name)
    if problem:
        raise CameraError(problem)
    return GPhoto2Backend()


# ── Planning (pure, and the part the tests actually exercise) ────────────────

def wanted(name):
    """Is this a file worth importing? Directories and the camera's own
    bookkeeping files are not."""
    ext = os.path.splitext(name)[1].lower()
    return (ext in RAW_EXTENSIONS or ext in JPEG_EXTENSIONS
            or ext in EXTRA_EXTENSIONS)


KIND_ALL, KIND_RAW, KIND_JPEG = 'all', 'raw', 'jpeg'


def kind_of(name):
    """'raw', 'jpeg' or 'other' for one file name."""
    ext = os.path.splitext(name)[1].lower()
    if ext in RAW_EXTENSIONS:
        return KIND_RAW
    if ext in JPEG_EXTENSIONS:
        return KIND_JPEG
    return 'other'


def filter_files(files, kind=KIND_ALL, day=None):
    """The subset a quick filter in the picker should tick.

    `day` is a session day as culling.session_day() spells it, or None for
    every day. Kept out of the dialog so it can be tested without Qt, and
    so the card-side day filter can use the same two helpers later.
    """
    out = []
    for f in files:
        if kind != KIND_ALL and kind_of(f.name) != kind:
            continue
        if day is not None and session_day(f.mtime) != day:
            continue
        out.append(f)
    return out


def camera_day_counts(files):
    """[(day, count)] for the files on the card, oldest first."""
    return day_counts(files, lambda f: f.mtime)


def scan_dest(dest):
    """{casefolded name: size} of what the target folder already holds. Only
    names and sizes, no file is opened."""
    out = {}
    try:
        with os.scandir(dest) as it:
            for entry in it:
                if entry.is_file():
                    try:
                        out[entry.name.casefold()] = entry.stat().st_size
                    except OSError:
                        out[entry.name.casefold()] = -1
    except OSError:
        return {}
    return out


def plan_import(files, existing):
    """Split the card contents into (todo, skipped, conflicts).

    `existing` is what scan_dest() returned. Same name and same size means
    the file is already here - that is what makes a cancelled import
    resumable without a journal. Same name but a different size is a
    genuine clash (a second card with the same running numbers), and
    because nothing is ever overwritten it is reported instead of renamed.
    """
    todo, skipped, conflicts = [], [], []
    for f in files:
        if f.key not in existing:
            todo.append(f)
        elif existing[f.key] == f.size and f.size > 0:
            skipped.append(f)
        else:
            conflicts.append(f)
    return todo, skipped, conflicts


def total_bytes(files):
    return sum(f.size for f in files)


def format_size(num):
    """Short human-readable size. Deliberately plain: it goes into a
    progress line, not into a report."""
    num = float(num or 0)
    for unit in ('B', 'KB', 'MB', 'GB'):
        if num < 1024 or unit == 'GB':
            return f'{num:.0f} {unit}' if unit == 'B' else f'{num:.1f} {unit}'
        num /= 1024
    return f'{num:.1f} GB'


def part_path(target):
    """Downloads land here first and are renamed on success, so a cancelled
    transfer can never leave a short file that the next run would mistake
    for an already imported one."""
    return target + '.part'


# ── gphoto2 backend (macOS, Linux) ───────────────────────────────────────────

class GPhoto2Backend:
    """Thin wrapper around python-gphoto2. Every name used here was checked
    against gphoto2 2.6.4 rather than remembered."""

    name = BACKEND_GPHOTO2

    def __init__(self):
        import gphoto2 as gp
        self._gp = gp
        self._camera = None
        for line in driver_report():
            logging.getLogger('Cammello').info('Camera driver path: %s', line)

    def _fail(self, exc):
        """Turn a gphoto2 error into something a photographer can act on.

        0.18.12: -4 used to escape unwrapped and reach the user as the bare
        string "[-4] Error loading a library", which says nothing about what
        to do. Every gphoto2 call in this class goes through here now.
        """
        gp = self._gp
        if exc.code == gp.GP_ERROR_LIBRARY:
            logging.getLogger('Cammello').error(
                'gphoto2 cannot load its drivers (-4). %s',
                '; '.join(driver_report()))
            return CameraError(DRIVER_LOAD_FAILED)
        if exc.code == gp.GP_ERROR_MODEL_NOT_FOUND:
            return CameraError(
                'No camera answered. Switch it on, connect the USB '
                'cable, and close any other program that may be '
                'holding the camera.')
        return CameraError(f'The camera could not be opened: {exc.string}')

    def list_devices(self):
        gp = self._gp
        out = []
        try:
            found = gp.Camera.autodetect()
        except gp.GPhoto2Error as exc:
            raise self._fail(exc) from exc
        for i in range(found.count()):
            out.append(CameraDevice(found.get_name(i), found.get_value(i),
                                    self.name))
        return out

    def connect(self, device=None):
        gp = self._gp
        camera = gp.Camera()
        try:
            if device is not None and device.addr:
                # Bind to one specific port; without this init() simply
                # takes the first camera, which is wrong with two bodies
                # attached. Inside the try since 0.18.12: loading the port
                # list is itself a library load and can fail with -4.
                port_info_list = gp.PortInfoList()
                port_info_list.load()
                idx = port_info_list.lookup_path(device.addr)
                camera.set_port_info(port_info_list.get_info(idx))
            camera.init()
        except gp.GPhoto2Error as exc:
            raise self._fail(exc) from exc
        self._camera = camera

    def list_files(self, progress=None):
        """Walk the camera's folders. Recursive on purpose: DCIM holds one
        folder per hundred frames, and a card can carry several."""
        if self._camera is None:
            raise CameraError('The camera is not open.')
        files = []
        self._walk('/', files, progress)
        files.sort(key=lambda f: (f.folder, f.name))
        return files

    def _walk(self, folder, out, progress):
        gp = self._gp
        camera = self._camera
        try:
            names = camera.folder_list_files(folder)
        except gp.GPhoto2Error:
            names = None
        if names is not None:
            for i in range(names.count()):
                name = names.get_name(i)
                if not wanted(name):
                    continue
                size = mtime = 0
                try:
                    info = camera.file_get_info(folder, name)
                    size = info.file.size
                    mtime = info.file.mtime
                except gp.GPhoto2Error:
                    pass
                out.append(CameraFile(folder, name, size, mtime))
                if progress is not None:
                    progress(len(out))
        try:
            subs = camera.folder_list_folders(folder)
        except gp.GPhoto2Error:
            return
        for i in range(subs.count()):
            sub = subs.get_name(i)
            self._walk(folder.rstrip('/') + '/' + sub, out, progress)

    def download(self, cfile, target):
        """Fetch one file. Writes to <target>.part and renames, so an
        interrupted run leaves nothing that looks complete."""
        gp = self._gp
        tmp = part_path(target)
        try:
            camera_file = self._camera.file_get(
                cfile.folder, cfile.name, gp.GP_FILE_TYPE_NORMAL)
            camera_file.save(tmp)
        except gp.GPhoto2Error as exc:
            _quiet_remove(tmp)
            raise CameraError(exc.string) from exc
        except Exception:
            _quiet_remove(tmp)
            raise
        os.replace(tmp, target)
        if cfile.mtime:
            try:
                os.utime(target, (time.time(), cfile.mtime))
            except OSError:
                pass
        return target

    def close(self):
        if self._camera is not None:
            try:
                self._camera.exit()
            except Exception:
                pass
            self._camera = None


class WpdBackend:
    """Placeholder for Windows Portable Devices.

    Not built yet, and deliberately not guessed: the WPD property keys are
    GUID+PID pairs, and writing them from memory is how you ship code that
    cannot work. Harald runs the probe script from notes_0183.md on the
    Windows machine, and the backend gets written against what it prints.
    """

    name = BACKEND_WPD

    def __init__(self):
        raise CameraError(backend_problem(BACKEND_WPD))


def _quiet_remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def summary_text(copied, skipped, failed, conflicts, cancelled=False):
    """One line for the status bar and the closing message box."""
    bits = [f'{copied} copied']
    if skipped:
        bits.append(f'{skipped} already there')
    if conflicts:
        bits.append(f'{conflicts} name clash(es) left alone')
    if failed:
        bits.append(f'{failed} failed')
    if cancelled:
        bits.append('cancelled')
    return ', '.join(bits) + '.'


# ── Removable volumes (0.18.7) ───────────────────────────────────────────────
#
# Harald: "hätte ich gerne das neu eingesteckte SD Karte sofort geöffnet
# wird". This half is about a card in a READER, which the system does mount
# as a volume - the opposite of the PTP case above, and the reason the two
# live in the same module: both answer "there is a card, get at it".

#: A card is recognised by this folder, not by its size or its name. Every
#: camera writes it (DCF standard), and a random USB stick does not.
DCIM = 'DCIM'


def volume_roots():
    """Directories under which the system mounts removable media."""
    if sys.platform == 'darwin':
        return ['/Volumes']
    if sys.platform.startswith('win'):
        return []                  # drive letters, handled in list_volumes()
    roots = ['/media', '/run/media']
    user = os.environ.get('USER') or ''
    if user:
        roots += [f'/media/{user}', f'/run/media/{user}']
    return roots


def list_volumes():
    """Every mounted volume that could hold a card, as a set of paths.

    Names only - nothing is opened, so this is cheap enough to call on a
    timer.
    """
    out = set()
    if sys.platform.startswith('win'):
        for letter in 'DEFGHIJKLMNOPQRSTUVWXYZ':
            path = f'{letter}:\\'
            if os.path.isdir(path):
                out.add(path)
        return out
    for root in volume_roots():
        try:
            with os.scandir(root) as it:
                for entry in it:
                    if entry.is_dir() and not entry.name.startswith('.'):
                        out.add(entry.path)
        except OSError:
            continue
    return out


def card_folder(volume):
    """The folder to open for a freshly mounted volume, or None.

    A DCIM folder is the whole test. Returning DCIM rather than the volume
    root keeps the scan away from the card's own bookkeeping folders, and
    the caller walks it recursively because a full card holds 100EOSR5,
    101EOSR5 and so on.
    """
    try:
        with os.scandir(volume) as it:
            for entry in it:
                if entry.is_dir() and entry.name.upper() == DCIM:
                    return entry.path
    except OSError:
        return None
    return None


def card_scope(folder):
    """The whole card a folder belongs to, or None (0.18.10).

    Harald: "ich möchte die Ordner einer Karte zusammen angezeigt bekommen."
    A card splits one shoot across 100EOSR5, 101EOSR5 and so on - that is
    the camera's file-numbering housekeeping, not the photographer's idea of
    an order, so opening one of them should bring the others along.

    Returns the DCIM folder when `folder` is DCIM itself, sits inside one,
    or contains one; None for an ordinary working folder, which must be left
    exactly as it is.
    """
    if not folder:
        return None
    inside = card_folder(folder)          # folder IS the card root
    if inside:
        return inside
    path = os.path.abspath(folder)
    while True:
        parent, name = os.path.split(path)
        if not name or parent == path:
            return None
        if name.upper() == DCIM:
            return path
        path = parent


def new_cards(previous, current):
    """Card folders on volumes that appeared between two polls.

    Sorted, so two cards inserted at once are handled in a defined order,
    and a volume that was already there when Cammello started is never
    reported - the caller seeds `previous` at startup.
    """
    found = []
    for volume in sorted(current - previous):
        folder = card_folder(volume)
        if folder:
            found.append(folder)
    return found
