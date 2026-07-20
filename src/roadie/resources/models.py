"""``bp.models`` — the model catalog (plan §21.2).

:meth:`ModelsResource.list` issues ``GET /v1/models`` and returns the catalog this
credential may use, narrowed by the credential's restrictions, each entry carrying
the model's capabilities.
"""

from __future__ import annotations

from typing import Optional

from .._transport import HttpClient
from ..types import ModelsPage
from ._shared import attach_metadata


class ModelsResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def list(self, *, timeout: Optional[float] = None) -> ModelsPage:
        """Return the model catalog available to this credential."""
        data, headers = self._http.request_json(method="GET", path="/v1/models", timeout=timeout)
        return attach_metadata(ModelsPage.from_dict(data), headers)
