"""Wire types for the Roadie data-plane API, as Python dataclasses.

Public request fields are snake_case, matching the gateway wire contract exactly.
Response objects are parsed defensively: unknown fields are ignored and missing
optional fields default to ``None``, so an additive gateway change (the ``/v1``
contract is additive-only) never breaks deserialization — mirroring the TS
SDK's no-runtime-validation stance.

Request bodies (messages, tools, content parts, ``user``) are passed through as
plain dicts/lists in the wire shape; see ``TypedDict`` aliases below for the
documented shapes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Literal, Mapping, Optional, Sequence, TypedDict

from ._metadata import RateLimitInfo

# --- Request-side TypedDicts (documentation + editor hints; passed as dicts) --


class EndUser(TypedDict, total=False):
    """End-user identity forwarded with a request (the ``user`` field)."""

    id: str
    plan: str


class TextContentPart(TypedDict):
    type: Literal["text"]
    text: str


class ChatMessage(TypedDict, total=False):
    """A single chat message. ``content`` is a string or a list of content parts."""

    role: Literal["system", "user", "assistant", "tool"]
    content: Any
    tool_calls: List[Mapping[str, Any]]
    tool_call_id: str


Messages = Sequence[Mapping[str, Any]]


# --- Shared response value objects -------------------------------------------


def _as_int(value: object, default: int = 0) -> int:
    return int(value) if isinstance(value, (int, float)) else default


@dataclass
class Usage:
    """Token accounting for a request."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    source: Optional[str] = None
    cached_input_tokens: Optional[int] = None
    reasoning_tokens: Optional[int] = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Usage":
        return cls(
            input_tokens=_as_int(data.get("input_tokens")),
            output_tokens=_as_int(data.get("output_tokens")),
            total_tokens=_as_int(data.get("total_tokens")),
            source=data.get("source"),
            cached_input_tokens=data.get("cached_input_tokens"),
            reasoning_tokens=data.get("reasoning_tokens"),
        )


@dataclass
class Cost:
    """Estimated request cost."""

    estimated_usd: float = 0.0

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Cost":
        value = data.get("estimated_usd", 0.0)
        return cls(estimated_usd=float(value) if isinstance(value, (int, float)) else 0.0)


@dataclass
class GatewayInfo:
    """Gateway routing metadata attached to a response."""

    fallback_used: bool = False
    retries: int = 0
    latency_ms: int = 0

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "GatewayInfo":
        return cls(
            fallback_used=bool(data.get("fallback_used", False)),
            retries=_as_int(data.get("retries")),
            latency_ms=_as_int(data.get("latency_ms")),
        )


@dataclass
class AssistantMessage:
    """The assistant's reply message."""

    role: str = "assistant"
    #: Content parts, verbatim, e.g. ``[{"type": "text", "text": "..."}]``.
    content: List[Mapping[str, Any]] = field(default_factory=list)
    tool_calls: List[Mapping[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AssistantMessage":
        content = data.get("content")
        tool_calls = data.get("tool_calls")
        return cls(
            role=data.get("role", "assistant"),
            content=list(content) if isinstance(content, list) else [],
            tool_calls=list(tool_calls) if isinstance(tool_calls, list) else [],
        )

    @property
    def text(self) -> str:
        """Convenience: the concatenated text of all ``text`` content parts."""
        return "".join(
            part["text"]
            for part in self.content
            if isinstance(part, Mapping) and part.get("type") == "text" and isinstance(part.get("text"), str)
        )


# --- Chat response -----------------------------------------------------------


@dataclass
class ChatResponse:
    """A non-streaming ``POST /v1/chat`` response."""

    id: Optional[str] = None
    model: Optional[str] = None
    provider: Optional[str] = None
    message: AssistantMessage = field(default_factory=AssistantMessage)
    finish_reason: Optional[str] = None
    usage: Usage = field(default_factory=Usage)
    provider_request_id: Optional[str] = None
    cost: Optional[Cost] = None
    gateway: Optional[GatewayInfo] = None
    #: Gateway request id (``X-Request-Id``); use it in support requests and feedback.
    request_id: Optional[str] = None
    #: Rate-limit snapshot from ``X-RateLimit-*``, when the gateway emitted the headers.
    rate_limit: Optional[RateLimitInfo] = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ChatResponse":
        message = data.get("message")
        cost = data.get("cost")
        gateway = data.get("gateway")
        usage = data.get("usage")
        return cls(
            id=data.get("id"),
            model=data.get("model"),
            provider=data.get("provider"),
            message=AssistantMessage.from_dict(message) if isinstance(message, Mapping) else AssistantMessage(),
            finish_reason=data.get("finish_reason"),
            usage=Usage.from_dict(usage) if isinstance(usage, Mapping) else Usage(),
            provider_request_id=data.get("provider_request_id"),
            cost=Cost.from_dict(cost) if isinstance(cost, Mapping) else None,
            gateway=GatewayInfo.from_dict(gateway) if isinstance(gateway, Mapping) else None,
        )

    @property
    def text(self) -> str:
        """Convenience: the assistant reply's concatenated text."""
        return self.message.text


# --- Embeddings --------------------------------------------------------------


@dataclass
class Embedding:
    index: int = 0
    embedding: List[float] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Embedding":
        vector = data.get("embedding")
        return cls(
            index=_as_int(data.get("index")),
            embedding=list(vector) if isinstance(vector, list) else [],
        )


@dataclass
class EmbeddingsResponse:
    """A ``POST /v1/embeddings`` response."""

    id: Optional[str] = None
    model: Optional[str] = None
    provider: Optional[str] = None
    data: List[Embedding] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    provider_request_id: Optional[str] = None
    cost: Optional[Cost] = None
    gateway: Optional[GatewayInfo] = None
    request_id: Optional[str] = None
    rate_limit: Optional[RateLimitInfo] = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EmbeddingsResponse":
        rows = data.get("data")
        cost = data.get("cost")
        gateway = data.get("gateway")
        usage = data.get("usage")
        return cls(
            id=data.get("id"),
            model=data.get("model"),
            provider=data.get("provider"),
            data=[Embedding.from_dict(row) for row in rows if isinstance(row, Mapping)]
            if isinstance(rows, list)
            else [],
            usage=Usage.from_dict(usage) if isinstance(usage, Mapping) else Usage(),
            provider_request_id=data.get("provider_request_id"),
            cost=Cost.from_dict(cost) if isinstance(cost, Mapping) else None,
            gateway=GatewayInfo.from_dict(gateway) if isinstance(gateway, Mapping) else None,
        )


# --- Models ------------------------------------------------------------------


@dataclass
class Model:
    """One entry in the ``GET /v1/models`` catalog."""

    id: Optional[str] = None
    object: str = "model"
    provider: Optional[str] = None
    display_name: Optional[str] = None
    capabilities: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Model":
        capabilities = data.get("capabilities")
        return cls(
            id=data.get("id"),
            object=data.get("object", "model"),
            provider=data.get("provider"),
            display_name=data.get("display_name"),
            capabilities=dict(capabilities) if isinstance(capabilities, Mapping) else {},
        )


@dataclass
class ModelsPage:
    """The ``GET /v1/models`` catalog page."""

    object: str = "list"
    data: List[Model] = field(default_factory=list)
    request_id: Optional[str] = None
    rate_limit: Optional[RateLimitInfo] = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ModelsPage":
        rows = data.get("data")
        return cls(
            object=data.get("object", "list"),
            data=[Model.from_dict(row) for row in rows if isinstance(row, Mapping)]
            if isinstance(rows, list)
            else [],
        )


# --- Client tokens -----------------------------------------------------------


@dataclass
class ClientToken:
    """A minted short-lived client token (``POST /v1/client-tokens``)."""

    #: The signed, short-lived client token (a JWT) — hand this to the end user's app.
    token: Optional[str] = None
    #: RFC 3339 timestamp at which the token expires.
    expires_at: Optional[str] = None
    #: The end user's external id the token was minted for.
    end_user_id: Optional[str] = None
    request_id: Optional[str] = None
    rate_limit: Optional[RateLimitInfo] = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ClientToken":
        return cls(
            token=data.get("token"),
            expires_at=data.get("expires_at"),
            end_user_id=data.get("end_user_id"),
        )
