"""Write ARCA's invoices, and attach invoice PDFs to them.

Invoices are keyed by (type, point of sale, number). A newer Mis Comprobantes export holds the
whole history again, so importing it updates what changed and adds what's new; it never
duplicates.

A PDF attaches to the invoice it matches (total, date and CAE must agree). When no invoice
matches yet, the PDF creates it, marked `source = "pdf"`; a later export confirms it in
place (same key) and keeps the PDF attached.
"""

import logging
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from mis_finanzas.core.money import CENT, to_cents
from mis_finanzas.monotributo.models import SOURCE_EXPORT, SOURCE_PDF, Invoice
from mis_finanzas.monotributo.records import (
    INVOICE_TYPES,
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
    pdf_creates: bool = False  # no invoice matches the PDF yet: it creates it
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
    """Any field differs, or the invoice was known only from its PDF until now."""
    if invoice.source != SOURCE_EXPORT:
        return True
    return any(getattr(invoice, name) != value for name, value in values.items())


def _pdf_rate(pdf: ParsedInvoicePdf) -> Decimal | None:
    """Pesos per unit: 1 for pesos; the printed rate otherwise (None when missing)."""
    return Decimal(1) if pdf.currency == "ARS" else pdf.fx_rate


def _pdf_comparisons(invoice: Invoice | None, pdf: ParsedInvoicePdf) -> list[Comparison]:
    if invoice is None:
        # Created from the PDF alone: a dollar invoice needs its printed rate.
        return [Comparison("tipo de cambio", Decimal(1), Decimal(_pdf_rate(pdf) is not None))]
    same_day = invoice.issued_on == pdf.issued_on
    same_cae = invoice.cae == pdf.cae
    return [
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
        existing = _find(session, data.pdf.key)
        summary.pdf_for = str(data.pdf.key)
        summary.pdf_creates = existing is None
        summary.comparisons = _pdf_comparisons(existing, data.pdf)
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
    invoice.source = SOURCE_EXPORT  # an invoice the PDF created is now confirmed
    return True


def _from_pdf(pdf: ParsedInvoicePdf, batch_id: int | None) -> Invoice:
    """An invoice known only from its PDF. Raises `ValueError` without an exchange rate."""
    rate = _pdf_rate(pdf)
    if rate is None:
        raise ValueError("a dollar invoice's PDF needs its exchange rate")
    sign = INVOICE_TYPES[pdf.key.type_code][1]
    key = pdf.key
    return Invoice(
        type_code=key.type_code,
        point_of_sale=key.point_of_sale,
        number_from=key.number,
        number_to=key.number,
        issued_on=pdf.issued_on,
        cae=pdf.cae,
        receiver_doc_type="",
        receiver_doc="",
        receiver_name=pdf.receiver_name,
        currency=pdf.currency,
        fx_rate=rate,
        net_taxed_cents=0,
        net_untaxed_cents=0,
        exempt_cents=0,
        other_taxes_cents=0,
        vat_cents=0,
        total_cents=to_cents(pdf.total),
        total_ars_cents=to_cents((sign * pdf.total * rate).quantize(CENT)),
        source=SOURCE_PDF,
        import_batch_id=batch_id,
    )


def store(session: Session, batch_id: int | None, data: InvoiceData) -> None:
    """Add to the session; the caller commits. A PDF that matches an invoice must agree with
    it (see `summarize`); one that matches none creates it."""
    written = sum(_upsert(session, batch_id, parsed) for parsed in data.invoices)
    if data.pdf is not None:
        invoice = _find(session, data.pdf.key)
        if invoice is None:
            invoice = _from_pdf(data.pdf, batch_id)
            session.add(invoice)
            written += 1
        invoice.pdf_batch_id = batch_id
    logger.info(
        "Invoices stored",
        extra={"batch_id": batch_id, "invoices": len(data.invoices), "written": written},
    )
