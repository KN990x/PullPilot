"""Limitación simple por IP de intentos fallidos de login (en memoria)."""

from __future__ import annotations

import time
from collections import defaultdict

from server.config import (
    LOGIN_RATE_LIMIT_ENABLED,
    LOGIN_RATE_LIMIT_MAX,
    LOGIN_RATE_LIMIT_WINDOW_SEC,
)

_failed_attempts: dict[str, list[float]] = defaultdict(list)


def _prune_old(ip: str, now: float) -> None:
    window = LOGIN_RATE_LIMIT_WINDOW_SEC
    times = _failed_attempts[ip]
    _failed_attempts[ip] = [t for t in times if now - t < window]


def is_login_rate_limited(client_ip: str) -> bool:
    if not LOGIN_RATE_LIMIT_ENABLED:
        return False
    now = time.time()
    _prune_old(client_ip, now)
    return len(_failed_attempts[client_ip]) >= LOGIN_RATE_LIMIT_MAX


def record_login_failure(client_ip: str) -> None:
    if not LOGIN_RATE_LIMIT_ENABLED:
        return
    now = time.time()
    _prune_old(client_ip, now)
    _failed_attempts[client_ip].append(now)


def clear_login_failures(client_ip: str) -> None:
    _failed_attempts.pop(client_ip, None)


def seconds_until_reset(client_ip: str) -> int:
    """Segundos que faltan para que caduque el intento más antiguo de la ventana."""
    times = _failed_attempts.get(client_ip)
    if not times:
        return 0
    remaining = LOGIN_RATE_LIMIT_WINDOW_SEC - (time.time() - min(times))
    return max(1, int(remaining))
