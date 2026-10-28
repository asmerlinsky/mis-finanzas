"""Daily refresh of public data. At most one successful download per source per day."""

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from functools import partial

from sqlalchemy import select
from sqlalchemy.orm import Session

from mis_finanzas.market.http import PublicHttpClient
from mis_finanzas.market.models import FetchLog, FetchStatus, FxRate, RateType
from mis_finanzas.market.prices import PriceSource, upsert_prices
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


def _refresh(
    session: Session, name: str, today: date, download: Callable[[], int]
) -> RefreshResult:
    """Run `download` (fetch and store, returning rows written) unless today's succeeded."""
    if fetched_today(session, name, today):
        return RefreshResult(source=name, status="skipped")
    try:
        written = download()
    except Exception as exc:
        session.rollback()
        logger.error("Public data fetch failed", extra={"source": name, "error": str(exc)})
        session.add(
            FetchLog(source=name, run_date=today, status=FetchStatus.FAILED, error=str(exc)[:500])
        )
        session.commit()
        return RefreshResult(source=name, status="failed", error=str(exc))
    session.add(FetchLog(source=name, run_date=today, status=FetchStatus.OK, rows=written))
    session.commit()
    logger.info("Public data refreshed", extra={"source": name, "rows": written})
    return RefreshResult(source=name, status="ok", rows=written)


def _download_rates(
    session: Session, client: PublicHttpClient, source: RateSource, rate_type: RateType
) -> int:
    return upsert_rates(session, rate_type, source.name, source.fetch(client))


def _download_prices(
    session: Session, client: PublicHttpClient, source: PriceSource, today: date
) -> int:
    return upsert_prices(session, source.name, today, source.fetch(client))


def refresh_rates(
    session: Session, client: PublicHttpClient, source: RateSource, rate_type: RateType, today: date
) -> RefreshResult:
    download = partial(_download_rates, session, client, source, rate_type)
    return _refresh(session, source.name, today, download)


def refresh_prices(
    session: Session, client: PublicHttpClient, source: PriceSource, today: date
) -> RefreshResult:
    """Prices are stored under the download day: the panels' last trade, as of `today`."""
    download = partial(_download_prices, session, client, source, today)
    return _refresh(session, source.name, today, download)
