"""End-to-end through the HTTP API: set up, import, dedupe, categorize, pair transfers, report."""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from mis_finanzas.core.config import Settings
from mis_finanzas.market.models import FxRate, RateType

JANUARY = (
    "Fecha;Concepto;Importe\n"
    "02/01/2026;SUPERMERCADO DIA;-10.000,00\n"
    "02/01/2026;CAFE;-1.000,00\n"
    "02/01/2026;CAFE;-1.000,00\n"
    "05/01/2026;SUELDO ENERO;2.000.000,00\n"
    "10/01/2026;TRANSF A BROKER;-500.000,00\n"
)
# Overlaps JANUARY on the 2nd and 5th, and adds one new row.
OVERLAP = (
    "Fecha;Concepto;Importe\n"
    "02/01/2026;CAFE;-1.000,00\n"
    "02/01/2026;CAFE;-1.000,00\n"
    "05/01/2026;SUELDO ENERO;2.000.000,00\n"
    "12/01/2026;FARMACIA;-3.000,00\n"
)
BROKER = "Fecha;Concepto;Importe\n11/01/2026;DEPOSITO;500.000,00\n"
MAPPING_CONFIG = {
    "date_column": "Fecha",
    "description_columns": ["Concepto"],
    "amount_column": "Importe",
}


def _post(client: TestClient, url: str, body: dict[str, Any]) -> dict[str, Any]:
    response = client.post(url, json=body)
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def _setup_account(client: TestClient, name: str, kind: str = "bank") -> int:
    account = _post(
        client,
        "/api/accounts",
        {"name": name, "institution": "Banco", "kind": kind, "currency": "ARS"},
    )
    mapping = _post(
        client,
        "/api/mappings",
        {"name": f"{name} csv", "account_id": account["id"], "config": MAPPING_CONFIG},
    )
    return int(mapping["id"])


def _upload(
    client: TestClient, path: str, mapping_id: int, text: str, filename: str = "mov.csv"
) -> Any:
    return client.post(
        path,
        data={"mapping_id": str(mapping_id)},
        files={"file": (filename, text.encode(), "text/csv")},
    )


@pytest.fixture
def bank_mapping(client: TestClient) -> int:
    return _setup_account(client, "Banco pesos")


def test_preview_flags_nothing_new_on_first_upload(client: TestClient, bank_mapping: int) -> None:
    preview = _upload(client, "/api/imports/preview", bank_mapping, JANUARY).json()
    assert (preview["new_count"], preview["duplicate_count"]) == (5, 0)
    assert preview["already_imported"] is False
    assert client.get("/api/transactions").json()["total"] == 0


def test_import_dedupes_same_file_and_overlaps(
    client: TestClient, bank_mapping: int, settings: Settings
) -> None:
    first = _upload(client, "/api/imports", bank_mapping, JANUARY)
    assert first.status_code == 201 and first.json()["rows_imported"] == 5
    assert len(list(settings.uploads_dir.iterdir())) == 1

    again = _upload(client, "/api/imports", bank_mapping, JANUARY, filename="copy.csv")
    assert again.status_code == 409

    overlap = _upload(client, "/api/imports", bank_mapping, OVERLAP).json()
    assert (overlap["rows_imported"], overlap["rows_duplicate"]) == (1, 3)
    assert client.get("/api/transactions").json()["total"] == 6


def test_rows_with_errors_block_commit_unless_skipped(
    client: TestClient, bank_mapping: int
) -> None:
    bad = JANUARY + "99/99/2026;MALA;-1,00\n"
    assert _upload(client, "/api/imports", bank_mapping, bad).status_code == 409
    response = client.post(
        "/api/imports",
        data={"mapping_id": str(bank_mapping), "skip_invalid_rows": "true"},
        files={"file": ("mov.csv", bad.encode(), "text/csv")},
    )
    assert response.status_code == 201
    assert response.json()["rows_skipped"] == 1


def test_unreadable_file_is_422(client: TestClient, bank_mapping: int) -> None:
    response = _upload(client, "/api/imports/preview", bank_mapping, "a;b\n1;2\n")
    assert response.status_code == 422


def test_rules_categorize_on_import_and_on_apply(client: TestClient, bank_mapping: int) -> None:
    food = _post(client, "/api/categories", {"name": "Comida"})
    _post(client, "/api/rules", {"category_id": food["id"], "pattern": "supermercado"})
    _upload(client, "/api/imports", bank_mapping, JANUARY)
    rows = client.get("/api/transactions", params={"search": "super"}).json()["items"]
    assert rows[0]["category_name"] == "Comida"

    _post(client, "/api/rules", {"category_id": food["id"], "pattern": "CAFE"})
    assert client.post("/api/rules/apply").json() == {"categorized": 2}
    uncategorized = client.get("/api/transactions", params={"uncategorized": True}).json()
    assert uncategorized["total"] == 2


def test_invalid_regex_rule_is_rejected(client: TestClient) -> None:
    food = _post(client, "/api/categories", {"name": "Comida"})
    response = client.post(
        "/api/rules", json={"category_id": food["id"], "pattern": "(", "match_type": "regex"}
    )
    assert response.status_code == 422


def test_category_kind_drives_transaction_kind(client: TestClient, bank_mapping: int) -> None:
    _upload(client, "/api/imports", bank_mapping, JANUARY)
    fx = _post(client, "/api/categories", {"name": "Compra MEP", "kind": "fx"})
    tx = client.get("/api/transactions", params={"search": "BROKER"}).json()["items"][0]
    patched = client.patch(f"/api/transactions/{tx['id']}", json={"category_id": fx["id"]})
    assert patched.json()["kind"] == "fx"


def test_transfer_pairing_excludes_rows_from_totals(
    client: TestClient, session: Session, bank_mapping: int
) -> None:
    broker_mapping = _setup_account(client, "Broker", kind="broker")
    _upload(client, "/api/imports", bank_mapping, JANUARY)
    _upload(client, "/api/imports", broker_mapping, BROKER)
    candidates = client.get("/api/transfers/candidates").json()
    assert len(candidates) == 1
    pair = candidates[0]
    response = client.post(
        "/api/transfers",
        json={"outgoing_id": pair["outgoing"]["id"], "incoming_id": pair["incoming"]["id"]},
    )
    assert response.status_code == 204
    assert client.get("/api/transfers/candidates").json() == []

    session.add(
        FxRate(
            rate_type=RateType.MEP,
            date=date(2026, 1, 2),
            buy=Decimal(990),
            sell=Decimal(1000),
            source="test",
        )
    )
    session.commit()
    months = client.get(
        "/api/reports/monthly", params={"start": "2026-01-01", "end": "2026-01-31"}
    ).json()
    assert months == [
        {
            "month": "2026-01",
            "income_ars": "2000000.00",
            "income_usd": "2000.00",
            "expense_ars": "12000.00",
            "expense_usd": "12.00",
            "net_ars": "1988000.00",
            "net_usd": "1988.00",
            "missing_rate": 0,
        }
    ]

    client.delete(f"/api/transfers/{pair['outgoing']['id']}")
    assert len(client.get("/api/transfers/candidates").json()) == 1


def test_reports_by_category_and_market_status(client: TestClient, bank_mapping: int) -> None:
    food = _post(client, "/api/categories", {"name": "Comida"})
    _post(client, "/api/rules", {"category_id": food["id"], "pattern": "CAFE"})
    _upload(client, "/api/imports", bank_mapping, JANUARY)
    totals = client.get(
        "/api/reports/categories", params={"start": "2026-01-01", "end": "2026-01-31"}
    ).json()
    assert [(t["category"], t["ars"], t["missing_rate"]) for t in totals] == [
        ("Sin categoría", "510000.00", 2),
        ("Comida", "2000.00", 2),
    ]
    status = client.get("/api/market/status").json()
    assert status == {"latest_rate_date": None, "latest_rate": None, "stale": True}


def test_crud_conflicts_and_not_found(client: TestClient) -> None:
    body = {"name": "Banco", "institution": "X", "kind": "bank", "currency": "ARS"}
    _post(client, "/api/accounts", body)
    assert client.post("/api/accounts", json=body).status_code == 409
    assert client.put("/api/accounts/999", json=body).status_code == 404
    assert client.post("/api/accounts", json={**body, "kind": "nope"}).status_code == 422
