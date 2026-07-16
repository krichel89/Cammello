"""Logging setup (file + in-app log tab + console), with credential masking."""
import faulthandler
import os
import logging
import tempfile
from logging.handlers import RotatingFileHandler
from datetime import datetime
from PyQt5.QtCore import QObject, pyqtSignal
from .constants import APP_NAME, __version__


def get_log_path():
    """Return a writable path for the log file."""
    base = os.path.join(os.path.expanduser('~'), APP_NAME)
    try:
        os.makedirs(base, exist_ok=True)
        return os.path.join(base, 'cammello_debug.log')
    except Exception:
        return os.path.join(tempfile.gettempdir(), 'cammello_debug.log')


# faulthandler needs its file object to stay alive for the whole run; a
# module-level reference keeps it from being garbage-collected.
_CRASH_LOG_FILE = None


def _enable_faulthandler(log_path):
    """Write native crash tracebacks (segfaults etc.) next to the log file.

    Python logging cannot catch crashes inside native libraries (pyexiv2,
    rawpy, Qt) - the process just dies and the debug log ends mid-line.
    faulthandler dumps the Python-level stack of every thread into
    cammello_crash.log at the moment of the crash, which is usually enough
    to see WHICH call went down. Returns the crash log path or None.
    """
    global _CRASH_LOG_FILE
    try:
        path = os.path.join(os.path.dirname(log_path), 'cammello_crash.log')
        _CRASH_LOG_FILE = open(path, 'a', encoding='utf-8')
        _CRASH_LOG_FILE.write('--- %s %s started %s ---\n' % (
            APP_NAME, __version__,
            datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        _CRASH_LOG_FILE.flush()
        faulthandler.enable(file=_CRASH_LOG_FILE)
        return path
    except Exception:
        return None                      # never let diagnostics break startup


class LogEmitter(QObject):
    """Bridge between the (thread-foreign) logging and the GUI.

    pyqtSignal provides a queued connection when emitted from the worker
    thread -- therefore thread-safe for updating the log view.
    """
    log_record = pyqtSignal(str)


class QtLogHandler(logging.Handler):
    def __init__(self, emitter):
        super().__init__()
        self.emitter = emitter

    def emit(self, record):
        try:
            self.emitter.log_record.emit(self.format(record))
        except Exception:
            pass


def setup_logging():
    """Set up file, GUI and console logging.

    Returns: (logger, emitter, gui_handler, log_path)
    """
    log_path = get_log_path()
    logger = logging.getLogger(APP_NAME)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    fmt = logging.Formatter('%(asctime)s %(levelname)-7s %(message)s',
                            '%Y-%m-%d %H:%M:%S')

    # File handler: always full detail (DEBUG) so nothing is lost.
    try:
        fh = RotatingFileHandler(log_path, maxBytes=2_000_000,
                                 backupCount=3, encoding='utf-8')
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except Exception:
        pass  # Continue without a file log if necessary.

    # GUI handler: INFO by default, DEBUG via the verbose checkbox.
    emitter = LogEmitter()
    gui_handler = QtLogHandler(emitter)
    gui_handler.setLevel(logging.INFO)
    gui_handler.setFormatter(fmt)
    logger.addHandler(gui_handler)

    # Console handler (e.g. when started from a terminal).
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    crash_path = _enable_faulthandler(log_path)
    logger.info('%s %s started. Log file: %s', APP_NAME, __version__, log_path)
    if crash_path:
        logger.debug('faulthandler active. Crash log: %s', crash_path)
    return logger, emitter, gui_handler, log_path


# ── Structured data extraction (logic unchanged since v0.1.1) ───────────────────
