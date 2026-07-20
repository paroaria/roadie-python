"""Typed error hierarchy (plan §21.1) — the Python mirror of the TS SDK's ``errors.ts``.

Every failure the SDK raises is a :class:`RoadieError`. Server failures are
mapped from the uniform §21.1 error envelope onto one class per ``type``, each
carrying ``code``, ``request_id`` (from ``X-Request-Id``), ``status`` and the
message; client-side failures (network, timeout, misconfiguration) get their own
classes so callers can branch on ``except``.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

__all__ = [
    "RoadieError",
    "is_roadie_error",
    "InvalidRequestError",
    "AuthenticationError",
    "PermissionError",
    "NotFoundError",
    "RateLimitError",
    "QuotaError",
    "BudgetError",
    "ProviderError",
    "IdempotencyError",
    "InternalError",
    "APIConnectionError",
    "APIConnectionTimeoutError",
    "RoadieConfigurationError",
    "error_from_envelope",
]


class RoadieError(Exception):
    """Base class for every error the SDK raises."""

    #: Discriminator: a §21.1 envelope type, or a client-side type
    #: (``connection_error`` / ``timeout_error`` / ``configuration_error``).
    type: str

    def __init__(
        self,
        type: str,
        message: str,
        *,
        status: Optional[int] = None,
        code: Optional[str] = None,
        request_id: Optional[str] = None,
        param: Optional[str] = None,
        doc_url: Optional[str] = None,
        retry_after: Optional[float] = None,
    ) -> None:
        super().__init__(message)
        self.type = type
        self.message = message
        #: HTTP status of the response that produced the error (absent for client-side errors).
        self.status = status
        #: Stable machine-readable §21.1 ``code``.
        self.code = code
        #: ``X-Request-Id`` of the failing request, when known.
        self.request_id = request_id
        #: Offending request parameter (§21.1 ``param``).
        self.param = param
        #: Documentation URL for this error (§21.1 ``doc_url``).
        self.doc_url = doc_url
        #: Seconds to wait before retrying (from the ``Retry-After`` header).
        self.retry_after = retry_after


def is_roadie_error(value: object) -> bool:
    """``True`` if ``value`` is any :class:`RoadieError`."""
    return isinstance(value, RoadieError)


# --- Envelope-mapped server errors (§21.1) ----------------------------------


class InvalidRequestError(RoadieError):
    def __init__(self, message: str, **meta: Any) -> None:
        super().__init__("invalid_request_error", message, **meta)


class AuthenticationError(RoadieError):
    def __init__(self, message: str, **meta: Any) -> None:
        super().__init__("authentication_error", message, **meta)


class PermissionError(RoadieError):
    def __init__(self, message: str, **meta: Any) -> None:
        super().__init__("permission_error", message, **meta)


class NotFoundError(RoadieError):
    def __init__(self, message: str, **meta: Any) -> None:
        super().__init__("not_found_error", message, **meta)


class RateLimitError(RoadieError):
    def __init__(self, message: str, **meta: Any) -> None:
        super().__init__("rate_limit_error", message, **meta)


class QuotaError(RoadieError):
    def __init__(self, message: str, **meta: Any) -> None:
        super().__init__("quota_error", message, **meta)


class BudgetError(RoadieError):
    def __init__(self, message: str, **meta: Any) -> None:
        super().__init__("budget_error", message, **meta)


class ProviderError(RoadieError):
    def __init__(self, message: str, **meta: Any) -> None:
        super().__init__("provider_error", message, **meta)


class IdempotencyError(RoadieError):
    def __init__(self, message: str, **meta: Any) -> None:
        super().__init__("idempotency_error", message, **meta)


class InternalError(RoadieError):
    def __init__(self, message: str, **meta: Any) -> None:
        super().__init__("internal_error", message, **meta)


# --- Client-side errors -----------------------------------------------------


class APIConnectionError(RoadieError):
    """A network-level failure (DNS, connection refused, TLS, mid-stream socket drop)."""

    def __init__(self, message: str = "Connection error.", **meta: Any) -> None:
        meta.setdefault("type", "connection_error")
        type_ = meta.pop("type")
        super().__init__(type_, message, **meta)


class APIConnectionTimeoutError(APIConnectionError):
    """The request exceeded its ``timeout`` deadline."""

    def __init__(self, message: str = "Request timed out.", **meta: Any) -> None:
        meta["type"] = "timeout_error"
        super().__init__(message, **meta)


class RoadieConfigurationError(RoadieError):
    """Invalid client construction (e.g. missing credentials)."""

    def __init__(self, message: str, **meta: Any) -> None:
        super().__init__("configuration_error", message, **meta)


# --- Envelope -> error mapping ----------------------------------------------

_ENVELOPE_CLASSES: dict[str, type[RoadieError]] = {
    "invalid_request_error": InvalidRequestError,
    "authentication_error": AuthenticationError,
    "permission_error": PermissionError,
    "not_found_error": NotFoundError,
    "rate_limit_error": RateLimitError,
    "quota_error": QuotaError,
    "budget_error": BudgetError,
    "provider_error": ProviderError,
    "idempotency_error": IdempotencyError,
    "internal_error": InternalError,
}

_STATUS_CLASSES: dict[int, type[RoadieError]] = {
    400: InvalidRequestError,
    401: AuthenticationError,
    402: BudgetError,
    403: PermissionError,
    404: NotFoundError,
    409: IdempotencyError,
    429: RateLimitError,
}


def _class_for_status(status: int) -> type[RoadieError]:
    """Fallback class when the body carried no recognizable envelope, keyed by HTTP status."""
    cls = _STATUS_CLASSES.get(status)
    if cls is not None:
        return cls
    if 400 <= status < 500:
        return InvalidRequestError
    return InternalError


def _envelope_error(body: object) -> Optional[Mapping[str, Any]]:
    if not isinstance(body, Mapping):
        return None
    error = body.get("error")
    if not isinstance(error, Mapping):
        return None
    if not isinstance(error.get("type"), str):
        return None
    return error


def error_from_envelope(
    status: int,
    body: object,
    *,
    request_id: Optional[str] = None,
    retry_after: Optional[float] = None,
) -> RoadieError:
    """Build the typed error for a non-2xx response.

    Prefers the §21.1 envelope's ``type``; falls back to the HTTP status when the
    body is missing or malformed. An UNRECOGNIZED envelope ``type`` (a future 11th
    gateway error type, or a malformed empty string) still yields a
    :class:`RoadieError` — never a ``KeyError`` — by falling back to the
    status-based class while keeping the envelope's message/code/request_id.
    This mirrors the TS SDK's ``errorFromEnvelope`` never throwing on unknown types.
    """
    envelope = _envelope_error(body)
    resolved_request_id = None
    if envelope is not None and isinstance(envelope.get("request_id"), str):
        resolved_request_id = envelope["request_id"]
    if resolved_request_id is None:
        resolved_request_id = request_id

    message = (
        envelope["message"]
        if envelope is not None and isinstance(envelope.get("message"), str)
        else f"The gateway returned HTTP {status}."
    )

    meta: dict[str, Any] = {"status": status}
    if envelope is not None:
        if isinstance(envelope.get("code"), str):
            meta["code"] = envelope["code"]
        if isinstance(envelope.get("param"), str):
            meta["param"] = envelope["param"]
        if isinstance(envelope.get("doc_url"), str):
            meta["doc_url"] = envelope["doc_url"]
    if resolved_request_id is not None:
        meta["request_id"] = resolved_request_id
    if retry_after is not None:
        meta["retry_after"] = retry_after

    cls: Optional[type[RoadieError]] = None
    if envelope is not None:
        cls = _ENVELOPE_CLASSES.get(envelope["type"])
    if cls is None:
        cls = _class_for_status(status)
    return cls(message, **meta)
