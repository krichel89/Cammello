"""Single-thread executor for the non-thread-safe native imaging libraries.

Why this exists
---------------
pyexiv2's C++ core (exiv2 + the Adobe XMP toolkit) is documented as NOT thread
safe: "Not thread safe, because pyexiv2 uses some global variables in C++"
(pyexiv2 README). On Windows this is worse than it sounds - the XMP toolkit
keeps global, thread-affine state, so it is unsafe not only to call pyexiv2
CONCURRENTLY but even to call it from DIFFERENT threads at different times.

A plain lock (which we tried first) serializes calls but does not fix the
thread-affinity: Cammello opened pyexiv2 from the metadata-reader QThread AND
from the preview-pool threads (read_orientation). The result was a hard access
violation in pyexiv2.Image.__init__ that a Python try/except cannot catch -
observed reproducibly on Windows/Python 3.13 while scanning a folder, even
after the lock was added. The single files read fine in isolation (one thread,
one XMP init/terminate cycle); only the multi-thread app crashed.

The fix
-------
Confine ALL native imaging-library work to ONE dedicated worker thread. Every
pyexiv2 and rawpy call is submitted to this thread and the caller blocks for
the result. From exiv2's point of view there is now exactly one thread that
ever touches it - no concurrency and no cross-thread global state. The Qt image
decode (QImageReader) is thread-safe for separate readers and deliberately
stays OFF this thread, so preview decoding remains parallel across the pool;
only the short native metadata/thumb calls serialize here.

The worker thread is a daemon and lives for the whole process. run() is safe to
call from any thread, including the GUI thread and QThreadPool workers.
"""
import logging
import queue
import threading

# Sentinel used only internally; never returned to callers.
_UNSET = object()

_queue = queue.Queue()
_thread = None
_start_lock = threading.Lock()


def _worker():
    log = logging.getLogger('Cammello')
    while True:
        fn, args, kwargs, box, ev = _queue.get()
        # Diagnostic: the file is logged (and flushed) BEFORE the native call,
        # so if that call dies with a hard access violation - which no Python
        # try/except can catch - the last line in cammello_debug.log names the
        # exact operation and file that brought the native library down.
        try:
            target = args[0] if args else ''
            log.debug('native: %s %r', getattr(fn, '__name__', fn), target)
        except Exception:
            pass
        try:
            box[0] = ('ok', fn(*args, **kwargs))
        except BaseException as exc:      # propagate EVERYTHING to the caller
            box[0] = ('err', exc)
        finally:
            ev.set()


def _ensure_started():
    global _thread
    if _thread is not None:
        return
    with _start_lock:
        if _thread is None:
            t = threading.Thread(target=_worker, name='native-imaging',
                                 daemon=True)
            t.start()
            _thread = t


def run(fn, *args, **kwargs):
    """Run fn(*args, **kwargs) on the dedicated native-imaging thread and
    return its result (or re-raise its exception) in the calling thread.

    Blocks the caller until the work is done. Safe to call from any thread.
    Re-entrancy note: fn itself must NOT call run() again - that would enqueue
    onto the thread that is currently busy and deadlock. All fns here are leaf
    native calls, so this does not arise.
    """
    _ensure_started()
    # If we are already ON the worker thread (should not happen, but guard
    # against accidental nesting), just run inline to avoid a self-deadlock.
    if threading.current_thread() is _thread:
        return fn(*args, **kwargs)
    box = [_UNSET]
    ev = threading.Event()
    _queue.put((fn, args, kwargs, box, ev))
    ev.wait()
    kind, value = box[0]
    if kind == 'err':
        raise value
    return value
