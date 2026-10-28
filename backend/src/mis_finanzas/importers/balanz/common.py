"""Helpers shared by the Balanz importers."""

import re
from dataclasses import replace
from datetime import date, datetime

from mis_finanzas.importers.pdf_layout import HeaderRow, Line
from mis_finanzas.importers.pdf_words import PageWords, Word
from mis_finanzas.ledger.text import normalize_description

BROKER = "balanz"
# Text this much bigger or smaller than the table's is a heading or the legal footer.
SIZE_MARGIN = 1.0
_FOOTER = "BALANZ.COM"
# One amount as these tables print it: 2 decimals, or 10 for a price (`6,8825704114`).
_AMOUNT = re.compile(r"-?\d+(?:\.\d{3})*,(?:\d{10}|\d{2})")


def parse_date(text: str) -> date:
    """`1/3/2025` or `31/03/2025`. Raises `ValueError` otherwise."""
    return datetime.strptime(text.strip(), "%d/%m/%Y").date()


def text_size(line: Line) -> float:
    return max(w.size for w in line.words)


def is_bold(line: Line) -> bool:
    return all("bold" in w.fontname.lower() for w in line.words)


def is_table_end(header: HeaderRow, line: Line) -> bool:
    """A heading, the legal footer, or anything else printed at another size than the table."""
    if _FOOTER in normalize_description(line.text):
        return True
    return abs(text_size(line) - text_size(header.line)) > SIZE_MARGIN


def heading_above(lines: list[Line], header: HeaderRow, after: float) -> Line | None:
    """The closest line printed bigger than the table, between `after` and the header."""
    above = [
        line
        for line in lines
        if after < line.top < header.line.top
        and text_size(line) > text_size(header.line) + SIZE_MARGIN
    ]
    return above[-1] if above else None


def split_amounts(text: str) -> list[str] | None:
    """`145.769,874432,25` -> [`145.769,87`, `4432,25`]: two amounts printed with no gap.

    None unless the text is two or more whole amounts. Tries 2 decimals before 10 at each step,
    backing off when the rest doesn't split.
    """
    if _AMOUNT.fullmatch(text):
        return [text]
    head = re.match(r"-?\d+(?:\.\d{3})*,", text)
    if head is None:
        return None
    for decimals in (2, 10):
        end = head.end() + decimals
        rest = text[end:]
        if rest and text[head.end() : end].isdigit():
            tail = split_amounts(rest)
            if tail is not None:
                return [text[:end], *tail]
    return None


def _split_word(word: Word) -> list[Word]:
    """A word holding glued amounts, as one word per amount; x spread by character count."""
    if word.text.count(",") < 2:
        return [word]
    parts = split_amounts(word.text)
    if parts is None or len(parts) < 2:
        return [word]
    per_char = (word.x1 - word.x0) / len(word.text)
    words, x = [], word.x0
    for part in parts:
        width = per_char * len(part)
        words.append(replace(word, text=part, x0=round(x, 2), x1=round(x + width, 2)))
        x += width
    return words


def split_glued_amounts(page: PageWords) -> PageWords:
    """Adjacent right-aligned amounts can print with no space and extract as one word."""
    return replace(page, words=[w for word in page.words for w in _split_word(word)])
