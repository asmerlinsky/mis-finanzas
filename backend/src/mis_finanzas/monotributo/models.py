"""Monotributo tables: issued invoices (from Mis Comprobantes) and the owner's category."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from mis_finanzas.core.db import Base, DecimalText

SOURCE_EXPORT, SOURCE_PDF = "export", "pdf"


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
    # Where the invoice came from: "export" (Mis Comprobantes) or "pdf" (its PDF alone, until
    # an export confirms it).
    source: Mapped[str] = mapped_column(String(10), default=SOURCE_EXPORT, server_default="export")
    # The incoming movement that paid it, once the owner links it.
    payment_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL"), unique=True, default=None
    )


class MonotributoProfile(Base):
    """A single row: the owner's current category, and the monthly invoicing they project."""

    __tablename__ = "monotributo_profile"

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str | None] = mapped_column(String(1), default=None)
    # The owner's own monthly amount for the projection; None: last month's invoicing.
    projected_amount: Mapped[Decimal | None] = mapped_column(DecimalText, default=None)
    projected_currency: Mapped[str | None] = mapped_column(String(3), default=None)
    # The month ("YYYY-MM") whose invoicing the owner last compared with the projection.
    projection_reviewed: Mapped[str | None] = mapped_column(String(7), default=None)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
