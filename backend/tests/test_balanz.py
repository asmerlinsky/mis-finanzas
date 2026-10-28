"""Balanz importers on synthetic statements, and end to end through the API."""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from balanz_fixtures import TRADE, holdings_pdf, movements_pdf
from mis_finanzas.importers.balanz.common import split_amounts, split_glued_amounts
from mis_finanzas.importers.balanz.holdings_pdf import BalanzHoldingsPdf
from mis_finanzas.importers.balanz.movements_pdf import (
    BalanzMovementsPdf,
    cash_target,
    instrument_ref,
)
from mis_finanzas.importers.base import ParseResult
from mis_finanzas.importers.pdf_layout import find_header_rows, table_rows
from mis_finanzas.importers.pdf_words import PageWords, Word, extract_pages
from mis_finanzas.investments.models import HoldingSnapshot, InvestmentOperation
from mis_finanzas.investments.records import SnapshotSource
from mis_finanzas.ledger.models import Transaction, TransactionKind


def _failed(result: ParseResult) -> list[str]:
    return [check.name for check in result.failed_checks]


def test_movements_pdf() -> None:
    pages = extract_pages(movements_pdf())
    importer = BalanzMovementsPdf()
    assert importer.detect_pages(pages)
    assert not BalanzHoldingsPdf().detect_pages(pages)
    result = importer.parse_pages(pages)
    assert result.errors == [] and _failed(result) == []
    assert result.metadata == {"periodo": "1/3/2026 al 31/3/2026"}
    assert [(r.date, r.amount, r.target, r.description) for r in result.rows] == [
        (date(2026, 3, 10), Decimal("-5034.25"), "balanz/ARS", TRADE),
        (date(2026, 3, 20), Decimal("-1.50"), "balanz/ARS", "Dividendo en efectivo / EJM"),
        (date(2026, 3, 20), Decimal("2.50"), "balanz/CABLE/USD", "Dividendo en efectivo / EJM"),
    ]
    data = result.investments
    assert data is not None and data.snapshot is not None
    [operation] = data.operations
    assert (operation.instrument.ticker, operation.instrument.broker_code) == ("EJM", "1234")
    assert (operation.quantity, operation.price, operation.fees, operation.net) == (
        Decimal("5.00"),
        Decimal("1000.00"),
        Decimal("34.25"),
        Decimal("-5034.25"),
    )
    assert (operation.trade_date, operation.settle_date) == (date(2026, 3, 10), date(2026, 3, 11))
    assert data.snapshot.as_of == date(2026, 3, 31)
    assert data.snapshot.source is SnapshotSource.MOVEMENTS
    assert [(p.instrument.ticker, p.quantity) for p in data.snapshot.positions] == [
        ("EJM", Decimal("15.00")),
        ("DOS", Decimal("100.00")),
    ]


def test_movements_pdf_never_reads_the_page_header_or_footer() -> None:
    result = BalanzMovementsPdf().parse_pages(extract_pages(movements_pdf()))
    read = repr(result)
    assert "JUANA" not in read.upper() and "BALANZ.COM" not in read.upper()


def test_movements_pdf_balance_check_fails_on_a_misread() -> None:
    result = BalanzMovementsPdf().parse_pages(extract_pages(movements_pdf(pesos_closing="1,00")))
    assert _failed(result) == ["saldos de monedas fila a fila"]


@pytest.mark.parametrize(
    ("title", "target"),
    [
        ("Pesos", "balanz/ARS"),
        ("Dólar MEP", "balanz/MEP/USD"),
        ("Dólares Cable", "balanz/CABLE/USD"),
    ],
)
def test_cash_targets(title: str, target: str) -> None:
    assert cash_target(title) == target


def test_unknown_currency_and_bad_instrument_titles_are_rejected() -> None:
    with pytest.raises(ValueError):
        cash_target("Euros")
    with pytest.raises(ValueError):
        instrument_ref("CEDEAR SIN TICKER")


def test_holdings_pdf() -> None:
    pages = extract_pages(holdings_pdf())
    importer = BalanzHoldingsPdf()
    assert importer.detect_pages(pages)
    assert not BalanzMovementsPdf().detect_pages(pages)
    result = importer.parse_pages(pages)
    assert result.errors == [] and _failed(result) == []
    assert result.rows == []
    assert result.metadata == {"fecha": "27/10/2026"}
    data = result.investments
    assert data is not None and data.snapshot is not None
    snapshot = data.snapshot
    assert (snapshot.as_of, snapshot.source) == (date(2026, 10, 27), SnapshotSource.HOLDINGS)
    assert [
        (p.instrument.ticker, p.instrument.asset_class, p.quantity, p.price, p.value, p.currency)
        for p in snapshot.positions
    ] == [
        ("DOS", "Acciones", Decimal("100.00"), Decimal("1000.00"), Decimal(100000), "ARS"),
        ("TRES", "Acciones", Decimal(50), Decimal("4000.00"), Decimal(200000), "ARS"),
        ("EJM", "Cedears", Decimal("15.00"), Decimal("46666.67"), Decimal(700000), "ARS"),
    ]
    assert [(c.label, c.currency, c.amount) for c in snapshot.cash] == [
        ("Pesos", "ARS", Decimal("-2761.55")),
        ("Dólares", "USD", Decimal("100.00")),
        ("US Dollar (Cable)", "USD", Decimal("50.00")),
    ]
    assert "JUANA" not in repr(result).upper()  # the page-1 account name is never read


def test_holdings_class_total_check() -> None:
    importer = BalanzHoldingsPdf()
    off_by_one_per_row = importer.parse_pages(extract_pages(holdings_pdf("700.001")))
    assert _failed(off_by_one_per_row) == []  # values print rounded to whole pesos
    misread = importer.parse_pages(extract_pages(holdings_pdf("710.000")))
    assert _failed(misread) == ["total de Cedears"]


def _upload(client: TestClient, path: str, name: str, content: bytes) -> Any:
    return client.post(path, files={"file": (name, content, "application/octet-stream")})


def _map_broker_accounts(client: TestClient) -> None:
    for key, name, currency in (
        ("balanz/ARS", "Balanz pesos", "ARS"),
        ("balanz/CABLE/USD", "Balanz cable", "USD"),
    ):
        body = {"name": name, "institution": "Balanz", "kind": "broker", "currency": currency}
        account = client.post("/api/accounts", json=body).json()["id"]
        client.put(f"/api/source-accounts/{key}", json={"account_id": account})


def test_movements_import_writes_cash_operations_and_snapshot(
    client: TestClient, session: Session
) -> None:
    preview = _upload(client, "/api/imports/preview", "movimientos.pdf", movements_pdf()).json()
    assert preview["importer"] == "balanz_movements_pdf"
    assert preview["unmapped_targets"] == ["balanz/ARS", "balanz/CABLE/USD"]
    assert preview["investments"] == {
        "as_of": "2026-03-31",
        "source": "movimientos",
        "positions": 2,
        "cash": 0,
        "operations": 1,
        "new_operations": 1,
        "replaces_snapshot": False,
    }
    _map_broker_accounts(client)
    assert _upload(client, "/api/imports", "movimientos.pdf", movements_pdf()).status_code == 201
    kinds = {(t.amount_cents, t.kind) for t in session.scalars(select(Transaction))}
    # Dividends and their fees in pesos both count as dividend income; a trade, as investment.
    assert (-150, TransactionKind.INCOME) in kinds and (250, TransactionKind.INCOME) in kinds
    assert (-503425, TransactionKind.INVESTMENT) in kinds
    assert len(session.scalars(select(InvestmentOperation)).all()) == 1
    [snapshot] = session.scalars(select(HoldingSnapshot)).all()
    assert len(snapshot.positions) == 2


def test_holdings_import_has_no_ledger_rows_and_replaces_its_snapshot(
    client: TestClient, session: Session
) -> None:
    preview = _upload(client, "/api/imports/preview", "tenencias.pdf", holdings_pdf()).json()
    assert preview["importer"] == "balanz_holdings_pdf"
    assert (preview["rows"], preview["targets"]) == ([], [])
    assert preview["investments"]["positions"] == 3
    assert _upload(client, "/api/imports", "tenencias.pdf", holdings_pdf()).status_code == 201
    # Another file for the same date (here, a total that is still within rounding) replaces it.
    again = holdings_pdf("700.001")
    preview = _upload(client, "/api/imports/preview", "tenencias-2.pdf", again).json()
    assert preview["investments"]["replaces_snapshot"] is True
    assert _upload(client, "/api/imports", "tenencias-2.pdf", again).status_code == 201
    [snapshot] = session.scalars(select(HoldingSnapshot)).all()
    assert len(snapshot.positions) == 3 and len(snapshot.cash) == 3


@pytest.mark.parametrize(
    ("text", "parts"),
    [
        ("145.769,874432,25", ["145.769,87", "4432,25"]),  # amount, amount
        ("312.391,838,9377655679", ["312.391,83", "8,9377655679"]),  # amount, 10-decimal price
        ("7192,3168219232-364.975,53", ["7192,3168219232", "-364.975,53"]),  # price, amount
        ("9081,4688635062", ["9081,4688635062"]),
        ("Boleto", None),
        ("1,2,3", None),
    ],
)
def test_split_amounts(text: str, parts: list[str] | None) -> None:
    assert split_amounts(text) == parts


def _word(text: str, x0: float, x1: float, top: float) -> Word:
    return Word(text=text, x0=x0, top=top, x1=x1, bottom=top + 7.5, fontname="F", size=7.5)


def test_glued_amounts_are_read_into_their_own_columns() -> None:
    words = [
        _word("Bruto", 100, 130, 100),
        _word("Arancel", 150, 185, 100),
        _word("5.000,0025,00", 95, 165, 120),  # right-aligned values printed with no gap
    ]
    page = split_glued_amounts(PageWords(1, 300, 400, words))
    [header] = find_header_rows(page, ["Bruto", "Arancel"])
    [row] = table_rows(page, header, ["Bruto"])
    assert (row.cell("Bruto"), row.cell("Arancel")) == ("5.000,00", "25,00")
