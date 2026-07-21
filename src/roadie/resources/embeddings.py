"""``roadie.embeddings`` — the unified embeddings surface.

:meth:`EmbeddingsResource.create` issues a non-streaming ``POST /v1/embeddings``
(auto ``Idempotency-Key``, retried on transient failures) and returns the typed
:class:`~roadie.types.EmbeddingsResponse`.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence, Union

from .._transport import HttpClient
from ..types import EmbeddingsResponse
from ._shared import IdentityDefaults, apply_identity_defaults, attach_metadata, prune_none


class EmbeddingsResource:
    def __init__(self, http: HttpClient, defaults: IdentityDefaults) -> None:
        self._http = http
        self._defaults = defaults

    def create(
        self,
        *,
        model: str,
        input: Union[str, Sequence[str]],
        dimensions: Optional[int] = None,
        user: Optional[Mapping[str, Any]] = None,
        metadata: Optional[Mapping[str, str]] = None,
        provider_options: Optional[Mapping[str, Mapping[str, Any]]] = None,
        timeout: Optional[float] = None,
    ) -> EmbeddingsResponse:
        body = prune_none(
            {
                "model": model,
                "input": list(input) if isinstance(input, (list, tuple)) else input,
                "dimensions": dimensions,
                "user": dict(user) if user is not None else None,
                "metadata": dict(metadata) if metadata is not None else None,
                "provider_options": provider_options,
            }
        )
        apply_identity_defaults(body, self._defaults)
        data, headers = self._http.request_json(
            method="POST", path="/v1/embeddings", body=body, idempotent=True, timeout=timeout
        )
        return attach_metadata(EmbeddingsResponse.from_dict(data), headers)
