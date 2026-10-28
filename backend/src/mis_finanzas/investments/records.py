"""What a broker statement says about investments, as plain records. Parsers produce them;
`investments.store` writes them. No database access here.
"""

import enum
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


class SnapshotSource(enum.StrEnum):
    HOLDINGS = "tenencias"  # a holdings statement: quantities, prices and values
    MOVEMENTS = "movimientos"  # a movements statement's closing quantities only


@dataclass(frozen=True)
class InstrumentRef:
    ticker: str
    name: str
    asset_class: str | None = None
    broker_code: str | None = None


@dataclass(frozen=True)
class ParsedOperation:
    """A change in an instrument's quantity. Amounts are as printed: the statement's
    instrument section doesn't name their currency."""

    line_number: int
    instrument: InstrumentRef
    trade_date: date
    settle_date: date | None
    description: str
    quantity: Decimal
    price: Decimal | None = None
    gross: Decimal | None = None
    fees: Decimal = Decimal(0)
    net: Decimal | None = None


@dataclass(frozen=True)
class ParsedPosition:
    instrument: InstrumentRef
    quantity: Decimal
    price: Decimal | None = None
    value: Decimal | None = None
    currency: str | None = None  # of price and value


@dataclass(frozen=True)
class ParsedCash:
    label: str  # as the statement names it: "Pesos", "US Dollar (Cable)"
    currency: str
    amount: Decimal


@dataclass(frozen=True)
class ParsedSnapshot:
    as_of: date
    source: SnapshotSource
    positions: list[ParsedPosition] = field(default_factory=list)
    cash: list[ParsedCash] = field(default_factory=list)


@dataclass
class InvestmentData:
    broker: str
    operations: list[ParsedOperation] = field(default_factory=list)
    snapshot: ParsedSnapshot | None = None
