"""``roadie.client_tokens`` — server-side client-token minting.

A customer BACKEND (authenticated with a secret key) exchanges an end-user
identity for a short-lived client token its app then uses to call the AI
endpoints as that one end user — the "Path A" backend mint.

This is the SERVER-SIDE counterpart of the TS SDK's ``federatedTokenProvider``
(which does the browser/no-backend "Path B" exchange with a publishable key). The
Python SDK is a backend SDK, so it implements the secret-key backend mint.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from .._transport import HttpClient
from ..types import ClientToken
from ._shared import attach_metadata, prune_none


class ClientTokensResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def create(
        self,
        *,
        end_user_id: str,
        plan: Optional[str] = None,
        attributes: Optional[Mapping[str, Any]] = None,
        ttl_seconds: Optional[int] = None,
        scopes: Optional[Sequence[str]] = None,
        timeout: Optional[float] = None,
    ) -> ClientToken:
        """Mint a short-lived client token for one end user (``POST /v1/client-tokens``).

        Args:
            end_user_id: The end user's stable external id in your system.
            plan: Optional plan tag for per-plan limits/budgets.
            attributes: Optional end-user attributes (JSON, ≤4 KB) persisted on first mint.
            ttl_seconds: Requested token lifetime; the gateway clamps to ≤3600.
            scopes: Requested client-token scopes; omit for the default set.
        """
        end_user: dict[str, Any] = prune_none(
            {
                "id": end_user_id,
                "plan": plan,
                "attributes": dict(attributes) if attributes is not None else None,
            }
        )
        body = prune_none(
            {
                "end_user": end_user,
                "ttl_seconds": ttl_seconds,
                "scopes": list(scopes) if scopes is not None else None,
            }
        )
        data, headers = self._http.request_json(
            method="POST", path="/v1/client-tokens", body=body, idempotent=False, timeout=timeout
        )
        return attach_metadata(ClientToken.from_dict(data), headers)
