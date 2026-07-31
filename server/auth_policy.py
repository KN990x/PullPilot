"""Username and password policy.

Dependency-free on purpose: both the service (which really validates) and the Pydantic
schemas (which reject early) need it, and either importing the other closes a cycle
through server.models.
"""

from __future__ import annotations

USERNAME_MIN_LEN = 3
USERNAME_MAX_LEN = 64
USERNAME_PATTERN = r"^[A-Za-z0-9._@+-]+$"
PASSWORD_MIN_LEN = 8
PASSWORD_MAX_LEN = 128
