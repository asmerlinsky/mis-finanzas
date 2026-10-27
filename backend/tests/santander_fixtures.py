"""Synthetic Santander statements laid out like the real ones. Invented values only.

Numbers are consistent, so every statement check passes unless a test breaks one on purpose.
"""

import io

from openpyxl import Workbook

from pdf_builder import Row, header, statement_pdf

PESOS_HEADER = [
    (28, "Fecha"),
    (70, "Comprobante"),
    (120, "Movimiento"),
    (337, "Caja de Ahorro en pesos"),
    (417, "Cuenta Corriente en pesos"),
    (530, "Saldo en cuenta"),
]
DOLLARS_HEADER = [
    (28, "Fecha"),
    (70, "Comprobante"),
    (120, "Movimiento"),
    (405, "Caja de Ahorro en dólares"),
    (528, "Saldo en cuenta"),
]


def _account_page_1() -> list[Row]:
    return [
        Row(64, [(30, "Mi resumen de cuenta")], bold=True),
        Row(103, [(482, "Desde: 28/08/26")]),
        Row(117, [(481, "Hasta: 01/10/26")]),
        Row(208, [(23, "Cuenta"), (89, "123-456789/0")]),
        Row(414, [(23, "Movimientos en pesos")], bold=True),
        header(449, PESOS_HEADER),
        Row(
            470,
            [
                (23, "28/08/26"),
                (115, "Saldo Inicial"),
                (357, "$ 1.000,00"),
                (468, "$ 0,00"),
                (527, "$ 1.000,00"),
            ],
        ),
        Row(
            490,
            [
                (23, "31/08/26"),
                (65, "111"),
                (115, "Transferencia no gravada"),
                (354, "-$ 200,00"),
                (528, "$ 800,00"),
            ],
        ),
        Row(496, [(23, "99/963")], size=0.1),  # invisible marker, like the real statement
        Row(501, [(115, "A Juana Perez / varios")], size=7),
        Row(
            520,
            [
                (65, "222"),
                (115, "Compra con tarjeta de debito"),
                (359, "-$ 50,00"),
                (532, "$ 750,00"),
            ],
        ),
        Row(531, [(115, "Kiosco Ejemplo - tarj nro. 1234")], size=7),
        Row(772, [(30, "Banco Santander Argentina S.A. es una sociedad anonima")]),
        Row(814, [(537, "1 - 2")], bold=True),
    ]


def _account_page_2(pesos_total: str) -> list[Row]:
    return [
        header(90, PESOS_HEADER),
        Row(
            111,
            [
                (23, "02/09/26"),
                (65, "333"),
                (115, "Transferencia recibida"),
                (468, "$ 100,00"),
                (528, "$ 850,00"),
            ],
        ),
        Row(122, [(115, "De Juana Perez")], size=7),
        Row(140, [(387, "Saldo total"), (509, pesos_total)], bold=True),
        Row(200, [(23, "Movimientos en dólares")], bold=True),
        header(235, DOLLARS_HEADER),
        Row(
            256, [(23, "28/08/26"), (115, "Saldo Inicial"), (423, "U$S 10,00"), (519, "U$S 10,00")]
        ),
        Row(
            276,
            [
                (23, "03/09/26"),
                (65, "444"),
                (115, "Comex - cobro exportacion de serv"),
                (429, "U$S 5,00"),
                (520, "U$S 15,00"),
            ],
        ),
        Row(300, [(387, "Saldo total"), (494, "U$S 15,00")], bold=True),
        Row(814, [(537, "2 - 2")], bold=True),
    ]


def account_pdf(pesos_total: str = "$ 850,00") -> bytes:
    return statement_pdf([_account_page_1(), _account_page_2(pesos_total)])


SIMPLE_HEADER = [
    (45, "Fecha"),
    (104, "Descripción"),
    (375, "Monto en pesos"),
    (466, "Monto en dólares"),
]
CARD_HEADER = [
    (45, "Fecha"),
    (104, "Descripción"),
    (253, "Cuota"),
    (300, "Comprobante"),
    (380, "Monto en pesos"),
    (470, "Monto en dólares"),
]
FOOTER = Row(813, [(40, "Copia fiel de carácter informativo")])


VISA_PAGE_1 = [
    Row(76, [(40, "Resumen Visa")], bold=True),
    Row(
        423,
        [
            (60, "27/08/26"),
            (148, "04/09/26"),
            (234, "01/10/26"),
            (320, "09/10/26"),
            (406, "29/10/26"),
            (481, "11/11/26"),
        ],
        bold=True,
    ),
]


def _visa_page_2() -> list[Row]:
    return [
        Row(251, [(40, "Pago anterior y devoluciones")], bold=True),
        header(286, SIMPLE_HEADER),
        Row(
            314,
            [(45, "04/09/26"), (104, "Saldo anterior"), (396, "$ 1.000,00"), (503, "U$S 10,00")],
        ),
        Row(339, [(104, "Su pago en pesos"), (392, "-$ 1.000,00")]),
        Row(365, [(104, "Su pago en usd"), (499, "-U$S 10,00")]),
        Row(
            425,
            [(53, "Saldo del resumen anterior *"), (428, "$ 0,00"), (509, "U$S 0,00")],
            bold=True,
        ),
        Row(523, [(42, "Movimientos de A JUANA PEREZ")], bold=True),
        Row(539, [(42, "Visa crédito terminada en 1234")]),
        header(574, CARD_HEADER),
        Row(
            602,
            [
                (45, "03/08/26"),
                (104, "Stock general paz"),
                (250, "5 de 8"),
                (300, "950230"),
                (404, "$ 3.000,00"),
            ],
        ),
        Row(
            627,
            [
                (45, "26/08/26"),
                (104, "Merpago*ejemplo"),
                (250, "1 de 6"),
                (300, "413666"),
                (410, "$ 500,00"),
            ],
        ),
        Row(653, [(104, "Cashpago brl 70,23"), (300, "157630"), (509, "U$S 7,70")]),
        Row(668, [(104, "16,55")]),
        FOOTER,
    ]


def _visa_page_3() -> list[Row]:
    return [
        header(81, CARD_HEADER),
        Row(107, [(104, "Spotify"), (300, "354319"), (509, "U$S 2,30")]),
        Row(
            418,
            [(103, "Subtotal de A JUANA PEREZ"), (398, "$ 3.500,00"), (489, "U$S 10,00")],
            bold=True,
        ),
        Row(461, [(42, "Impuestos, intereses y percepciones")], bold=True),
        header(496, SIMPLE_HEADER),
        Row(524, [(45, "01/10/26"), (104, "Impuesto de sellos $"), (403, "$ 35,00")]),
        FOOTER,
    ]


def visa_pdf(total_due: str = "$ 3.535,00") -> bytes:
    page_4 = [Row(110, [(54, "Total a pagar"), (391, total_due), (489, "U$S 10,00")], bold=True)]
    return statement_pdf([VISA_PAGE_1, _visa_page_2(), _visa_page_3(), page_4])


MOVEMENTS_HEADER = [
    "Fecha",
    "Sucursal origen",
    "Descripción",
    "Referencia",
    "Caja de Ahorro",
    "Cuenta Corriente",
    "Saldo",
]


XlsxRow = list[str]


def default_movements(last_balance: str = "1400.00") -> list[XlsxRow]:
    """Newest first, like the bank's export; today's row has no balance yet."""
    return [
        [
            "27/10/2026",
            "100 - CENTRAL",
            "Compra con tarjeta de debito \t Kiosco",
            "11111111",
            "-100.00",
            "",
            "",
        ],
        [
            "26/10/2026",
            "100 - CENTRAL",
            "Transferencia recibida \t De Juana",
            "22222222",
            "500.00",
            "",
            last_balance,
        ],
        [
            "26/10/2026",
            "100 - CENTRAL",
            "Pago de servicios \t Luz Ejemplo",
            "33333333",
            "",
            "-100.00",
            "900.00",
        ],
        [
            "23/10/2026",
            "100 - CENTRAL",
            "Transferencia no gravada \t A Juana",
            "44444444",
            "-50.00",
            "",
            "1000.00",
        ],
    ]


def movements_xlsx(moneda: str = "Pesos", rows: list[XlsxRow] | None = None) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "UltimosMovimientos"
    for _ in range(6):
        sheet.append([None])
    sheet.append([None, "Cuenta", "Cuenta única 123-456789/0"])
    sheet.append([None, "Moneda", moneda])
    sheet.append([None, "Fecha", "01/10/2026 - 27/10/2026"])
    for _ in range(4):
        sheet.append([None])
    sheet.append([None, *MOVEMENTS_HEADER])
    for row in default_movements() if rows is None else rows:
        sheet.append([None, *row])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
