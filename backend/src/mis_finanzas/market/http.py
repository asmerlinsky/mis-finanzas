"""The only way the app talks to the network.

GET only, HTTPS only, allowlisted hosts only, no cookies, no redirects. Callers fetch whole
public datasets; nothing about the owner's accounts or holdings goes into a request.
"""

import logging
from collections.abc import Iterable
from typing import Any
from urllib.parse import urlsplit

import httpx

logger = logging.getLogger(__name__)

USER_AGENT = "mis-finanzas/0.1"


class DisallowedHostError(ValueError):
    pass


class PublicHttpClient:
    def __init__(
        self,
        allowed_hosts: Iterable[str],
        timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._allowed_hosts = frozenset(h.lower() for h in allowed_hosts)
        self._client = httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=False,
            headers={"User-Agent": USER_AGENT},
            transport=transport,
        )

    def check_url(self, url: str) -> None:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        if parts.scheme != "https" or host not in self._allowed_hosts:
            raise DisallowedHostError(f"refusing to contact {parts.scheme}://{host}")

    def get_json(self, url: str) -> Any:
        self.check_url(url)
        logger.info("Public data request", extra={"url": url})
        response = self._client.get(url)
        response.raise_for_status()
        return response.json()

    def close(self) -> None:
        self._client.close()
