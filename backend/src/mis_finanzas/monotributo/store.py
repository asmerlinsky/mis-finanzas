"""Write ARCA's invoices, and attach invoice PDFs to them.

Invoices are keyed by (type, point of sale, number). A newer Mis Comprobantes export holds the
whole history again, so importing it updates what changed and adds what's new; it never
duplicates. A PDF is attached only to the invoice it matches (date, total and CAE).
"""

import logging
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from mis_finanzas.core.money import CENT, to_cents
from mis_finanzas.monotributo.models import Invoice
from mis_finanzas.monotributo.records import (
    InvoiceData,
    InvoiceKey,
    ParsedInvoice,
    ParsedInvoicePdf,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Comparison:
    """A PDF field against the invoice's, for the import preview's checks."""

    name: str
    expected: Decimal
    actual: Decimal


@dataclass
class InvoiceSummary:
    """What committing would do, for the import preview."""

    invoices: int = 0
    new: int = 0
    changed: list[str] = field(default_factory=list)  # "Factura E 00001-00000017"
    pdf_for: str | None = None  # the invoice a PDF belongs to
    comparisons: list[Comparison] = field(default_factory=list)


def _find(session: Session, key: InvoiceKey) -> Invoice | None:
    query = select(Invoice).where(
        Invoice.type_code == key.type_code,
        Invoice.point_of_sale == key.point_of_sale,
        Invoice.number_from == key.number,
    )
    return session.scalar(query)


def _values(parsed: ParsedInvoice) -> dict[str, object]:
    return {
        "number_to": parsed.number_to,
        "issued_on": parsed.issued_on,
        "cae": parsed.cae,
        "receiver_doc_type": parsed.receiver_doc_type,
        "receiver_doc": parsed.receiver_doc,
        "receiver_name": parsed.receiver_name,
        "currency": parsed.currency,
        "fx_rate": parsed.fx_rate,
        "net_taxed_cents": to_cents(parsed.net_taxed),
        "net_untaxed_cents": to_cents(parsed.net_untaxed),
        "exempt_cents": to_cents(parsed.exempt),
        "other_taxes_cents": to_cents(parsed.other_taxes),
        "vat_cents": to_cents(parsed.vat),
        "total_cents": to_cents(parsed.total),
        "total_ars_cents": to_cents(parsed.total_ars.quantize(CENT)),
    }


def _changed(invoice: Invoice, values: dict[str, object]) -> bool:
    return any(getattr(invoice, name) != value for name, value in values.items())


def _pdf_comparisons(invoice: Invoice | None, pdf: ParsedInvoicePdf) -> list[Comparison]:
    found = Comparison("comprobante en Mis Comprobantes", Decimal(1), Decimal(invoice is not None))
    if invoice is None:
        return [found]
    same_day = invoice.issued_on == pdf.issued_on
    same_cae = invoice.cae == pdf.cae
    return [
        found,
        Comparison("importe total", Decimal(invoice.total_cents) / 100, pdf.total),
        Comparison("fecha de emisión", Decimal(1), Decimal(same_day)),
        Comparison("CAE", Decimal(1), Decimal(same_cae)),
    ]


def summarize(session: Session, data: InvoiceData) -> InvoiceSummary:
    summary = InvoiceSummary(invoices=len(data.invoices))
    for parsed in data.invoices:
        existing = _find(session, parsed.key)
        if existing is None:
            summary.new += 1
        elif _changed(existing, _values(parsed)):
            summary.changed.append(str(parsed.key))
    if data.pdf is not None:
        summary.pdf_for = str(data.pdf.key)
        summary.comparisons = _pdf_comparisons(_find(session, data.pdf.key), data.pdf)
    return summary


def _upsert(session: Session, batch_id: int | None, parsed: ParsedInvoice) -> bool:
    """True when the invoice was added or changed."""
    values = _values(parsed)
    invoice = _find(session, parsed.key)
    if invoice is None:
        key = parsed.key
        invoice = Invoice(
            type_code=key.type_code, point_of_sale=key.point_of_sale, number_from=key.number
        )
        session.add(invoice)
    elif not _changed(invoice, values):
        return False
    for name, value in values.items():
        setattr(invoice, name, value)
    invoice.import_batch_id = batch_id
    return True


def store(session: Session, batch_id: int | None, data: InvoiceData) -> None:
    """Add to the session; the caller commits. A PDF must match: see `summarize`."""
    written = sum(_upsert(session, batch_id, parsed) for parsed in data.invoices)
    if data.pdf is not None:
        invoice = _find(session, data.pdf.key)
        if invoice is None:
            raise ValueError("no invoice matches this PDF")
        invoice.pdf_batch_id = batch_id
    logger.info(
        "Invoices stored",
        extra={"batch_id": batch_id, "invoices": len(data.invoices), "written": written},
    )
