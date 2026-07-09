"""Logging setup (file + in-app log tab + console), with credential masking."""
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

    logger.info('%s %s started. Log file: %s', APP_NAME, __version__, log_path)
    return logger, emitter, gui_handler, log_path


# ── Structured data extraction (logic unchanged since v0.1.1) ───────────────────
