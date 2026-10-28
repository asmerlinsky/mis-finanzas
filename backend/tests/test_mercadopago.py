"""Mercado Pago account summary CSV, on synthetic exports with invented values."""

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from mis_finanzas.importers.mercadopago.account_csv import MercadoPagoAccountCsv

HEADER = "RELEASE_DATE;TRANSACTION_TYPE;REFERENCE_ID;TRANSACTION_NET_AMOUNT;PARTIAL_BALANCE"


def export(final: str = "2.200,00", comma: bool = True) -> bytes:
    rows = [
        "04-09-2026;Transferencia recibida Juana Perez;111;1.490,00;2.490,00",
        "05-09-2026;Pago con QR Kiosco Ejemplo;222;-300,00;2.190,00",
        "16-09-2026;Rendimientos ;333;10,00;2.200,00",
    ]
    text = (
        "\n".join(
            [
                "INITIAL_BALANCE;CREDITS;DEBITS;FINAL_BALANCE;",
                f"1.000,00;1.500,00;-300,00;{final};",
                ";;;;",
                HEADER,
                *rows,
            ]
        )
        + "\n"
    )
    if not comma:  # the same export with a dot decimal and comma thousands
        text = text.replace(".", "#").replace(",", ".").replace("#", ",")
    return text.encode()


def _failed(content: bytes) -> list[str]:
    return [c.name for c in MercadoPagoAccountCsv().parse(content, "mp.csv").failed_checks]


@pytest.mark.parametrize("comma", [True, False])
def test_reads_either_number_format(comma: bool) -> None:
    result = MercadoPagoAccountCsv().parse(export(comma=comma), "mp.csv")
    assert result.errors == [] and result.failed_checks == []
    assert result.metadata["separador_decimal"] == ("," if comma else ".")
    assert [(r.date, r.amount, r.reference, r.description, r.target) for r in result.rows] == [
        (
            date(2026, 9, 4),
            Decimal("1490.00"),
            "111",
            "Transferencia recibida Juana Perez",
            "mercadopago/ARS",
        ),
        (
            date(2026, 9, 5),
            Decimal("-300.00"),
            "222",
            "Pago con QR Kiosco Ejemplo",
            "mercadopago/ARS",
        ),
        (date(2026, 9, 16), Decimal("10.00"), "333", "Rendimientos", "mercadopago/ARS"),
    ]


def test_wrong_final_balance_fails_its_check() -> None:
    assert _failed(export(final="2.201,00")) == ["saldo final"]


def test_a_broken_row_balance_is_reported() -> None:
    content = export().replace(b"-300,00;2.190,00", b"-300,00;2.191,00")
    assert "saldos fila a fila" in _failed(content)


def test_detection() -> None:
    importer = MercadoPagoAccountCsv()
    assert importer.detect("resumen.csv", export())
    assert not importer.detect("resumen.txt", export())
    settlement = b"SOURCE_ID;PAYMENT_METHOD_TYPE;TRANSACTION_TYPE;TRANSACTION_AMOUNT\n1;x;y;2\n"
    assert not importer.detect("liquidaciones.csv", settlement)
    assert not importer.detect("generic.csv", b"Fecha;Concepto;Importe\n01/01/2026;x;1,00\n")


def test_import_through_the_api_with_seeded_rendimientos_rule(client: TestClient) -> None:
    files = {"file": ("resumen-mp.csv", export(), "text/csv")}
    preview = client.post("/api/imports/preview", files=files).json()
    assert preview["importer"] == "mercadopago_account_csv"
    assert preview["unmapped_targets"] == ["mercadopago/ARS"]
    account = client.post(
        "/api/accounts",
        json={"name": "Mercado Pago", "institution": "MP", "kind": "wallet", "currency": "ARS"},
    ).json()
    client.put("/api/source-accounts/mercadopago/ARS", json={"account_id": account["id"]})
    assert client.post("/api/imports", files=files).status_code == 201
    rows = client.get("/api/transactions", params={"search": "rendimientos"}).json()["items"]
    assert [(r["category_name"], r["kind"]) for r in rows] == [("Rendimientos", "income")]
