from datetime import date
from decimal import Decimal

import pytest

from mis_finanzas.core.money import from_cents, parse_amount, to_cents
from mis_finanzas.ledger.dedup import fingerprint, occurrence_indexes
from mis_finanzas.ledger.text import clean_description, normalize_description


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1.234,56", Decimal("1234.56")),
        ("-1.234,56", Decimal("-1234.56")),
        ("$ 1.234,56", Decimal("1234.56")),
        ("U$S 10,50", Decimal("10.50")),
        ("(500,00)", Decimal("-500.00")),
        ("0", Decimal("0")),
        (" 12 ", Decimal("12")),
    ],
)
def test_parse_amount_argentine_format(text: str, expected: Decimal) -> None:
    assert parse_amount(text) == expected


def test_parse_amount_dot_decimal() -> None:
    assert parse_amount("1,234.56", decimal_separator=".", thousands_separator=",") == Decimal(
        "1234.56"
    )


@pytest.mark.parametrize("text", ["", "abc", "1,2,3x", "NaN", "Infinity"])
def test_parse_amount_rejects_non_numbers(text: str) -> None:
    with pytest.raises(ValueError):
        parse_amount(text)


@pytest.mark.parametrize(
    ("amount", "cents"),
    [
        (Decimal("1234.56"), 123456),
        (Decimal("-0.01"), -1),
        (Decimal("0.005"), 0),  # half-even
        (Decimal("0.015"), 2),
    ],
)
def test_cents_round_trip(amount: Decimal, cents: int) -> None:
    assert to_cents(amount) == cents
    assert from_cents(cents) == amount.quantize(Decimal("0.01"), rounding="ROUND_HALF_EVEN")


def test_normalize_description() -> None:
    assert normalize_description("  Pagó   rappi\tCABA ") == "PAGO RAPPI CABA"


def test_occurrence_indexes_count_identical_rows() -> None:
    a = (date(2026, 1, 1), -100)
    b = (date(2026, 1, 1), -200)
    assert occurrence_indexes([a, b, a, a]) == [0, 0, 1, 2]


def test_fingerprint_depends_on_account_date_amount_and_occurrence() -> None:
    base = fingerprint(1, date(2026, 1, 1), -100, 0)
    assert base == fingerprint(1, date(2026, 1, 1), -100, 0)
    variants = [
        fingerprint(2, date(2026, 1, 1), -100, 0),
        fingerprint(1, date(2026, 1, 2), -100, 0),
        fingerprint(1, date(2026, 1, 1), -101, 0),
        fingerprint(1, date(2026, 1, 1), -100, 1),
    ]
    assert base not in variants


def test_normalize_description_decodes_html_entities() -> None:
    assert normalize_description("A mart&#237;n &amp; co") == "A MARTIN & CO"


def test_normalize_description_repairs_double_encoded_accents() -> None:
    assert normalize_description("Transf a martÃ\xadn") == "TRANSF A MARTIN"
    assert normalize_description("Peluquería") == "PELUQUERIA"  # already fine: untouched


@pytest.mark.parametrize(
    ("printed", "shown", "normalized"),
    [
        # MARTÍN encoded twice and then lowercased by the bank, behind HTML entities.
        ("Transf. a mart&#227;&#141;n gomez", "Transf. a martín gomez", "TRANSF. A MARTIN GOMEZ"),
        ("MARTÃ\x8dN", "MARTÍN", "MARTIN"),
        ("pe\u00f1a mart\u00e3\u00adn", "peña martín", "PENA MARTIN"),
        ("São Paulo", "São Paulo", "SAO PAULO"),  # real accents: untouched
        ("  Pagó   rappi ", "Pagó rappi", "PAGO RAPPI"),
    ],
)
def test_clean_description_keeps_case_and_accents(
    printed: str, shown: str, normalized: str
) -> None:
    assert clean_description(printed) == shown
    assert normalize_description(printed) == normalized


def test_normalize_description_drops_invisible_characters() -> None:
    assert normalize_description("mart\x8dn pa\xadgo") == "MARTN PAGO"
