"""Balanz "Posición consolidada" PDF: what the account holds on one date.

**What is read:**
- `Fecha resumen` on page 1: the snapshot's date. The `Cuenta` field on the same line (a
  name) is not read.
- Page 1 prints two columns: totals per asset class under `Instrumentos`, and cash per
  currency under `Monedas` (`Pesos $ …`, `Dólares USD …`, `US Dollar (Cable) USD …`).
- Positions, only from rows under a header holding all of `Especie · Descripción · Cantidad
  · Garantía · Precio · Valor Actual`. The asset class is the heading above the header.
  `Garantía` is not read.

**Check:** per asset class, Σ `Valor Actual` = the page-1 total. Values print in whole
pesos, so the sum may be off by up to 1 peso per row.
"""

import math
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from functools import partial

from mis_finanzas.importers.amounts import Money, parse_money
from mis_finanzas.importers.balanz.common import BROKER, heading_above, is_table_end, parse_date
from mis_finanzas.importers.base import Check, ParseResult, RowError
from mis_finanzas.importers.pdf_layout import (
    HeaderRow,
    Line,
    TableRow,
    find_header_rows,
    lines,
    table_rows,
    visible,
)
from mis_finanzas.importers.pdf_words import PageWords, Word
from mis_finanzas.investments.records import (
    InstrumentRef,
    InvestmentData,
    ParsedCash,
    ParsedPosition,
    ParsedSnapshot,
    SnapshotSource,
)
from mis_finanzas.ledger.text import normalize_description

LABELS = ("Especie", "Descripción", "Cantidad", "Garantía", "Precio", "Valor Actual")
TITLE = "POSICION CONSOLIDADA"
SYMBOLS = {"$", "USD", "U$S"}
_AS_OF = re.compile(r"fecha\s+resumen\s+(\d{1,2}/\d{1,2}/\d{4})", re.IGNORECASE)


@dataclass
class _Totals:
    """Page 1: the total per asset class and the cash per currency."""

    classes: dict[str, Decimal] = field(default_factory=dict)  # normalized class -> total
    cash: list[ParsedCash] = field(default_factory=list)


@dataclass
class _Class:
    name: str
    positions: list[ParsedPosition] = field(default_factory=list)

    @property
    def total(self) -> Decimal:
        return sum((p.value or Decimal(0) for p in self.positions), Decimal(0))


def _labeled_amount(words: list[Word]) -> tuple[str, Money] | None:
    """`Acciones $ 66.023.789` -> ("Acciones", 66023789 ARS); None without a symbol."""
    texts = [w.text for w in words]
    at = next((i for i, text in enumerate(texts) if text in SYMBOLS), None)
    if at is None or at == 0:
        return None
    return " ".join(texts[:at]), parse_money(" ".join(texts[at:]))


def _split_x(line: Line) -> float | None:
    """The left edge of `Monedas` on the `Instrumentos  Monedas` heading line."""
    words = [normalize_description(w.text) for w in line.words]
    if "INSTRUMENTOS" in words and "MONEDAS" in words:
        return line.words[words.index("MONEDAS")].x0
    return None


def _add_totals(totals: _Totals, line: Line, split: float) -> bool:
    """Read one line of the two columns; False once neither side holds an amount."""
    left = _labeled_amount([w for w in line.words if w.x1 <= split])
    right = _labeled_amount([w for w in line.words if w.x0 >= split])
    if left is not None:
        totals.classes[normalize_description(left[0])] = left[1].amount
    if right is not None:
        label, money = right
        totals.cash.append(ParsedCash(label, money.currency or "ARS", money.amount))
    return left is not None or right is not None


def _page_totals(page: PageWords) -> _Totals:
    totals = _Totals()
    split: float | None = None
    for line in lines(visible(page.words)):
        if split is None:
            split = _split_x(line)
        elif not _add_totals(totals, line, split):
            break
    return totals


def _as_of(pages: list[PageWords]) -> date | None:
    for line in lines(visible(pages[0].words)) if pages else []:
        if match := _AS_OF.search(line.text):
            return parse_date(match.group(1))
    return None


def _position(row: TableRow, asset_class: str) -> ParsedPosition:
    """Raises `ValueError` for a row that can't be read."""
    especie = row.cell("Especie").split()
    if not especie:
        raise ValueError("missing Especie")
    price = parse_money(row.cell("Precio")) if row.cell("Precio") else None
    value = parse_money(row.cell("Valor Actual"))
    return ParsedPosition(
        instrument=InstrumentRef(especie[0], row.cell("Descripción"), asset_class=asset_class),
        quantity=parse_money(row.cell("Cantidad")).amount,
        price=price.amount if price else None,
        value=value.amount,
        currency=value.currency,
    )


def _read_class(
    page: PageWords, header: HeaderRow, until: float, asset_class: _Class, errors: list[RowError]
) -> None:
    stop = partial(is_table_end, header)
    for row in table_rows(page, header, ["Especie"], until=until, stop=stop):
        line_number = page.number * 1000 + int(row.top)
        try:
            asset_class.positions.append(_position(row, asset_class.name))
        except ValueError as exc:
            errors.append(RowError(line_number, str(exc)))


def _read_classes(pages: list[PageWords], errors: list[RowError]) -> list[_Class]:
    classes: list[_Class] = []
    for page in pages:
        page_lines = lines(visible(page.words))
        headers = find_header_rows(page, LABELS)
        previous = 0.0
        for index, header in enumerate(headers):
            heading = heading_above(page_lines, header, after=previous)
            asset_class = _Class(heading.text if heading else "?")
            until = headers[index + 1].line.top if index + 1 < len(headers) else math.inf
            _read_class(page, header, until, asset_class, errors)
            classes.append(asset_class)
            previous = header.line.top
    return classes


def _checks(classes: list[_Class], totals: _Totals) -> list[Check]:
    checks = [Check("totales de la primera página", Decimal(1), Decimal(bool(totals.classes)))]
    for asset_class in classes:
        expected = totals.classes.get(normalize_description(asset_class.name))
        name = f"total de {asset_class.name}"
        if expected is None:
            checks.append(Check(f"{name} en la primera página", Decimal(1), Decimal(0)))
            continue
        tolerance = Decimal(len(asset_class.positions))
        checks.append(Check(name, expected, asset_class.total, tolerance))
    return checks


class BalanzHoldingsPdf:
    name = "balanz_holdings_pdf"
    version = "1"

    def detect_pages(self, pages: list[PageWords]) -> bool:
        if not pages:
            return False
        first = lines(visible(pages[0].words))
        titled = any(normalize_description(line.text).startswith(TITLE) for line in first[:3])
        return titled and any(find_header_rows(page, LABELS) for page in pages)

    def parse_pages(self, pages: list[PageWords]) -> ParseResult:
        errors: list[RowError] = []
        classes = _read_classes(pages, errors)
        totals = _page_totals(pages[0])
        as_of = _as_of(pages)
        checks = [Check("fecha del resumen", Decimal(1), Decimal(as_of is not None))]
        result = ParseResult(errors=errors, checks=[*checks, *_checks(classes, totals)])
        if as_of is not None:
            result.metadata["fecha"] = as_of.strftime("%d/%m/%Y")
            positions = [p for c in classes for p in c.positions]
            snapshot = ParsedSnapshot(as_of, SnapshotSource.HOLDINGS, positions, totals.cash)
            result.investments = InvestmentData(broker=BROKER, snapshot=snapshot)
        return result
