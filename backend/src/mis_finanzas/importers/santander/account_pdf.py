"""Santander "Mi resumen de cuenta" PDF: the movements in pesos and in dollars.

**What is read:**
- Only rows under a header `Fecha · Comprobante · Movimiento · Caja de Ahorro en <moneda> ·
  [Cuenta Corriente en <moneda>] · Saldo en cuenta`. The header repeats on every page of a
  section. The card, debit, investment and legal pages are not read.
- A movement prints on two lines: type and amounts at 8.5pt, detail at 7pt. Its date prints
  only on the first movement of each day.
- The amount's column decides the target: `santander/CA/ARS`, `santander/CC/ARS`,
  `santander/CA/USD`.
- A section opens with a `Saldo Inicial` row and closes with a `Saldo total` line.

**Checks, per currency:**
- every row's `Saldo en cuenta` follows from the previous one;
- opening + movements = `Saldo total`.
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

CURRENCY_WORDS = {"ARS": "pesos", "USD": "dólares"}
TITLE = "MI RESUMEN DE CUENTA"
_ACCOUNT_NUMBER = re.compile(r"\b\d{3}-\d{6}/\d\b")
_DATE = re.compile(r"\d{2}/\d{2}/\d{2}")


def _labels(currency: str, with_current_account: bool) -> list[str]:
    word = CURRENCY_WORDS[currency]
    labels = ["Fecha", "Comprobante", "Movimiento", f"Caja de Ahorro en {word}"]
    if with_current_account:
        labels.append(f"Cuenta Corriente en {word}")
    return [*labels, "Saldo en cuenta"]


def _products(currency: str) -> dict[str, str]:
    word = CURRENCY_WORDS[currency]
    return {f"Caja de Ahorro en {word}": "CA", f"Cuenta Corriente en {word}": "CC"}


def find_tables(page: PageWords) -> list[tuple[HeaderRow, str]]:
    """Movement table headers on the page with their currency, top to bottom."""
    found = []
    for currency in CURRENCY_WORDS:
        headers = find_header_rows(page, _labels(currency, True))
        headers = headers or find_header_rows(page, _labels(currency, False))
        found += [(header, currency) for header in headers]
    return sorted(found, key=lambda pair: pair[0].line.top)


def is_table_end(line: Line) -> bool:
    text = normalize_description(line.text)
    return (
        text.startswith(("SALDO TOTAL", "BANCO SANTANDER", "*"))
        or PAGE_NUMBER.match(line.text) is not None
    )


@dataclass
class _Section:
    """Running state of one currency's movements, across pages."""

    currency: str
    opening: Decimal | None = None
    closing: Decimal | None = None
    balance: Decimal | None = None
    last_date: date | None = None
    total: Decimal = Decimal(0)
    mismatches: int = 0
    rows: list[ParsedRow] = field(default_factory=list)

    def checks(self) -> list[Check]:
        name = CURRENCY_WORDS[self.currency]
        found = Decimal(int(self.opening is not None and self.closing is not None))
        checks = [
            Check(f"saldo inicial y saldo total en {name}", Decimal(1), found),
            Check(f"saldos fila a fila en {name}", Decimal(0), Decimal(self.mismatches)),
        ]
        if self.opening is not None and self.closing is not None:
            checks.append(Check(f"saldo total en {name}", self.closing, self.opening + self.total))
        return checks


def _amount(row: TableRow, currency: str) -> tuple[str, Decimal]:
    filled = [
        (product, row.cell(label))
        for label, product in _products(currency).items()
        if row.cell(label)
    ]
    if len(filled) != 1:
        raise ValueError("expected one amount, in Caja de Ahorro or Cuenta Corriente")
    product, text = filled[0]
    return product, parse_money(text).amount


def _follow_balance(section: _Section, amount: Decimal, printed: str) -> None:
    if section.balance is not None:
        section.balance += amount
    if printed:
        balance = parse_money(printed).amount
        if section.balance is not None and section.balance != balance:
            section.mismatches += 1
        section.balance = balance


def _read_row(section: _Section, row: TableRow, line_number: int) -> None:
    """Adds the movement to `section`, or records the opening balance. Raises `ValueError`."""
    if row.cell("Fecha"):
        section.last_date = parse_date(row.cell("Fecha"))
    if normalize_description(row.cell("Movimiento")).startswith("SALDO INICIAL"):
        section.opening = parse_money(row.cell("Saldo en cuenta")).amount
        section.balance = section.opening
        return
    if section.last_date is None:
        raise ValueError("movement before any date")
    product, amount = _amount(row, section.currency)
    _follow_balance(section, amount, row.cell("Saldo en cuenta"))
    section.total += amount
    section.rows.append(
        ParsedRow(
            line_number=line_number,
            date=section.last_date,
            amount=amount,
            description=row.cell("Movimiento"),
            target=target(product, section.currency),
            reference=row.cell("Comprobante") or None,
        )
    )


def _closing(page: PageWords, header: HeaderRow, currency: str) -> Decimal | None:
    for line in page_lines(page):
        if line.top > header.bottom and normalize_description(line.text).startswith("SALDO TOTAL"):
            return amounts_by_currency(line.text).get(currency)
    return None


def _read_table(
    sections: dict[str, _Section],
    page: PageWords,
    header: HeaderRow,
    currency: str,
    until: float,
    errors: list[RowError],
) -> None:
    section = sections.setdefault(currency, _Section(currency))
    rows = table_rows(
        page, header, key_columns=list(_products(currency)), until=until, stop=is_table_end
    )
    for index, row in enumerate(rows):
        line_number = page.number * 1000 + index
        try:
            _read_row(section, row, line_number)
        except ValueError as exc:
            errors.append(RowError(line_number, str(exc)))
    section.closing = _closing(page, header, currency) or section.closing


def _metadata(pages: list[PageWords]) -> dict[str, str]:
    text = " ".join(line.text for line in page_lines(pages[0]))
    metadata = {}
    if account := _ACCOUNT_NUMBER.search(text):
        metadata["cuenta"] = account.group()
    for label in ("Desde", "Hasta"):
        if found := re.search(rf"{label}:\s*({_DATE.pattern})", text):
            metadata[label.lower()] = found.group(1)
    return metadata


class SantanderAccountPdf:
    name = "santander_account_pdf"
    version = "1"

    def detect_pages(self, pages: list[PageWords]) -> bool:
        if not pages:
            return False
        first = normalize_description(" ".join(line.text for line in page_lines(pages[0])))
        return TITLE in first and any(find_tables(page) for page in pages)

    def parse_pages(self, pages: list[PageWords]) -> ParseResult:
        result = ParseResult(metadata=_metadata(pages))
        sections: dict[str, _Section] = {}
        for page in pages:
            tables = find_tables(page)
            for index, (header, currency) in enumerate(tables):
                until = tables[index + 1][0].line.top if index + 1 < len(tables) else float("inf")
                _read_table(sections, page, header, currency, until, result.errors)
        for section in sections.values():
            result.rows += section.rows
            result.checks += section.checks()
        return result
