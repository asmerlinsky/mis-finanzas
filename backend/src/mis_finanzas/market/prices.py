"""Public instrument prices: whole market panels, downloaded at most once a day.

A panel holds every listed symbol of a kind, so the request says nothing about what the owner
holds. Never request one ticker.
"""

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from mis_finanzas.market.http import PublicHttpClient
from mis_finanzas.market.models import InstrumentPrice

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PriceQuote:
    panel: str
    symbol: str
    price: Decimal


class PriceSource(Protocol):
    name: str

    def fetch(self, client: PublicHttpClient) -> list[PriceQuote]: ...


def _quote(panel: str, item: Any) -> PriceQuote | None:
    """None for a symbol with no trade (price 0) or a malformed row."""
    try:
        price = Decimal(str(item["c"]))
        symbol = str(item["symbol"]).strip().upper()
    except (KeyError, TypeError, InvalidOperation):
        return None
    return PriceQuote(panel, symbol, price) if symbol and price > 0 else None


class Data912PanelsSource:
    """data912.com live panels: last price `c` per `symbol`. Bonds quote per 100 nominal."""

    name = "data912:panels"
    base_url = "https://data912.com/live/"
    panels = ("arg_cedears", "arg_stocks", "arg_bonds", "arg_corp")

    def fetch(self, client: PublicHttpClient) -> list[PriceQuote]:
        quotes: list[PriceQuote] = []
        for panel in self.panels:
            payload = client.get_json(self.base_url + panel)
            if not isinstance(payload, list):
                raise ValueError(f"{self.name}: {panel} is not a list")
            found = [q for q in (_quote(panel, item) for item in payload) if q is not None]
            quotes.extend(found)
            logger.info(
                "Price panel read",
                extra={"panel": panel, "rows": len(payload), "priced": len(found)},
            )
        return quotes


def upsert_prices(session: Session, source: str, day: date, quotes: list[PriceQuote]) -> int:
    """Store each symbol's price for `day`; a symbol in two panels keeps the first."""
    existing = {
        p.symbol: p
        for p in session.scalars(select(InstrumentPrice).where(InstrumentPrice.date == day))
    }
    written = 0
    for quote in quotes:
        row = existing.get(quote.symbol)
        if row is None:
            row = InstrumentPrice(
                symbol=quote.symbol, date=day, price=quote.price, panel=quote.panel, source=source
            )
            session.add(row)
            existing[quote.symbol] = row
        elif row.panel != quote.panel or row.price == quote.price:
            continue
        else:
            row.price = quote.price
        written += 1
    return written


def latest_prices(
    session: Session, symbols: set[str], on_or_before: date
) -> dict[str, InstrumentPrice]:
    """Each symbol's most recent stored price up to `on_or_before`."""
    if not symbols:
        return {}
    query = (
        select(InstrumentPrice)
        .where(InstrumentPrice.symbol.in_(symbols), InstrumentPrice.date <= on_or_before)
        .order_by(InstrumentPrice.date)
    )
    return {p.symbol: p for p in session.scalars(query)}
