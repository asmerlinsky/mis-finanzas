"""Santander importers on synthetic statements, and end to end through the API."""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mis_finanzas.importers.base import ParseResult
from mis_finanzas.importers.pdf_words import extract_pages
from mis_finanzas.importers.santander.account_pdf import SantanderAccountPdf
from mis_finanzas.importers.santander.movements_xlsx import SantanderMovementsXlsx
from mis_finanzas.importers.santander.visa_pdf import SantanderVisaPdf
from santander_fixtures import account_pdf, default_movements, movements_xlsx, visa_pdf


def _failed(result: ParseResult) -> list[str]:
    return [check.name for check in result.failed_checks]


def test_movements_xlsx() -> None:
    importer = SantanderMovementsXlsx()
    content = movements_xlsx()
    assert importer.detect("movimientos.xlsx", content)
    assert not importer.detect("movimientos.csv", content)
    result = importer.parse(content, "movimientos.xlsx")
    assert result.errors == [] and _failed(result) == []
    assert result.metadata == {
        "cuenta": "Cuenta única 123-456789/0",
        "moneda": "Pesos",
        "periodo": "01/10/2026 - 27/10/2026",
    }
    assert [(r.date, r.amount, r.target, r.reference) for r in result.rows] == [
        (date(2026, 10, 27), Decimal("-100.00"), "santander/CA/ARS", "11111111"),
        (date(2026, 10, 26), Decimal("500.00"), "santander/CA/ARS", "22222222"),
        (date(2026, 10, 26), Decimal("-100.00"), "santander/CC/ARS", "33333333"),
        (date(2026, 10, 23), Decimal("-50.00"), "santander/CA/ARS", "44444444"),
    ]
    assert result.rows[0].description == "Compra con tarjeta de debito Kiosco"


def test_movements_xlsx_balance_check_and_currency() -> None:
    importer = SantanderMovementsXlsx()
    broken = importer.parse(movements_xlsx(rows=default_movements("1399.00")), "m.xlsx")
    assert _failed(broken) == ["saldos fila a fila"]
    dollars = importer.parse(movements_xlsx(moneda="Dólares"), "m.xlsx")
    assert {r.target for r in dollars.rows} == {"santander/CA/USD", "santander/CC/USD"}


def test_account_pdf() -> None:
    pages = extract_pages(account_pdf())
    importer = SantanderAccountPdf()
    assert importer.detect_pages(pages)
    assert not SantanderVisaPdf().detect_pages(pages)
    result = importer.parse_pages(pages)
    assert result.errors == [] and _failed(result) == []
    assert result.metadata == {"cuenta": "123-456789/0", "desde": "28/08/26", "hasta": "01/10/26"}
    assert [(r.date, r.amount, r.target, r.reference, r.description) for r in result.rows] == [
        (
            date(2026, 8, 31),
            Decimal("-200.00"),
            "santander/CA/ARS",
            "111",
            "Transferencia no gravada A Juana Perez / varios",
        ),
        (
            date(2026, 8, 31),
            Decimal("-50.00"),
            "santander/CA/ARS",
            "222",
            "Compra con tarjeta de debito Kiosco Ejemplo - tarj nro. 1234",
        ),
        (
            date(2026, 9, 2),
            Decimal("100.00"),
            "santander/CC/ARS",
            "333",
            "Transferencia recibida De Juana Perez",
        ),
        (
            date(2026, 9, 3),
            Decimal("5.00"),
            "santander/CA/USD",
            "444",
            "Comex - cobro exportacion de serv",
        ),
    ]


def test_account_pdf_wrong_total_fails_its_check() -> None:
    result = SantanderAccountPdf().parse_pages(extract_pages(account_pdf("$ 851,00")))
    assert _failed(result) == ["saldo total en pesos"]


def test_visa_pdf() -> None:
    pages = extract_pages(visa_pdf())
    importer = SantanderVisaPdf()
    assert importer.detect_pages(pages)
    assert not SantanderAccountPdf().detect_pages(pages)
    result = importer.parse_pages(pages)
    assert result.errors == [] and _failed(result) == []
    assert result.metadata["tarjetas"] == "1234"
    assert (result.metadata["cierre"], result.metadata["vencimiento"]) == ("01/10/26", "09/10/26")
    rows = [(r.date, r.amount, r.target, r.installment, r.description) for r in result.rows]
    assert rows == [
        (date(2026, 9, 4), Decimal("1000.00"), "santander/visa/ARS", None, "Su pago en pesos"),
        (date(2026, 9, 4), Decimal("10.00"), "santander/visa/USD", None, "Su pago en usd"),
        (
            date(2026, 8, 3),
            Decimal("-3000.00"),
            "santander/visa/ARS",
            (5, 8),
            "Stock general paz (5/8)",
        ),
        (
            date(2026, 8, 26),
            Decimal("-500.00"),
            "santander/visa/ARS",
            (1, 6),
            "Merpago*ejemplo (1/6)",
        ),
        (
            date(2026, 8, 26),
            Decimal("-7.70"),
            "santander/visa/USD",
            None,
            "Cashpago brl 70,23 16,55",
        ),
        (date(2026, 8, 26), Decimal("-2.30"), "santander/visa/USD", None, "Spotify"),
        (date(2026, 10, 1), Decimal("-35.00"), "santander/visa/ARS", None, "Impuesto de sellos"),
    ]


def test_visa_pdf_wrong_total_fails_its_check() -> None:
    result = SantanderVisaPdf().parse_pages(extract_pages(visa_pdf("$ 3.536,00")))
    assert _failed(result) == ["total a pagar ARS"]


def _upload(client: TestClient, path: str, name: str, content: bytes) -> Any:
    return client.post(path, files={"file": (name, content, "application/octet-stream")})


def _account(client: TestClient, name: str, currency: str) -> int:
    body = {"name": name, "institution": "Santander", "kind": "bank", "currency": currency}
    return int(client.post("/api/accounts", json=body).json()["id"])


@pytest.mark.parametrize(
    ("name", "content", "importer", "targets"),
    [
        (
            "movimientos.xlsx",
            movements_xlsx(),
            "santander_movements_xlsx",
            ["santander/CA/ARS", "santander/CC/ARS"],
        ),
        (
            "resumen.pdf",
            account_pdf(),
            "santander_account_pdf",
            ["santander/CA/ARS", "santander/CA/USD", "santander/CC/ARS"],
        ),
        (
            "visa.pdf",
            visa_pdf(),
            "santander_visa_pdf",
            ["santander/visa/ARS", "santander/visa/USD"],
        ),
    ],
)
def test_detected_through_the_api(
    client: TestClient, name: str, content: bytes, importer: str, targets: list[str]
) -> None:
    preview = _upload(client, "/api/imports/preview", name, content).json()
    assert preview["importer"] == importer
    assert preview["unmapped_targets"] == targets
    assert all(check["ok"] for check in preview["checks"])


def test_xlsx_and_pdf_of_the_same_account_dedupe(client: TestClient) -> None:
    pesos, cc, dollars = (
        _account(client, "CA pesos", "ARS"),
        _account(client, "CC pesos", "ARS"),
        _account(client, "CA dólares", "USD"),
    )
    for key, account in (
        ("santander/CA/ARS", pesos),
        ("santander/CC/ARS", cc),
        ("santander/CA/USD", dollars),
    ):
        client.put(f"/api/source-accounts/{key}", json={"account_id": account})
    assert _upload(client, "/api/imports", "resumen.pdf", account_pdf()).status_code == 201
    # The Excel export repeats the PDF's 31/08 transfer, worded and referenced its own way.
    overlap = movements_xlsx(
        rows=[
            [
                "01/09/2026",
                "100 - CENTRAL",
                "Compra con tarjeta de debito \t Otro",
                "55555555",
                "-10.00",
                "",
                "",
            ],
            [
                "31/08/2026",
                "100 - CENTRAL",
                "Transf. no gravada \t A J. Perez",
                "99999999",
                "-200.00",
                "",
                "",
            ],
        ]
    )
    preview = _upload(client, "/api/imports/preview", "movimientos.xlsx", overlap).json()
    assert (preview["new_count"], preview["duplicate_count"]) == (1, 1)
    assert _upload(client, "/api/imports", "movimientos.xlsx", overlap).json()["rows_imported"] == 1
