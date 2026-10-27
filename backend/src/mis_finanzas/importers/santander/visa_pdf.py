"""Santander Visa statement ("Resumen Visa") PDF.

**Sections**, each under its title and a header row:
- "Pago anterior y devoluciones" (`Fecha · Descripción · Monto en pesos · Monto en dólares`);
- one "Movimientos de <titular>" per card (`Fecha · Descripción · Cuota · Comprobante · Monto
  en pesos · Monto en dólares`), ending in a `Subtotal` line;
- "Impuestos, intereses y percepciones".

A table continues on the next page under a repeated header.

**Signs:** the statement prints charges positive and payments negative. On the card account
(targets `santander/visa/ARS`, `santander/visa/USD`) a charge is money out, so every amount
is negated. `Saldo anterior` is the previous statement's balance, not a movement.

**Checks, per currency:**
- each card's movements = its `Subtotal`;
- saldo anterior + payments = `Saldo del resumen anterior`;
- saldo anterior + everything = `Total a pagar`.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from mis_finanzas.importers.amounts import parse_money
from mis_finanzas.importers.base import Check, ParsedRow, ParseResult, RowError
from mis_finanzas.importers.pdf_layout import (
    HeaderRow,
    Line,
    TableRow,
    find_header_rows,
    table_rows,
)
from mis_finanzas.importers.pdf_words import PageWords
from mis_finanzas.importers.santander.common import (
    PAGE_NUMBER,
    amounts_by_currency,
    page_lines,
    parse_date,
    target,
)
from mis_finanzas.ledger.text import normalize_description

SIMPLE_LABELS = ["Fecha", "Descripción", "Monto en pesos", "Monto en dólares"]
CARD_LABELS = ["Fecha", "Descripción", "Cuota", "Comprobante", "Monto en pesos", "Monto en dólares"]
AMOUNT_COLUMNS = {"Monto en pesos": "ARS", "Monto en dólares": "USD"}
TITLES = {
    "PAGO ANTERIOR Y DEVOLUCIONES": "pagos",
    "MOVIMIENTOS DE": "tarjeta",
    "IMPUESTOS, INTERESES Y PERCEPCIONES": "impuestos",
}
SUMMARIES = ("SUBTOTAL", "SALDO DEL RESUMEN ANTERIOR", "TOTAL A PAGAR")
_CARD = re.compile(r"TERMINADA EN (\d{4})")
_INSTALLMENT = re.compile(r"^(\d+)\s+de\s+(\d+)$")
_DATE = re.compile(r"\b\d{2}/\d{2}/\d{2}\b")
DATE_KEYS = (
    "cierre_anterior",
    "vencimiento_anterior",
    "cierre",
    "vencimiento",
    "proximo_cierre",
    "proximo_vencimiento",
)


def _zero() -> dict[str, Decimal]:
    return {"ARS": Decimal(0), "USD": Decimal(0)}


@dataclass
class _Card:
    number: str
    printed: dict[str, Decimal] = field(default_factory=_zero)
    subtotal: dict[str, Decimal] | None = None


@dataclass
class _State:
    section: str | None = None
    last_date: date | None = None
    previous_balance: dict[str, Decimal] | None = None
    previous_summary: dict[str, Decimal] | None = None
    total_due: dict[str, Decimal] | None = None
    printed: dict[str, dict[str, Decimal]] = field(default_factory=dict)  # section -> sums
    cards: list[_Card] = field(default_factory=list)
    rows: list[ParsedRow] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)


def is_table_end(line: Line) -> bool:
    text = normalize_description(line.text)
    return text.startswith((*SUMMARIES, "COPIA FIEL")) or PAGE_NUMBER.match(line.text) is not None


def _title(line: Line) -> str | None:
    text = normalize_description(line.text)
    return next((kind for title, kind in TITLES.items() if text.startswith(title)), None)


def _headers(page: PageWords) -> list[HeaderRow]:
    """Card headers, plus the simple headers that aren't the same line as a card header."""
    cards = find_header_rows(page, CARD_LABELS)
    card_tops = {header.line.top for header in cards}
    simple = [h for h in find_header_rows(page, SIMPLE_LABELS) if h.line.top not in card_tops]
    return sorted(cards + simple, key=lambda header: header.line.top)


def _amount(row: TableRow) -> tuple[str, Decimal]:
    filled = [
        (currency, row.cell(label)) for label, currency in AMOUNT_COLUMNS.items() if row.cell(label)
    ]
    if len(filled) != 1:
        raise ValueError("expected one amount, in pesos or in dollars")
    currency, text = filled[0]
    return currency, parse_money(text).amount


def _installment(text: str) -> tuple[int, int] | None:
    match = _INSTALLMENT.match(text.strip())
    return (int(match.group(1)), int(match.group(2))) if match else None


def _movement(state: _State, row: TableRow, line_number: int) -> None:
    """Raises `ValueError` for a row that can't be read."""
    if state.last_date is None:
        raise ValueError("movement before any date")
    currency, printed = _amount(row)
    section = state.section or "tarjeta"
    sums = state.printed.setdefault(section, _zero())
    sums[currency] += printed
    if section == "tarjeta" and state.cards:
        state.cards[-1].printed[currency] += printed
    installment = _installment(row.cell("Cuota"))
    # Tax rows print a stray currency symbol at the end of the description column.
    description = re.sub(r"(\s+(\$|U\$S))+$", "", row.cell("Descripción"))
    if installment:
        description = f"{description} ({installment[0]}/{installment[1]})"
    state.rows.append(
        ParsedRow(
            line_number=line_number,
            date=state.last_date,
            amount=-printed,
            description=description,
            target=target("visa", currency),
            reference=row.cell("Comprobante") or None,
            installment=installment,
        )
    )


def _read_row(state: _State, row: TableRow, line_number: int) -> None:
    if row.cell("Fecha"):
        state.last_date = parse_date(row.cell("Fecha"))
    if normalize_description(row.cell("Descripción")).startswith("SALDO ANTERIOR"):
        state.previous_balance = {
            c: parse_money(row.cell(label)).amount
            for label, c in AMOUNT_COLUMNS.items()
            if row.cell(label)
        }
        return
    _movement(state, row, line_number)


def _read_table(state: _State, page: PageWords, header: HeaderRow, until: float) -> None:
    rows = table_rows(
        page, header, key_columns=list(AMOUNT_COLUMNS), until=until, stop=is_table_end
    )
    for index, row in enumerate(rows):
        line_number = page.number * 1000 + int(header.line.top) + index
        try:
            _read_row(state, row, line_number)
        except ValueError as exc:
            state.errors.append(RowError(line_number, str(exc)))


def _summary(state: _State, line: Line) -> None:
    text = normalize_description(line.text)
    amounts = amounts_by_currency(line.text)
    if text.startswith("SUBTOTAL") and state.cards:
        state.cards[-1].subtotal = amounts
    elif text.startswith("SALDO DEL RESUMEN ANTERIOR"):
        state.previous_summary = amounts
    elif text.startswith("TOTAL A PAGAR"):
        state.total_due = amounts


def _card_number(lines: list[Line], below: float) -> str:
    for line in lines:
        if line.top > below and (match := _CARD.search(normalize_description(line.text))):
            return match.group(1)
    return "?"


@dataclass(frozen=True)
class _Event:
    top: float
    kind: str  # "title", "header" or "summary"
    line: Line
    header: HeaderRow | None = None


def _events(page: PageWords) -> list[_Event]:
    lines = page_lines(page)
    events = [_Event(h.line.top, "header", h.line, h) for h in _headers(page)]
    events += [_Event(line.top, "title", line) for line in lines if _title(line)]
    events += [
        _Event(line.top, "summary", line)
        for line in lines
        if normalize_description(line.text).startswith(SUMMARIES)
    ]
    return sorted(events, key=lambda event: event.top)


def _read_page(state: _State, page: PageWords) -> None:
    events = _events(page)
    for index, event in enumerate(events):
        if event.kind == "title":
            state.section = _title(event.line)
            if state.section == "tarjeta":
                state.cards.append(_Card(_card_number(page_lines(page), event.top)))
        elif event.kind == "summary":
            _summary(state, event.line)
        elif event.header is not None:
            until = events[index + 1].top if index + 1 < len(events) else float("inf")
            _read_table(state, page, event.header, until)


def _sum(values: list[Decimal]) -> Decimal:
    return sum(values, Decimal(0))


def _checks(state: _State) -> list[Check]:
    found = Decimal(int(state.previous_balance is not None and state.total_due is not None))
    checks = [Check("saldo anterior y total a pagar", Decimal(1), found)]
    previous = state.previous_balance or {}
    for currency in ("ARS", "USD"):
        for card in state.cards:
            subtotal = (card.subtotal or {}).get(currency, Decimal(0))
            checks.append(
                Check(
                    f"subtotal tarjeta {card.number} {currency}", subtotal, card.printed[currency]
                )
            )
        payments = state.printed.get("pagos", _zero())[currency]
        if state.previous_summary is not None:
            checks.append(
                Check(
                    f"saldo del resumen anterior {currency}",
                    state.previous_summary.get(currency, Decimal(0)),
                    previous.get(currency, Decimal(0)) + payments,
                )
            )
        if state.total_due is not None:
            everything = _sum([sums[currency] for sums in state.printed.values()])
            checks.append(
                Check(
                    f"total a pagar {currency}",
                    state.total_due.get(currency, Decimal(0)),
                    previous.get(currency, Decimal(0)) + everything,
                )
            )
    return checks


def _metadata(pages: list[PageWords], cards: list[_Card]) -> dict[str, str]:
    metadata = {"tarjetas": ",".join(card.number for card in cards)}
    for line in page_lines(pages[0]):
        dates = _DATE.findall(line.text)
        if len(dates) == len(DATE_KEYS):
            metadata.update(zip(DATE_KEYS, dates, strict=True))
            break
    return metadata


class SantanderVisaPdf:
    name = "santander_visa_pdf"
    version = "1"

    def detect_pages(self, pages: list[PageWords]) -> bool:
        if not pages:
            return False
        first = normalize_description(" ".join(line.text for line in page_lines(pages[0])))
        return "RESUMEN VISA" in first and any(find_header_rows(p, CARD_LABELS) for p in pages)

    def parse_pages(self, pages: list[PageWords]) -> ParseResult:
        state = _State()
        for page in pages:
            _read_page(state, page)
        return ParseResult(
            rows=state.rows,
            errors=state.errors,
            checks=_checks(state),
            metadata=_metadata(pages, state.cards),
        )
