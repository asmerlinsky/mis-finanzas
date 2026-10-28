"""An invoice PDF as ARCA's "Comprobantes en línea" prints it, to attach to its invoice.

**What is read**, from page 1 only (pages 2 and 3 are the Duplicado and Triplicado):
- the title (`FACTURA`, `NOTA DE CRÉDITO`, `NOTA DE DÉBITO`, possibly `DE EXPORTACIÓN`) and
  the big letter (`C`, `E`): together they give the comprobante type;
- `Compr. Nro: PPPPP-NNNNNNNN`, `Fecha de Emisión: dd/mm/yyyy`;
- `Importe Total: USD 3907,69` (or `$ …`): the total and its currency;
- `CAE N°: …`.

Nothing else is read: not the receiver, the items or the issuer's data.

**Check:** the `COD.` printed under the letter equals the type read from title and letter.
Whether the invoice exists, and its total and CAE, are checked against Mis Comprobantes when
the PDF is attached.
"""

import re
from datetime import datetime
from decimal import Decimal

from mis_finanzas.importers.amounts import parse_money
from mis_finanzas.importers.base import Check, ImportFileError, ParseResult
from mis_finanzas.importers.pdf_layout import Line, lines, visible
from mis_finanzas.importers.pdf_words import PageWords
from mis_finanzas.ledger.text import normalize_description
from mis_finanzas.monotributo.records import InvoiceData, InvoiceKey, ParsedInvoicePdf

# (title kind, letter) -> ARCA type code
TYPES = {
    ("FACTURA", "C"): 11,
    ("NOTA DE DEBITO", "C"): 12,
    ("NOTA DE CREDITO", "C"): 13,
    ("FACTURA", "E"): 19,
    ("NOTA DE DEBITO", "E"): 20,
    ("NOTA DE CREDITO", "E"): 21,
}
KINDS = ("FACTURA", "NOTA DE DEBITO", "NOTA DE CREDITO")
LETTER_SIZE = 18.0  # the letter box prints far bigger than anything else
_NUMBER = re.compile(r"COMPR\. NRO:\s*(\d+)-(\d+)")
_ISSUED = re.compile(r"FECHA DE EMISION:\s*(\d{2}/\d{2}/\d{4})")
_TOTAL = re.compile(r"Importe Total:\s*(.+)$", re.IGNORECASE)
_CAE = re.compile(r"CAE N\S*:?\s*(\d{14})")
_CODE = re.compile(r"^COD\.\s*(\d+)$")


def _texts(page: PageWords) -> list[tuple[Line, str]]:
    return [(line, normalize_description(line.text)) for line in lines(visible(page.words))]


def _find(texts: list[tuple[Line, str]], pattern: re.Pattern[str]) -> re.Match[str] | None:
    return next((m for _, text in texts if (m := pattern.search(text))), None)


def _kind(texts: list[tuple[Line, str]]) -> str | None:
    return next((k for _, text in texts for k in KINDS if text.startswith(k)), None)


def _letter(texts: list[tuple[Line, str]]) -> str | None:
    for line, text in texts:
        if len(text) == 1 and text.isalpha() and line.words[0].size >= LETTER_SIZE:
            return text
    return None


def _total(texts: list[tuple[Line, str]]) -> tuple[Decimal, str]:
    for line, _ in texts:
        if match := _TOTAL.search(line.text):
            money = parse_money(match.group(1))
            return money.amount, money.currency or "ARS"
    raise ImportFileError("Importe Total not found")


def _required(texts: list[tuple[Line, str]], pattern: re.Pattern[str], what: str) -> re.Match[str]:
    match = _find(texts, pattern)
    if match is None:
        raise ImportFileError(f"{what} not found")
    return match


def read_invoice(page: PageWords) -> tuple[ParsedInvoicePdf, int | None]:
    """The invoice's identity, and the printed `COD.` if any. Raises `ImportFileError`."""
    texts = _texts(page)
    kind, letter = _kind(texts), _letter(texts)
    type_code = TYPES.get((kind or "", letter or ""))
    if type_code is None:
        raise ImportFileError(f"comprobante {kind} {letter} is not supported")
    number = _required(texts, _NUMBER, "Compr. Nro")
    issued = _required(texts, _ISSUED, "Fecha de Emisión")
    total, currency = _total(texts)
    code = _find(texts, _CODE)
    invoice = ParsedInvoicePdf(
        key=InvoiceKey(type_code, int(number.group(1)), int(number.group(2))),
        issued_on=datetime.strptime(issued.group(1), "%d/%m/%Y").date(),
        currency=currency,
        total=total,
        cae=_required(texts, _CAE, "CAE").group(1),
    )
    return invoice, int(code.group(1)) if code else None


class ArcaInvoicePdf:
    name = "arca_invoice_pdf"
    version = "1"

    def detect_pages(self, pages: list[PageWords]) -> bool:
        if not pages:
            return False
        texts = _texts(pages[0])
        return (
            _kind(texts) is not None
            and _find(texts, _NUMBER) is not None
            and _find(texts, _CAE) is not None
        )

    def parse_pages(self, pages: list[PageWords]) -> ParseResult:
        invoice, code = read_invoice(pages[0])
        checks = []
        if code is not None:
            checks.append(
                Check("código del comprobante", Decimal(invoice.key.type_code), Decimal(code))
            )
        result = ParseResult(checks=checks, invoices=InvoiceData(pdf=invoice))
        result.metadata["comprobante"] = str(invoice.key)
        result.metadata["fecha"] = invoice.issued_on.strftime("%d/%m/%Y")
        return result
