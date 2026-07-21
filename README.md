# roadie (Python SDK) — **BETA**

The **server-side** Python SDK for the Roadie AI gateway — chat, embeddings,
streaming, the model catalog, typed errors, and client-token minting. Targets
**Python 3.11+** with **zero required runtime dependencies** (standard library
only).

> **Beta (`0.1.0b1`).** This SDK mirrors the contract of the authoritative
> [TypeScript SDK](../sdk-typescript) and the gateway's `/v1` API. The surface may
> change while we gather feedback. Distributed on PyPI as **`roadie-sdk`**;
> imported as **`roadie`**.

This is a **backend** SDK. It authenticates with a project **secret key**
(`rd_sk_{env}_…`), which is safe in a trusted server environment — so, unlike the
isomorphic TS SDK, there is no browser secret-key guard. For browser / mobile
apps, mint a short-lived **client token** here (server-side) and hand it to the
app.

## Install

```sh
pip install roadie-sdk
```

## Quickstart

```python
import os
from roadie import Roadie

roadie = Roadie(api_key=os.environ["ROADIE_KEY"])

res = roadie.chat.create(
    model="smart",
    messages=[{"role": "user", "content": "Summarize the news."}],
    user={"id": "u_123", "plan": "pro"},
)
print(res.text)          # concatenated assistant text
print(res.usage, res.cost, res.request_id)
```

### Streaming

```python
with roadie.chat.stream(model="smart", messages=messages) as stream:
    for event in stream:
        if event.type == "content_delta":
            print(event["delta"], end="", flush=True)
        elif event.type == "message_end":
            print("\n", event.get("usage"), event.get("cost"))
```

Frames are yielded verbatim as `StreamEvent` objects: `event.type` is the
discriminator and fields are read with `event["delta"]` / `event.get("usage")`.
NDJSON framing is available with `roadie.chat.stream(..., framing="ndjson")`. Using
the stream as a context manager (or fully iterating it) releases the socket.

### Embeddings

```python
res = roadie.embeddings.create(model="smart-embed", input=["hello", "world"])
for row in res.data:
    print(row.index, len(row.embedding))
```

### Model catalog

```python
for model in roadie.models.list().data:
    print(model.id, model.provider, model.capabilities)
```

### Mint a client token for an end user (server-side)

Your backend exchanges an end-user identity for a short-lived client token its
app then uses to call the AI endpoints as that one end user:

```python
token = roadie.client_tokens.create(
    end_user_id="u_123",
    plan="pro",
    ttl_seconds=600,           # gateway clamps to <= 3600
    scopes=["ai.chat", "ai.embed"],
)
# Return token.token to the app; it expires at token.expires_at.
```

## Errors

Every failure is a `RoadieError` subclass carrying `type`, `code`,
`request_id`, `status`, and (where relevant) `retry_after`:

```python
from roadie import RateLimitError, is_roadie_error

try:
    roadie.chat.create(model="smart", messages=messages)
except RateLimitError as err:
    print("retry after", err.retry_after)
except RoadieError as err:
    print(err.type, err.code, err.request_id)
```

Envelope-mapped classes: `InvalidRequestError`, `AuthenticationError`,
`PermissionError`, `NotFoundError`, `RateLimitError`, `QuotaError`,
`BudgetError`, `ProviderError`, `IdempotencyError`, `InternalError`. Client-side:
`APIConnectionError`, `APIConnectionTimeoutError`, `RoadieConfigurationError`.
An unrecognized future error `type` never crashes the SDK — it falls back to a
status-based class while preserving the envelope's message/code/request id.

## Transport behavior

- **Retries** only pre-first-byte, safe-to-repeat failures (network errors,
  `408`, `429`, `5xx`) with exponential backoff + jitter, honoring `Retry-After`
  (`max_retries`, default `2`).
- **Idempotency:** non-streaming `create` calls auto-send an `Idempotency-Key`
  (ULID) that stays stable across retries, so a retried create is de-duplicated.
- **Timeouts:** `timeout` (seconds) applies per request as a socket deadline; a
  fired deadline raises `APIConnectionTimeoutError`. A per-call `timeout=` argument
  overrides the client default.
- **Streaming safety:** the SSE/NDJSON decoders bound their buffer (4 MiB) so a
  hostile or buggy upstream line cannot exhaust client memory.
- **Metadata:** `X-Request-Id` and `X-RateLimit-*` are surfaced as
  `result.request_id` / `result.rate_limit`.
- **Identity:** `user` / `metadata` accepted per-call or as client-level defaults.
- `User-Agent: roadie-sdk-python/<version>`.

## Mapping to the TypeScript SDK

| TypeScript                            | Python                                          |
| ------------------------------------- | ----------------------------------------------- |
| `new Roadie({ apiKey })`           | `Roadie(api_key=...)`                         |
| `roadie.chat.create(params)`              | `roadie.chat.create(...)` → `ChatResponse`          |
| `roadie.chat.stream(params)`              | `roadie.chat.stream(...)` → `ChatStream`            |
| `roadie.embeddings.create(params)`        | `roadie.embeddings.create(...)` → `EmbeddingsResponse` |
| _(not in TS SDK)_ `GET /v1/models`    | `roadie.models.list()` → `ModelsPage`               |
| `federatedTokenProvider` (Path B)     | `roadie.client_tokens.create(...)` (Path A, server) |
| `errorFromEnvelope` unknown-type safe | `error_from_envelope` unknown-type safe         |

## Design notes

- **Zero runtime dependencies (stdlib only).** The transport is built on
  `urllib.request` / `http.client`, mirroring the TS SDK's zero-runtime-dependency
  stance and keeping the beta install dependency-light. `httpx` would be marginally
  cleaner for async, but the beta is synchronous and server-side, and stdlib fully
  covers incremental streaming reads.
- **Beta scope (deliberately deferred vs. the TS SDK):** async/`await` client;
  the browser-only secret-key guard and the client-app token cache/refresh
  (`TokenManager`) and federated Path-B provider (all client-app concerns — this is
  a backend SDK); explicit request-cancellation signals; and `roadie.feedback` (the
  gateway endpoint is later-wave). These are documented gaps, not oversights.

## Development

```sh
# From packages/sdk-python/
python -m venv .venv && ./.venv/bin/python -m pip install pytest
./.venv/bin/python -m pytest        # offline; runs against a local mock server
```
