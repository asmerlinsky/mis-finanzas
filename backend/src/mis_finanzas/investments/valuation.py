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
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from mis_finanzas.core.money import CENT
from mis_finanzas.investments.cost_basis import CostBasis, cost_basis, opening_quantity
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
HISTORY_DAYS = 365
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
    # Cost and gain of the part whose cost is known (`coverage` of the quantity); None when
    # no part is.
    coverage: Decimal | None = None
    cost_ars: Decimal | None = None
    cost_usd: Decimal | None = None
    gain_ars: Decimal | None = None
    gain_usd: Decimal | None = None


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
    # Over the parts of positions whose cost is known.
    cost_ars: Decimal = Decimal(0)
    gain_ars: Decimal = Decimal(0)
    cost_usd: Decimal = Decimal(0)
    gain_usd: Decimal = Decimal(0)


@dataclass(frozen=True)
class HistoryPoint:
    day: date
    total_ars: Decimal
    total_usd: Decimal | None
    source: PriceOrigin  # STATEMENT: a holdings statement's date; MARKET: a price download


@dataclass(frozen=True)
class _Reference:
    """A holdings statement's line for an instrument: what it was worth on `day`."""

    position: HoldingPosition
    day: date


def power_of_ten(ratio: Decimal) -> Decimal:
    """The power of ten closest to `ratio` (on a log scale): 0.0098 -> 0.01, 1.03 -> 1."""
    return Decimal(10) ** int(ratio.log10().to_integral_value())


def _latest_snapshots(
    session: Session, source: SnapshotSource | None, day: date
) -> list[HoldingSnapshot]:
    """Each broker's most recent snapshot on or before `day`; holdings win a tie with
    movements (sorted last)."""
    query = (
        select(HoldingSnapshot)
        .where(HoldingSnapshot.as_of <= day)
        .order_by(HoldingSnapshot.as_of, HoldingSnapshot.source)
    )
    if source is not None:
        query = query.where(HoldingSnapshot.source == source)
    latest: dict[str, HoldingSnapshot] = {}
    for snapshot in session.scalars(query):
        latest[snapshot.broker] = snapshot
    return list(latest.values())


def _quantities(
    session: Session, snapshots: list[HoldingSnapshot], day: date
) -> dict[int, Decimal]:
    """Instrument id -> quantity: the snapshot's, plus operations traded after it, to `day`."""
    held: dict[int, Decimal] = defaultdict(Decimal)
    for snapshot in snapshots:
        for position in snapshot.positions:
            held[position.instrument_id] += position.quantity
        later = select(InvestmentOperation).where(
            InvestmentOperation.broker == snapshot.broker,
            InvestmentOperation.trade_date > snapshot.as_of,
            InvestmentOperation.trade_date <= day,
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


def _gain(value: Decimal | None, coverage: Decimal, cost: Decimal) -> Decimal | None:
    return (value * coverage - cost).quantize(CENT) if value is not None else None


def _with_cost(position: PositionValue, basis: CostBasis | None) -> PositionValue:
    coverage = basis.coverage if basis else None
    if basis is None or not coverage:
        return position
    return replace(
        position,
        coverage=coverage,
        cost_ars=basis.cost_ars.quantize(CENT),
        cost_usd=basis.cost_usd.quantize(CENT),
        gain_ars=_gain(position.value_ars, coverage, basis.cost_ars),
        gain_usd=_gain(position.value_usd, coverage, basis.cost_usd),
    )


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


def _cost_bases(
    session: Session, instrument_ids: set[int], day: date, rates: RateTable
) -> dict[int, CostBasis]:
    """Average cost of each instrument held, from the trades and snapshots up to `day`."""
    trades = session.scalars(
        select(InvestmentOperation).where(
            InvestmentOperation.instrument_id.in_(instrument_ids),
            InvestmentOperation.trade_date <= day,
        )
    )
    by_instrument: dict[int, list[InvestmentOperation]] = defaultdict(list)
    for trade in trades:
        by_instrument[trade.instrument_id].append(trade)
    held: dict[int, list[tuple[date, Decimal]]] = defaultdict(list)
    query = select(HoldingSnapshot).where(HoldingSnapshot.as_of <= day)
    for snapshot in session.scalars(query):
        for p in snapshot.positions:
            if p.instrument_id in instrument_ids:
                held[p.instrument_id].append((snapshot.as_of, p.quantity))
    bases = {}
    for instrument_id in instrument_ids:
        own = by_instrument.get(instrument_id, [])
        opening = opening_quantity(held.get(instrument_id, []), own)
        bases[instrument_id] = cost_basis(own, opening, rates.rate_on)
    return bases


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
    session: Session, snapshots: list[HoldingSnapshot], today: date, rates: RateTable
) -> list[PositionValue]:
    quantities = _quantities(session, snapshots, today)
    instruments = {
        i.id: i for i in session.scalars(select(Instrument).where(Instrument.id.in_(quantities)))
    }
    references = _references(_latest_snapshots(session, SnapshotSource.HOLDINGS, today))
    market = latest_prices(session, {i.ticker for i in instruments.values()}, today)
    bases = _cost_bases(session, set(quantities), today, rates)
    usd_rate = rates.rate_on(today)
    values = []
    for instrument_id, quantity in quantities.items():
        instrument = instruments[instrument_id]
        reference = references.get(instrument_id)
        price = _price(market.get(instrument.ticker), reference)
        position = _position_value(instrument, quantity, price, reference, usd_rate)
        values.append(_with_cost(position, bases.get(instrument_id)))
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
    known = [p for p in portfolio.positions if p.cost_ars is not None]
    portfolio.cost_ars = sum((p.cost_ars or Decimal(0) for p in known), Decimal(0))
    portfolio.gain_ars = sum((p.gain_ars or Decimal(0) for p in known), Decimal(0))
    portfolio.cost_usd = sum((p.cost_usd or Decimal(0) for p in known), Decimal(0))
    portfolio.gain_usd = sum((p.gain_usd or Decimal(0) for p in known), Decimal(0))


def value_portfolio(session: Session, today: date, rates: RateTable | None = None) -> Portfolio:
    """The portfolio as of `today`: only snapshots, trades and prices up to that day count."""
    rates = rates or load_rate_table(session)
    snapshots = _latest_snapshots(session, None, today)
    holdings = _latest_snapshots(session, SnapshotSource.HOLDINGS, today)
    portfolio = Portfolio(
        as_of=today,
        quantities_as_of=max((s.as_of for s in snapshots), default=None),
        cash_as_of=max((s.as_of for s in holdings), default=None),
        positions=_positions(session, snapshots, today, rates),
        cash=_cash(holdings, rates.rate_on(today)),
    )
    _totals(portfolio, rates)
    return portfolio


def value_history(session: Session, today: date, days: int = HISTORY_DAYS) -> list[HistoryPoint]:
    """The portfolio's value on each holdings statement's date, and on each day with
    downloaded prices in the last `days` days."""
    statements = set(
        session.scalars(
            select(HoldingSnapshot.as_of).where(
                HoldingSnapshot.source == SnapshotSource.HOLDINGS, HoldingSnapshot.as_of <= today
            )
        )
    )
    since = today - timedelta(days=days)
    priced = set(
        session.scalars(
            select(InstrumentPrice.date)
            .where(InstrumentPrice.date >= since, InstrumentPrice.date <= today)
            .distinct()
        )
    )
    rates = load_rate_table(session)
    points = []
    for day in sorted(statements | priced):
        portfolio = value_portfolio(session, day, rates)
        if portfolio.quantities_as_of is None:
            continue  # nothing known to be held yet
        source = PriceOrigin.STATEMENT if day in statements else PriceOrigin.MARKET
        points.append(HistoryPoint(day, portfolio.total_ars, portfolio.total_usd, source))
    return points
