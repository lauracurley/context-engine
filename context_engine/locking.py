"""Process-lifetime advisory writer lock; released by the OS after crashes."""

import os
from contextlib import contextmanager


class WriterBusy(ValueError):
    pass


@contextmanager
def writer_lock(engine):
    from .runtime_identity import require_current

    require_current()
    # Nested index/history calls within one crawl share the owning lock.
    depth = getattr(engine, "_writer_depth", 0)
    if depth:
        engine._writer_depth += 1
        try:
            yield
        finally:
            engine._writer_depth -= 1
        return
    path = str(engine.store) + ".writer.lock"
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    locked = False
    try:
        if os.name == "nt":
            import msvcrt

            os.write(descriptor, b"0")
            os.lseek(descriptor, 0, os.SEEK_SET)
            try:
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise WriterBusy(
                    "Another writer is refreshing this scoped store; retry later"
                ) from exc
        else:
            import fcntl

            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise WriterBusy(
                    "Another writer is refreshing this scoped store; retry later"
                ) from exc
        locked = True
        engine._writer_depth = 1
        yield
    finally:
        if locked:
            engine._writer_depth = 0
            if os.name == "nt":
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def exclusive(method):
    from functools import wraps

    @wraps(method)
    def wrapped(self, *args, **kwargs):
        engine = getattr(self, "engine", self)
        with writer_lock(engine):
            return method(self, *args, **kwargs)

    return wrapped
