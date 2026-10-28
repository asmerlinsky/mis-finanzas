"""The Visa section of the account statement, and American Express in both layouts."""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from card_fixtures import account_with_visa_pdf, amex_legacy_pdf, amex_pdf
from mis_finanzas.importers.base import ParseResult
from mis_finanzas.importers.pdf_words import extract_pages
from mis_finanzas.importers.santander.account_pdf import SantanderAccountPdf
from mis_finanzas.importers.santander.amex_legacy_pdf import (
    SantanderAmexLegacyPdf,
    _movement_date,
    _State,
)
from mis_finanzas.importers.santander.visa_pdf import SantanderAmexPdf, SantanderVisaPdf
from santander_fixtures import visa_pdf


def _failed(result: ParseResult) -> list[str]:
    return [check.name for check in result.failed_checks]


def test_account_statement_reads_its_visa_section() -> None:
    result = SantanderAccountPdf().parse_pages(extract_pages(account_with_visa_pdf()))
    assert result.errors == [] and _failed(result) == []
    visa = [r for r in result.rows if r.target.startswith("santander/visa/")]
    assert [(r.date, r.amount, r.target, r.installment) for r in visa] == [
        (date(2026, 9, 4), Decimal("1000.00"), "santander/visa/ARS", None),
        (date(2026, 9, 4), Decimal("10.00"), "santander/visa/USD", None),
        (date(2026, 8, 3), Decimal("-3000.00"), "santander/visa/ARS", (5, 8)),
        (date(2026, 8, 26), Decimal("-500.00"), "santander/visa/ARS", (1, 6)),
        (date(2026, 8, 26), Decimal("-7.70"), "santander/visa/USD", None),
        (date(2026, 8, 26), Decimal("-2.30"), "santander/visa/USD", None),
        (date(2026, 10, 1), Decimal("-35.00"), "santander/visa/ARS", None),
    ]
    assert visa[2].description == "Stock general paz (5/8)"
    assert result.metadata["tarjetas_visa"] == "1234"
    assert not any("Super ejemplo" in r.description for r in result.rows)  # debit page


def test_account_statement_visa_total_is_checked() -> None:
    pages = extract_pages(account_with_visa_pdf(total_due="$ 3.600,00"))
    result = SantanderAccountPdf().parse_pages(pages)
    assert _failed(result) == ["Visa: total a pagar ARS"]


def test_account_statement_visa_overpaid_month() -> None:
    """Paying more than was owed closes the payments at `Total -$ …`."""
    result = SantanderAccountPdf().parse_pages(extract_pages(account_with_visa_pdf(overpaid=True)))
    assert result.errors == [] and _failed(result) == []
    assert "Visa: saldo del resumen anterior ARS" in [c.name for c in result.checks]


def test_account_statement_visa_missing_payments_total_fails_a_check() -> None:
    pages = extract_pages(account_with_visa_pdf(payments_total=False))
    result = SantanderAccountPdf().parse_pages(pages)
    assert _failed(result) == [
        "Visa: saldo del resumen anterior ARS",
        "Visa: saldo del resumen anterior USD",
    ]


def _upload(client: TestClient, path: str, name: str, content: bytes) -> Any:
    return client.post(path, files={"file": (name, content, "application/octet-stream")})


def test_visa_statement_and_account_statement_add_each_movement_once(client: TestClient) -> None:
    for key, currency in (
        ("santander/CA/ARS", "ARS"),
        ("santander/CC/ARS", "ARS"),
        ("santander/CA/USD", "USD"),
        ("santander/visa/ARS", "ARS"),
        ("santander/visa/USD", "USD"),
    ):
        body = {"name": key, "institution": "Santander", "kind": "bank", "currency": currency}
        account = client.post("/api/accounts", json=body).json()["id"]
        client.put(f"/api/source-accounts/{key}", json={"account_id": account})
    assert _upload(client, "/api/imports", "visa.pdf", visa_pdf()).status_code == 201
    preview = _upload(client, "/api/imports/preview", "cuenta.pdf", account_with_visa_pdf()).json()
    visa_rows = [r for r in preview["rows"] if r["target"].startswith("santander/visa/")]
    assert len(visa_rows) == 7 and all(r["duplicate"] for r in visa_rows)


def test_amex_in_the_visa_design() -> None:
    pages = extract_pages(amex_pdf())
    assert SantanderAmexPdf().detect_pages(pages)
    assert not SantanderVisaPdf().detect_pages(pages)
    assert not SantanderAmexLegacyPdf().detect_pages(pages)
    result = SantanderAmexPdf().parse_pages(pages)
    assert result.errors == [] and _failed(result) == []
    assert [(r.date, r.amount, r.target) for r in result.rows] == [
        (date(2026, 9, 7), Decimal("2000.00"), "santander/amex/ARS"),
    ]
    assert result.metadata["vencimiento"] == "13/10/26"


@pytest.mark.parametrize(
    ("total_usd", "opening"),
    [
        ("U$S 40,59", "ARS 0.00 / USD 0.00"),  # nothing owed before
        ("U$S 10,00", "ARS 0.00 / USD -30.59"),  # a credit carried over, not printed
    ],
)
def test_amex_in_the_visa_design_without_a_payments_section(total_usd: str, opening: str) -> None:
    """No payments section: the opening balance isn't printed, so `Total a pagar` can't be
    checked; the card subtotal still is, and the implied opening balance is shown."""
    result = SantanderAmexPdf().parse_pages(extract_pages(amex_pdf(False, total_usd)))
    assert result.errors == [] and _failed(result) == []
    assert not any(c.name.startswith("total a pagar") for c in result.checks)
    assert [c.name for c in result.checks if c.name.startswith("subtotal")] == [
        "subtotal tarjeta 1234 ARS",
        "subtotal tarjeta 1234 USD",
    ]
    assert result.metadata["saldo anterior (no impreso)"] == opening
    assert [(r.date, r.amount, r.target, r.reference) for r in result.rows] == [
        (date(2026, 7, 2), Decimal("-40.59"), "santander/amex/USD", "167250"),
    ]


def test_amex_older_layout() -> None:
    pages = extract_pages(amex_legacy_pdf())
    importer = SantanderAmexLegacyPdf()
    assert importer.detect_pages(pages)
    assert not SantanderAmexPdf().detect_pages(pages)
    result = importer.parse_pages(pages)
    assert result.errors == [] and _failed(result) == []
    assert [(r.date, r.amount, r.target, r.description, r.reference) for r in result.rows] == [
        (date(2026, 5, 4), Decimal("1000.00"), "santander/amex/ARS", "SU PAGO EN PESOS", None),
        (date(2026, 5, 5), Decimal("10.00"), "santander/amex/USD", "SU PAGO EN USD", None),
        (
            date(2026, 4, 28),
            Decimal("-2500.00"),
            "santander/amex/ARS",
            "COMERCIO EJEMPLO USD 2,00",
            "952869",
        ),
        (date(2026, 5, 20), Decimal("-2.41"), "santander/amex/ARS", "INTERESES FINANCIACION", None),
    ]
    assert result.metadata == {"cierre": "28 MAY 26", "tarjetas": "1234"}
    assert "JUANA" not in repr(result).upper()


def test_amex_older_layout_balance_is_checked() -> None:
    result = SantanderAmexLegacyPdf().parse_pages(extract_pages(amex_legacy_pdf("2.600,00")))
    assert _failed(result) == ["saldo actual ARS"]


def test_amex_older_layout_unreadable_date_is_a_row_error() -> None:
    result = SantanderAmexLegacyPdf().parse_pages(extract_pages(amex_legacy_pdf(purchase_day="45")))
    [error] = result.errors
    assert "day is out of range" in error.message
    assert len(result.rows) == 3


@pytest.mark.parametrize(
    ("dates", "expected"),
    [
        ([["26", "Diciembre", "28"]], date(2026, 12, 28)),
        ([["26", "Diciem.", "28"], ["03"]], date(2026, 12, 3)),  # day only: same year and month
        ([["25", "Set", "05"]], date(2025, 9, 5)),
    ],
)
def test_amex_older_layout_dates_are_year_month_day(dates: list[list[str]], expected: date) -> None:
    state = _State()
    found = [_movement_date(state, words) for words in dates]
    assert found[-1] == expected


def test_amex_older_layout_day_alone_needs_a_full_date_first() -> None:
    with pytest.raises(ValueError):
        _movement_date(_State(), ["03"])
