"""Per-project mutual exclusion for updates.

Updating a stack is `git pull` + `compose pull` + `down`/`stop` + `up -d`. Two of those
overlapping on one directory fight each other: the second brings containers up while the
first is taking them down, and one rollback reverts the other deploy. A double click or
two open tabs was enough.

`threading.Lock` because that is where it happens: endpoints run in FastAPI's threadpool
and the scheduler in its own thread, all in one process. More than one uvicorn worker
would defeat this, and is already discouraged for the scheduler's sake (see README).
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

_registry_lock = threading.Lock()
_project_locks: dict[str, threading.Lock] = {}


def _lock_for(name: str) -> threading.Lock:
    with _registry_lock:
        lock = _project_locks.get(name)
        if lock is None:
            lock = threading.Lock()
            _project_locks[name] = lock
        return lock


class ProjectBusyError(Exception):
    """An update is already running for that project."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name


@contextmanager
def project_update_slot(name: str) -> Iterator[None]:
    """Take the project's slot or raise ProjectBusyError.

    Non-blocking on purpose: whoever arrives second should be told (409, or a line in the
    scheduler log), not queue up to run the very same update again straight after.
    """
    lock = _lock_for(name)
    if not lock.acquire(blocking=False):
        raise ProjectBusyError(name)
    try:
        yield
    finally:
        lock.release()


def is_busy(name: str) -> bool:
    """Informational only: it can change between this call and an acquire."""
    return _lock_for(name).locked()


def reset_for_tests() -> None:
    with _registry_lock:
        _project_locks.clear()
