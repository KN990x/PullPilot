"""The two things the limiter got wrong: it grew forever, and a header could dodge it.

Every lookup went through a defaultdict, so merely asking about an IP created an entry
that was never removed. And with `PUBLIC_URL` set, `X-Forwarded-For` is trusted, which the
client itself sends: a fresh forged value per request meant a fresh bucket per request.
"""

import pytest

from server import login_rate_limit as rl
from server.login_rate_limit import (
    MAX_ATTEMPTS,
    MAX_ATTEMPTS_PER_PEER,
    MAX_TRACKED_KEYS,
    ClientIdentity,
    clear_login_failures,
    is_login_rate_limited,
    record_login_failure,
    seconds_until_reset,
)


def direct(ip: str) -> ClientIdentity:
    """No proxy: the reported IP is the peer."""
    return ClientIdentity(reported_ip=ip, peer_ip=ip)


def proxied(reported: str, peer: str = "10.0.0.1") -> ClientIdentity:
    return ClientIdentity(reported_ip=reported, peer_ip=peer)


@pytest.fixture(autouse=True)
def _clean():
    rl.reset_for_tests()
    yield
    rl.reset_for_tests()


def test_asking_never_creates_an_entry() -> None:
    for n in range(50):
        assert is_login_rate_limited(direct(f"192.0.2.{n}")) is False

    assert rl._failed_attempts == {}


def test_a_cleared_bucket_leaves_nothing_behind() -> None:
    who = direct("192.0.2.7")
    record_login_failure(who)
    assert rl._failed_attempts

    clear_login_failures(who)
    assert rl._failed_attempts == {}


def test_an_expired_window_drops_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    # Fake clock from the start, so the recorded attempt and the later check share it.
    now = [1000.0]
    monkeypatch.setattr(rl.time, "time", lambda: now[0])

    who = direct("192.0.2.8")
    record_login_failure(who)
    now[0] += rl.WINDOW_SEC + 1

    assert is_login_rate_limited(who) is False
    assert rl._failed_attempts == {}, "the stale key should be gone, not merely emptied"


def test_the_map_has_a_ceiling() -> None:
    for n in range(MAX_TRACKED_KEYS + 200):
        record_login_failure(direct(f"198.51.100.{n}"))

    assert len(rl._failed_attempts) <= MAX_TRACKED_KEYS


def test_a_single_ip_is_limited_after_max_attempts() -> None:
    who = direct("192.0.2.10")
    for _ in range(MAX_ATTEMPTS):
        assert is_login_rate_limited(who) is False
        record_login_failure(who)

    assert is_login_rate_limited(who) is True
    assert seconds_until_reset(who) > 0


def test_rotating_a_forged_forwarded_for_does_not_grant_endless_attempts() -> None:
    """The whole point of the peer bucket."""
    for n in range(MAX_ATTEMPTS_PER_PEER):
        who = proxied(f"203.0.113.{n}", peer="10.0.0.1")
        assert is_login_rate_limited(who) is False, f"blocked too early at {n}"
        record_login_failure(who)

    # A brand new forged client IP, from the same socket: no longer a free pass.
    assert is_login_rate_limited(proxied("203.0.113.254", peer="10.0.0.1")) is True


def test_one_noisy_client_does_not_lock_out_another_network() -> None:
    """A global counter would; the peer bucket must not."""
    for n in range(MAX_ATTEMPTS_PER_PEER + 20):
        record_login_failure(proxied(f"203.0.113.{n}", peer="10.0.0.1"))

    assert is_login_rate_limited(proxied("198.51.100.5", peer="10.0.0.2")) is False


def test_without_a_proxy_there_is_only_one_bucket() -> None:
    who = direct("192.0.2.20")
    record_login_failure(who)

    assert len(rl._failed_attempts) == 1
