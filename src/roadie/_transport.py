"""The HTTP transport (plan §28): a single ``urllib``-based request path shared by
every resource. The Python mirror of the TS SDK's ``transport.ts`` + ``http.ts``.

Responsibilities:

- Assemble headers once per request: ``Authorization`` (secret key), ``Accept``,
  ``User-Agent`` (``roadie-sdk-python/<version>``), ``Content-Type`` for bodies,
  and — for non-streaming create calls — a stable ``Idempotency-Key`` (ULID).
- Retry ONLY pre-first-byte, safe-to-repeat failures (network errors, ``429``,
  ``408``, ``5xx``) with exponential backoff + jitter, honoring ``Retry-After``, up
  to ``max_retries``. The auto ``Idempotency-Key`` is generated once and reused
  across attempts, so a retried create is de-duplicated by the gateway.
- Map a non-2xx §21.1 envelope to a typed error; surface ``X-Request-Id`` +
  ``X-RateLimit-*`` on every result via the caller.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Callable, Mapping, Optional, Protocol, Tuple

from ._backoff import is_retryable_status, parse_retry_after_seconds, retry_delay_seconds
from ._idempotency import ulid
from ._metadata import Headers, request_id_from
from ._streaming import StreamConnection
from ._version import VERSION
from .errors import (
    APIConnectionError,
    APIConnectionTimeoutError,
    error_from_envelope,
)
import random as _random_module
import time as _time_module

DEFAULT_BASE_URL = "https://gateway.roadie.paroaria.ai"

#: The credential resolver — returns the current bearer credential (secret key).
AuthResolver = Callable[[], str]


class _Opener(Protocol):
    def open(self, request: urllib.request.Request, timeout: Optional[float] = ...) -> Any: ...


def _join_url(base_url: str, path: str) -> str:
    trimmed_base = base_url.rstrip("/")
    trimmed_path = path if path.startswith("/") else f"/{path}"
    return f"{trimmed_base}{trimmed_path}"


def _read_json_safe(response: Any) -> Optional[object]:
    try:
        raw = response.read()
    except OSError:
        return None
    finally:
        try:
            response.close()
        except OSError:
            pass
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


class HttpClient:
    """Shared request path for every resource."""

    def __init__(
        self,
        *,
        base_url: str,
        auth: AuthResolver,
        max_retries: int,
        timeout: Optional[float],
        opener: Optional[_Opener] = None,
        sleep: Callable[[float], None] = _time_module.sleep,
        rng: Callable[[], float] = _random_module.random,
    ) -> None:
        self._base_url = base_url
        self._auth = auth
        self._max_retries = max(0, max_retries)
        self._timeout = timeout
        self._opener: _Opener = opener if opener is not None else urllib.request.build_opener()
        self._sleep = sleep
        self._rng = rng

    def request_json(
        self,
        *,
        method: str,
        path: str,
        body: Optional[Mapping[str, Any]] = None,
        idempotent: bool = False,
        timeout: Optional[float] = None,
    ) -> Tuple[Mapping[str, Any], Headers]:
        """Non-streaming request → the parsed §21.2 body plus the response headers."""
        idempotency_key = ulid() if idempotent else None
        headers = self._headers("application/json", has_body=body is not None, idempotency_key=idempotency_key)
        body_bytes = json.dumps(body).encode("utf-8") if body is not None else None
        response = self._open_with_retries(
            method=method,
            url=_join_url(self._base_url, path),
            body_bytes=body_bytes,
            headers=headers,
            timeout=self._effective_timeout(timeout),
        )
        response_headers = response.headers
        try:
            raw = response.read()
        except OSError as error:
            raise APIConnectionError(
                "The response stream was interrupted.",
                request_id=request_id_from(response_headers),
            ) from error
        finally:
            try:
                response.close()
            except OSError:
                pass
        try:
            data = json.loads(raw) if raw else {}
        except (ValueError, TypeError) as error:
            raise APIConnectionError(
                "Failed to parse the response body as JSON.",
                request_id=request_id_from(response_headers),
            ) from error
        if not isinstance(data, Mapping):
            raise APIConnectionError(
                "The response body was not a JSON object.",
                request_id=request_id_from(response_headers),
            )
        return data, response_headers

    def request_stream(
        self,
        *,
        path: str,
        body: Mapping[str, Any],
        accept: str,
        timeout: Optional[float] = None,
    ) -> StreamConnection:
        """Streaming request → a committed 2xx response wrapped as a :class:`StreamConnection`.

        Retries apply only pre-first-byte (before the 2xx is returned); ownership of
        the connection (and its ``close``) transfers to the caller on success.
        """
        headers = self._headers(accept, has_body=True, idempotency_key=None)
        body_bytes = json.dumps(body).encode("utf-8")
        response = self._open_with_retries(
            method="POST",
            url=_join_url(self._base_url, path),
            body_bytes=body_bytes,
            headers=headers,
            timeout=self._effective_timeout(timeout),
        )
        return StreamConnection(reader=response, headers=response.headers, close=response.close)

    def _headers(
        self, accept: str, *, has_body: bool, idempotency_key: Optional[str]
    ) -> dict[str, str]:
        token = self._auth()
        headers = {
            "accept": accept,
            "authorization": f"Bearer {token}",
            "user-agent": f"roadie-sdk-python/{VERSION}",
        }
        if has_body:
            headers["content-type"] = "application/json"
        if idempotency_key is not None:
            headers["idempotency-key"] = idempotency_key
        return headers

    def _effective_timeout(self, per_call: Optional[float]) -> Optional[float]:
        return per_call if per_call is not None else self._timeout

    def _open_with_retries(
        self,
        *,
        method: str,
        url: str,
        body_bytes: Optional[bytes],
        headers: Mapping[str, str],
        timeout: Optional[float],
    ) -> Any:
        """The retry loop. Returns a committed 2xx response or raises a typed error."""
        attempt = 0
        while True:
            request = urllib.request.Request(
                url, data=body_bytes, method=method, headers=dict(headers)
            )
            try:
                return self._opener.open(request, timeout=timeout)
            except urllib.error.HTTPError as error:
                status = error.code
                retry_after = parse_retry_after_seconds(error.headers.get("retry-after"))
                if is_retryable_status(status) and attempt < self._max_retries:
                    try:
                        error.close()
                    except OSError:
                        pass
                    attempt += 1
                    self._sleep(retry_delay_seconds(attempt, retry_after, self._rng))
                    continue
                body = _read_json_safe(error)
                raise error_from_envelope(
                    status,
                    body,
                    request_id=request_id_from(error.headers),
                    retry_after=retry_after,
                ) from None
            except TimeoutError as error:
                raise APIConnectionTimeoutError("The request exceeded its timeout.") from error
            except urllib.error.URLError as error:
                if isinstance(error.reason, TimeoutError):
                    raise APIConnectionTimeoutError(
                        "The request exceeded its timeout."
                    ) from error
                if attempt < self._max_retries:
                    attempt += 1
                    self._sleep(retry_delay_seconds(attempt, None, self._rng))
                    continue
                raise APIConnectionError("Connection error.") from error
