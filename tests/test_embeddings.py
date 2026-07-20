"""Embeddings: request shape and response parsing."""

from __future__ import annotations

from roadie import Roadie

from conftest import json_response

_EMBEDDINGS_BODY = {
    "id": "emb_1",
    "model": "openai/text-embedding-3-small",
    "provider": "openai",
    "data": [
        {"index": 0, "embedding": [0.1, 0.2, 0.3]},
        {"index": 1, "embedding": [0.4, 0.5, 0.6]},
    ],
    "usage": {"input_tokens": 8, "output_tokens": 0, "total_tokens": 8, "source": "provider"},
}


def test_embeddings_create_parses_response(mock_server):
    mock_server.respond_with(json_response(_EMBEDDINGS_BODY, headers={"x-request-id": "req_emb"}))
    bp = Roadie(api_key="rd_sk_test_key", base_url=mock_server.base_url)

    res = bp.embeddings.create(model="smart-embed", input=["a", "b"])

    assert len(res.data) == 2
    assert res.data[0].index == 0
    assert res.data[0].embedding == [0.1, 0.2, 0.3]
    assert res.data[1].embedding == [0.4, 0.5, 0.6]
    assert res.usage.input_tokens == 8
    assert res.request_id == "req_emb"


def test_embeddings_create_sends_expected_request(mock_server):
    mock_server.respond_with(json_response(_EMBEDDINGS_BODY))
    bp = Roadie(api_key="rd_sk_test_key", base_url=mock_server.base_url)

    bp.embeddings.create(model="smart-embed", input="single string", dimensions=256)

    request = mock_server.captured[0]
    assert request.method == "POST"
    assert request.path == "/v1/embeddings"
    assert request.headers.get("idempotency-key")
    payload = request.json()
    assert payload["model"] == "smart-embed"
    assert payload["input"] == "single string"
    assert payload["dimensions"] == 256
