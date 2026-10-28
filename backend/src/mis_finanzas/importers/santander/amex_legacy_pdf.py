"""Santander American Express statement PDF, older layout ("AMERICAN EXPRESS RESUMEN DE
CUENTA", letter-size pages). Newer statements use the Visa design: see `visa_pdf`.

**What is read:**
- Each page repeats the header `Fecha · Comprobante · Referencia · $ · U$S`. The legal text
  runs on inside the same area across pages, so a line counts as a row only when it holds an
  amount by itself in the `$` or `U$S` column (`1.234,56`, or `1.234,56-` for a credit).
  Anything else (legal text, separators) is skipped.
- Dates print year first, `25 Junio 28`; later rows print only the day (`30`) while the year
  and month stay the same. The voucher number follows the date, before the reference.
- `SALDO ANTERIOR` is the previous balance, not a movement. A line of underscores starts the
  card's purchases, which end in `Tarjeta NNNN Total Consumos de … $ … * U$S …*`.
- `SALDO ACTUAL $ … U$S …`, on the last page, is the new balance.

**Signs:** charges print positive, credits with a trailing minus. On the card account
(`santander/amex/ARS|USD`, as in the newer layout) a charge is money out, so every amount is
negated.

**Checks, per currency:** each card's purchases = its `Total Consumos`; saldo anterior +
movements = saldo actual.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from mis_finanzas.core.money import parse_amount
from mis_finanzas.importers.base import Check, ParsedRow, ParseResult, RowError
from mis_finanzas.importers.pdf_layout import HeaderRow, Line, find_header_rows, line_cells
from mis_finanzas.importers.pdf_words import PageWords
from mis_finanzas.importers.santander.common import page_lines, target
from mis_finanzas.ledger.text import normalize_description

TITLE = "AMERICAN EXPRESS RESUMEN DE CUENTA"
LABELS = ("Fecha", "Comprobante", "Referencia", "$", "U$S")
AMOUNT_COLUMNS = {"$": "ARS", "U$S": "USD"}
END_OF_TABLE = ("SALDO ACTUAL", "DEBITAREMOS", "EL PRESENTE ES COPIA")
MONTHS = {
    "ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AGO": 8, "SEP": 9, "SET": 9, "OCT": 10, "NOV": 11, "DIC": 12,
}  # fmt: skip
# Words up to this far left of a label still belong to the column before it.
LABEL_SLACK = 2.0
_AMOUNT = re.compile(r"^\d{1,3}(?:\.\d{3})*,\d{2}-?$")
_CLOSING = re.compile(r"CIERRE (\d{1,2} [A-Z]{3} \d{2})")
_CARD_TOTAL = re.compile(r"TARJETA (\d{4,5}) TOTAL CONSUMOS DE")
_BALANCE = {
    "ARS": re.compile(r"(?<!U)\$\s*(\d[\d.]*,\d{2}-?)"),
    "USD": re.compile(r"U\$S\s*(\d[\d.]*,\d{2}-?)"),
}


def _zero() -> dict[str, Decimal]:
    return {"ARS": Decimal(0), "USD": Decimal(0)}


def _signed(text: str) -> Decimal:
    """`1.234,56` -> 1234.56; `1.234,56-` -> -1234.56."""
    text = text.strip()
    negative = text.endswith("-")
    value = parse_amount(text.rstrip("-"))
    return -value if negative else value


def _amount_cell(text: str) -> str | None:
    """The amount in a `$`/`U$S` cell, when the cell is an amount and nothing else."""
    text = re.sub(r"^(U\$S|\$)\s*", "", text.replace("*", "").strip())
    return text if _AMOUNT.match(text) else None


def _amounts(found: dict[str, str]) -> dict[str, str]:
    return {
        currency: amount
        for label, currency in AMOUNT_COLUMNS.items()
        if (amount := _amount_cell(found.get(label, ""))) is not None
    }


@dataclass
class _CardTotal:
    number: str
    printed: dict[str, Decimal]
    total: dict[str, Decimal]


@dataclass
class _State:
    year_month: tuple[int, int] | None = None
    last_date: date | None = None
    previous: dict[str, Decimal] | None = None
    current: dict[str, Decimal] | None = None
    printed: dict[str, Decimal] = field(default_factory=_zero)
    card_printed: dict[str, Decimal] = field(default_factory=_zero)  # since the separator
    cards: list[_CardTotal] = field(default_factory=list)
    rows: list[ParsedRow] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)


def _movement_date(state: _State, words: list[str]) -> date:
    """`25 Junio 28` (year, month, day), or `30` with the year and month of the row above.

    Raises `ValueError` for anything else, or a day the month doesn't have.
    """
    if len(words) == 3:
        month = MONTHS.get(normalize_description(words[1])[:3])
        if month is None or not (words[0].isdigit() and words[2].isdigit()):
            raise ValueError("unreadable date")
        state.year_month = (2000 + int(words[0]), month)
        return date(*state.year_month, int(words[2]))
    if len(words) == 1 and words[0].isdigit() and state.year_month is not None:
        return date(*state.year_month, int(words[0]))
    raise ValueError("unreadable date")


def _split_left(line: Line, header: HeaderRow) -> tuple[list[str], str]:
    """The date's words and the voucher number: everything left of the Referencia label."""
    by_label = {c.label: c for c in header.columns}
    voucher_x0 = by_label["Comprobante"].label_x0 - LABEL_SLACK
    reference_x0 = by_label["Referencia"].label_x0 - LABEL_SLACK
    dates = [w.text for w in line.words if w.x0 < voucher_x0]
    voucher = [w.text for w in line.words if voucher_x0 <= w.x0 < reference_x0]
    return dates, " ".join(voucher)


def _card_total(state: _State, line: Line, found: dict[str, str]) -> None:
    match = _CARD_TOTAL.search(normalize_description(line.text))
    total = {currency: _signed(amount) for currency, amount in _amounts(found).items()}
    state.cards.append(
        _CardTotal(match.group(1) if match else "?", dict(state.card_printed), total)
    )
    state.card_printed = _zero()


def _movement(
    state: _State, line: Line, header: HeaderRow, found: dict[str, str], line_number: int
) -> None:
    """Raises `ValueError` for a row that can't be read."""
    amounts = _amounts(found)
    if not amounts:
        return  # legal text, empty lines
    reference = re.sub(r"(\s+(\$|U\$S))+$", "", found.get("Referencia", "")).strip()
    if normalize_description(reference).startswith("SALDO ANTERIOR"):
        state.previous = {c: _signed(a) for c, a in amounts.items()}
        return
    dates, voucher = _split_left(line, header)
    if dates:
        state.last_date = _movement_date(state, dates)
    if state.last_date is None:
        raise ValueError("movement before any date")
    if len(amounts) != 1:
        raise ValueError("expected one amount, in pesos or in dollars")
    [(currency, text)] = amounts.items()
    printed = _signed(text)
    state.printed[currency] += printed
    state.card_printed[currency] += printed
    state.rows.append(
        ParsedRow(
            line_number=line_number,
            date=state.last_date,
            amount=-printed,
            description=reference,
            target=target("amex", currency),
            reference=voucher or None,
        )
    )


def _read_line(state: _State, line: Line, header: HeaderRow, line_number: int) -> None:
    text = normalize_description(line.text)
    if text and set(text.replace(" ", "")) == {"_"}:
        state.card_printed = _zero()  # the card's purchases start here
        return
    found = line_cells(line, header)
    if "TOTAL CONSUMOS DE" in text:
        _card_total(state, line, found)
    else:
        _movement(state, line, header, found, line_number)


def _read_page(state: _State, page: PageWords, header: HeaderRow) -> None:
    for line in page_lines(page):
        if line.top <= header.bottom:
            continue
        if normalize_description(line.text).startswith(END_OF_TABLE):
            break
        line_number = page.number * 1000 + int(line.top)
        try:
            _read_line(state, line, header, line_number)
        except ValueError as exc:
            state.errors.append(RowError(line_number, str(exc)))


def _current_balance(pages: list[PageWords]) -> dict[str, Decimal] | None:
    """The last `SALDO ACTUAL` that prints amounts (earlier pages print the label only)."""
    found = None
    for page in pages:
        for line in page_lines(page):
            if normalize_description(line.text).startswith("SALDO ACTUAL"):
                amounts = {
                    currency: _signed(match.group(1))
                    for currency, pattern in _BALANCE.items()
                    if (match := pattern.search(line.text))
                }
                found = amounts or found
    return found


def _checks(state: _State) -> list[Check]:
    found = Decimal(int(state.previous is not None and state.current is not None))
    checks = [Check("saldo anterior y saldo actual", Decimal(1), found)]
    for currency in ("ARS", "USD"):
        for card in state.cards:
            name = f"total consumos tarjeta {card.number} {currency}"
            expected = card.total.get(currency, Decimal(0))
            checks.append(Check(name, expected, card.printed[currency]))
        if state.previous is not None and state.current is not None:
            expected = state.current.get(currency, Decimal(0))
            actual = state.previous.get(currency, Decimal(0)) + state.printed[currency]
            checks.append(Check(f"saldo actual {currency}", expected, actual))
    return checks


def _closing(pages: list[PageWords]) -> str | None:
    """The closing date as printed (`29 May 25`), for the preview only."""
    for line in page_lines(pages[0]):
        if match := _CLOSING.search(normalize_description(line.text)):
            return match.group(1)
    return None


class SantanderAmexLegacyPdf:
    name = "santander_amex_legacy_pdf"
    version = "1"

    def detect_pages(self, pages: list[PageWords]) -> bool:
        if not pages:
            return False
        first = page_lines(pages[0])[:2]
        titled = any(normalize_description(line.text).startswith(TITLE) for line in first)
        return titled and bool(find_header_rows(pages[0], LABELS))

    def parse_pages(self, pages: list[PageWords]) -> ParseResult:
        state = _State()
        for page in pages:
            for header in find_header_rows(page, LABELS)[:1]:
                _read_page(state, page, header)
        state.current = _current_balance(pages)
        result = ParseResult(rows=state.rows, errors=state.errors, checks=_checks(state))
        closing = _closing(pages)
        if closing:
            result.metadata["cierre"] = closing
        result.metadata["tarjetas"] = ",".join(card.number for card in state.cards)
        return result
