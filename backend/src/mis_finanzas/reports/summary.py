"""Monthly income/expense totals and category breakdowns, in ARS and in USD at MEP.

Only `income` and `expense` count. Transfers, FX operations and investment moves are money
changing place, not money earned or spent.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from mis_finanzas.core.money import CENT, from_cents
from mis_finanzas.ledger.models import Currency, Transaction, TransactionKind
from mis_finanzas.market.fx import RateTable, load_rate_table

COUNTED_KINDS = (TransactionKind.INCOME, TransactionKind.EXPENSE)
UNCATEGORIZED = "Sin categoría"


@dataclass(frozen=True)
class DualAmount:
    """One amount in both currencies. `usd`/`ars` is None when no rate exists for the date."""

    ars: Decimal | None
    usd: Decimal | None


@dataclass
class Totals:
    ars: Decimal = Decimal(0)
    usd: Decimal = Decimal(0)
    missing_rate: int = 0

    def add(self, amount: DualAmount) -> None:
        if amount.ars is None or amount.usd is None:
            self.missing_rate += 1
        self.ars += amount.ars or 0
        self.usd += amount.usd or 0


@dataclass
class MonthSummary:
    month: str
    income: Totals = field(default_factory=Totals)
    expense: Totals = field(default_factory=Totals)


def to_dual(tx: Transaction, rates: RateTable) -> DualAmount:
    amount = from_cents(tx.amount_cents)
    if tx.account.currency is Currency.USD:
        rate = rates.rate_on(tx.date)
        return DualAmount(ars=(amount * rate).quantize(CENT) if rate else None, usd=amount)
    return DualAmount(ars=amount, usd=rates.ars_to_usd(amount, tx.date))


def _counted_transactions(session: Session, start: date, end: date) -> list[Transaction]:
    query = (
        select(Transaction)
        .where(
            Transaction.date >= start, Transaction.date <= end, Transaction.kind.in_(COUNTED_KINDS)
        )
        .order_by(Transaction.date)
    )
    return list(session.scalars(query))


def monthly_summary(session: Session, start: date, end: date) -> list[MonthSummary]:
    """Expenses are reported as positive totals; refunds in an expense category reduce them."""
    rates = load_rate_table(session)
    months: dict[str, MonthSummary] = {}
    for tx in _counted_transactions(session, start, end):
        key = tx.date.strftime("%Y-%m")
        summary = months.setdefault(key, MonthSummary(month=key))
        dual = to_dual(tx, rates)
        if tx.kind is TransactionKind.INCOME:
            summary.income.add(dual)
        else:
            summary.expense.add(_negate(dual))
    return [months[k] for k in sorted(months)]


def expenses_by_category(session: Session, start: date, end: date) -> dict[str, Totals]:
    rates = load_rate_table(session)
    totals: dict[str, Totals] = defaultdict(Totals)
    for tx in _counted_transactions(session, start, end):
        if tx.kind is TransactionKind.EXPENSE:
            name = tx.category.name if tx.category else UNCATEGORIZED
            totals[name].add(_negate(to_dual(tx, rates)))
    return dict(sorted(totals.items(), key=lambda item: item[1].ars, reverse=True))


def _negate(amount: DualAmount) -> DualAmount:
    return DualAmount(
        ars=None if amount.ars is None else -amount.ars,
        usd=None if amount.usd is None else -amount.usd,
    )
