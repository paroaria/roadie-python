"""Non-streaming chat: response parsing, metadata surfacing, identity defaults."""

from __future__ import annotations

from roadie import Roadie

from conftest import json_response

_CHAT_BODY = {
    "id": "chatcmpl_123",
    "model": "openai/gpt-4o-mini",
    "provider": "openai",
    "message": {
        "role": "assistant",
        "content": [{"type": "text", "text": "Hello there."}],
        "tool_calls": [],
    },
    "finish_reason": "stop",
    "usage": {
        "input_tokens": 11,
        "output_tokens": 3,
        "total_tokens": 14,
        "source": "provider",
    },
    "cost": {"estimated_usd": 0.00012},
    "gateway": {"fallback_used": False, "retries": 0, "latency_ms": 420},
}


def test_chat_create_parses_response_and_metadata(mock_server):
    mock_server.respond_with(
        json_response(
            _CHAT_BODY,
            headers={
                "x-request-id": "req_abc",
                "x-ratelimit-limit": "100",
                "x-ratelimit-remaining": "99",
                "x-ratelimit-reset": "1700000000",
            },
        )
    )
    bp = Roadie(api_key="rd_sk_test_key", base_url=mock_server.base_url)

    res = bp.chat.create(
        model="smart",
        messages=[{"role": "user", "content": "Hi"}],
    )

    assert res.id == "chatcmpl_123"
    assert res.provider == "openai"
    assert res.finish_reason == "stop"
    assert res.text == "Hello there."
    assert res.message.content[0]["text"] == "Hello there."
    assert res.usage.input_tokens == 11
    assert res.usage.total_tokens == 14
    assert res.usage.source == "provider"
    assert res.cost is not None and res.cost.estimated_usd == 0.00012
    assert res.gateway is not None and res.gateway.latency_ms == 420

    # Response metadata from headers.
    assert res.request_id == "req_abc"
    assert res.rate_limit is not None
    assert res.rate_limit.limit == 100
    assert res.rate_limit.remaining == 99
    assert res.rate_limit.reset == 1700000000


def test_chat_create_sends_expected_request(mock_server):
    mock_server.respond_with(json_response(_CHAT_BODY))
    bp = Roadie(api_key="rd_sk_test_key", base_url=mock_server.base_url)

    bp.chat.create(model="smart", messages=[{"role": "user", "content": "Hi"}])

    assert len(mock_server.captured) == 1
    request = mock_server.captured[0]
    assert request.method == "POST"
    assert request.path == "/v1/chat"
    assert request.headers.get("authorization") == "Bearer rd_sk_test_key"
    assert request.headers.get("accept") == "application/json"
    assert request.headers.get("content-type") == "application/json"
    assert request.headers.get("user-agent", "").startswith("roadie-sdk-python/")
    # Non-streaming create auto-sends a stable Idempotency-Key.
    assert request.headers.get("idempotency-key")

    payload = request.json()
    assert payload["model"] == "smart"
    assert payload["messages"] == [{"role": "user", "content": "Hi"}]
    assert payload["stream"] is False


def test_chat_create_applies_identity_defaults(mock_server):
    mock_server.respond_with(json_response(_CHAT_BODY))
    bp = Roadie(
        api_key="rd_sk_test_key",
        base_url=mock_server.base_url,
        user={"id": "default_user", "plan": "pro"},
        metadata={"team": "growth", "tier": "gold"},
    )

    # Per-call metadata is shallow-merged over the default (per-call wins); user omitted.
    bp.chat.create(
        model="smart",
        messages=[{"role": "user", "content": "Hi"}],
        metadata={"tier": "platinum"},
    )

    payload = mock_server.captured[0].json()
    assert payload["user"] == {"id": "default_user", "plan": "pro"}
    assert payload["metadata"] == {"team": "growth", "tier": "platinum"}


def test_chat_create_per_call_user_overrides_default(mock_server):
    mock_server.respond_with(json_response(_CHAT_BODY))
    bp = Roadie(
        api_key="rd_sk_test_key",
        base_url=mock_server.base_url,
        user={"id": "default_user"},
    )

    bp.chat.create(
        model="smart",
        messages=[{"role": "user", "content": "Hi"}],
        user={"id": "call_user", "plan": "free"},
    )

    payload = mock_server.captured[0].json()
    assert payload["user"] == {"id": "call_user", "plan": "free"}
