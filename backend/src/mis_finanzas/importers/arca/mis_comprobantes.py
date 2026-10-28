"""ARCA "Mis Comprobantes - Emitidos" CSV export: every invoice issued, history included.

**What is read:** one header row (`;`-separated, names and values usually quoted) and one
invoice per row. Columns are found
**by header name**, not position, so columns ARCA adds later don't matter. Amounts use a comma
decimal and are in the invoice's currency; `Tipo Cambio` converts them to pesos.

**Row errors** (shown in the preview; they block the import unless skipped):
- a comprobante type this app doesn't know (only Facturas, Notas de Débito and Notas de
  Crédito C and E);
- a currency other than pesos or dollars;
- `Imp. Total` different from the sum of its parts (net taxed + untaxed + exempt + other taxes
  + VAT): the row was misread, or edited.
"""

import csv
import io
import re
from datetime import date
from decimal import Decimal

from mis_finanzas.core.money import parse_amount
from mis_finanzas.importers.base import ImportFileError, ParseResult, RowError
from mis_finanzas.importers.tabular import decode_text
from mis_finanzas.monotributo.records import (
    INVOICE_TYPES,
    InvoiceData,
    InvoiceKey,
    ParsedInvoice,
)

DETECT = ("Tipo de Comprobante", "Punto de Venta", "Cód. Autorización", "Imp. Total")
PARTS = (
    "Imp. Neto Gravado Total",
    "Imp. Neto No Gravado",
    "Imp. Op. Exentas",
    "Otros Tributos",
    "Total IVA",
)
REQUIRED = (
    "Fecha de Emisión",
    *DETECT,
    "Número Desde",
    "Número Hasta",
    "Tipo Doc. Receptor",
    "Nro. Doc. Receptor",
    "Denominación Receptor",
    "Tipo Cambio",
    "Moneda",
    *PARTS,
)
# ARCA's own currency codes, and ISO codes as some exports print them.
CURRENCIES = {"PES": "ARS", "ARS": "ARS", "$": "ARS", "DOL": "USD", "USD": "USD"}


def _header(text: str) -> list[str]:
    """The first line's column names. ARCA quotes them (`"Fecha de Emisión";…`)."""
    first = text.splitlines()[0] if text else ""
    return [name.strip() for name in next(csv.reader([first], delimiter=";"), [])]


def _type_code(text: str) -> int:
    """`11`, or `11 - Factura C` should the type print with its name. Raises `ValueError`."""
    match = re.match(r"\s*(\d+)", text)
    if match is None:
        raise ValueError("unreadable comprobante type")
    return int(match.group(1))


def _amount(text: str) -> Decimal:
    return parse_amount(text) if text.strip() else Decimal(0)


def _invoice(line_number: int, row: dict[str, str]) -> ParsedInvoice:
    """Raises `ValueError` for a row that can't be read or doesn't add up."""
    type_code = _type_code(row["Tipo de Comprobante"])
    if type_code not in INVOICE_TYPES:
        raise ValueError(f"comprobante type {type_code} is not supported")
    currency = CURRENCIES.get(row["Moneda"].strip().upper())
    if currency is None:
        raise ValueError(f"currency {row['Moneda']!r} is not supported")
    parts = [_amount(row[name]) for name in PARTS]
    total = _amount(row["Imp. Total"])
    if sum(parts, Decimal(0)) != total:
        raise ValueError("Imp. Total is not the sum of its parts")
    rate = _amount(row["Tipo Cambio"]) if currency == "USD" else Decimal(1)
    if rate <= 0:
        raise ValueError("missing Tipo Cambio")
    return ParsedInvoice(
        line_number=line_number,
        key=InvoiceKey(type_code, int(row["Punto de Venta"]), int(row["Número Desde"])),
        number_to=int(row["Número Hasta"] or row["Número Desde"]),
        issued_on=date.fromisoformat(row["Fecha de Emisión"].strip()),
        cae=row["Cód. Autorización"].strip(),
        receiver_doc_type=row["Tipo Doc. Receptor"].strip(),
        receiver_doc=row["Nro. Doc. Receptor"].strip(),
        receiver_name=row["Denominación Receptor"].strip(),
        currency=currency,
        fx_rate=rate,
        net_taxed=parts[0],
        net_untaxed=parts[1],
        exempt=parts[2],
        other_taxes=parts[3],
        vat=parts[4],
        total=total,
    )


class MisComprobantesCsv:
    name = "arca_mis_comprobantes_csv"
    version = "1"

    def detect(self, filename: str, content: bytes) -> bool:
        if not filename.lower().endswith(".csv"):
            return False
        header = _header(decode_text(content))
        return all(name in header for name in DETECT)

    def parse(self, content: bytes, filename: str) -> ParseResult:
        reader = csv.DictReader(io.StringIO(decode_text(content)), delimiter=";")
        fields = [name.strip() for name in reader.fieldnames or []]
        missing = [name for name in REQUIRED if name not in fields]
        if missing:
            raise ImportFileError(f"missing columns: {', '.join(missing)}")
        reader.fieldnames = fields
        data, errors = InvoiceData(), []
        for line_number, row in enumerate(reader, start=2):
            if not any((value or "").strip() for value in row.values()):
                continue
            try:
                data.invoices.append(_invoice(line_number, {k: v or "" for k, v in row.items()}))
            except (ValueError, KeyError) as exc:
                errors.append(RowError(line_number, str(exc)))
        result = ParseResult(errors=errors, invoices=data)
        if data.invoices:
            days = [i.issued_on for i in data.invoices]
            result.metadata["periodo"] = f"{min(days):%d/%m/%Y} - {max(days):%d/%m/%Y}"
        return result
