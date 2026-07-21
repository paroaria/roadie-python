"""``roadie.chat`` — the unified chat surface.

- :meth:`ChatResource.create` → non-streaming ``POST /v1/chat``, returns a typed
  :class:`~roadie.types.ChatResponse` (id, message, finish_reason, usage, cost,
  gateway metadata) with ``request_id`` / ``rate_limit`` attached. Carries an auto
  ``Idempotency-Key`` and is retried on transient failures.
- :meth:`ChatResource.stream` → streaming ``POST /v1/chat`` (``stream: true``),
  returns a :class:`~roadie._streaming.ChatStream` iterable of stream events.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from .._streaming import ChatStream
from .._transport import HttpClient
from ..types import ChatResponse
from ._shared import IdentityDefaults, apply_identity_defaults, attach_metadata, prune_none

_ACCEPT = {"sse": "text/event-stream", "ndjson": "application/x-ndjson"}


class ChatResource:
    def __init__(self, http: HttpClient, defaults: IdentityDefaults) -> None:
        self._http = http
        self._defaults = defaults

    def create(
        self,
        *,
        model: str,
        messages: Sequence[Mapping[str, Any]],
        temperature: Optional[float] = None,
        max_output_tokens: Optional[int] = None,
        response_format: Optional[Mapping[str, Any]] = None,
        tools: Optional[Sequence[Mapping[str, Any]]] = None,
        tool_choice: Optional[Any] = None,
        user: Optional[Mapping[str, Any]] = None,
        metadata: Optional[Mapping[str, str]] = None,
        provider_options: Optional[Mapping[str, Mapping[str, Any]]] = None,
        timeout: Optional[float] = None,
    ) -> ChatResponse:
        """Non-streaming completion."""
        body = self._build_body(
            model=model,
            messages=messages,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            response_format=response_format,
            tools=tools,
            tool_choice=tool_choice,
            user=user,
            metadata=metadata,
            provider_options=provider_options,
            stream=False,
        )
        data, headers = self._http.request_json(
            method="POST", path="/v1/chat", body=body, idempotent=True, timeout=timeout
        )
        return attach_metadata(ChatResponse.from_dict(data), headers)

    def stream(
        self,
        *,
        model: str,
        messages: Sequence[Mapping[str, Any]],
        temperature: Optional[float] = None,
        max_output_tokens: Optional[int] = None,
        response_format: Optional[Mapping[str, Any]] = None,
        tools: Optional[Sequence[Mapping[str, Any]]] = None,
        tool_choice: Optional[Any] = None,
        user: Optional[Mapping[str, Any]] = None,
        metadata: Optional[Mapping[str, str]] = None,
        provider_options: Optional[Mapping[str, Mapping[str, Any]]] = None,
        framing: str = "sse",
        timeout: Optional[float] = None,
    ) -> ChatStream:
        """Streaming completion — iterate the returned :class:`ChatStream`."""
        accept = _ACCEPT.get(framing, _ACCEPT["sse"])
        body = self._build_body(
            model=model,
            messages=messages,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            response_format=response_format,
            tools=tools,
            tool_choice=tool_choice,
            user=user,
            metadata=metadata,
            provider_options=provider_options,
            stream=True,
        )
        resolved_framing = "ndjson" if framing == "ndjson" else "sse"
        return ChatStream(
            lambda: self._http.request_stream(
                path="/v1/chat", body=body, accept=accept, timeout=timeout
            ),
            resolved_framing,
        )

    def _build_body(
        self,
        *,
        model: str,
        messages: Sequence[Mapping[str, Any]],
        temperature: Optional[float],
        max_output_tokens: Optional[int],
        response_format: Optional[Mapping[str, Any]],
        tools: Optional[Sequence[Mapping[str, Any]]],
        tool_choice: Optional[Any],
        user: Optional[Mapping[str, Any]],
        metadata: Optional[Mapping[str, str]],
        provider_options: Optional[Mapping[str, Mapping[str, Any]]],
        stream: bool,
    ) -> dict[str, Any]:
        body = prune_none(
            {
                "model": model,
                "messages": list(messages),
                "temperature": temperature,
                "max_output_tokens": max_output_tokens,
                "response_format": response_format,
                "tools": list(tools) if tools is not None else None,
                "tool_choice": tool_choice,
                "user": dict(user) if user is not None else None,
                "metadata": dict(metadata) if metadata is not None else None,
                "provider_options": provider_options,
            }
        )
        body["stream"] = stream
        apply_identity_defaults(body, self._defaults)
        return body
