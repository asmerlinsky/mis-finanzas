"""Where the owner stands in the monotributo: pure functions over invoice totals in pesos.

- **Last 12 months:** gross income invoiced from a year ago (exclusive) to today, against
  the current category's cap. Warnings at 80%, 90% and 100% of it.
- **Next recategorization** (RG 5637/2025): deadlines 5 February and 5 August. February
  looks at the 12 months ending 31 December, August at those ending 30 June. The category
  those months imply is the lowest whose cap covers them.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from mis_finanzas.monotributo.categories import Category, CategoryTable

WARNING_LEVELS = (Decimal("0.8"), Decimal("0.9"), Decimal(1))
RECATEGORIZATION_DAY = 5


@dataclass(frozen=True)
class Window:
    start: date
    end: date  # inclusive

    def total(self, invoices: Iterable[tuple[date, Decimal]]) -> Decimal:
        return sum((ars for day, ars in invoices if self.start <= day <= self.end), Decimal(0))


@dataclass(frozen=True)
class Recategorization:
    deadline: date
    window: Window
    income: Decimal  # invoiced so far within the window
    implied: Category | None  # None: above the highest category


@dataclass(frozen=True)
class Status:
    today: date
    table: CategoryTable
    category: Category | None  # the owner's current one, once set
    last_12_months: Window
    income: Decimal
    usage: Decimal | None  # income / cap
    level: Decimal | None  # the highest warning level reached (0.8, 0.9, 1), if any
    margin: Decimal | None  # what can still be invoiced before reaching the cap
    next: Recategorization


def year_before(day: date) -> date:
    """The same day a year earlier (28 February for 29 February)."""
    try:
        return day.replace(year=day.year - 1)
    except ValueError:
        return day.replace(year=day.year - 1, day=28)


def last_12_months(today: date) -> Window:
    return Window(year_before(today) + timedelta(days=1), today)


def next_recategorization_window(today: date) -> tuple[date, Window]:
    """The next deadline on or after `today`, and the 12 months it looks at."""
    february = date(today.year, 2, RECATEGORIZATION_DAY)
    august = date(today.year, 8, RECATEGORIZATION_DAY)
    if today <= february:
        return february, Window(date(today.year - 1, 1, 1), date(today.year - 1, 12, 31))
    if today <= august:
        return august, Window(date(today.year - 1, 7, 1), date(today.year, 6, 30))
    return date(today.year + 1, 2, RECATEGORIZATION_DAY), Window(
        date(today.year, 1, 1), date(today.year, 12, 31)
    )


def warning_level(usage: Decimal) -> Decimal | None:
    reached = [level for level in WARNING_LEVELS if usage >= level]
    return reached[-1] if reached else None


def compute_status(
    invoices: list[tuple[date, Decimal]], table: CategoryTable, letter: str | None, today: date
) -> Status:
    """`invoices`: (issue date, signed total in pesos)."""
    window = last_12_months(today)
    income = window.total(invoices)
    category = table.get(letter) if letter else None
    usage = income / category.annual_cap if category else None
    deadline, recat_window = next_recategorization_window(today)
    recat_income = recat_window.total(invoices)
    return Status(
        today=today,
        table=table,
        category=category,
        last_12_months=window,
        income=income,
        usage=usage,
        level=warning_level(usage) if usage is not None else None,
        margin=category.annual_cap - income if category else None,
        next=Recategorization(deadline, recat_window, recat_income, table.for_income(recat_income)),
    )


def monthly_totals(invoices: Iterable[tuple[date, Decimal]]) -> list[tuple[str, Decimal]]:
    """Invoiced pesos per month ("YYYY-MM"), oldest first."""
    months: dict[str, Decimal] = {}
    for day, ars in invoices:
        key = day.strftime("%Y-%m")
        months[key] = months.get(key, Decimal(0)) + ars
    return sorted(months.items())
