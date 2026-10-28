"""Synthetic Balanz statements laid out like the real ones. Invented values only.

Numbers are consistent, so every statement check passes unless a test breaks one on purpose.
"""

from pdf_builder import Row, statement_pdf

LANDSCAPE = (842.0, 596.0)
SMALL = (624.0, 454.0)
ROW = 7.5  # movements: header and rows print at the same size

MOVEMENTS_LABELS = [
    (23, "Descripción"),
    (182, "Cant. VN"),
    (240, "Saldo"),
    (280, "Precio"),
    (325, "Bruto"),
    (366, "Arancel"),
    (397, "Impor. IVA"),
    (473, "Impor. Derech"),
    (555, "Impor. IVA"),
    (644, "Neto"),
    (701, "Fecha Co."),
    (763, "Fecha Li."),
]
TRADE = "Boleto / 7654321 / COMPRA / 1 / EJM / $"
FOOTER = Row(577, [(39, "Balanz Capital Valores S.A.U. | Av. Ejemplo 123 | www.balanz.com")])


def _cols(shift: float = 0) -> dict[str, float]:
    return {label: x + shift for x, label in MOVEMENTS_LABELS}


def _header(top: float, shift: float = 0) -> Row:
    return Row(top, [(x + shift, label) for x, label in MOVEMENTS_LABELS], size=ROW, bold=True)


def _page_top(top: float = 16) -> list[Row]:
    return [
        Row(top, [(12, "Cuenta Corriente por Concertación del 1/3/2026 al 31/3/2026")], size=11.7),
        Row(top + 18, [(12, "Comitente 99999 | Juana Pérez")], size=11.7),
    ]


def _title(top: float, text: str) -> Row:
    return Row(top, [(23, text)], size=ROW, bold=True)


def _line(top: float, description: str, values: dict[str, str], shift: float = 0) -> Row:
    cols = _cols(shift)
    return Row(top, [(23, description), *((cols[k], v) for k, v in values.items())], size=ROW)


def _instruments_page() -> list[Row]:
    return [
        *_page_top(),
        Row(80, [(22, "Cartera disponible")], size=12),
        Row(115, [(22, "Instrumentos")], size=9.8),
        _header(140),
        _title(153, "CEDEAR EJEMPLO CORP. - EJM 1234"),
        _line(166, "Saldo Anterior", {"Cant. VN": "10,00"}),
        _line(
            179,
            TRADE,
            {
                "Cant. VN": "5,00",
                "Precio": "1.000,00",
                "Bruto": "5.000,00",
                "Arancel": "25,00",
                "Impor. IVA": "5,25",
                "Impor. Derech": "4,00",
                "Neto": "-5.034,25",
                "Fecha Co.": "10/3/2026",
                "Fecha Li.": "11/3/2026",
            },
        ),
        _line(192, "Saldo al 10/3/2026", {}),  # intermediate balances may print no quantity
        _line(205, "Saldo al 31/03/2026", {"Cant. VN": "15,00"}),
        _title(230, "ACCION DOS S.A. - DOS 555"),
        _line(243, "Saldo Anterior", {"Cant. VN": "100,00"}),
        _line(256, "Saldo al 31/03/2026", {"Cant. VN": "100,00"}),
        FOOTER,
    ]


def _pesos_page(pesos_closing: str) -> list[Row]:
    dividend_fee = {"Neto": "-1,50", "Fecha Co.": "20/3/2026", "Fecha Li.": "20/3/2026"}
    return [
        *_page_top(),
        Row(88, [(22, "Monedas")], size=9.8),
        _header(113),
        _title(126, "Pesos - $"),
        _line(139, "Saldo Anterior", {"Neto": "10.000,00"}),
        _line(
            152,
            TRADE,
            {"Neto": "-5.034,25", "Fecha Co.": "10/3/2026", "Fecha Li.": "11/3/2026"},
        ),
        _line(165, "Saldo al 10/3/2026", {"Neto": "4.965,75"}),
        _line(178, "Dividendo en efectivo / EJM", {"Saldo": "15,00", **dividend_fee}),
        _line(191, "Saldo al 20/3/2026", {"Neto": "4.964,25"}),
        _line(204, "Saldo al 31/03/2026", {"Neto": pesos_closing}),
        _title(229, "Dólares Cable - usd C"),
        _line(242, "Saldo Anterior", {"Neto": "100,00"}),
        FOOTER,
    ]


def _dollars_page() -> list[Row]:
    """The dollar section runs on from the previous page, under a header placed differently."""
    shift = 10
    dividend = {"Saldo": "15,00", "Neto": "2,50", "Fecha Co.": "20/3/2026"}
    return [
        *_page_top(),
        _header(80, shift),
        _line(93, "Dividendo en efectivo / EJM", {**dividend, "Fecha Li.": "20/3/2026"}, shift),
        _line(106, "Saldo al 20/3/2026", {"Neto": "102,50"}, shift),
        _line(119, "Saldo al 31/03/2026", {"Neto": "102,50"}, shift),
        FOOTER,
    ]


def movements_pdf(pesos_closing: str = "4.964,25") -> bytes:
    pages = [_instruments_page(), _pesos_page(pesos_closing), _dollars_page()]
    return statement_pdf(pages, *LANDSCAPE)


HOLDINGS_SIZE = 6.8


def _holdings_header(top: float, xs: tuple[float, ...]) -> Row:
    labels = ("Especie", "Descripción", "Cantidad", "Garantía", "Precio", "Valor Actual")
    return Row(top, list(zip(xs, labels, strict=True)), size=HOLDINGS_SIZE, bold=True)


def _position(top: float, xs: tuple[float, ...], values: tuple[str, ...]) -> Row:
    return Row(top, list(zip(xs, values, strict=True)), size=HOLDINGS_SIZE)


def _side(top: float, left: str | None, right: str) -> Row:
    """Page 1's two columns: asset classes on the left, currencies on the right."""
    cells = [(22.0, left)] if left else []
    return Row(top, [*cells, (270.0, right)], size=HOLDINGS_SIZE, bold=True)


def _holdings_page_1(cedears_total: str) -> list[Row]:
    return [
        Row(12, [(560, "Balanz")], size=12.9, bold=True),
        Row(26, [(14, "Posición consolidada por concertación")], size=11.8),
        Row(76, [(22, "Información de cuenta | Tenencias")], size=11.2),
        Row(
            103,
            [(40, "Cuenta"), (153, "Juana Pérez"), (278, "Fecha resumen"), (457, "27/10/2026")],
            size=HOLDINGS_SIZE,
            bold=True,
        ),
        Row(158, [(22, "Total"), (444, "$ 1.000.000")], size=11.2, bold=True),
        _side(177, "Instrumentos", "Monedas"),
        _side(189, "Acciones $ 300.000", "Pesos $ -2.761,55"),
        _side(206, f"Cedears $ {cedears_total}", "Dólares USD 100,00"),
        _side(222, None, "US Dollar (Cable) USD 50,00"),
        Row(258, [(148, "Evolución de Cartera")], size=9, bold=True),
    ]


def _holdings_page_2() -> list[Row]:
    stocks = (23, 88, 279, 355, 430, 503)
    cedears = (23, 75, 329, 390, 451, 522)
    return [
        Row(76, [(22, "Distribución por tipo de activos")], size=11.2),
        Row(101, [(22, "Acciones")], size=9),
        _holdings_header(122, stocks),
        _position(
            135, stocks, ("DOS", "ACCION DOS S.A.", "100,00", "0.75", "$ 1.000,00", "$ 100.000")
        ),
        _position(147, stocks, ("TRES", "TRES S.A.", "50", "0.75", "$ 4.000,00", "$ 200.000")),
        Row(179, [(22, "Cedears")], size=9),
        _holdings_header(199, cedears),
        _position(
            212,
            cedears,
            ("EJM", "CEDEAR EJEMPLO CORP", "15,00", "1.75", "$ 46.666,67", "$ 700.000"),
        ),
        Row(438, [(22, "Balanz Capital | www.balanz.com")], size=5.1, bold=True),
    ]


def holdings_pdf(cedears_total: str = "700.000") -> bytes:
    return statement_pdf([_holdings_page_1(cedears_total), _holdings_page_2()], *SMALL)
