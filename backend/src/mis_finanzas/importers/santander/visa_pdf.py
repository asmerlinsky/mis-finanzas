"""Santander card statement PDFs: Visa ("Resumen Visa") and, in the same design, American
Express ("Resumen American Express"). The reading and checks are in `card_statement`.

**Layout:**
- "Pago anterior y devoluciones" (`Fecha · Descripción · Monto en pesos · Monto en dólares`),
  closed by `Saldo del resumen anterior`;
- one "Movimientos de <titular>" per card (`Fecha · Descripción · Cuota · Comprobante · Monto
  en pesos · Monto en dólares`), ending in a `Subtotal` line;
- "Impuestos, intereses y percepciones";
- `Total a pagar`.

A month with no purchases has no card table at all: the statement is then only payments and
totals.
"""

import re

from mis_finanzas.importers.base import ParseResult
from mis_finanzas.importers.pdf_layout import find_header_rows
from mis_finanzas.importers.pdf_words import PageWords
from mis_finanzas.importers.santander.card_statement import (
    CARD,
    PAYMENTS,
    PREVIOUS,
    SUBTOTAL,
    TAXES,
    TOTAL_DUE,
    CardLayout,
    CardStatement,
    checks,
    describe_opening,
    implied_opening,
    read_page,
)
from mis_finanzas.importers.santander.common import page_lines
from mis_finanzas.ledger.text import normalize_description

AMOUNT_COLUMNS = {"Monto en pesos": "ARS", "Monto en dólares": "USD"}
SIMPLE_LABELS = ("Fecha", "Descripción", "Monto en pesos", "Monto en dólares")
CARD_LABELS = ("Fecha", "Descripción", "Cuota", "Comprobante", "Monto en pesos", "Monto en dólares")
TITLES = {
    "PAGO ANTERIOR Y DEVOLUCIONES": PAYMENTS,
    "MOVIMIENTOS DE": CARD,
    "IMPUESTOS, INTERESES Y PERCEPCIONES": TAXES,
}
SUMMARIES: dict[str, str | None] = {
    "SUBTOTAL": SUBTOTAL,
    "SALDO DEL RESUMEN ANTERIOR": PREVIOUS,
    "TOTAL A PAGAR": TOTAL_DUE,
}
_DATE = re.compile(r"\b\d{2}/\d{2}/\d{2}\b")
DATE_KEYS = (
    "cierre_anterior",
    "vencimiento_anterior",
    "cierre",
    "vencimiento",
    "proximo_cierre",
    "proximo_vencimiento",
)


def layout(product: str) -> CardLayout:
    return CardLayout(product, SIMPLE_LABELS, CARD_LABELS, AMOUNT_COLUMNS, TITLES, SUMMARIES)


def _metadata(pages: list[PageWords], state: CardStatement) -> dict[str, str]:
    metadata = {"tarjetas": ",".join(card.number for card in state.cards)}
    opening = implied_opening(state)
    if opening is not None:
        metadata["saldo anterior (no impreso)"] = describe_opening(opening)
    for line in page_lines(pages[0]):
        dates = _DATE.findall(line.text)
        if len(dates) == len(DATE_KEYS):
            metadata.update(zip(DATE_KEYS, dates, strict=True))
            break
    return metadata


class _SantanderCardPdf:
    name: str
    version = "1"
    title: str  # normalized, on page 1
    product: str

    def detect_pages(self, pages: list[PageWords]) -> bool:
        if not pages:
            return False
        first = normalize_description(" ".join(line.text for line in page_lines(pages[0])))
        if self.title not in first:
            return False
        return any(
            find_header_rows(p, CARD_LABELS) or find_header_rows(p, SIMPLE_LABELS) for p in pages
        )

    def parse_pages(self, pages: list[PageWords]) -> ParseResult:
        statement_layout = layout(self.product)
        state = CardStatement()
        for page in pages:
            read_page(statement_layout, state, page)
        return ParseResult(
            rows=state.rows,
            errors=state.errors,
            checks=checks(state),
            metadata=_metadata(pages, state),
        )


class SantanderVisaPdf(_SantanderCardPdf):
    name = "santander_visa_pdf"
    title = "RESUMEN VISA"
    product = "visa"


class SantanderAmexPdf(_SantanderCardPdf):
    """American Express statements since Santander moved them to the Visa design."""

    name = "santander_amex_pdf"
    title = "RESUMEN AMERICAN EXPRESS"
    product = "amex"
