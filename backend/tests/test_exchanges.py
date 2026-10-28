"""Currency exchanges between own accounts: pairing, linking, and the seeded category."""

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from mis_finanzas.ledger.exchanges import find_exchange_candidates, link_exchange
from mis_finanzas.ledger.models import (
    Account,
    AccountKind,
    Category,
    Currency,
    Transaction,
    TransactionKind,
)
from mis_finanzas.ledger.transfers import unlink_transfer

PESOS = Account(
    id=1, name="CA pesos", institution="B", kind=AccountKind.BANK, currency=Currency.ARS
)
DOLLARS = Account(
    id=2, name="CA dólares", institution="B", kind=AccountKind.BANK, currency=Currency.USD
)
FX = Category(id=5, name="Cambio de moneda", kind=TransactionKind.FX)


def _tx(tx_id: int, account: Account, day: int, cents: int) -> Transaction:
    return Transaction(
        id=tx_id,
        account=account,
        account_id=account.id,
        date=date(2026, 5, day),
        amount_cents=cents,
        kind=TransactionKind.FX,
        category=FX,
        category_id=FX.id,
        transfer_pair_id=None,
        description_raw="",
        description_norm="",
        fingerprint=str(tx_id),
    )


def _no_rate(_: date) -> Decimal | None:
    return None


def _mep(_: date) -> Decimal | None:
    return Decimal(1450)


def test_one_sale_a_day_pairs_with_its_rate() -> None:
    sold = _tx(1, DOLLARS, 8, -100000)  # USD 1000 out
    got = _tx(2, PESOS, 8, 145000000)  # ARS 1.450.000 in
    other_day = _tx(3, PESOS, 9, 145000000)
    [candidate] = find_exchange_candidates([sold, got, other_day], _no_rate)
    assert (candidate.outgoing.id, candidate.incoming.id, candidate.rate) == (1, 2, Decimal(1450))


def test_several_a_day_pair_closest_to_the_mep_and_leftovers_stay() -> None:
    sides = [
        _tx(1, DOLLARS, 8, -200000),  # USD 2000
        _tx(2, DOLLARS, 8, -100000),  # USD 1000
        _tx(3, DOLLARS, 8, -50000),  # USD 500: no peso side left for it
        _tx(4, PESOS, 8, 145000000),  # ARS 1.450.000
        _tx(5, PESOS, 8, 290000000),  # ARS 2.900.000
    ]
    pairs = [(c.outgoing.id, c.incoming.id) for c in find_exchange_candidates(sides, _mep)]
    assert pairs == [(1, 5), (2, 4)]


def test_a_rate_far_from_the_mep_is_not_proposed() -> None:
    """One sale settled in two debits: neither debit alone is an exchange at a real rate."""
    sides = [
        _tx(1, DOLLARS, 8, -60000),  # USD 600
        _tx(2, DOLLARS, 8, -40000),  # USD 400
        _tx(3, PESOS, 8, 145000000),  # ARS 1.450.000 for the USD 1000
    ]
    assert find_exchange_candidates(sides, _mep) == []


def test_same_currency_or_not_fx_is_no_exchange() -> None:
    pesos_out = _tx(1, PESOS, 8, -100)
    pesos_in = _tx(2, PESOS, 8, 100)
    income = _tx(3, DOLLARS, 8, 100)
    income.kind = TransactionKind.INCOME
    assert find_exchange_candidates([pesos_out, pesos_in, income], _no_rate) == []
    with pytest.raises(ValueError):
        link_exchange(pesos_out, pesos_in)


def test_unlinked_exchange_stays_an_exchange() -> None:
    sold, got = _tx(1, DOLLARS, 8, -100000), _tx(2, PESOS, 8, 145000000)
    link_exchange(sold, got)
    assert (sold.transfer_pair_id, got.transfer_pair_id) == (2, 1)
    unlink_transfer(sold, got)
    assert (sold.kind, got.kind, sold.transfer_pair_id) == (
        TransactionKind.FX,
        TransactionKind.FX,
        None,
    )


def test_api_lists_and_links_exchanges(client: TestClient, session: Session) -> None:
    fx = session.scalar(select(Category).where(Category.name == "Cambio de moneda"))
    assert fx is not None and fx.kind is TransactionKind.FX  # seeded
    pesos = Account(name="CA pesos", institution="B", kind=AccountKind.BANK, currency=Currency.ARS)
    dollars = Account(
        name="CA dólares", institution="B", kind=AccountKind.BANK, currency=Currency.USD
    )
    session.add_all([pesos, dollars])
    session.flush()
    for account, cents, text in (
        (dollars, -100000, "LIQUIDACION TITULOS DEBITO"),
        (pesos, 145000000, "LIQUIDACION TITULOS PUBLICOS CREDI"),
    ):
        session.add(
            Transaction(
                account_id=account.id,
                date=date(2026, 5, 8),
                amount_cents=cents,
                description_raw=text.title(),
                description_norm=text,
                kind=TransactionKind.INCOME,
                fingerprint=text,
            )
        )
    session.commit()
    assert client.post("/api/rules/apply").json() == {"categorized": 2}  # the seeded rules
    [candidate] = client.get("/api/exchanges/candidates").json()
    assert (candidate["rate"], candidate["mep"]) == ("1450.00", None)
    assert client.post("/api/exchanges/all").json() == {"linked": 1}
    assert client.get("/api/exchanges/candidates").json() == []
    kinds = client.get("/api/transactions").json()["items"]
    assert {t["kind"] for t in kinds} == {"fx"}
    assert client.delete(f"/api/transfers/{candidate['outgoing']['id']}").status_code == 204
    assert {t["kind"] for t in client.get("/api/transactions").json()["items"]} == {"fx"}
