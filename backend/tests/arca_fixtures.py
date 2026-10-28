"""Synthetic ARCA files: a Mis Comprobantes export and an invoice PDF. Invented values and
receivers only; never values from a real export."""

from collections.abc import Sequence

from pdf_builder import Row, statement_pdf

# A shuffled subset of ARCA's columns, plus one it might add: read by name, not position.
HEADER = [
    "Fecha de Emisión",
    "Tipo de Comprobante",
    "Punto de Venta",
    "Número Desde",
    "Número Hasta",
    "Cód. Autorización",
    "Tipo Doc. Receptor",
    "Nro. Doc. Receptor",
    "Denominación Receptor",
    "Columna Nueva",
    "Moneda",
    "Tipo Cambio",
    "Imp. Neto Gravado Total",
    "Imp. Neto No Gravado",
    "Imp. Op. Exentas",
    "Otros Tributos",
    "Total IVA",
    "Imp. Total",
]


def invoice_row(
    day: str,
    type_code: int,
    number: int,
    total: str,
    currency: str = "DOL",
    rate: str = "1000,00",
    receiver: str = "Cliente Ejemplo SRL",
    imp_total: str | None = None,
) -> list[str]:
    """One exported row; its untaxed amount is `total`, and `Imp. Total` too unless given."""
    cae = f"7{number:013d}"
    return [
        day, str(type_code), "1", str(number), str(number), cae, "80", "30000000007", receiver,
        "x", currency, rate, "0,00", total, "0,00", "0,00", "0,00", imp_total or total,
    ]  # fmt: skip


def comprobantes_csv(rows: Sequence[list[str]]) -> bytes:
    lines = [";".join(HEADER), *(";".join(row) for row in rows)]
    return ("\n".join(lines) + "\n").encode("utf-8")


DEFAULT_ROWS = [
    invoice_row("2026-03-10", 19, 7, "3000,00"),  # USD 3000 at 1000
    invoice_row("2026-04-10", 11, 3, "500000,00", currency="PES", rate="1,00"),
    invoice_row("2026-05-10", 21, 2, "1000,00"),  # credit note: subtracts
]


def invoice_pdf(
    number: int = 7,
    total: str = "USD 3000,00",
    day: str = "10/03/2026",
    code: str = "19",
    title: str = "FACTURA DE EXPORTACIÓN",
    letter: str = "E",
) -> bytes:
    page = [
        Row(24, [(268, "ORIGINAL")], size=12, bold=True),
        Row(43, [(290, letter)], size=24, bold=True),
        Row(56, [(334, title)], size=12, bold=True),
        Row(68, [(282, f"COD. {code}")], size=8, bold=True),
        Row(85, [(334, f"Compr. Nro: 00001-{number:08d}")], size=9, bold=True),
        Row(99, [(334, f"Fecha de Emisión: {day}")], size=9, bold=True),
        Row(177, [(24, "Señor(es): Cliente Ejemplo SRL")], size=9, bold=True),
        Row(665, [(23, "Tipo de Cambio: 1000.000000")], size=8, bold=True),
        Row(685, [(398, f"Importe Total: {total}")], size=10, bold=True),
        Row(710, [(432, f"CAE N°: 7{number:013d}")], size=10, bold=True),
        Row(752, [(115, "Comprobante Autorizado")], size=9, bold=True),
    ]
    return statement_pdf([page, page])  # a second copy, as the Duplicado
