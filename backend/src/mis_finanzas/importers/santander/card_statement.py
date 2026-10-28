"""Santander credit card statements: one reader for every layout Santander prints them in.

A `CardLayout` names a layout's section titles, column labels and summary lines. Three use it:
- the Visa statement PDF ("Resumen Visa");
- the American Express statement PDF in the same design ("Resumen American Express");
- the Visa section inside the account statement ("Mi resumen de cuenta").

**Sections**, each under its title and a header row:
- payments and refunds (opening with `Saldo anterior`, the previous statement's balance, which
  is not a movement);
- one movements table per card, ending in that card's subtotal;
- taxes, interest and charges.

A table continues on the next page under a repeated header. Dates print only on a day's first
row; the rest inherit it.

**Signs:** statements print charges positive and payments negative. On the card account
(targets `santander/<product>/ARS|USD`) a charge is money out, so every amount is negated.

**Checks, per currency:**
- each card's movements = its subtotal;
- saldo anterior + payments = the payments' closing line;
- the taxes = their total, where the layout prints one;
- saldo anterior + everything = `Total a pagar`.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from functools import partial

from mis_finanzas.importers.amounts import parse_money
from mis_finanzas.importers.base import Check, ParsedRow, RowError
from mis_finanzas.importers.pdf_layout import (
    HeaderRow,
    Line,
    TableRow,
    find_header_rows,
    table_rows,
)
from mis_finanzas.importers.pdf_words import PageWords
from mis_finanzas.importers.santander.common import PAGE_NUMBER, amounts_by_currency, page_lines
from mis_finanzas.importers.santander.common import parse_date as parse_short_date
from mis_finanzas.importers.santander.common import target as santander_target
from mis_finanzas.ledger.text import normalize_description

PAYMENTS, CARD, TAXES = "pagos", "tarjeta", "impuestos"
# What a summary line closes: a card's subtotal, the payments, the taxes, or the statement.
SUBTOTAL, PREVIOUS, TAXES_TOTAL, TOTAL_DUE = "subtotal", "anterior", "impuestos", "total"
_CARD_NUMBER = re.compile(r"TERMINADA EN (\d{4,5})")
_INSTALLMENT = re.compile(r"^(\d+)\s+de\s+(\d+)$")


@dataclass(frozen=True)
class CardLayout:
    product: str  # target segment: "visa", "amex"
    simple_labels: tuple[str, ...]  # payments and taxes tables
    card_labels: tuple[str, ...]  # a card's movements table
    amount_columns: dict[str, str]  # label -> currency
    titles: dict[str, str]  # normalized title prefix -> section
    # Normalized prefix -> what the line closes; a value of None means "depends on the
    # section": PREVIOUS after payments, TAXES_TOTAL after taxes.
    summaries: dict[str, str | None]
    stops: tuple[str, ...] = ()  # other lines that end a table

    def target(self, currency: str) -> str:
        return santander_target(self.product, currency)


def _zero() -> dict[str, Decimal]:
    return {"ARS": Decimal(0), "USD": Decimal(0)}


@dataclass
class _Card:
    number: str
    printed: dict[str, Decimal] = field(default_factory=_zero)
    subtotal: dict[str, Decimal] | None = None


@dataclass
class CardStatement:
    """What was read; `checks()` compares it with the statement's own totals."""

    section: str | None = None
    seen: set[str] = field(default_factory=set)  # sections whose title was found
    last_date: date | None = None
    previous_balance: dict[str, Decimal] | None = None
    previous_summary: dict[str, Decimal] | None = None
    taxes_total: dict[str, Decimal] | None = None
    total_due: dict[str, Decimal] | None = None
    printed: dict[str, dict[str, Decimal]] = field(default_factory=dict)  # section -> sums
    cards: list[_Card] = field(default_factory=list)
    rows: list[ParsedRow] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)


def _summary_kind(layout: CardLayout, line: Line) -> tuple[str, str | None] | None:
    """(prefix, kind) of a summary line, longest prefix first ("TOTAL A PAGAR" before "TOTAL")."""
    text = normalize_description(line.text)
    for prefix in sorted(layout.summaries, key=len, reverse=True):
        if text.startswith(prefix):
            return prefix, layout.summaries[prefix]
    return None


def _is_table_end(layout: CardLayout, line: Line) -> bool:
    text = normalize_description(line.text)
    return (
        _summary_kind(layout, line) is not None
        or text.startswith(("COPIA FIEL", *layout.stops))
        or PAGE_NUMBER.match(line.text) is not None
    )


def _title(layout: CardLayout, line: Line) -> str | None:
    text = normalize_description(line.text)
    return next((kind for title, kind in layout.titles.items() if text.startswith(title)), None)


def _headers(layout: CardLayout, page: PageWords) -> list[HeaderRow]:
    """Card headers, plus the simple headers that aren't the same line as a card header."""
    cards = find_header_rows(page, layout.card_labels)
    card_tops = {header.line.top for header in cards}
    simple = [
        h for h in find_header_rows(page, layout.simple_labels) if h.line.top not in card_tops
    ]
    return sorted(cards + simple, key=lambda header: header.line.top)


def _amount(layout: CardLayout, row: TableRow) -> tuple[str, Decimal]:
    filled = [
        (currency, row.cell(label))
        for label, currency in layout.amount_columns.items()
        if row.cell(label)
    ]
    if len(filled) != 1:
        raise ValueError("expected one amount, in pesos or in dollars")
    currency, text = filled[0]
    return currency, parse_money(text).amount


def _installment(text: str) -> tuple[int, int] | None:
    match = _INSTALLMENT.match(text.strip())
    return (int(match.group(1)), int(match.group(2))) if match else None


def _movement(layout: CardLayout, state: CardStatement, row: TableRow, line_number: int) -> None:
    """Raises `ValueError` for a row that can't be read."""
    if state.last_date is None:
        raise ValueError("movement before any date")
    currency, printed = _amount(layout, row)
    section = state.section or CARD
    sums = state.printed.setdefault(section, _zero())
    sums[currency] += printed
    if section == CARD and state.cards:
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
            target=layout.target(currency),
            reference=row.cell("Comprobante") or None,
            installment=installment,
        )
    )


def _read_row(layout: CardLayout, state: CardStatement, row: TableRow, line_number: int) -> None:
    if row.cell("Fecha"):
        state.last_date = parse_short_date(row.cell("Fecha"))
    if normalize_description(row.cell("Descripción")).startswith("SALDO ANTERIOR"):
        state.previous_balance = {
            c: parse_money(row.cell(label)).amount
            for label, c in layout.amount_columns.items()
            if row.cell(label)
        }
        return
    _movement(layout, state, row, line_number)


def _read_table(
    layout: CardLayout, state: CardStatement, page: PageWords, header: HeaderRow, until: float
) -> None:
    rows = table_rows(
        page,
        header,
        key_columns=list(layout.amount_columns),
        until=until,
        stop=partial(_is_table_end, layout),
    )
    for index, row in enumerate(rows):
        line_number = page.number * 1000 + int(header.line.top) + index
        try:
            _read_row(layout, state, row, line_number)
        except ValueError as exc:
            state.errors.append(RowError(line_number, str(exc)))


def _summary(layout: CardLayout, state: CardStatement, line: Line) -> None:
    found = _summary_kind(layout, line)
    if found is None:
        return
    kind = found[1]
    if kind is None:
        kind = PREVIOUS if state.section == PAYMENTS else TAXES_TOTAL
    amounts = amounts_by_currency(line.text)
    if kind == SUBTOTAL and state.cards:
        state.cards[-1].subtotal = amounts
    elif kind == PREVIOUS:
        state.previous_summary = amounts
    elif kind == TAXES_TOTAL:
        state.taxes_total = amounts
    elif kind == TOTAL_DUE:
        state.total_due = amounts


def _card_number(lines: list[Line], title: Line) -> str:
    """The card number on the title line, or on the first line below it that has one."""
    for line in lines:
        if line.top >= title.top and (
            match := _CARD_NUMBER.search(normalize_description(line.text))
        ):
            return match.group(1)
    return "?"


@dataclass(frozen=True)
class _Event:
    top: float
    kind: str  # "title", "header" or "summary"
    line: Line
    header: HeaderRow | None = None


def _events(layout: CardLayout, page: PageWords) -> list[_Event]:
    lines = page_lines(page)
    events = [_Event(h.line.top, "header", h.line, h) for h in _headers(layout, page)]
    events += [_Event(line.top, "title", line) for line in lines if _title(layout, line)]
    events += [
        _Event(line.top, "summary", line)
        for line in lines
        if _summary_kind(layout, line) is not None
    ]
    return sorted(events, key=lambda event: event.top)


def read_page(layout: CardLayout, state: CardStatement, page: PageWords) -> None:
    events = _events(layout, page)
    for index, event in enumerate(events):
        if event.kind == "title":
            state.section = _title(layout, event.line)
            state.seen.add(state.section or "")
            if state.section == CARD:
                state.cards.append(_Card(_card_number(page_lines(page), event.line)))
        elif event.kind == "summary":
            _summary(layout, state, event.line)
        elif event.header is not None:
            until = events[index + 1].top if index + 1 < len(events) else float("inf")
            _read_table(layout, state, page, event.header, until)


def _check(name: str, expected: dict[str, Decimal] | None, actual: Decimal, currency: str) -> Check:
    return Check(name, (expected or {}).get(currency, Decimal(0)), actual)


def opening_not_printed(state: CardStatement) -> bool:
    """No payments section and no `Saldo anterior`: the statement doesn't print its opening
    balance. It is zero when nothing was owed, but a balance can also carry over unprinted
    (a credit after a refund did, on the first statement in the new layout)."""
    return state.previous_balance is None and PAYMENTS not in state.seen


def implied_opening(state: CardStatement) -> dict[str, Decimal] | None:
    """`Total a pagar` minus everything read, per currency, when the opening isn't printed."""
    if not opening_not_printed(state) or state.total_due is None:
        return None
    return {
        currency: state.total_due.get(currency, Decimal(0))
        - sum((sums[currency] for sums in state.printed.values()), Decimal(0))
        for currency in ("ARS", "USD")
    }


def describe_opening(opening: dict[str, Decimal]) -> str:
    return f"ARS {opening['ARS']} / USD {opening['USD']}"


def checks(state: CardStatement, prefix: str = "") -> list[Check]:
    """`Total a pagar` must always be found. When the opening balance isn't printed, the
    total can't be checked (see `opening_not_printed`); the card subtotals still are, and the
    implied opening balance is shown instead (`implied_opening`)."""
    opening_found = state.previous_balance is not None or PAYMENTS not in state.seen
    found = Decimal(int(opening_found and state.total_due is not None))
    result = [Check(f"{prefix}saldo anterior y total a pagar", Decimal(1), found)]
    previous = state.previous_balance or {}
    for currency in ("ARS", "USD"):
        for card in state.cards:
            name = f"{prefix}subtotal tarjeta {card.number} {currency}"
            result.append(_check(name, card.subtotal, card.printed[currency], currency))
        sums = {section: state.printed.get(section, _zero())[currency] for section in state.printed}
        opening = previous.get(currency, Decimal(0))
        if state.previous_summary is None and PAYMENTS in state.seen:
            # The payments' closing line wasn't recognized: never skip its check silently.
            name = f"{prefix}saldo del resumen anterior {currency}"
            result.append(Check(name, Decimal(1), Decimal(0)))
        if state.previous_summary is not None:
            name = f"{prefix}saldo del resumen anterior {currency}"
            actual = opening + sums.get(PAYMENTS, Decimal(0))
            result.append(_check(name, state.previous_summary, actual, currency))
        if state.taxes_total is not None:
            name = f"{prefix}total de impuestos {currency}"
            result.append(_check(name, state.taxes_total, sums.get(TAXES, Decimal(0)), currency))
        if state.total_due is not None and not opening_not_printed(state):
            name = f"{prefix}total a pagar {currency}"
            actual = opening + sum(sums.values(), Decimal(0))
            result.append(_check(name, state.total_due, actual, currency))
    return result
