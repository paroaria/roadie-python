"""``roadie`` — the server-side Python SDK (BETA) for the Roadie AI gateway.

Chat, embeddings, streaming, the model catalog, typed errors, and server-side
client-token minting. Targets Python 3.11+ with ZERO required runtime
dependencies (stdlib only). Mirrors the authoritative TypeScript SDK contract.

    import os
    from roadie import Roadie

    roadie = Roadie(api_key=os.environ["ROADIE_KEY"])

    res = roadie.chat.create(
        model="smart",
        messages=[{"role": "user", "content": "Summarize the news."}],
        user={"id": "u_123", "plan": "pro"},
    )
    print(res.text, res.usage, res.request_id)
"""

from __future__ import annotations

from ._streaming import ChatStream, StreamEvent
from ._version import VERSION
from .client import Roadie
from .errors import (
    APIConnectionError,
    APIConnectionTimeoutError,
    AuthenticationError,
    RoadieConfigurationError,
    RoadieError,
    BudgetError,
    IdempotencyError,
    InternalError,
    InvalidRequestError,
    NotFoundError,
    PermissionError,
    ProviderError,
    QuotaError,
    RateLimitError,
    is_roadie_error,
)
from ._metadata import RateLimitInfo
from .resources import (
    ChatResource,
    ClientTokensResource,
    EmbeddingsResource,
    ModelsResource,
)
from .types import (
    AssistantMessage,
    ChatResponse,
    ClientToken,
    Cost,
    Embedding,
    EmbeddingsResponse,
    GatewayInfo,
    Model,
    ModelsPage,
    Usage,
)

__version__ = VERSION

__all__ = [
    # Client
    "Roadie",
    "VERSION",
    "__version__",
    # Resources
    "ChatResource",
    "EmbeddingsResource",
    "ModelsResource",
    "ClientTokensResource",
    # Streaming
    "ChatStream",
    "StreamEvent",
    # Response types
    "ChatResponse",
    "EmbeddingsResponse",
    "ModelsPage",
    "Model",
    "ClientToken",
    "AssistantMessage",
    "Usage",
    "Cost",
    "GatewayInfo",
    "Embedding",
    "RateLimitInfo",
    # Errors
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
]
