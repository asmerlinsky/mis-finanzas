from datetime import date

from fastapi import APIRouter
from sqlalchemy import select

from mis_finanzas.api.deps import SessionDep
from mis_finanzas.api.schemas import (
    AllocationOut,
    CashValueOut,
    HistoryPointOut,
    InstrumentDividendsOut,
    MonthAmountOut,
    PortfolioOut,
    PositionValueOut,
    PriceOut,
)
from mis_finanzas.investments.models import Instrument
from mis_finanzas.investments.valuation import PositionValue, value_history, value_portfolio
from mis_finanzas.reports.summary import category_by_instrument, category_by_month

router = APIRouter(tags=["investments"])

DIVIDENDS_CATEGORY = "Dividendos"


def _position_out(p: PositionValue) -> PositionValueOut:
    price = p.price
    return PositionValueOut(
        ticker=p.ticker,
        name=p.name,
        asset_class=p.asset_class,
        quantity=p.quantity,
        price=PriceOut(price=price.price, date=price.day, origin=price.origin.value)
        if price
        else None,
        value_ars=p.value_ars,
        value_usd=p.value_usd,
        coverage=p.coverage,
        cost_ars=p.cost_ars,
        cost_usd=p.cost_usd,
        gain_ars=p.gain_ars,
        gain_usd=p.gain_usd,
    )


@router.get("/investments/portfolio", response_model=PortfolioOut)
def portfolio(session: SessionDep) -> PortfolioOut:
    result = value_portfolio(session, date.today())
    return PortfolioOut(
        as_of=result.as_of,
        quantities_as_of=result.quantities_as_of,
        cash_as_of=result.cash_as_of,
        total_ars=result.total_ars,
        total_usd=result.total_usd,
        missing_price=result.missing_price,
        positions=[_position_out(p) for p in result.positions],
        cash=[
            CashValueOut(
                label=c.label,
                currency=c.currency,
                amount=c.amount,
                value_ars=c.value_ars,
                value_usd=c.value_usd,
            )
            for c in result.cash
        ],
        allocation=[
            AllocationOut(asset_class=name, ars=ars)
            for name, ars in sorted(result.allocation.items(), key=lambda item: -item[1])
        ],
        cost_ars=result.cost_ars,
        gain_ars=result.gain_ars,
        cost_usd=result.cost_usd,
        gain_usd=result.gain_usd,
    )


@router.get("/investments/history", response_model=list[HistoryPointOut])
def history(session: SessionDep) -> list[HistoryPointOut]:
    """The portfolio's value on each holdings statement's date and each day with prices."""
    return [
        HistoryPointOut(date=p.day, ars=p.total_ars, usd=p.total_usd, source=p.source.value)
        for p in value_history(session, date.today())
    ]


@router.get("/investments/dividends/by-instrument", response_model=list[InstrumentDividendsOut])
def dividends_by_instrument(
    start: date, end: date, session: SessionDep
) -> list[InstrumentDividendsOut]:
    """Net dividends per instrument (dividends minus the fees charged on them)."""
    names = {i.ticker: i.name for i in session.scalars(select(Instrument))}
    return [
        InstrumentDividendsOut(
            ticker=item.ticker,
            name=names.get(item.ticker),
            ars=item.totals.ars,
            usd=item.totals.usd,
            payments=item.payments,
            missing_rate=item.totals.missing_rate,
        )
        for item in category_by_instrument(session, DIVIDENDS_CATEGORY, start, end)
    ]


@router.get("/investments/dividends", response_model=list[MonthAmountOut])
def dividends(start: date, end: date, session: SessionDep) -> list[MonthAmountOut]:
    """Net dividends per month: the dividends minus the fees charged on them."""
    return [
        MonthAmountOut(month=month, ars=t.ars, usd=t.usd, missing_rate=t.missing_rate)
        for month, t in category_by_month(session, DIVIDENDS_CATEGORY, start, end)
    ]
