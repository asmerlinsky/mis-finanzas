"""Signed amounts as statements print them, and table reading over positioned words."""

from decimal import Decimal

import pytest

from mis_finanzas.importers.amounts import Money, parse_money
from mis_finanzas.importers.pdf_layout import find_header_rows, lines, table_rows, visible
from mis_finanzas.importers.pdf_words import PageWords, Word


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("-$ 1.234,56", Money(Decimal("-1234.56"), "ARS")),
        ("$-533.444,86", Money(Decimal("-533444.86"), "ARS")),
        ("$ 899.680,27", Money(Decimal("899680.27"), "ARS")),
        ("U$S47,11", Money(Decimal("47.11"), "USD")),
        ("-U$S 47,52", Money(Decimal("-47.52"), "USD")),
        ("USD 3907,69", Money(Decimal("3907.69"), "USD")),
        ("1.000", Money(Decimal("1000"), None)),
        ("(5,00)", Money(Decimal("-5.00"), None)),
    ],
)
def test_parse_money(text: str, expected: Money) -> None:
    assert parse_money(text) == expected


def test_parse_money_dot_decimal() -> None:
    assert parse_money("2949.488593", ".", "") == Money(Decimal("2949.488593"), None)


@pytest.mark.parametrize("text", ["", "$", "abc", "U$S -"])
def test_parse_money_rejects_non_amounts(text: str) -> None:
    with pytest.raises(ValueError):
        parse_money(text)


def _w(text: str, x0: float, top: float, size: float = 8.5, width: float | None = None) -> Word:
    x1 = x0 + (width if width is not None else 5 * len(text))
    return Word(text=text, x0=x0, top=top, x1=x1, bottom=top + size, fontname="F", size=size)


HEADER = [
    _w("Fecha", 23, 100),
    _w("Movimiento", 115, 100),
    _w("Caja", 337, 100),
    _w("de", 357, 100),
    _w("Ahorro", 370, 100),
    _w("Saldo", 530, 100),
]
BODY = [
    # Row 1: amount in "Caja de Ahorro", balance right-aligned starting left of "Saldo".
    _w("31/08/26", 23, 120),
    _w("Transferencia", 115, 120),
    _w("-$", 354, 120),
    _w("1.000,00", 364, 120),
    _w("$", 517, 120),
    _w("9.000,00", 527, 120),
    # Its detail line: smaller text, no amount -> continues row 1.
    _w("A", 115, 131, size=7),
    _w("juan", 121, 131, size=7),
    # Invisible marker inside the date column.
    _w("99/963", 23, 126, size=0.1, width=0.4),
    # Row 2: no date (inherited by the parser later).
    _w("Pago", 115, 150),
    _w("$", 358, 150),
    _w("50,00", 364, 150),
    # Legal text after the table.
    _w("Banco", 30, 300),
    _w("S.A.", 60, 300),
]
PAGE = PageWords(1, 595, 842, HEADER + BODY + [_w("Caja", 30, 50)])


def test_visible_drops_tiny_words() -> None:
    assert "99/963" not in [w.text for w in visible(PAGE.words)]


def test_lines_group_by_top() -> None:
    texts = [line.text for line in lines(visible(PAGE.words))]
    assert texts[1] == "Fecha Movimiento Caja de Ahorro Saldo"
    assert texts[2] == "31/08/26 Transferencia -$ 1.000,00 $ 9.000,00"


def test_header_needs_all_labels_including_multiword_ones() -> None:
    labels = ["Fecha", "Movimiento", "Caja de Ahorro", "Saldo"]
    headers = find_header_rows(PAGE, labels)
    assert len(headers) == 1  # the lone "Caja" at the top is not a header
    columns = {c.label: (c.left, c.right) for c in headers[0].columns}
    assert columns["Fecha"][0] == 0 and columns["Saldo"][1] == 595
    assert columns["Caja de Ahorro"] == (335, 528)
    assert find_header_rows(PAGE, ["Fecha", "Especie"]) == []


def test_table_rows_join_continuations_and_stop() -> None:
    header = find_header_rows(PAGE, ["Fecha", "Movimiento", "Caja de Ahorro", "Saldo"])[0]
    rows = table_rows(
        PAGE,
        header,
        key_columns=["Caja de Ahorro"],
        stop=lambda line: line.text.startswith("Banco"),
    )
    assert [r.cells for r in rows] == [
        {
            "Fecha": "31/08/26",
            "Movimiento": "Transferencia A juan",
            "Caja de Ahorro": "-$ 1.000,00",
            "Saldo": "$ 9.000,00",
        },
        {"Movimiento": "Pago", "Caja de Ahorro": "$ 50,00"},
    ]
    assert len(rows[0].lines) == 2


def test_table_rows_until_limits_the_section() -> None:
    header = find_header_rows(PAGE, ["Fecha", "Movimiento", "Caja de Ahorro", "Saldo"])[0]
    rows = table_rows(PAGE, header, key_columns=["Caja de Ahorro"], until=140)
    assert len(rows) == 1
