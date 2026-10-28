"""The Visa card section inside the Santander account statement ("Mi resumen de cuenta").

The account statement repeats the Visa statement: from a big "Visa crédito" heading to the next
big heading ("Tarjeta de débito", "Pagos", …), with the same sections in other words:
- "Pago anterior y devoluciones" (`Fecha · Descripción · Pesos · Dólares`), closed by `Total`;
- per card, "Total consumos de <titular> | Tarjeta terminada en NNNN"
  (`Fecha · Comprobante · Descripción · Cuota · Pesos · Dólares`), closed by `Consumos
  totales`;
- "Impuestos", closed by `Total`;
- `Total a pagar`.

Its rows go to the same targets as the Visa statement's (`santander/visa/ARS|USD`), so importing
both for one month adds each movement once. The debit card and payments pages after it only
repeat account movements and are not read.
"""

from mis_finanzas.importers.base import Check, ParsedRow, RowError
from mis_finanzas.importers.pdf_layout import Line
from mis_finanzas.importers.pdf_words import PageWords
from mis_finanzas.importers.santander.card_statement import (
    CARD,
    PAYMENTS,
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

HEADING_SIZE = 18.0  # product headings print at 20pt; nothing else in the statement does
LAYOUT = CardLayout(
    product="visa",
    simple_labels=("Fecha", "Descripción", "Pesos", "Dólares"),
    card_labels=("Fecha", "Comprobante", "Descripción", "Cuota", "Pesos", "Dólares"),
    amount_columns={"Pesos": "ARS", "Dólares": "USD"},
    titles={
        "PAGO ANTERIOR Y DEVOLUCIONES": PAYMENTS,
        "TOTAL CONSUMOS DE": CARD,
        "IMPUESTOS": TAXES,
    },
    # `Total $ …` closes the payments or the taxes, whichever section it ends. It is negative
    # (`Total -$ …`) when more was paid than owed.
    summaries={
        "TOTAL A PAGAR": TOTAL_DUE,
        "CONSUMOS TOTALES": SUBTOTAL,
        "TOTAL $": None,
        "TOTAL U$S": None,
        "TOTAL -$": None,
        "TOTAL -U$S": None,
    },
    stops=("CONSUMOS DEL MES", "¿QUE ES EL PAGO MINIMO"),
)


def _headings(page: PageWords) -> list[Line]:
    return [line for line in page_lines(page) if max(w.size for w in line.words) >= HEADING_SIZE]


def visa_pages(pages: list[PageWords]) -> list[PageWords]:
    """The pages from the "Visa crédito" heading up to the next product's heading."""
    found: list[PageWords] = []
    inside = False
    for page in pages:
        headings = [normalize_description(line.text) for line in _headings(page)]
        if any("VISA" in text for text in headings):
            inside = True
        elif headings and inside:
            break
        if inside:
            found.append(page)
    return found


def read_visa_section(
    pages: list[PageWords],
) -> tuple[list[ParsedRow], list[RowError], list[Check], dict[str, str]] | None:
    """The section's rows, errors, checks and metadata; None when the statement has none."""
    section = visa_pages(pages)
    if not section:
        return None
    state = CardStatement()
    for page in section:
        read_page(LAYOUT, state, page)
    metadata = {"tarjetas_visa": ",".join(card.number for card in state.cards)}
    opening = implied_opening(state)
    if opening is not None:
        metadata["Visa: saldo anterior (no impreso)"] = describe_opening(opening)
    return state.rows, state.errors, checks(state, prefix="Visa: "), metadata
