"""Daily refresh of public data. At most one successful download per source per day."""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from mis_finanzas.market.http import PublicHttpClient
from mis_finanzas.market.models import FetchLog, FetchStatus, FxRate, RateType
from mis_finanzas.market.sources import RateQuote, RateSource

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RefreshResult:
    source: str
    status: str  # "ok", "failed" or "skipped"
    rows: int = 0
    error: str | None = None


def fetched_today(session: Session, source: str, today: date) -> bool:
    query = select(FetchLog.id).where(
        FetchLog.source == source,
        FetchLog.run_date == today,
        FetchLog.status == FetchStatus.OK,
    )
    return session.scalars(query).first() is not None


def upsert_rates(
    session: Session, rate_type: RateType, source: str, quotes: Sequence[RateQuote]
) -> int:
    """Insert new days and update changed ones. Returns the number of rows written."""
    existing = {
        r.date: r for r in session.scalars(select(FxRate).where(FxRate.rate_type == rate_type))
    }
    written = 0
    for quote in quotes:
        row = existing.get(quote.date)
        if row is None:
            session.add(
                FxRate(
                    rate_type=rate_type,
                    date=quote.date,
                    buy=quote.buy,
                    sell=quote.sell,
                    source=source,
                )
            )
        elif (row.buy, row.sell) != (quote.buy, quote.sell):
            row.buy, row.sell, row.source = quote.buy, quote.sell, source
        else:
            continue
        written += 1
    return written


def refresh_rates(
    session: Session, client: PublicHttpClient, source: RateSource, rate_type: RateType, today: date
) -> RefreshResult:
    if fetched_today(session, source.name, today):
        return RefreshResult(source=source.name, status="skipped")
    try:
        quotes = source.fetch(client)
    except Exception as exc:
        logger.error("Public data fetch failed", extra={"source": source.name, "error": str(exc)})
        session.add(
            FetchLog(
                source=source.name, run_date=today, status=FetchStatus.FAILED, error=str(exc)[:500]
            )
        )
        session.commit()
        return RefreshResult(source=source.name, status="failed", error=str(exc))
    written = upsert_rates(session, rate_type, source.name, quotes)
    session.add(FetchLog(source=source.name, run_date=today, status=FetchStatus.OK, rows=written))
    session.commit()
    logger.info("Public data refreshed", extra={"source": source.name, "rows": written})
    return RefreshResult(source=source.name, status="ok", rows=written)
