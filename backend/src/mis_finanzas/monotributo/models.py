"""Monotributo tables: issued invoices (from Mis Comprobantes) and the owner's category."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from mis_finanzas.core.db import Base, DecimalText


class Invoice(Base):
    """An issued comprobante. Amounts are cents in the invoice's currency, as printed;
    `total_ars_cents` is signed (credit notes subtract)."""

    __tablename__ = "invoices"
    __table_args__ = (UniqueConstraint("type_code", "point_of_sale", "number_from"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    type_code: Mapped[int] = mapped_column(Integer)
    point_of_sale: Mapped[int] = mapped_column(Integer)
    number_from: Mapped[int] = mapped_column(Integer)
    number_to: Mapped[int] = mapped_column(Integer)
    issued_on: Mapped[date] = mapped_column(Date, index=True)
    cae: Mapped[str] = mapped_column(String(20))
    receiver_doc_type: Mapped[str] = mapped_column(String(5))
    receiver_doc: Mapped[str] = mapped_column(String(20))
    receiver_name: Mapped[str] = mapped_column(String(200))
    currency: Mapped[str] = mapped_column(String(3))
    fx_rate: Mapped[Decimal] = mapped_column(DecimalText)
    net_taxed_cents: Mapped[int] = mapped_column(Integer)
    net_untaxed_cents: Mapped[int] = mapped_column(Integer)
    exempt_cents: Mapped[int] = mapped_column(Integer)
    other_taxes_cents: Mapped[int] = mapped_column(Integer)
    vat_cents: Mapped[int] = mapped_column(Integer)
    total_cents: Mapped[int] = mapped_column(Integer)
    total_ars_cents: Mapped[int] = mapped_column(Integer)
    import_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_batches.id"), default=None
    )
    # The upload holding the invoice's PDF, once attached.
    pdf_batch_id: Mapped[int | None] = mapped_column(ForeignKey("import_batches.id"), default=None)


class MonotributoProfile(Base):
    """A single row: the owner's current category."""

    __tablename__ = "monotributo_profile"

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(1))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
