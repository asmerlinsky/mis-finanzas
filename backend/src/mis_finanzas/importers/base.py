"""What every importer produces. Parsing is pure: bytes in, rows out, no database access."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

# The single target of a generic (column-mapping) import: its mapping names the account.
DEFAULT_TARGET = "default"


@dataclass(frozen=True)
class ParsedRow:
    """One movement. `target` names the sub-account it belongs to inside the statement,
    e.g. `santander/CA/ARS` or `visa/USD`; each target is mapped to one ledger account."""

    line_number: int
    date: date
    amount: Decimal
    description: str
    target: str = DEFAULT_TARGET
    reference: str | None = None
    installment: tuple[int, int] | None = None  # cuota (number, total)


@dataclass(frozen=True)
class RowError:
    line_number: int
    message: str


@dataclass(frozen=True)
class Check:
    """A total the statement states (`expected`) against what was parsed (`actual`).

    A failed check means the layout was misread, so it blocks the import.
    """

    name: str
    expected: Decimal
    actual: Decimal

    @property
    def ok(self) -> bool:
        return self.expected == self.actual


@dataclass
class ParseResult:
    rows: list[ParsedRow] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def failed_checks(self) -> list[Check]:
        return [c for c in self.checks if not c.ok]


class ImportFileError(ValueError):
    """The file as a whole can't be read (wrong type, missing header, bad encoding)."""
