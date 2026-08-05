"""Outcome of the per-project updates that run in the background.

`POST /api/projects/{name}/update` used to hold its request open for the whole deploy:
`COMMAND_TIMEOUT` is 300 s per command and the healthcheck adds up to 60 s, so any reverse
proxy with a 60 s read timeout reported a failure for a deploy that had in fact worked, and
the browser had nothing to show meanwhile but a spinner. The endpoint now answers 202 and
the work continues here, which leaves somewhere for the result to live until the SPA polls
for it.

In memory, like `locks.py` and for the same reason: more than one uvicorn worker would
already defeat the per-project lock and the scheduler (see README).
"""

from __future__ import annotations

import threading
import time
from typing import Literal

UpdateState = Literal["running", "success", "error"]

# How long a finished entry stays readable. The SPA polls once a second, so this is
# generous; it only has to outlive a poll the browser missed while the tab was hidden.
FINISHED_TTL_SEC = 120.0
# Ceiling on tracked names, mirroring locks.MAX_TRACKED_PROJECTS.
MAX_TRACKED_PROJECTS = 1024

_lock = threading.Lock()
_states: dict[str, tuple[UpdateState, float]] = {}


def _purge_expired_locked(now: float) -> None:
    """Drop finished entries past their TTL. Call with `_lock` held."""
    for name, (state, stamp) in list(_states.items()):
        if state != "running" and now - stamp >= FINISHED_TTL_SEC:
            del _states[name]


def mark_running(name: str) -> None:
    now = time.monotonic()
    with _lock:
        _purge_expired_locked(now)
        # Only ever drops finished entries: a running update must never lose its slot in
        # the map, or the SPA would stop being told about it while it is still going.
        if len(_states) >= MAX_TRACKED_PROJECTS:
            for other, (state, _stamp) in list(_states.items()):
                if state != "running":
                    del _states[other]
        _states[name] = ("running", now)


def mark_finished(name: str, *, success: bool) -> None:
    with _lock:
        _states[name] = ("success" if success else "error", time.monotonic())


def snapshot() -> dict[str, str]:
    """What every project's last known update did, for the status endpoint."""
    now = time.monotonic()
    with _lock:
        _purge_expired_locked(now)
        return {name: state for name, (state, _stamp) in _states.items()}


def is_running(name: str) -> bool:
    with _lock:
        entry = _states.get(name)
    return entry is not None and entry[0] == "running"


def reset_for_tests() -> None:
    with _lock:
        _states.clear()
