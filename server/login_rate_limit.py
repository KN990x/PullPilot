"""In-memory limit on failed login attempts.

Two buckets, not one. The reported client IP is the useful identity, but behind a proxy
it comes from `X-Forwarded-For`, which the client itself sends: anyone who can reach the
port directly rotates a fake value per request and never fills a bucket. So the socket
peer gets a second, looser bucket, which a spoofer cannot escape because it is where the
connection actually comes from.

A global counter would also stop the rotation, but an attacker anywhere could then lock
the owner out of their own homelab. The peer bucket cannot: it only ever limits the
network the requests really arrive from.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

# Constants, not configuration: 15 failures in 5 minutes stops brute force without
# bothering anyone who mistypes their password twice.
MAX_ATTEMPTS = 15
# Looser, because behind a reverse proxy every legitimate user shares one peer. Still far
# below what rotating forged client IPs would need to be worth trying.
MAX_ATTEMPTS_PER_PEER = 60
WINDOW_SEC = 300
# Ceiling on distinct identities held at once. Without it the map grew by one entry per
# IP that ever reached the login endpoint and never shrank.
MAX_TRACKED_KEYS = 1024

_failed_attempts: dict[str, list[float]] = {}


@dataclass(frozen=True)
class ClientIdentity:
    """Who is asking: the IP we believe, and the socket the request came from."""

    reported_ip: str
    peer_ip: str


def _buckets(identity: ClientIdentity) -> list[tuple[str, int]]:
    buckets = [(f"ip:{identity.reported_ip}", MAX_ATTEMPTS)]
    # Only when they differ, i.e. when a trusted proxy header named someone else.
    if identity.peer_ip != identity.reported_ip:
        buckets.append((f"peer:{identity.peer_ip}", MAX_ATTEMPTS_PER_PEER))
    return buckets


def _recent(key: str, now: float) -> list[float]:
    """Attempts still inside the window. Drops the key when nothing is left.

    Read-only on purpose: asking about an unknown key must not create an entry for it,
    which is how the map used to grow from probes that never failed anything.
    """
    times = _failed_attempts.get(key)
    if times is None:
        return []
    fresh = [t for t in times if now - t < WINDOW_SEC]
    if fresh:
        _failed_attempts[key] = fresh
    else:
        _failed_attempts.pop(key, None)
    return fresh


def _evict_if_full() -> None:
    """Drop the least recently active identity once the map is at its ceiling."""
    if len(_failed_attempts) < MAX_TRACKED_KEYS:
        return
    oldest = min(_failed_attempts, key=lambda k: max(_failed_attempts[k], default=0.0))
    _failed_attempts.pop(oldest, None)


def is_login_rate_limited(identity: ClientIdentity) -> bool:
    now = time.time()
    return any(len(_recent(key, now)) >= limit for key, limit in _buckets(identity))


def record_login_failure(identity: ClientIdentity) -> None:
    now = time.time()
    for key, _limit in _buckets(identity):
        times = _recent(key, now)
        if key not in _failed_attempts:
            _evict_if_full()
        _failed_attempts.setdefault(key, times).append(now)


def clear_login_failures(identity: ClientIdentity) -> None:
    for key, _limit in _buckets(identity):
        _failed_attempts.pop(key, None)


def seconds_until_reset(identity: ClientIdentity) -> int:
    """Seconds until the oldest attempt of whichever bucket is blocking expires."""
    now = time.time()
    blocked = [
        min(times)
        for key, limit in _buckets(identity)
        if len(times := _recent(key, now)) >= limit
    ]
    if not blocked:
        return 0
    return max(1, int(WINDOW_SEC - (now - max(blocked))))


def reset_for_tests() -> None:
    _failed_attempts.clear()
