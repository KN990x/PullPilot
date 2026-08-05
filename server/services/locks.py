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

# Ceiling on distinct project names held at once, mirroring login_rate_limit. A slot used
# to be created for any string the caller passed, so requests naming projects that do not
# exist grew this map without bound.
MAX_TRACKED_PROJECTS = 1024

_registry_lock = threading.Lock()
_project_locks: dict[str, threading.Lock] = {}


def _evict_idle_locked() -> None:
    """Drop slots nobody holds. Call with _registry_lock held."""
    if len(_project_locks) < MAX_TRACKED_PROJECTS:
        return
    for name in [n for n, lock in _project_locks.items() if not lock.locked()]:
        del _project_locks[name]


def _lock_for(name: str) -> threading.Lock:
    with _registry_lock:
        lock = _project_locks.get(name)
        if lock is None:
            _evict_idle_locked()
            lock = threading.Lock()
            _project_locks[name] = lock
        return lock


class ProjectBusyError(Exception):
    """An update is already running for that project."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name


def try_acquire_project_slot(name: str) -> bool:
    """Take the slot without blocking. False when somebody else holds it.

    The explicit pair exists because the HTTP endpoint has to take the slot and a
    background task has to release it, which no context manager can span. Checking
    `is_busy` in the request and acquiring in the task would be a check-then-act with a
    window wide enough for two clicks to both get through.
    """
    return _lock_for(name).acquire(blocking=False)


def release_project_slot(name: str) -> None:
    """Release a slot taken by try_acquire_project_slot.

    Looks the lock up rather than going through `_lock_for`: creating one here would mean
    releasing a brand-new unlocked Lock — a RuntimeError that says nothing about the real
    problem, which is a release without a matching acquire. Eviction cannot lose it, since
    `_evict_idle_locked` only drops slots nobody holds.
    """
    with _registry_lock:
        lock = _project_locks.get(name)
    if lock is not None and lock.locked():
        lock.release()


@contextmanager
def project_update_slot(name: str) -> Iterator[None]:
    """Take the project's slot or raise ProjectBusyError.

    Non-blocking on purpose: whoever arrives second should be told (409, or a line in the
    scheduler log), not queue up to run the very same update again straight after.
    """
    if not try_acquire_project_slot(name):
        raise ProjectBusyError(name)
    try:
        yield
    finally:
        release_project_slot(name)


def is_busy(name: str) -> bool:
    """Informational only: it can change between this call and an acquire."""
    return _lock_for(name).locked()


def reset_for_tests() -> None:
    with _registry_lock:
        _project_locks.clear()
