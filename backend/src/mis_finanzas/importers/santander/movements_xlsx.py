"""Santander "Últimos movimientos" Excel export.

- **Header row**, found by its labels: `Fecha · Sucursal origen · Descripción · Referencia ·
  Caja de Ahorro · Cuenta Corriente · Saldo`.
- **Above it:** `Cuenta`, `Moneda` (Pesos or Dólares) and the date range.
- **Rows** are newest first. Amounts are text with a `.` decimal and no thousands separator.
  A description is `type \t detail`.
- **Check:** where a row shows `Saldo`, it must equal the previous balance plus the
  movements since. The most recent day's rows show no balance yet.
"""

from datetime import date, datetime
from decimal import Decimal

from mis_finanzas.core.money import parse_amount
from mis_finanzas.importers.base import Check, ImportFileError, ParsedRow, ParseResult, RowError
from mis_finanzas.importers.santander.common import CURRENCIES, parse_date, target
from mis_finanzas.importers.tabular import Cell, excel_lines
from mis_finanzas.ledger.text import normalize_description

LABELS = (
    "Fecha",
    "Sucursal origen",
    "Descripción",
    "Referencia",
    "Caja de Ahorro",
    "Cuenta Corriente",
    "Saldo",
)
PRODUCTS = {"Caja de Ahorro": "CA", "Cuenta Corriente": "CC"}
METADATA = {"CUENTA": "cuenta", "MONEDA": "moneda", "FECHA": "periodo"}


def _text(cell: Cell) -> str:
    return "" if cell is None else " ".join(str(cell).split())


def _find_header(rows: list[list[Cell]]) -> tuple[int, dict[str, int]] | None:
    wanted = {normalize_description(label): label for label in LABELS}
    for index, row in enumerate(rows):
        found = {
            wanted[norm]: col
            for col, cell in enumerate(row)
            if (norm := normalize_description(_text(cell))) in wanted
        }
        if len(found) == len(LABELS):
            return index, found
    return None


def _metadata(rows: list[list[Cell]]) -> dict[str, str]:
    """`Cuenta`, `Moneda`, `Fecha` label/value pairs above the table."""
    metadata: dict[str, str] = {}
    for row in rows:
        cells = [_text(c) for c in row if _text(c)]
        if len(cells) == 2 and normalize_description(cells[0]) in METADATA:
            metadata[METADATA[normalize_description(cells[0])]] = cells[1]
    return metadata


def _amount(cell: Cell) -> Decimal | None:
    if cell is None or (isinstance(cell, str) and not cell.strip()):
        return None
    if isinstance(cell, int | float) and not isinstance(cell, bool):
        return Decimal(str(cell))
    if isinstance(cell, str):
        return parse_amount(cell, decimal_separator=".", thousands_separator="")
    raise ValueError(f"not an amount: {cell!r}")


def _date(cell: Cell) -> date:
    if isinstance(cell, datetime):
        return cell.date()
    if isinstance(cell, date):
        return cell
    return parse_date(_text(cell))


class _Row:
    """One movement plus the balance the bank printed for it, if any."""

    def __init__(self, parsed: ParsedRow, balance: Decimal | None) -> None:
        self.parsed, self.balance = parsed, balance


def _row(line_number: int, cells: list[Cell], cols: dict[str, int], currency: str) -> _Row:
    amounts = {p: _amount(cells[cols[label]]) for label, p in PRODUCTS.items()}
    filled = [(product, value) for product, value in amounts.items() if value is not None]
    if len(filled) != 1:
        raise ValueError("expected an amount in exactly one of Caja de Ahorro / Cuenta Corriente")
    product, amount = filled[0]
    parsed = ParsedRow(
        line_number=line_number,
        date=_date(cells[cols["Fecha"]]),
        amount=amount,
        description=_text(cells[cols["Descripción"]]),
        target=target(product, currency),
        reference=_text(cells[cols["Referencia"]]) or None,
    )
    return _Row(parsed, _amount(cells[cols["Saldo"]]))


def balance_mismatches(rows: list[_Row]) -> int:
    """Walk oldest to newest; each printed balance must follow from the previous one."""
    running: Decimal | None = None
    mismatches = 0
    for row in reversed(rows):
        if running is not None:
            running += row.parsed.amount
        if row.balance is not None:
            if running is not None and running != row.balance:
                mismatches += 1
            running = row.balance
    return mismatches


def _currency(metadata: dict[str, str]) -> str:
    currency = CURRENCIES.get(metadata.get("moneda", "").strip().lower())
    if currency is None:
        raise ImportFileError("the export's Moneda is neither Pesos nor Dólares")
    return currency


class SantanderMovementsXlsx:
    name = "santander_movements_xlsx"
    version = "1"

    def detect(self, filename: str, content: bytes) -> bool:
        if not filename.lower().endswith(".xlsx"):
            return False
        try:
            return _find_header(excel_lines(content)) is not None
        except ImportFileError:
            return False

    def parse(self, content: bytes, filename: str) -> ParseResult:
        lines = excel_lines(content)
        found = _find_header(lines)
        if found is None:
            raise ImportFileError("not a Santander movements export")
        header, cols = found
        result = ParseResult(metadata=_metadata(lines[:header]))
        currency = _currency(result.metadata)
        rows: list[_Row] = []
        for index, cells in enumerate(lines[header + 1 :], start=header + 2):
            if not any(_text(c) for c in cells):
                continue
            try:
                rows.append(_row(index, cells, cols, currency))
            except (ValueError, IndexError) as exc:
                result.errors.append(RowError(index, str(exc)))
        result.rows = [r.parsed for r in rows]
        result.checks = [Check("saldos fila a fila", Decimal(0), Decimal(balance_mismatches(rows)))]
        return result
