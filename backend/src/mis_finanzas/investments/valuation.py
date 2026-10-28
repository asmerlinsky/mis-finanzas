"""What the portfolio is worth today, in ARS and USD MEP.

- **Quantities:** each broker's latest snapshot (holdings or movements statement), plus the
  operations traded after it.
- **Price:** the newer of the latest public market price and the latest holdings statement's
  price.
- **Units:** panels quote bonds per 100 nominal, statements may not. The latest holdings
  statement says what a position was worth, so `value / (quantity * price)`, rounded to a
  power of ten, gives each instrument's factor: 1 for shares and CEDEARs, 0.01 for bonds
  quoted per 100. Without a holdings statement the factor is 1.
- **Cash:** the latest holdings statement's currency lines. (The ledger has no opening balance
  for broker accounts, so their transactions don't add up to the cash held.)
- Values are in pesos: the panels used quote in pesos, and so do the statements.
"""

import enum
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from mis_finanzas.core.money import CENT
from mis_finanzas.investments.models import (
    HoldingPosition,
    HoldingSnapshot,
    Instrument,
    InvestmentOperation,
)
from mis_finanzas.investments.records import SnapshotSource
from mis_finanzas.market.fx import RateTable, load_rate_table
from mis_finanzas.market.models import InstrumentPrice
from mis_finanzas.market.prices import latest_prices

UNCLASSIFIED = "Sin clasificar"
CASH_CLASS = "Monedas"


class PriceOrigin(enum.StrEnum):
    MARKET = "mercado"
    STATEMENT = "resumen"


@dataclass(frozen=True)
class Priced:
    price: Decimal
    day: date
    origin: PriceOrigin


@dataclass(frozen=True)
class PositionValue:
    ticker: str
    name: str
    asset_class: str
    quantity: Decimal
    price: Priced | None
    value_ars: Decimal | None
    value_usd: Decimal | None


@dataclass(frozen=True)
class CashValue:
    label: str
    currency: str
    amount: Decimal
    value_ars: Decimal | None
    value_usd: Decimal | None


@dataclass
class Portfolio:
    as_of: date
    quantities_as_of: date | None = None
    cash_as_of: date | None = None
    positions: list[PositionValue] = field(default_factory=list)
    cash: list[CashValue] = field(default_factory=list)
    total_ars: Decimal = Decimal(0)
    total_usd: Decimal | None = None
    missing_price: int = 0
    allocation: dict[str, Decimal] = field(default_factory=dict)  # asset class -> ARS


@dataclass(frozen=True)
class _Reference:
    """A holdings statement's line for an instrument: what it was worth on `day`."""

    position: HoldingPosition
    day: date


def power_of_ten(ratio: Decimal) -> Decimal:
    """The power of ten closest to `ratio` (on a log scale): 0.0098 -> 0.01, 1.03 -> 1."""
    return Decimal(10) ** int(ratio.log10().to_integral_value())


def _latest_snapshots(session: Session, source: SnapshotSource | None) -> list[HoldingSnapshot]:
    """Each broker's most recent snapshot; holdings win a tie with movements (sorted last)."""
    query = select(HoldingSnapshot).order_by(HoldingSnapshot.as_of, HoldingSnapshot.source)
    if source is not None:
        query = query.where(HoldingSnapshot.source == source)
    latest: dict[str, HoldingSnapshot] = {}
    for snapshot in session.scalars(query):
        latest[snapshot.broker] = snapshot
    return list(latest.values())


def _quantities(session: Session, snapshots: list[HoldingSnapshot]) -> dict[int, Decimal]:
    """Instrument id -> quantity: the snapshot's, plus operations traded after it."""
    held: dict[int, Decimal] = defaultdict(Decimal)
    for snapshot in snapshots:
        for position in snapshot.positions:
            held[position.instrument_id] += position.quantity
        later = select(InvestmentOperation).where(
            InvestmentOperation.broker == snapshot.broker,
            InvestmentOperation.trade_date > snapshot.as_of,
        )
        for operation in session.scalars(later):
            held[operation.instrument_id] += operation.quantity
    return {k: v for k, v in held.items() if v != 0}


def _references(snapshots: list[HoldingSnapshot]) -> dict[int, _Reference]:
    return {
        p.instrument_id: _Reference(p, s.as_of)
        for s in snapshots
        for p in s.positions
        if p.price is not None and p.value is not None and p.quantity != 0
    }


def _price(market: InstrumentPrice | None, reference: _Reference | None) -> Priced | None:
    statement_price = reference.position.price if reference else None
    if market is not None and (
        reference is None or statement_price is None or market.date >= reference.day
    ):
        return Priced(market.price, market.date, PriceOrigin.MARKET)
    if reference is not None and statement_price is not None:
        return Priced(statement_price, reference.day, PriceOrigin.STATEMENT)
    return None


def _factor(price: Decimal, reference: _Reference | None) -> Decimal:
    if reference is None or reference.position.value is None or price == 0:
        return Decimal(1)
    ratio = reference.position.value / (reference.position.quantity * price)
    return power_of_ten(ratio) if ratio > 0 else Decimal(1)


def _position_value(
    instrument: Instrument,
    quantity: Decimal,
    price: Priced | None,
    reference: _Reference | None,
    usd_rate: Decimal | None,
) -> PositionValue:
    value = None
    if price is not None:
        value = (quantity * price.price * _factor(price.price, reference)).quantize(CENT)
    return PositionValue(
        ticker=instrument.ticker,
        name=instrument.name,
        asset_class=instrument.asset_class or UNCLASSIFIED,
        quantity=quantity,
        price=price,
        value_ars=value,
        value_usd=(value / usd_rate).quantize(CENT) if value is not None and usd_rate else None,
    )


def _cash(snapshots: list[HoldingSnapshot], usd_rate: Decimal | None) -> list[CashValue]:
    lines = []
    for line in (c for s in snapshots for c in s.cash):
        if line.currency == "USD":
            ars = (line.amount * usd_rate).quantize(CENT) if usd_rate else None
            usd: Decimal | None = line.amount
        else:
            ars = line.amount
            usd = (line.amount / usd_rate).quantize(CENT) if usd_rate else None
        lines.append(CashValue(line.label, line.currency, line.amount, ars, usd))
    return lines


def _positions(
    session: Session, snapshots: list[HoldingSnapshot], today: date, usd_rate: Decimal | None
) -> list[PositionValue]:
    quantities = _quantities(session, snapshots)
    instruments = {
        i.id: i for i in session.scalars(select(Instrument).where(Instrument.id.in_(quantities)))
    }
    references = _references(_latest_snapshots(session, SnapshotSource.HOLDINGS))
    market = latest_prices(session, {i.ticker for i in instruments.values()}, today)
    values = []
    for instrument_id, quantity in quantities.items():
        instrument = instruments[instrument_id]
        reference = references.get(instrument_id)
        price = _price(market.get(instrument.ticker), reference)
        values.append(_position_value(instrument, quantity, price, reference, usd_rate))
    return sorted(values, key=lambda p: (p.asset_class, -(p.value_ars or 0), p.ticker))


def _totals(portfolio: Portfolio, rates: RateTable) -> None:
    allocation: dict[str, Decimal] = defaultdict(Decimal)
    for position in portfolio.positions:
        allocation[position.asset_class] += position.value_ars or 0
    for line in portfolio.cash:
        allocation[CASH_CLASS] += line.value_ars or 0
    portfolio.allocation = dict(allocation)
    portfolio.total_ars = sum(allocation.values(), Decimal(0))
    portfolio.missing_price = sum(p.value_ars is None for p in portfolio.positions)
    portfolio.total_usd = rates.ars_to_usd(portfolio.total_ars, portfolio.as_of)


def value_portfolio(session: Session, today: date) -> Portfolio:
    rates = load_rate_table(session)
    usd_rate = rates.rate_on(today)
    snapshots = _latest_snapshots(session, None)
    holdings = _latest_snapshots(session, SnapshotSource.HOLDINGS)
    portfolio = Portfolio(
        as_of=today,
        quantities_as_of=max((s.as_of for s in snapshots), default=None),
        cash_as_of=max((s.as_of for s in holdings), default=None),
        positions=_positions(session, snapshots, today, usd_rate),
        cash=_cash(holdings, usd_rate),
    )
    _totals(portfolio, rates)
    return portfolio
