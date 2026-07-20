"""Shared resource helpers: client-level identity defaults (``user`` / ``metadata``)
and response-metadata attachment. Mirrors the TS SDK's ``resources/shared.ts``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, MutableMapping, Optional, TypeVar

from .._metadata import Headers, parse_rate_limit, request_id_from


@dataclass(frozen=True)
class IdentityDefaults:
    """Client-level identity defaults applied when a call omits them (§28)."""

    user: Optional[Mapping[str, Any]] = None
    metadata: Optional[Mapping[str, str]] = None


def apply_identity_defaults(
    body: MutableMapping[str, Any], defaults: IdentityDefaults
) -> MutableMapping[str, Any]:
    """Fill ``user`` / ``metadata`` from client defaults.

    A per-call ``user`` replaces the default outright; per-call ``metadata`` is
    shallow-merged over the default (per-call keys win).
    """
    if body.get("user") is None and defaults.user is not None:
        body["user"] = dict(defaults.user)

    call_metadata = body.get("metadata")
    if defaults.metadata is not None or call_metadata is not None:
        merged: dict[str, str] = {}
        if defaults.metadata is not None:
            merged.update(defaults.metadata)
        if isinstance(call_metadata, Mapping):
            merged.update(call_metadata)
        if merged:
            body["metadata"] = merged
    return body


def prune_none(body: MutableMapping[str, Any]) -> dict[str, Any]:
    """Drop keys whose value is ``None`` so optional params are omitted from the wire body."""
    return {key: value for key, value in body.items() if value is not None}


_T = TypeVar("_T")


def attach_metadata(obj: _T, headers: Headers) -> _T:
    """Set ``request_id`` and ``rate_limit`` on a parsed response object from the headers."""
    setattr(obj, "request_id", request_id_from(headers))
    setattr(obj, "rate_limit", parse_rate_limit(headers))
    return obj
