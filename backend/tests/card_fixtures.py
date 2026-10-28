"""Synthetic Santander card statements: the Visa section inside the account statement, and
American Express in both layouts. Invented values only; every check passes unless a test
breaks one on purpose.

The account statement's Visa section holds the same movements as `santander_fixtures.visa_pdf`,
so importing both must add each movement once.
"""

from pdf_builder import Row, header, statement_pdf
from santander_fixtures import CARD_HEADER, _account_page_1, _account_page_2

LETTER = (612.0, 792.0)
ACCOUNT_SIMPLE = [(45, "Fecha"), (104, "Descripción"), (395, "Pesos"), (480, "Dólares")]
ACCOUNT_CARD = [
    (45, "Fecha"),
    (100, "Comprobante"),
    (160, "Descripción"),
    (300, "Cuota"),
    (395, "Pesos"),
    (480, "Dólares"),
]


def _heading(top: float, text: str) -> Row:
    return Row(top, [(40, text)], size=20, bold=True)


def _account_visa_page_1(paid: str, payments_total: Row | None) -> list[Row]:
    return [
        _heading(72, "Tarjeta Santander"),
        _heading(96, "Visa crédito"),
        Row(250, [(40, "Pago anterior y devoluciones")], size=10),
        header(275, ACCOUNT_SIMPLE),
        Row(
            300,
            [(45, "04/09/26"), (104, "Saldo anterior"), (395, "$ 1.000,00"), (480, "U$S 10,00")],
        ),
        Row(320, [(104, "Tu pago en pesos"), (395, paid)]),
        Row(340, [(104, "Tu pago en dólares"), (480, "-U$S 10,00")]),
        *([payments_total] if payments_total else []),
        Row(400, [(40, "Consumos del mes")], size=14),
        Row(430, [(40, "Total consumos de A JUANA PEREZ | Tarjeta terminada en 1234")], size=10),
        header(455, ACCOUNT_CARD),
        Row(
            480,
            [
                (45, "03/08/26"),
                (100, "950230"),
                (160, "Stock general paz"),
                (300, "5 de 8"),
                (395, "$ 3.000,00"),
            ],
        ),
        Row(
            500,
            [
                (45, "26/08/26"),
                (100, "413666"),
                (160, "Merpago*ejemplo"),
                (300, "1 de 6"),
                (395, "$ 500,00"),
            ],
        ),
        Row(520, [(100, "157630"), (160, "Cashpago brl 70,23"), (480, "U$S 7,70")]),
        Row(814, [(537, "3 - 5")]),
    ]


def _account_visa_page_2(total_due: str) -> list[Row]:
    return [
        header(85, ACCOUNT_CARD),
        Row(105, [(100, "354319"), (160, "Spotify"), (480, "U$S 2,30")]),
        Row(130, [(104, "Consumos totales"), (395, "$ 3.500,00"), (480, "U$S 10,00")]),
        Row(160, [(40, "Impuestos")], size=10),
        header(185, ACCOUNT_SIMPLE),
        Row(205, [(45, "01/10/26"), (104, "Impuesto de sellos $"), (395, "$ 35,00")]),
        Row(230, [(104, "Total"), (395, "$ 35,00")]),
        Row(270, [(54, "Total a pagar"), (395, total_due), (480, "U$S 10,00")], size=10),
        Row(814, [(537, "4 - 5")]),
    ]


def _account_debit_page() -> list[Row]:
    """The debit card page only repeats account movements: never read."""
    return [
        _heading(72, "Tarjeta de débito"),
        header(
            270, [(45, "Fecha"), (100, "Comprobante"), (200, "Establecimiento"), (480, "Importe")]
        ),
        Row(285, [(45, "18/09/26"), (100, "852762"), (200, "Super ejemplo"), (480, "$ 60,00")]),
        Row(814, [(537, "5 - 5")]),
    ]


def account_with_visa_pdf(
    total_due: str = "$ 3.535,00", overpaid: bool = False, payments_total: bool = True
) -> bytes:
    """`overpaid`: 1.200,00 paid on 1.000,00 owed, so the payments close at `Total -$ 200,00`
    and the total due is 200,00 lower. `payments_total=False` leaves that closing line out."""
    paid, closing = ("-$ 1.200,00", "-$ 200,00") if overpaid else ("-$ 1.000,00", "$ 0,00")
    if overpaid and total_due == "$ 3.535,00":
        total_due = "$ 3.335,00"
    total_row = Row(365, [(104, "Total"), (395, closing), (480, "U$S 0,00")])
    return statement_pdf(
        [
            _account_page_1(),
            _account_page_2("$ 850,00"),
            _account_visa_page_1(paid, total_row if payments_total else None),
            _account_visa_page_2(total_due),
            _account_debit_page(),
        ]
    )


SIMPLE_HEADER = [
    (45, "Fecha"),
    (104, "Descripción"),
    (375, "Monto en pesos"),
    (466, "Monto en dólares"),
]


def _amex_payments() -> list[Row]:
    return [
        Row(91, [(40, "Pago anterior y devoluciones")], size=12),
        header(129, SIMPLE_HEADER),
        Row(157, [(45, "07/09/26"), (104, "Saldo anterior"), (396, "$ 2.000,00")]),
        Row(182, [(104, "Su pago en pesos"), (392, "-$ 2.000,00")]),
        Row(217, [(53, "Saldo del resumen anterior"), (428, "$ 0,00"), (509, "U$S 0,00")]),
    ]


def _amex_purchase() -> list[Row]:
    return [
        Row(268, [(42, "Movimientos de A JUANA PEREZ")], size=12),
        Row(284, [(42, "American Express crédito terminada en 1234")], size=12),
        header(319, CARD_HEADER),
        Row(347, [(45, "02/07/26"), (104, "Ali*aliexpress"), (300, "167250"), (504, "U$S 40,59")]),
        Row(376, [(103, "Subtotal de A JUANA PEREZ"), (430, "$ 0,00"), (503, "U$S 40,59")]),
    ]


def amex_pdf(payments: bool = True, total_usd: str = "U$S 40,59") -> bytes:
    """The newer layout (the Visa design). With payments: a month with no purchases. Without:
    no payments section at all, and one purchase of U$S 40,59. Its `Total a pagar` may carry
    an unprinted balance from the statement before (`total_usd="U$S 10,00"`: a 30,59 credit)."""
    page_1 = [
        Row(76, [(40, "Resumen American Express")], size=24, bold=True),
        Row(423, [(60, "27/08/26 07/09/26 01/10/26 13/10/26 29/10/26 12/11/26")]),
    ]
    if payments:
        total = Row(274, [(53, "Total a pagar"), (428, "$ 0,00"), (509, "U$S 0,00")])
        page_2 = [*_amex_payments(), total]
    else:
        total = Row(597, [(54, "Total a pagar"), (428, "$ 0,00"), (509, total_usd)])
        page_2 = [*_amex_purchase(), total]
    return statement_pdf([page_1, page_2])


LEGACY_HEADER = Row(
    314,
    [(11, "Fecha"), (79, "Comprobante"), (140, "Referencia"), (439, "$"), (533, "U$S")],
    size=8,
    bold=True,
)
LEGACY_TITLE = Row(
    25, [(11, "AMERICAN EXPRESS RESUMEN DE CUENTA"), (470, "Santander Río")], size=14, bold=True
)


def _legacy_row(top: float, cells: list[tuple[float, str]]) -> Row:
    return Row(top, cells, size=8)


def _legacy_page_1(purchase_day: str) -> list[Row]:
    """Dates print year first (`26 Mayo 04`); following rows print only the day."""
    card_total = "Tarjeta 1234 Total Consumos de A JUANA PEREZ"
    return [
        LEGACY_TITLE,
        Row(198, [(43, "JUANA PEREZ")], size=8),
        Row(205, [(353, "CIERRE 28 May 26 VENCIMIENTO 09 Jun 26")], size=10, bold=True),
        _legacy_row(279, [(14, "LIMITES: COMPRA $ 1.000.000,00")]),
        LEGACY_HEADER,
        _legacy_row(329, [(145, "SALDO ANTERIOR"), (415, "1.000,00"), (521, "10,00")]),
        _legacy_row(
            356, [(22, "26 Mayo"), (74, "04"), (145, "SU PAGO EN PESOS"), (420, "1.000,00-")]
        ),
        _legacy_row(365, [(74, "05"), (145, "SU PAGO EN USD"), (521, "10,00-")]),
        _legacy_row(374, [(22, "_" * 60)]),
        _legacy_row(
            383,
            [
                (22, "26 Abril"),
                (74, purchase_day),
                (89, "952869"),
                (145, "COMERCIO EJEMPLO USD 2,00"),
                (415, "2.500,00"),
            ],
        ),
        _legacy_row(392, [(22, card_total), (415, "2.500,00"), (463, "*"), (521, "0,00*")]),
        _legacy_row(
            401,
            [
                (22, "26 Mayo"),
                (74, "20"),
                (145, "INTERESES FINANCIACION"),
                (262, "$"),
                (439, "2,41"),
            ],
        ),
        # Legal text runs on inside the table area, numbers included: never rows.
        _legacy_row(
            420, [(98, "Tasa de financiación máx. aplicada en presente resumen TNA 50,945%,")]
        ),
        _legacy_row(430, [(98, "el cargo de 1.234,56 por mes se informa en el resumen")]),
        Row(572, [(276, "SALDO ACTUAL"), (406, "$"), (503, "U$S")], size=10),
    ]


def _legacy_page_2(balance: str) -> list[Row]:
    return [
        LEGACY_TITLE,
        LEGACY_HEADER,
        _legacy_row(356, [(98, "gravados con el impuesto de sellos a la tasa del 57,6 por mil")]),
        Row(
            572,
            [(276, "SALDO ACTUAL"), (406, "$"), (455, balance), (503, "U$S"), (559, "0,00")],
            size=10,
        ),
        Row(593, [(276, "PAGO MINIMO"), (406, "$"), (505, "250,00")], size=10),
    ]


def amex_legacy_pdf(balance: str = "2.502,41", purchase_day: str = "28") -> bytes:
    """The older layout. 1.000,00 - 1.000,00 + 2.500,00 + 2,41 = 2.502,41."""
    return statement_pdf([_legacy_page_1(purchase_day), _legacy_page_2(balance)], *LETTER)
