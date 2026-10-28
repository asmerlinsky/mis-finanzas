"""Matching invoices to the incoming movements that paid them. Invented values only."""

from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from arca_fixtures import comprobantes_csv, invoice_row
from mis_finanzas.ledger.models import Account, AccountKind, Currency, Transaction, TransactionKind

ROWS = [
    invoice_row("2026-03-10", 19, 7, "3000,00"),  # USD, paid on 20/03
    invoice_row("2026-04-10", 19, 8, "3000,00"),  # same amount a month later: paid on 18/04
    invoice_row("2026-04-10", 11, 3, "500000,00", currency="PES", rate="1,00"),
    invoice_row("2026-05-10", 21, 2, "1000,00"),  # a credit note: never matched
]


def _tx(session: Session, account: Account, day: date, cents: int, **extra: Any) -> Transaction:
    tx = Transaction(
        account_id=account.id,
        date=day,
        amount_cents=cents,
        description_raw="Cobro",
        description_norm="COBRO",
        kind=extra.pop("kind", TransactionKind.INCOME),
        fingerprint=f"{account.id}-{day}-{cents}",
        **extra,
    )
    session.add(tx)
    session.flush()
    return tx


@pytest.fixture
def seeded(client: TestClient, session: Session) -> dict[str, int]:
    files = {"file": ("c.csv", comprobantes_csv(ROWS), "text/csv")}
    assert client.post("/api/imports", files=files).status_code == 201
    dollars = Account(
        name="CA dólares", institution="B", kind=AccountKind.BANK, currency=Currency.USD
    )
    pesos = Account(name="CA pesos", institution="B", kind=AccountKind.BANK, currency=Currency.ARS)
    session.add_all([dollars, pesos])
    session.flush()
    ids = {
        "usd_0320": _tx(session, dollars, date(2026, 3, 20), 300000).id,
        "usd_0321_fees": _tx(session, dollars, date(2026, 3, 21), 297500).id,
        "usd_0418": _tx(session, dollars, date(2026, 4, 18), 300000).id,
        "usd_0801_late": _tx(session, dollars, date(2026, 8, 1), 300000).id,
        "ars_0412": _tx(session, pesos, date(2026, 4, 12), 50000000).id,
    }
    own = _tx(session, pesos, date(2026, 4, 11), 50000000, kind=TransactionKind.TRANSFER)
    own.transfer_pair_id = ids["ars_0412"]  # stands for a transfer between own accounts
    session.commit()
    return ids


def _by_number(client: TestClient) -> dict[str, dict[str, Any]]:
    return {i["number"]: i for i in client.get("/api/monotributo/invoices").json()}


def test_suggestions_take_the_exact_payment_closest_in_date(
    client: TestClient, seeded: dict[str, int]
) -> None:
    invoices = _by_number(client)
    suggested = {n: (i["suggestion"] or {}).get("transaction_id") for n, i in invoices.items()}
    assert suggested == {
        "00001-00000007": seeded["usd_0320"],
        "00001-00000008": seeded["usd_0418"],  # not 20/03: the March invoice took that one
        "00001-00000003": seeded["ars_0412"],  # the transfer between own accounts is left out
        "00001-00000002": None,  # credit note
    }
    assert all(i["payment"] is None for i in invoices.values())


def test_candidates_list_any_amount_in_the_currency_exact_first(
    client: TestClient, seeded: dict[str, int]
) -> None:
    invoice = _by_number(client)["00001-00000007"]
    found = client.get(f"/api/monotributo/invoices/{invoice['id']}/candidates").json()
    assert [(c["transaction_id"], c["exact"]) for c in found] == [
        (seeded["usd_0320"], True),
        (seeded["usd_0418"], True),
        (seeded["usd_0321_fees"], False),
    ]  # pesos and the movement 4 months later are not candidates


def test_link_categorizes_the_payment_and_unlink_undoes_it(
    client: TestClient, session: Session, seeded: dict[str, int]
) -> None:
    invoice = _by_number(client)["00001-00000007"]
    url = f"/api/monotributo/invoices/{invoice['id']}/payment"
    wrong = client.put(url, json={"transaction_id": seeded["ars_0412"]})
    assert wrong.status_code == 422  # pesos can't pay a dollar invoice
    fees = client.put(url, json={"transaction_id": seeded["usd_0321_fees"]})
    assert fees.status_code == 204  # chosen by hand: any amount
    linked = _by_number(client)
    assert linked["00001-00000007"]["payment"]["exact"] is False
    assert linked["00001-00000007"]["suggestion"] is None
    payment = session.get(Transaction, seeded["usd_0321_fees"])
    assert payment is not None and payment.category is not None
    assert (payment.category.name, payment.kind) == ("Facturación", TransactionKind.INCOME)
    other = _by_number(client)["00001-00000008"]
    taken = client.get(f"/api/monotributo/invoices/{other['id']}/candidates").json()
    assert seeded["usd_0321_fees"] not in [c["transaction_id"] for c in taken]
    assert client.delete(url).status_code == 204
    assert _by_number(client)["00001-00000007"]["payment"] is None
