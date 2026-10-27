"""Public market data stored locally: FX rates and a log of daily fetches."""

import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from mis_finanzas.core.db import Base, DecimalText, str_enum


class RateType(enum.StrEnum):
    MEP = "MEP"


class FxRate(Base):
    """ARS per USD for one day and rate type."""

    __tablename__ = "fx_rates"
    __table_args__ = (UniqueConstraint("rate_type", "date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    rate_type: Mapped[RateType] = mapped_column(str_enum(RateType))
    date: Mapped[date] = mapped_column(Date, index=True)
    buy: Mapped[Decimal] = mapped_column(DecimalText)
    sell: Mapped[Decimal] = mapped_column(DecimalText)
    source: Mapped[str] = mapped_column(String(100))


class FetchStatus(enum.StrEnum):
    OK = "ok"
    FAILED = "failed"


class FetchLog(Base):
    """One row per fetch attempt; enforces the at-most-daily download rule."""

    __tablename__ = "fetch_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(100), index=True)
    run_date: Mapped[date] = mapped_column(Date)
    status: Mapped[FetchStatus] = mapped_column(str_enum(FetchStatus))
    rows: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(500), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
