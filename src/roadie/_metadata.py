"""Response metadata surfaced on every result: the ``X-Request-Id`` and the
``X-RateLimit-*`` snapshot (plan §21.1). Mirrors the TS SDK's ``response-metadata.ts``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol


class Headers(Protocol):
    """The subset of a case-insensitive header container the SDK reads.

    Satisfied by :class:`http.client.HTTPMessage` (``urllib`` responses/errors).
    """

    def get(self, name: str, failobj: object = ...) -> object: ...


@dataclass(frozen=True)
class RateLimitInfo:
    """Snapshot from the ``X-RateLimit-*`` headers (§21.1)."""

    #: ``X-RateLimit-Limit`` — ceiling of the most-constrained window.
    limit: Optional[int] = None
    #: ``X-RateLimit-Remaining`` — requests left in that window.
    remaining: Optional[int] = None
    #: ``X-RateLimit-Reset`` — epoch seconds when that window resets.
    reset: Optional[int] = None


def _numeric_header(headers: Headers, name: str) -> Optional[int]:
    raw = headers.get(name, None)
    if raw is None:
        return None
    text = str(raw).strip()
    if text == "":
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def request_id_from(headers: Headers) -> Optional[str]:
    """The gateway request id (``X-Request-Id``), or ``None``."""
    raw = headers.get("x-request-id", None)
    return str(raw) if raw is not None else None


def parse_rate_limit(headers: Headers) -> Optional[RateLimitInfo]:
    """Read the ``X-RateLimit-*`` snapshot, or ``None`` if none of the headers are present."""
    limit = _numeric_header(headers, "x-ratelimit-limit")
    remaining = _numeric_header(headers, "x-ratelimit-remaining")
    reset = _numeric_header(headers, "x-ratelimit-reset")
    if limit is None and remaining is None and reset is None:
        return None
    return RateLimitInfo(limit=limit, remaining=remaining, reset=reset)
