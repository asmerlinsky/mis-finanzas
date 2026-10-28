"""What ARCA's files say about invoices, as plain records. Parsers produce them;
`monotributo.store` writes them. No database access here.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

# ARCA's comprobante type codes this app reads, and whether each adds to or subtracts from
# gross income.
INVOICE_TYPES: dict[int, tuple[str, int]] = {
    11: ("Factura C", 1),
    12: ("Nota de Débito C", 1),
    13: ("Nota de Crédito C", -1),
    19: ("Factura E", 1),
    20: ("Nota de Débito E", 1),
    21: ("Nota de Crédito E", -1),
}


@dataclass(frozen=True)
class InvoiceKey:
    type_code: int
    point_of_sale: int
    number: int

    def __str__(self) -> str:
        return f"{INVOICE_TYPES[self.type_code][0]} {self.point_of_sale:05d}-{self.number:08d}"


@dataclass(frozen=True)
class ParsedInvoice:
    """One row of "Mis Comprobantes - Emitidos". Amounts are in the invoice's currency, as
    printed (positive, also for credit notes)."""

    line_number: int
    key: InvoiceKey
    number_to: int
    issued_on: date
    cae: str
    receiver_doc_type: str
    receiver_doc: str
    receiver_name: str
    currency: str  # "ARS" or "USD"
    fx_rate: Decimal  # pesos per unit of `currency`; 1 for pesos
    net_taxed: Decimal
    net_untaxed: Decimal
    exempt: Decimal
    other_taxes: Decimal
    vat: Decimal
    total: Decimal

    @property
    def total_ars(self) -> Decimal:
        """Signed: credit notes subtract."""
        return INVOICE_TYPES[self.key.type_code][1] * self.total * self.fx_rate


@dataclass(frozen=True)
class ParsedInvoicePdf:
    """What an invoice PDF's first page identifies it by."""

    key: InvoiceKey
    issued_on: date
    currency: str
    total: Decimal
    cae: str


@dataclass
class InvoiceData:
    invoices: list[ParsedInvoice] = field(default_factory=list)
    pdf: ParsedInvoicePdf | None = None
