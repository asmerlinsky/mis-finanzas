"""Public FX rate sources. Each source is an adapter: unofficial APIs change, so swap freely."""

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

from mis_finanzas.market.http import PublicHttpClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RateQuote:
    date: date
    buy: Decimal
    sell: Decimal


class RateSource(Protocol):
    name: str

    def fetch(self, client: PublicHttpClient) -> list[RateQuote]: ...


def _parse_quote(item: Any) -> RateQuote:
    return RateQuote(
        date=date.fromisoformat(item["fecha"]),
        buy=Decimal(str(item["compra"])),
        sell=Decimal(str(item["venta"])),
    )


class ArgentinaDatosMepSource:
    """Full daily MEP ("bolsa") history in one request, from 2018 to today."""

    name = "argentinadatos:mep"
    url = "https://api.argentinadatos.com/v1/cotizaciones/dolares/bolsa"

    def fetch(self, client: PublicHttpClient) -> list[RateQuote]:
        payload = client.get_json(self.url)
        if not isinstance(payload, list):
            raise ValueError(f"{self.name}: expected a list, got {type(payload).__name__}")
        quotes = []
        skipped = 0
        for item in payload:
            try:
                quotes.append(_parse_quote(item))
            except (KeyError, TypeError, ValueError, InvalidOperation):
                skipped += 1
        if skipped:
            logger.warning(
                "Skipped malformed rate rows", extra={"source": self.name, "skipped": skipped}
            )
        return quotes
