from datetime import date

from fastapi import APIRouter

from mis_finanzas.api.deps import SessionDep
from mis_finanzas.api.schemas import (
    AllocationOut,
    CashValueOut,
    MonthAmountOut,
    PortfolioOut,
    PositionValueOut,
    PriceOut,
)
from mis_finanzas.investments.valuation import PositionValue, value_portfolio
from mis_finanzas.reports.summary import category_by_month

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
    )


@router.get("/investments/dividends", response_model=list[MonthAmountOut])
def dividends(start: date, end: date, session: SessionDep) -> list[MonthAmountOut]:
    """Net dividends per month: the dividends minus the fees charged on them."""
    return [
        MonthAmountOut(month=month, ars=t.ars, usd=t.usd, missing_rate=t.missing_rate)
        for month, t in category_by_month(session, DIVIDENDS_CATEGORY, start, end)
    ]
