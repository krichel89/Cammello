"""Metadata calls in a dedicated HELPER PROCESS (0.12.6; was a thread).

Why this exists
---------------
pyexiv2's C++ core is documented as NOT thread safe ("uses some global
variables in C++"), and on Windows its ERROR paths have repeatedly killed the
whole application with access violations that no Python try/except can catch:
once while writing a freshly created sidecar (first exiv2 call of the
process), once while opening a Canon DNG whose maker note exiv2 cannot parse.
Isolated reproduction scripts - same file, same wheel, main thread or worker
thread - raise a clean RuntimeError instead, so the trigger inside the full
application (Qt loaded, event loop running, preview threads busy) was never
pinned down. The 0.11.2 folder-scan crash followed the same pattern and was
only solved by removing exiv2 from that path entirely.

The fix
-------
Stop sharing an address space with exiv2. Every call runs in a single-worker
helper PROCESS (spawn context - identical semantics on all three platforms,
and the only context PyInstaller supports well). If exiv2 takes the helper
down, the pool reports it, Cammello raises a catchable NativeCrash carrying
the file name, rebuilds the pool lazily, and keeps running; ratings queued in
the write-behind land in .errors instead of vanishing with the process.

The helper imports only cammello.native_ops (pyexiv2 + stdlib, no Qt), so it
starts quickly and stays small. The first call pays the spawn cost once; the
process then lives until app exit.

run() keeps its old signature and blocking behaviour, so callers are
unchanged. Functions passed in must be top-level in native_ops (picklable by
reference) and all arguments/results must be picklable - they are: paths,
dicts, strings.
"""
import concurrent.futures
import logging
import multiprocessing
import sys
import threading

__all__ = ['run', 'NativeCrash', 'shutdown']


class NativeCrash(RuntimeError):
    """The native library killed the helper process (hard crash, not a normal
    exception). The operation and file are in the message."""


_pool = None
_pool_lock = threading.Lock()


def _ensure_pool():
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                # Windows has only 'spawn'; Cammello.py carries the required
                # __main__ guard + freeze_support for it. On POSIX 'fork' is
                # used deliberately: spawn RE-IMPORTS the __main__ module,
                # which would re-run any script without a main guard (the CI
                # test scripts) inside the helper. The fork child touches
                # only pyexiv2 + stdlib (native_ops), no Qt, so inheriting
                # the parent's address space is safe here.
                method = 'spawn' if sys.platform == 'win32' else 'fork'
                ctx = multiprocessing.get_context(method)
                _pool = concurrent.futures.ProcessPoolExecutor(
                    max_workers=1, mp_context=ctx)
    return _pool


def run(fn, *args, **kwargs):
    """Run fn(*args, **kwargs) in the metadata helper process; return its
    result or re-raise its exception in the calling thread.

    Blocks the caller. Safe to call from any thread. A hard native crash
    surfaces as NativeCrash (instead of taking the application down), and the
    helper is respawned on the next call.
    """
    global _pool
    log = logging.getLogger('Cammello')
    target = args[0] if args else ''
    # Logged (and flushed to the debug log) BEFORE the call, so even a crash
    # of the HELPER process is attributable to an exact file.
    log.debug('native: %s %r', getattr(fn, '__name__', fn), target)
    pool = _ensure_pool()
    try:
        return pool.submit(fn, *args, **kwargs).result()
    except concurrent.futures.process.BrokenProcessPool:
        with _pool_lock:
            try:
                pool.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass
            if _pool is pool:
                _pool = None            # respawn lazily on the next call
        msg = (f'The metadata library crashed while processing {target!r}. '
               f'The file was skipped; Cammello keeps running.')
        log.error('native: helper process crashed on %r (%s)', target,
                  getattr(fn, '__name__', fn))
        raise NativeCrash(msg) from None


def shutdown():
    """App exit: stop the helper process (best effort)."""
    global _pool
    with _pool_lock:
        if _pool is not None:
            try:
                _pool.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass
            _pool = None
