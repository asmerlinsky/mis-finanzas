from datetime import date

from fastapi import APIRouter

from mis_finanzas.api.deps import SessionDep
from mis_finanzas.api.schemas import CategoryTotalOut, MarketStatusOut, MonthSummaryOut
from mis_finanzas.market.fx import load_rate_table, rate_status
from mis_finanzas.reports.summary import expenses_by_category, monthly_summary

router = APIRouter(tags=["reports"])


@router.get("/reports/monthly", response_model=list[MonthSummaryOut])
def monthly(start: date, end: date, session: SessionDep) -> list[MonthSummaryOut]:
    return [
        MonthSummaryOut(
            month=m.month,
            income_ars=m.income.ars,
            income_usd=m.income.usd,
            expense_ars=m.expense.ars,
            expense_usd=m.expense.usd,
            net_ars=m.income.ars - m.expense.ars,
            net_usd=m.income.usd - m.expense.usd,
            missing_rate=m.income.missing_rate + m.expense.missing_rate,
        )
        for m in monthly_summary(session, start, end)
    ]


@router.get("/reports/categories", response_model=list[CategoryTotalOut])
def by_category(start: date, end: date, session: SessionDep) -> list[CategoryTotalOut]:
    return [
        CategoryTotalOut(category=name, ars=t.ars, usd=t.usd, missing_rate=t.missing_rate)
        for name, t in expenses_by_category(session, start, end).items()
    ]


@router.get("/market/status", response_model=MarketStatusOut)
def market_status(session: SessionDep) -> MarketStatusOut:
    status = rate_status(session, date.today())
    latest = load_rate_table(session).rate_on(status.latest_date) if status.latest_date else None
    return MarketStatusOut(
        latest_rate_date=status.latest_date, latest_rate=latest, stale=status.stale
    )
