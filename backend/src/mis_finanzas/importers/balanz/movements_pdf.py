"""Balanz "Cuenta Corriente por Concertación" PDF: cash movements and instrument quantities.

**What is read:**
- Only rows under a header holding all 12 labels. Column positions differ from page to page,
  so each page's own header is used. `Impor. IVA` appears twice (IVA on the fee, IVA on
  the market rights).
- Two groups, each under a heading above its header row: `Instrumentos` and `Monedas`. A
  bold row with only a description opens a section, and a section runs on across pages.
  - An instrument section is titled `<name> - <TICKER> <code>`. Its rows are operations;
    quantities are in `Cant. VN`.
  - A currency section is titled `Pesos - $`, `Dólar MEP - usd`, `Dólares … - …`. Its rows
    are ledger movements: amount `Neto`, dated `Fecha Co.` (the statement's balances run by
    trade date).
- `Saldo Anterior` opens a section; each `Saldo al <date>` is the balance after that day.
  An instrument's intermediate `Saldo al` may print without a quantity: nothing to check.
- Long amounts in adjacent columns can print with no gap and extract as one word
  (`145.769,874432,25`); they are split back before reading the table.
- The page header, the legal footer and anything outside a table are never read.

**Checks:**
- every section ends with a `Saldo al` line;
- every `Saldo al` equals the opening balance plus the rows before it, for cash and for
  quantities.
"""

import enum
import math
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from functools import partial

from mis_finanzas.importers.amounts import parse_money
from mis_finanzas.importers.balanz.common import (
    BROKER,
    heading_above,
    is_bold,
    is_table_end,
    parse_date,
    split_glued_amounts,
)
from mis_finanzas.importers.base import Check, ParsedRow, ParseResult, RowError
from mis_finanzas.importers.pdf_layout import (
    HeaderRow,
    Line,
    TableRow,
    find_header_rows,
    lines,
    table_rows,
    visible,
)
from mis_finanzas.importers.pdf_words import PageWords
from mis_finanzas.investments.records import (
    InstrumentRef,
    InvestmentData,
    ParsedOperation,
    ParsedPosition,
    ParsedSnapshot,
    SnapshotSource,
)
from mis_finanzas.ledger.text import normalize_description

LABELS = (
    "Descripción",
    "Cant. VN",
    "Saldo",
    "Precio",
    "Bruto",
    "Arancel",
    "Impor. IVA",
    "Impor. Derech",
    "Impor. IVA",
    "Neto",
    "Fecha Co.",
    "Fecha Li.",
)
FEE_COLUMNS = ("Arancel", "Impor. IVA", "Impor. Derech", "Impor. IVA (2)")
TITLE = "CUENTA CORRIENTE POR CONCERTACION"
# Bigger text above a table that is the page's own header, not a group heading.
PAGE_HEADER = (TITLE, "COMITENTE", "CARTERA DISPONIBLE")
_PERIOD = re.compile(r"del (\d{1,2}/\d{1,2}/\d{4}) al (\d{1,2}/\d{1,2}/\d{4})", re.IGNORECASE)


class Group(enum.Enum):
    INSTRUMENTS = "INSTRUMENTOS"
    CASH = "MONEDAS"
    UNKNOWN = "?"


@dataclass
class _Section:
    group: Group
    target: str | None = None  # cash sections
    instrument: InstrumentRef | None = None  # instrument sections
    running: Decimal = Decimal(0)
    closing: Decimal | None = None
    mismatches: int = 0

    @property
    def value_column(self) -> str:
        return "Cant. VN" if self.group is Group.INSTRUMENTS else "Neto"


@dataclass
class _State:
    group: Group | None = None
    section: _Section | None = None
    sections: list[_Section] = field(default_factory=list)
    rows: list[ParsedRow] = field(default_factory=list)
    operations: list[ParsedOperation] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)


def cash_target(title: str) -> str:
    """`Pesos` -> `balanz/ARS`; `Dólar MEP` -> `balanz/MEP/USD`; `Dólares Cable` ->
    `balanz/CABLE/USD`. Raises `ValueError` for any other currency."""
    words = normalize_description(title).split()
    if words and words[0] == "PESOS":
        return f"{BROKER}/ARS"
    if words and words[0] in ("DOLAR", "DOLARES"):
        return "/".join([BROKER, *(["-".join(words[1:])] if len(words) > 1 else []), "USD"])
    raise ValueError("currency section not recognized")


def instrument_ref(title: str) -> InstrumentRef:
    """`CEDEAR APPLE INC. - AAPL 8445` -> ticker `AAPL`. Raises `ValueError` otherwise."""
    name, _, rest = title.rpartition(" - ")
    codes = rest.split()
    if not name or not codes:
        raise ValueError("instrument title without ' - TICKER'")
    return InstrumentRef(
        ticker=codes[0], name=name.strip(), broker_code=" ".join(codes[1:]) or None
    )


def _open_section(state: _State, title: str) -> _Section:
    if state.group is Group.INSTRUMENTS:
        section = _Section(Group.INSTRUMENTS, instrument=instrument_ref(title))
    elif state.group is Group.CASH:
        label = title.rpartition(" - ")[0] or title
        section = _Section(Group.CASH, target=cash_target(label))
    else:
        section = _Section(Group.UNKNOWN)
    state.sections.append(section)
    return section


def _amount(row: TableRow, column: str) -> Decimal | None:
    text = row.cell(column)
    return parse_money(text).amount if text else None


def _required(row: TableRow, column: str) -> Decimal:
    value = _amount(row, column)
    if value is None:
        raise ValueError(f"missing {column}")
    return value


def _close(section: _Section, row: TableRow) -> None:
    """`Saldo al d/m/yyyy`: count a mismatch, then follow the statement's balance."""
    balance = _amount(row, section.value_column)
    if balance is None:
        return
    if balance != section.running:
        section.mismatches += 1
    section.running = section.closing = balance


def _operation(section: _Section, row: TableRow, line_number: int) -> ParsedOperation:
    if section.instrument is None:
        raise ValueError("operation outside an instrument")
    settle = row.cell("Fecha Li.")
    return ParsedOperation(
        line_number=line_number,
        instrument=section.instrument,
        trade_date=parse_date(row.cell("Fecha Co.")),
        settle_date=parse_date(settle) if settle else None,
        description=row.cell("Descripción"),
        quantity=_required(row, "Cant. VN"),
        price=_amount(row, "Precio"),
        gross=_amount(row, "Bruto"),
        fees=sum((_amount(row, c) or Decimal(0) for c in FEE_COLUMNS), Decimal(0)),
        net=_amount(row, "Neto"),
    )


def _movement(state: _State, section: _Section, row: TableRow, line_number: int) -> None:
    if section.group is Group.INSTRUMENTS:
        operation = _operation(section, row, line_number)
        section.running += operation.quantity
        state.operations.append(operation)
        return
    if section.target is None:
        raise ValueError("row outside Instrumentos or Monedas")
    amount = _required(row, "Neto")
    section.running += amount
    state.rows.append(
        ParsedRow(
            line_number=line_number,
            date=parse_date(row.cell("Fecha Co.")),
            amount=amount,
            description=row.cell("Descripción"),
            target=section.target,
        )
    )


def _is_title(row: TableRow) -> bool:
    return all(is_bold(line) for line in row.lines) and set(row.cells) == {"Descripción"}


def _read_row(state: _State, row: TableRow, line_number: int) -> None:
    """Raises `ValueError` for a row that can't be read."""
    description = row.cell("Descripción")
    if _is_title(row):
        state.section = _open_section(state, description)
        return
    section = state.section
    if section is None:
        raise ValueError("row before any section title")
    norm = normalize_description(description)
    if norm.startswith("SALDO ANTERIOR"):
        section.running = _required(row, section.value_column)
    elif norm.startswith("SALDO AL"):
        _close(section, row)
    else:
        _movement(state, section, row, line_number)


def _group(heading: Line | None, current: Group | None) -> Group | None:
    if heading is None:
        return current
    text = normalize_description(heading.text)
    if text.startswith(PAGE_HEADER):
        return current
    return next((g for g in Group if g.value == text), Group.UNKNOWN)


def _read_table(state: _State, page: PageWords, header: HeaderRow, until: float) -> None:
    stop = partial(is_table_end, header)
    for row in table_rows(page, header, ["Descripción"], until=until, stop=stop):
        line_number = page.number * 1000 + int(row.top)
        try:
            _read_row(state, row, line_number)
        except ValueError as exc:
            state.errors.append(RowError(line_number, str(exc)))


def _read_page(state: _State, page: PageWords) -> None:
    page = split_glued_amounts(page)
    page_lines = lines(visible(page.words))
    headers = find_header_rows(page, LABELS)
    previous = 0.0
    for index, header in enumerate(headers):
        heading = heading_above(page_lines, header, after=previous)
        group = _group(heading, state.group)
        if group is not state.group:
            state.group, state.section = group, None
        until = headers[index + 1].line.top if index + 1 < len(headers) else math.inf
        _read_table(state, page, header, until)
        previous = header.line.top


def _period(pages: list[PageWords]) -> tuple[str, str] | None:
    for line in lines(visible(pages[0].words)) if pages else []:
        if match := _PERIOD.search(line.text):
            return match.group(1), match.group(2)
    return None


def _snapshot(state: _State, as_of: date) -> ParsedSnapshot:
    positions = [
        ParsedPosition(instrument=s.instrument, quantity=s.closing)
        for s in state.sections
        if s.instrument is not None and s.closing is not None
    ]
    return ParsedSnapshot(as_of=as_of, source=SnapshotSource.MOVEMENTS, positions=positions)


def _checks(state: _State) -> list[Check]:
    cash = [s for s in state.sections if s.group is Group.CASH]
    held = [s for s in state.sections if s.group is Group.INSTRUMENTS]
    unclosed = sum(s.closing is None for s in state.sections)
    return [
        Check("secciones con saldo final", Decimal(0), Decimal(unclosed)),
        Check(
            "saldos de monedas fila a fila", Decimal(0), Decimal(sum(s.mismatches for s in cash))
        ),
        Check(
            "cantidades de instrumentos fila a fila",
            Decimal(0),
            Decimal(sum(s.mismatches for s in held)),
        ),
    ]


class BalanzMovementsPdf:
    name = "balanz_movements_pdf"
    version = "1"

    def detect_pages(self, pages: list[PageWords]) -> bool:
        if not pages:
            return False
        first = lines(visible(pages[0].words))
        titled = any(normalize_description(line.text).startswith(TITLE) for line in first[:3])
        return titled and any(find_header_rows(page, LABELS) for page in pages)

    def parse_pages(self, pages: list[PageWords]) -> ParseResult:
        state = _State()
        for page in pages:
            _read_page(state, page)
        period = _period(pages)
        checks = [Check("período del resumen", Decimal(1), Decimal(period is not None))]
        result = ParseResult(rows=state.rows, errors=state.errors, checks=checks + _checks(state))
        if period is not None:
            result.metadata["periodo"] = f"{period[0]} al {period[1]}"
            result.investments = InvestmentData(
                broker=BROKER,
                operations=state.operations,
                snapshot=_snapshot(state, parse_date(period[1])),
            )
        return result
