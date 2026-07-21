"""ULID generation for the auto ``Idempotency-Key`` on non-streaming create calls
— mirrors the TS ``idempotency.ts``.

A ULID is 128 bits (48-bit millisecond timestamp + 80 bits of randomness),
Crockford-base32 encoded to 26 characters. Uniqueness (not cryptographic
unpredictability) is what an idempotency key needs; :mod:`secrets` supplies the
randomness anyway.
"""

from __future__ import annotations

import secrets
import time

_ENCODING = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base32
_TIME_LEN = 10
_RANDOM_LEN = 16


def _encode_time(now_ms: int) -> str:
    out = ""
    value = now_ms
    for _ in range(_TIME_LEN):
        mod = value % len(_ENCODING)
        out = _ENCODING[mod] + out
        value //= len(_ENCODING)
    return out


def _encode_random() -> str:
    return "".join(_ENCODING[secrets.randbelow(len(_ENCODING))] for _ in range(_RANDOM_LEN))


def ulid(now_ms: int | None = None) -> str:
    """Return a fresh 26-character ULID string."""
    ms = now_ms if now_ms is not None else int(time.time() * 1000)
    return _encode_time(ms) + _encode_random()
