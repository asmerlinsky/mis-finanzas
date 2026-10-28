"""Mercado Pago "resumen de cuenta" CSV export.

Layout (`;`-separated):

    INITIAL_BALANCE;CREDITS;DEBITS;FINAL_BALANCE;
    <values>
    <blank line>
    RELEASE_DATE;TRANSACTION_TYPE;REFERENCE_ID;TRANSACTION_NET_AMOUNT;PARTIAL_BALANCE
    dd-mm-yyyy;<description>;<id>;<amount>;<balance after the movement>

**Number format:** the decimal separator isn't fixed in the exports seen (`2,35`, `0.13`), so
both a comma and a dot decimal are tried; the reading under which the balances add up wins.
If neither does, the comma reading is kept, and its failed checks block the import.

**Checks:**
- every row: previous balance (`INITIAL_BALANCE` for the first) + amount = `PARTIAL_BALANCE`;
- `INITIAL_BALANCE` + all movements = `FINAL_BALANCE`;
- credits = `CREDITS` and debits = `DEBITS` (compared without sign).
"""

import csv
import io
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from mis_finanzas.core.money import parse_amount
from mis_finanzas.importers.base import Check, ImportFileError, ParsedRow, ParseResult, RowError
from mis_finanzas.importers.tabular import decode_text

SUMMARY = ["INITIAL_BALANCE", "CREDITS", "DEBITS", "FINAL_BALANCE"]
COLUMNS = [
    "RELEASE_DATE",
    "TRANSACTION_TYPE",
    "REFERENCE_ID",
    "TRANSACTION_NET_AMOUNT",
    "PARTIAL_BALANCE",
]
# (decimal separator, thousands separator), in order of preference.
FORMATS = ((",", "."), (".", ","))
TARGET = "mercadopago/ARS"


@dataclass(frozen=True)
class _Layout:
    summary: list[str]  # INITIAL_BALANCE, CREDITS, DEBITS, FINAL_BALANCE, as printed
    rows: list[tuple[int, list[str]]]  # (line number, fields)


def _fields(line: list[str]) -> list[str]:
    return [field.strip() for field in line]


def _find_layout(lines: list[list[str]]) -> _Layout | None:
    summary_at = next((i for i, line in enumerate(lines) if _fields(line)[:4] == SUMMARY), None)
    header_at = next((i for i, line in enumerate(lines) if _fields(line)[:5] == COLUMNS), None)
    if summary_at is None or header_at is None or summary_at + 1 >= len(lines):
        return None
    rows = [
        (number, _fields(line))
        for number, line in enumerate(lines[header_at + 1 :], start=header_at + 2)
        if any(field.strip() for field in line)
    ]
    return _Layout(summary=_fields(lines[summary_at + 1])[:4], rows=rows)


def _read_layout(content: bytes) -> _Layout | None:
    text = decode_text(content)
    return _find_layout(list(csv.reader(io.StringIO(text), delimiter=";")))


@dataclass
class _Totals:
    balance: Decimal
    mismatches: int = 0
    total: Decimal = Decimal(0)
    credits: Decimal = Decimal(0)
    debits: Decimal = Decimal(0)

    def add(self, amount: Decimal, printed_balance: Decimal | None) -> None:
        self.balance += amount
        self.total += amount
        if amount > 0:
            self.credits += amount
        else:
            self.debits += -amount
        if printed_balance is not None:
            if printed_balance != self.balance:
                self.mismatches += 1
            self.balance = printed_balance


def _row(number: int, fields: list[str], fmt: tuple[str, str]) -> tuple[ParsedRow, Decimal | None]:
    """Raises `ValueError` for a field that can't be read."""
    if len(fields) < len(COLUMNS):
        raise ValueError(f"expected {len(COLUMNS)} fields, got {len(fields)}")
    day, description, reference, amount, balance = fields[:5]
    parsed = ParsedRow(
        line_number=number,
        date=datetime.strptime(day, "%d-%m-%Y").date(),
        amount=parse_amount(amount, *fmt),
        description=description,
        target=TARGET,
        reference=reference or None,
    )
    return parsed, parse_amount(balance, *fmt) if balance else None


def _checks(summary: list[Decimal], totals: _Totals) -> list[Check]:
    initial, credits, debits, final = summary
    return [
        Check("saldos fila a fila", Decimal(0), Decimal(totals.mismatches)),
        Check("saldo final", final, initial + totals.total),
        Check("créditos", abs(credits), totals.credits),
        Check("débitos", abs(debits), totals.debits),
    ]


def read(layout: _Layout, fmt: tuple[str, str]) -> ParseResult:
    """Read every row with one number format. Raises `ValueError` if the summary can't be read."""
    summary = [parse_amount(value, *fmt) for value in layout.summary]
    totals = _Totals(balance=summary[0])
    result = ParseResult(metadata={"separador_decimal": fmt[0]})
    for number, fields in layout.rows:
        try:
            row, balance = _row(number, fields, fmt)
        except ValueError as exc:
            result.errors.append(RowError(number, str(exc)))
            continue
        totals.add(row.amount, balance)
        result.rows.append(row)
    result.checks = _checks(summary, totals)
    if result.rows:
        result.metadata["desde"] = min(r.date for r in result.rows).isoformat()
        result.metadata["hasta"] = max(r.date for r in result.rows).isoformat()
    return result


class MercadoPagoAccountCsv:
    name = "mercadopago_account_csv"
    version = "1"

    def detect(self, filename: str, content: bytes) -> bool:
        if not filename.lower().endswith(".csv"):
            return False
        try:
            return _read_layout(content) is not None
        except ImportFileError:
            return False

    def parse(self, content: bytes, filename: str) -> ParseResult:
        layout = _read_layout(content)
        if layout is None or len(layout.summary) < len(SUMMARY):
            raise ImportFileError("not a Mercado Pago account summary export")
        readings = []
        for fmt in FORMATS:
            try:
                result = read(layout, fmt)
            except ValueError:
                continue
            if not result.errors and not result.failed_checks:
                return result
            readings.append(result)
        if not readings:
            raise ImportFileError("the summary amounts can't be read in any number format")
        return readings[0]
