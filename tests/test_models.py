"""Model catalog: ``GET /v1/models`` request shape and parsing."""

from __future__ import annotations

from roadie import Roadie

from conftest import json_response

_MODELS_BODY = {
    "object": "list",
    "data": [
        {
            "id": "openai/gpt-4o-mini",
            "object": "model",
            "provider": "openai",
            "display_name": "GPT-4o mini",
            "capabilities": {"streaming": True, "tools": True, "json_schema": True},
        },
        {
            "id": "openai/text-embedding-3-small",
            "object": "model",
            "provider": "openai",
            "display_name": "Text Embedding 3 Small",
            "capabilities": {},
        },
    ],
}


def test_models_list_parses_catalog(mock_server):
    mock_server.respond_with(json_response(_MODELS_BODY))
    bp = Roadie(api_key="rd_sk_test_key", base_url=mock_server.base_url)

    page = bp.models.list()

    assert page.object == "list"
    assert len(page.data) == 2
    assert page.data[0].id == "openai/gpt-4o-mini"
    assert page.data[0].provider == "openai"
    assert page.data[0].display_name == "GPT-4o mini"
    assert page.data[0].capabilities["streaming"] is True


def test_models_list_uses_get_without_body(mock_server):
    mock_server.respond_with(json_response(_MODELS_BODY))
    bp = Roadie(api_key="rd_sk_test_key", base_url=mock_server.base_url)

    bp.models.list()

    request = mock_server.captured[0]
    assert request.method == "GET"
    assert request.path == "/v1/models"
    assert request.body == b""
    assert request.headers.get("authorization") == "Bearer rd_sk_test_key"
