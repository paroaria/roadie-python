"""Retry policy: which failures retry, and how long to wait (mirrors TS ``backoff.ts``).

Only pre-first-byte, safe-to-repeat failures retry: network errors plus
``429`` / ``408`` / ``5xx`` responses. Backoff is exponential with equal jitter,
capped, and a ``Retry-After`` header (seconds or HTTP-date) always wins. Delays
are expressed in SECONDS (idiomatic for :func:`time.sleep`).
"""

from __future__ import annotations

import time
from email.utils import parsedate_to_datetime
from typing import Callable, Optional

_INITIAL_DELAY_SECONDS = 0.4
_MAX_DELAY_SECONDS = 8.0


def is_retryable_status(status: int) -> bool:
    """Retryable HTTP status codes (pre-first-byte): rate limiting and server faults."""
    return status == 429 or status == 408 or (500 <= status <= 599)


def parse_retry_after_seconds(
    header_value: Optional[str], now: Optional[float] = None
) -> Optional[float]:
    """Parse a ``Retry-After`` header into seconds.

    Supports the delta form (``"12"`` seconds) and the HTTP-date form. Returns
    ``None`` when absent or unparseable.
    """
    if header_value is None:
        return None
    text = header_value.strip()
    if text == "":
        return None
    try:
        return max(0.0, float(text))
    except ValueError:
        pass
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None
    if parsed is None:
        return None
    reference = now if now is not None else time.time()
    return max(0.0, parsed.timestamp() - reference)


def retry_delay_seconds(
    attempt: int,
    retry_after_seconds: Optional[float],
    rng: Callable[[], float],
) -> float:
    """Delay (seconds) before retry ``attempt`` (1-based).

    Honors ``retry_after_seconds`` when the server provided one (capped); otherwise
    exponential backoff with equal jitter — half fixed, half random — to avoid a
    thundering herd.
    """
    if retry_after_seconds is not None:
        return min(retry_after_seconds, _MAX_DELAY_SECONDS)
    exponential = min(_INITIAL_DELAY_SECONDS * (2 ** (attempt - 1)), _MAX_DELAY_SECONDS)
    return exponential / 2 + rng() * (exponential / 2)
