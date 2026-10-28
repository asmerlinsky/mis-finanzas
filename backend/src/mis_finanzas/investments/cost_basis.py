"""What the owner paid for each instrument still held: average cost, from imported trades.

- **Currency** of a trade: the last `/` token of its description (`… / usd` → USD, `… / $` →
  ARS), as Balanz prints it. Without one (fund subscriptions, transfers) its cost is unknown.
- **Cost** of a buy: |net|, which includes fees; |gross| + fees when net is missing.
- **Average cost**, per instrument, over trades by date:
  - an *unknown* lot starts with what was held before the first imported trade, inferred
    from the earliest snapshot: its quantity minus the trades up to its date;
  - a buy with a known cost and currency adds to the *known* lot; any other increase to the
    unknown one;
  - a sell or transfer out reduces both lots, and the known cost, in proportion.
- Cost is kept in pesos and in dollars, each trade converted at the MEP of its date.

So a position bought before the first imported statement shows a partial cost: the share
covered by known trades (`coverage`). Importing older statements completes it.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

RateOn = Callable[[date], Decimal | None]


class Trade(Protocol):
    """What a trade needs to have, read-only (an imported `InvestmentOperation` has it)."""

    @property
    def trade_date(self) -> date: ...
    @property
    def description(self) -> str: ...
    @property
    def quantity(self) -> Decimal: ...
    @property
    def gross(self) -> Decimal | None: ...
    @property
    def fees(self) -> Decimal: ...
    @property
    def net(self) -> Decimal | None: ...


@dataclass(frozen=True)
class CostBasis:
    known_quantity: Decimal
    unknown_quantity: Decimal
    cost_ars: Decimal  # of the known quantity
    cost_usd: Decimal

    @property
    def coverage(self) -> Decimal | None:
        """The share of the quantity whose cost is known; None when nothing is held."""
        total = self.known_quantity + self.unknown_quantity
        return self.known_quantity / total if total > 0 else None


def trade_currency(description: str) -> str | None:
    token = description.rsplit("/", 1)[-1].strip().upper() if "/" in description else ""
    return {"USD": "USD", "U$S": "USD", "$": "ARS", "ARS": "ARS"}.get(token)


def trade_cost(trade: Trade) -> Decimal | None:
    if trade.net is not None:
        return abs(trade.net)
    if trade.gross is not None:
        return abs(trade.gross) + trade.fees
    return None


def _priced(trade: Trade, rate_on: RateOn) -> tuple[Decimal, Decimal] | None:
    """(pesos, dollars) the trade cost, or None when its cost or currency is unknown."""
    currency, cost = trade_currency(trade.description), trade_cost(trade)
    rate = rate_on(trade.trade_date)
    if currency is None or cost is None or not rate:
        return None
    return (cost, cost / rate) if currency == "ARS" else (cost * rate, cost)


def cost_basis(trades: Sequence[Trade], opening: Decimal, rate_on: RateOn) -> CostBasis:
    """`opening`: the quantity held before the first trade, of unknown cost."""
    known, unknown = Decimal(0), max(opening, Decimal(0))
    ars, usd = Decimal(0), Decimal(0)
    for trade in sorted(trades, key=lambda t: t.trade_date):
        if trade.quantity > 0:
            priced = _priced(trade, rate_on)
            if priced is None:
                unknown += trade.quantity
            else:
                known, ars, usd = known + trade.quantity, ars + priced[0], usd + priced[1]
        elif trade.quantity < 0 and known + unknown > 0:
            keep = max(Decimal(0), 1 + trade.quantity / (known + unknown))
            known, unknown, ars, usd = known * keep, unknown * keep, ars * keep, usd * keep
    return CostBasis(known, unknown, ars, usd)


def opening_quantity(snapshots: Sequence[tuple[date, Decimal]], trades: Sequence[Trade]) -> Decimal:
    """What was held before the trades: the earliest snapshot, minus the trades up to it."""
    earliest = min(snapshots, default=None, key=lambda s: s[0])
    if earliest is None:
        return Decimal(0)
    day, quantity = earliest
    before = sum((t.quantity for t in trades if t.trade_date <= day), Decimal(0))
    return max(quantity - before, Decimal(0))
