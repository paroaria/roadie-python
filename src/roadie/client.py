"""The :class:`Roadie` client — the server-side entry point.

    from roadie import Roadie

    roadie = Roadie(api_key=os.environ["ROADIE_KEY"])
    res = roadie.chat.create(model="smart", messages=[{"role": "user", "content": "Hi"}])

The Python SDK is a BACKEND SDK: it authenticates with a secret key
(``rd_sk_...``), which is safe in a trusted server environment. There is
therefore no browser secret-key guard (that guard exists in the isomorphic TS
SDK because it also runs in browsers).
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from ._transport import DEFAULT_BASE_URL, HttpClient
from .errors import RoadieConfigurationError
from .resources._shared import IdentityDefaults
from .resources.chat import ChatResource
from .resources.client_tokens import ClientTokensResource
from .resources.embeddings import EmbeddingsResource
from .resources.models import ModelsResource

_DEFAULT_MAX_RETRIES = 2


class Roadie:
    """The Roadie API client.

    Args:
        api_key: The project secret key (``rd_sk_{env}_...``).
        base_url: Data-plane base URL; defaults to ``https://gateway.roadie.paroaria.ai``.
        max_retries: Max automatic retries for transient, pre-first-byte failures.
        timeout: Default per-request deadline in seconds (a per-call ``timeout``
            overrides it). ``None`` means no client-imposed deadline.
        user: Default end-user identity (``{"id": ..., "plan": ...}``), applied when
            a call omits ``user``.
        metadata: Default metadata, shallow-merged under each call's ``metadata``.
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        timeout: Optional[float] = None,
        user: Optional[Mapping[str, Any]] = None,
        metadata: Optional[Mapping[str, str]] = None,
    ) -> None:
        if not isinstance(api_key, str) or api_key == "":
            raise RoadieConfigurationError(
                "Provide a Roadie secret key (`rd_sk_...`) via `api_key`."
            )

        http = HttpClient(
            base_url=base_url,
            auth=lambda: api_key,
            max_retries=max_retries,
            timeout=timeout,
        )
        defaults = IdentityDefaults(user=user, metadata=metadata)

        self.chat = ChatResource(http, defaults)
        self.embeddings = EmbeddingsResource(http, defaults)
        self.models = ModelsResource(http)
        self.client_tokens = ClientTokensResource(http)
