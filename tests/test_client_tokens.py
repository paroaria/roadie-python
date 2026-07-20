"""Client-token minting (server-side, secret key — §18.1 Path A)."""

from __future__ import annotations

from roadie import Roadie

from conftest import json_response


def test_client_token_mint_sends_end_user_and_parses_response(mock_server):
    mock_server.respond_with(
        json_response(
            {
                "token": "bp_ct_minted",
                "expires_at": "2026-07-17T12:34:56Z",
                "end_user_id": "u_789",
            },
            status=201,
            headers={"x-request-id": "req_mint"},
        )
    )
    bp = Roadie(api_key="rd_sk_test_key", base_url=mock_server.base_url)

    token = bp.client_tokens.create(
        end_user_id="u_789",
        plan="pro",
        attributes={"region": "us"},
        ttl_seconds=600,
        scopes=["ai.chat", "ai.embed"],
    )

    assert token.token == "bp_ct_minted"
    assert token.expires_at == "2026-07-17T12:34:56Z"
    assert token.end_user_id == "u_789"
    assert token.request_id == "req_mint"

    request = mock_server.captured[0]
    assert request.method == "POST"
    assert request.path == "/v1/client-tokens"
    # A mint is not idempotency-keyed (the gateway mint route has no replay).
    assert request.headers.get("idempotency-key") is None
    payload = request.json()
    assert payload["end_user"] == {"id": "u_789", "plan": "pro", "attributes": {"region": "us"}}
    assert payload["ttl_seconds"] == 600
    assert payload["scopes"] == ["ai.chat", "ai.embed"]


def test_client_token_mint_minimal_body(mock_server):
    mock_server.respond_with(
        json_response(
            {"token": "t", "expires_at": "2026-07-17T12:00:00Z", "end_user_id": "u_1"},
            status=201,
        )
    )
    bp = Roadie(api_key="rd_sk_test_key", base_url=mock_server.base_url)

    bp.client_tokens.create(end_user_id="u_1")

    payload = mock_server.captured[0].json()
    assert payload == {"end_user": {"id": "u_1"}}
