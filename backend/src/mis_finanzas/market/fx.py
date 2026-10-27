"""Convert ARS to USD with the stored MEP rate of a date (or the closest earlier one)."""

from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mis_finanzas.core.money import CENT
from mis_finanzas.market.models import FxRate, RateType


@dataclass(frozen=True)
class RateStatus:
    latest_date: date | None
    stale: bool


class RateTable:
    """ARS-per-USD rates by date. Weekends and holidays use the last business day."""

    def __init__(self, rates: Sequence[tuple[date, Decimal]]) -> None:
        ordered = sorted(rates)
        self._dates = [d for d, _ in ordered]
        self._rates = [r for _, r in ordered]

    def rate_on(self, day: date) -> Decimal | None:
        index = bisect_right(self._dates, day)
        return self._rates[index - 1] if index else None

    def ars_to_usd(self, amount: Decimal, day: date) -> Decimal | None:
        rate = self.rate_on(day)
        if rate is None or rate == 0:
            return None
        return (amount / rate).quantize(CENT)


def load_rate_table(session: Session, rate_type: RateType = RateType.MEP) -> RateTable:
    """Uses the sell rate: what a peso would have cost in dollars that day."""
    rows = session.execute(select(FxRate.date, FxRate.sell).where(FxRate.rate_type == rate_type))
    return RateTable([(d, r) for d, r in rows])


def rate_status(
    session: Session, today: date, max_age_days: int = 4, rate_type: RateType = RateType.MEP
) -> RateStatus:
    """Stale when the newest rate is older than `max_age_days` (covers long weekends)."""
    latest = session.scalar(select(func.max(FxRate.date)).where(FxRate.rate_type == rate_type))
    stale = latest is None or (today - latest).days > max_age_days
    return RateStatus(latest_date=latest, stale=stale)
