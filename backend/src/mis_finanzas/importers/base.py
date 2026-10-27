"""What every importer produces. Parsing is pure: bytes in, rows out, no database access."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class ParsedRow:
    line_number: int
    date: date
    amount: Decimal
    description: str


@dataclass(frozen=True)
class RowError:
    line_number: int
    message: str


@dataclass
class ParseResult:
    rows: list[ParsedRow] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)


class ImportFileError(ValueError):
    """The file as a whole can't be read (wrong type, missing header, bad encoding)."""
