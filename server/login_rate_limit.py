"""Simple in-memory per-IP limit on failed login attempts."""

from __future__ import annotations

import time
from collections import defaultdict

# Constants, not configuration: 15 failures in 5 minutes stops brute force without
# bothering anyone who mistypes their password twice.
MAX_ATTEMPTS = 15
WINDOW_SEC = 300

_failed_attempts: dict[str, list[float]] = defaultdict(list)


def _prune_old(ip: str, now: float) -> None:
    times = _failed_attempts[ip]
    _failed_attempts[ip] = [t for t in times if now - t < WINDOW_SEC]


def is_login_rate_limited(client_ip: str) -> bool:
    now = time.time()
    _prune_old(client_ip, now)
    return len(_failed_attempts[client_ip]) >= MAX_ATTEMPTS


def record_login_failure(client_ip: str) -> None:
    now = time.time()
    _prune_old(client_ip, now)
    _failed_attempts[client_ip].append(now)


def clear_login_failures(client_ip: str) -> None:
    _failed_attempts.pop(client_ip, None)


def seconds_until_reset(client_ip: str) -> int:
    """Seconds until the oldest attempt in the window expires."""
    times = _failed_attempts.get(client_ip)
    if not times:
        return 0
    remaining = WINDOW_SEC - (time.time() - min(times))
    return max(1, int(remaining))
