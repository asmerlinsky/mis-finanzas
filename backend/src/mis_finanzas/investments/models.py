"""Investment tables: instruments, their operations, and holdings snapshots from statements.

Broker cash is not here: it is ledger transactions on the broker's cash accounts.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mis_finanzas.core.db import Base, DecimalText, str_enum
from mis_finanzas.investments.records import SnapshotSource


class Instrument(Base):
    __tablename__ = "instruments"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    asset_class: Mapped[str | None] = mapped_column(String(50), default=None)
    broker_code: Mapped[str | None] = mapped_column(String(30), default=None)


class InvestmentOperation(Base):
    __tablename__ = "investment_operations"

    id: Mapped[int] = mapped_column(primary_key=True)
    broker: Mapped[str] = mapped_column(String(30))
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), index=True)
    trade_date: Mapped[date] = mapped_column(Date, index=True)
    settle_date: Mapped[date | None] = mapped_column(Date, default=None)
    description: Mapped[str] = mapped_column(String(500))
    quantity: Mapped[Decimal] = mapped_column(DecimalText)
    price: Mapped[Decimal | None] = mapped_column(DecimalText, default=None)
    gross: Mapped[Decimal | None] = mapped_column(DecimalText, default=None)
    fees: Mapped[Decimal] = mapped_column(DecimalText)
    net: Mapped[Decimal | None] = mapped_column(DecimalText, default=None)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    import_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_batches.id"), default=None
    )

    instrument: Mapped[Instrument] = relationship(lazy="joined")


class HoldingSnapshot(Base):
    """What a statement says the broker held on `as_of`. A later file replaces it."""

    __tablename__ = "holding_snapshots"
    __table_args__ = (UniqueConstraint("broker", "as_of", "source"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    broker: Mapped[str] = mapped_column(String(30))
    as_of: Mapped[date] = mapped_column(Date, index=True)
    source: Mapped[SnapshotSource] = mapped_column(str_enum(SnapshotSource))
    import_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_batches.id"), default=None
    )

    positions: Mapped[list["HoldingPosition"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )
    cash: Mapped[list["HoldingCash"]] = relationship(cascade="all, delete-orphan", lazy="selectin")


class HoldingPosition(Base):
    __tablename__ = "holding_positions"
    __table_args__ = (UniqueConstraint("snapshot_id", "instrument_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("holding_snapshots.id", ondelete="CASCADE"))
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"))
    quantity: Mapped[Decimal] = mapped_column(DecimalText)
    price: Mapped[Decimal | None] = mapped_column(DecimalText, default=None)
    value: Mapped[Decimal | None] = mapped_column(DecimalText, default=None)
    currency: Mapped[str | None] = mapped_column(String(3), default=None)

    instrument: Mapped[Instrument] = relationship(lazy="joined")


class HoldingCash(Base):
    __tablename__ = "holding_cash"

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("holding_snapshots.id", ondelete="CASCADE"))
    label: Mapped[str] = mapped_column(String(50))
    currency: Mapped[str] = mapped_column(String(3))
    amount: Mapped[Decimal] = mapped_column(DecimalText)
