"""Error-envelope → typed-exception mapping, the unknown-type fallback, retries,
and client construction validation."""

from __future__ import annotations

import pytest

from roadie import (
    AuthenticationError,
    Roadie,
    RoadieConfigurationError,
    InternalError,
    InvalidRequestError,
    RateLimitError,
    is_roadie_error,
)
from roadie.errors import error_from_envelope

from conftest import MockResponse, json_response


def _envelope(type_: str, code: str, message: str, **extra):
    error = {"type": type_, "code": code, "message": message}
    error.update(extra)
    return {"error": error}


def test_authentication_error_mapped_from_envelope(mock_server):
    mock_server.respond_with(
        json_response(
            _envelope("authentication_error", "invalid_api_key", "The API key is invalid.",
                      request_id="req_env"),
            status=401,
        )
    )
    bp = Roadie(api_key="rd_sk_bad", base_url=mock_server.base_url)

    with pytest.raises(AuthenticationError) as excinfo:
        bp.chat.create(model="smart", messages=[{"role": "user", "content": "Hi"}])

    err = excinfo.value
    assert err.type == "authentication_error"
    assert err.status == 401
    assert err.code == "invalid_api_key"
    assert err.message == "The API key is invalid."
    assert err.request_id == "req_env"
    assert is_roadie_error(err)


def test_unknown_envelope_type_falls_back_to_status_class(mock_server):
    # A future 11th gateway error type must not crash the SDK; it falls back to the
    # status-based class (400 -> InvalidRequestError) while keeping the message/code.
    mock_server.respond_with(
        json_response(
            _envelope("some_future_error_type", "brand_new", "A brand new failure."),
            status=400,
        )
    )
    bp = Roadie(api_key="rd_sk_test", base_url=mock_server.base_url)

    with pytest.raises(InvalidRequestError) as excinfo:
        bp.chat.create(model="smart", messages=[{"role": "user", "content": "Hi"}])

    err = excinfo.value
    # The discriminator stays the status-based fallback, but envelope fields survive.
    assert err.status == 400
    assert err.code == "brand_new"
    assert err.message == "A brand new failure."


def test_missing_envelope_uses_status_default(mock_server):
    mock_server.respond_with(MockResponse(status=500, body="not json at all"))
    bp = Roadie(api_key="rd_sk_test", base_url=mock_server.base_url, max_retries=0)

    with pytest.raises(InternalError) as excinfo:
        bp.chat.create(model="smart", messages=[{"role": "user", "content": "Hi"}])

    assert excinfo.value.status == 500
    assert excinfo.value.message == "The gateway returned HTTP 500."


def test_rate_limit_error_carries_retry_after(mock_server):
    mock_server.respond_with(
        json_response(
            _envelope("rate_limit_error", "rate_limited", "Too many requests."),
            status=429,
            headers={"retry-after": "7"},
        )
    )
    # max_retries=0 so the 429 surfaces immediately rather than retrying.
    bp = Roadie(api_key="rd_sk_test", base_url=mock_server.base_url, max_retries=0)

    with pytest.raises(RateLimitError) as excinfo:
        bp.chat.create(model="smart", messages=[{"role": "user", "content": "Hi"}])

    assert excinfo.value.retry_after == 7.0


def test_transient_failure_is_retried_with_stable_idempotency_key(mock_server):
    state = {"calls": 0}

    def responder(_request):
        state["calls"] += 1
        if state["calls"] == 1:
            return json_response(
                _envelope("rate_limit_error", "rate_limited", "slow down"), status=429
            )
        return json_response(
            {
                "id": "ok",
                "model": "m",
                "provider": "p",
                "message": {"role": "assistant", "content": [], "tool_calls": []},
                "finish_reason": "stop",
                "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2, "source": "provider"},
            }
        )

    mock_server.respond(responder)
    bp = Roadie(api_key="rd_sk_test", base_url=mock_server.base_url, max_retries=2)

    res = bp.chat.create(model="smart", messages=[{"role": "user", "content": "Hi"}])

    assert res.id == "ok"
    assert len(mock_server.captured) == 2
    # The auto Idempotency-Key is generated once and REUSED across the retry, so a
    # retried create is de-duplicated by the gateway.
    first_key = mock_server.captured[0].headers.get("idempotency-key")
    second_key = mock_server.captured[1].headers.get("idempotency-key")
    assert first_key and first_key == second_key


def test_missing_api_key_raises_configuration_error():
    with pytest.raises(RoadieConfigurationError):
        Roadie(api_key="")


def test_error_from_envelope_never_raises_on_garbage():
    # Directly exercise the mapper's robustness: none of these shapes may raise.
    for body in (None, {}, {"error": None}, {"error": {}}, {"error": {"type": 123}}, "plain string"):
        err = error_from_envelope(503, body)
        assert is_roadie_error(err)
        assert err.status == 503
