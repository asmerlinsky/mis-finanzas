"""Dedicated importers end to end: detection, targets, checks, dedup v2, near-duplicates."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from conftest import make_pdf
from fake_importers import (
    MAGIC,
    BrokenDetector,
    FakePageImporter,
    FakeStatementImporter,
    GreedyImporter,
)
from mis_finanzas.importers import registry
from mis_finanzas.importers.base import ImportFileError
from mis_finanzas.ledger.models import Transaction


def _statement(*lines: str) -> bytes:
    return MAGIC + b"\n" + "\n".join(lines).encode()


STATEMENT = _statement(
    "TOTAL;bank/ARS;-1500.00",
    "TOTAL;bank/USD;-20.00",
    "05/01/2026;-1000.00;bank/ARS;Compra super;R1;",
    "05/01/2026;-500.00;bank/ARS;Cuota tele;R2;3/12",
    "06/01/2026;-20.00;bank/USD;Dropbox;R3;",
)


@pytest.fixture
def fake_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry, "_FILE_IMPORTERS", [FakeStatementImporter()])
    monkeypatch.setattr(registry, "_PAGE_IMPORTERS", [FakePageImporter()])


def test_registry_picks_the_one_importer_that_detects(fake_registry: None) -> None:
    parsed = registry.parse_file("x.txt", STATEMENT)
    assert parsed is not None and parsed.importer == "fake_statement"
    assert len(parsed.result.rows) == 3
    assert registry.parse_file("x.txt", b"something else") is None


def test_registry_reads_pdfs_through_page_importers(fake_registry: None) -> None:
    parsed = registry.parse_file("r.pdf", make_pdf([(72, 800, "FAKEBANK resumen")]))
    assert parsed is not None and parsed.importer == "fake_pages"
    assert registry.parse_file("r.pdf", make_pdf([(72, 800, "otro banco")])) is None


def test_registry_rejects_ambiguity_and_survives_broken_detectors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(registry, "_FILE_IMPORTERS", [BrokenDetector(), FakeStatementImporter()])
    parsed = registry.parse_file("x.txt", STATEMENT)
    assert parsed is not None and parsed.importer == "fake_statement"
    monkeypatch.setattr(registry, "_FILE_IMPORTERS", [FakeStatementImporter(), GreedyImporter()])
    with pytest.raises(ImportFileError, match="several importers"):
        registry.parse_file("x.txt", STATEMENT)


def _account(client: TestClient, name: str, currency: str = "ARS") -> int:
    body = {"name": name, "institution": "Banco de Prueba", "kind": "bank", "currency": currency}
    response = client.post("/api/accounts", json=body)
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _upload(client: TestClient, path: str, content: bytes, **fields: str) -> Any:
    return client.post(path, data=fields, files={"file": ("resumen.txt", content, "text/plain")})


def _map(client: TestClient, target: str, account_id: int) -> None:
    response = client.put(f"/api/source-accounts/{target}", json={"account_id": account_id})
    assert response.status_code == 200, response.text


def test_unmapped_targets_block_until_mapped(
    client: TestClient, session: Session, fake_registry: None
) -> None:
    preview = _upload(client, "/api/imports/preview", STATEMENT).json()
    assert preview["importer"] == "fake_statement"
    assert preview["unmapped_targets"] == ["bank/ARS", "bank/USD"]
    assert [c["ok"] for c in preview["checks"]] == [True, True]
    assert preview["metadata"] == {"bank": "Banco de Prueba"}
    assert _upload(client, "/api/imports", STATEMENT).status_code == 409

    ars, usd = _account(client, "Banco pesos"), _account(client, "Banco dólares", "USD")
    _map(client, "bank/ARS", ars)
    _map(client, "bank/USD", usd)
    batch = _upload(client, "/api/imports", STATEMENT)
    assert batch.status_code == 201, batch.text
    assert batch.json()["account_id"] is None  # rows went to two accounts
    stored = {t.reference: t for t in session.scalars(select(Transaction))}
    assert stored["R2"].account_id == ars and stored["R3"].account_id == usd
    assert (stored["R2"].installment_number, stored["R2"].installment_total) == (3, 12)
    assert [s["key"] for s in client.get("/api/source-accounts").json()] == ["bank/ARS", "bank/USD"]


def test_failed_totals_check_blocks_the_import(client: TestClient, fake_registry: None) -> None:
    _map(client, "bank/ARS", _account(client, "Banco pesos"))
    wrong = _statement("TOTAL;bank/ARS;-999.00", "05/01/2026;-1000.00;bank/ARS;Compra;R1;")
    check = _upload(client, "/api/imports/preview", wrong).json()["checks"][0]
    assert check == {
        "name": "total bank/ARS",
        "expected": "-999.00",
        "actual": "-1000.00",
        "ok": False,
    }
    response = _upload(client, "/api/imports", wrong)
    assert response.status_code == 409 and "totals" in response.json()["detail"]


def test_same_movement_from_another_source_is_a_duplicate(
    client: TestClient, fake_registry: None
) -> None:
    ars = _account(client, "Banco pesos")
    mapping = client.post(
        "/api/mappings",
        json={
            "name": "Banco csv",
            "account_id": ars,
            "config": {
                "date_column": "Fecha",
                "description_columns": ["Concepto"],
                "amount_column": "Importe",
            },
        },
    ).json()
    csv = b"Fecha;Concepto;Importe\n05/01/2026;COMPRA SUPERMERCADO DIA;-1.000,00\n"
    first = client.post(
        "/api/imports",
        data={"mapping_id": str(mapping["id"])},
        files={"file": ("mov.csv", csv, "text/csv")},
    )
    assert first.status_code == 201
    _map(client, "bank/ARS", ars)
    only_ars = _statement(
        "05/01/2026;-1000.00;bank/ARS;Compra super;R1;", "05/01/2026;-500.00;bank/ARS;Cuota;R2;"
    )
    preview = _upload(client, "/api/imports/preview", only_ars).json()
    assert (preview["new_count"], preview["duplicate_count"]) == (1, 1)


def test_near_duplicates_are_flagged_and_can_be_skipped(
    client: TestClient, fake_registry: None
) -> None:
    _map(client, "bank/ARS", _account(client, "Banco pesos"))
    _upload(client, "/api/imports", _statement("03/01/2026;-700.00;bank/ARS;Luz;A;"))
    later = _statement(
        "05/01/2026;-700.00;bank/ARS;Edesur luz;B;", "05/01/2026;-80.00;bank/ARS;Kiosco;C;"
    )
    preview = _upload(client, "/api/imports/preview", later).json()
    assert preview["near_duplicate_count"] == 1
    near = next(r for r in preview["rows"] if r["near_duplicate"])
    assert _upload(client, "/api/imports", later, skip_lines="99").status_code == 409
    assert _upload(client, "/api/imports", later, skip_lines="x").status_code == 422
    batch = _upload(client, "/api/imports", later, skip_lines=str(near["line_number"])).json()
    assert (batch["rows_imported"], batch["rows_skipped"]) == (1, 1)


def test_unrecognized_file_without_mapping_is_422(client: TestClient, fake_registry: None) -> None:
    response = _upload(client, "/api/imports/preview", b"Fecha;Importe\n")
    assert response.status_code == 422 and "no importer" in response.json()["detail"]


def test_source_account_endpoints(client: TestClient) -> None:
    assert client.put("/api/source-accounts/x/ARS", json={"account_id": 999}).status_code == 404
    _map(client, "x/ARS", _account(client, "Banco pesos"))
    other = _account(client, "Otro")
    _map(client, "x/ARS", other)
    assert client.get("/api/source-accounts").json() == [{"key": "x/ARS", "account_id": other}]
    assert client.delete("/api/source-accounts/x/ARS").status_code == 204
    assert client.delete("/api/source-accounts/x/ARS").status_code == 404
