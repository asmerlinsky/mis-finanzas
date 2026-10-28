"""Rule suggestions: merchant keys, patterns, grouping, ranking and the rule they lead to.
Invented descriptions only."""

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from mis_finanzas.ledger.models import (
    Account,
    AccountKind,
    AmountSign,
    Category,
    Currency,
    Transaction,
    TransactionKind,
)
from mis_finanzas.ledger.suggestions import merchant_key, pattern_for
from mis_finanzas.market.models import FxRate, RateType
from mis_finanzas.reports.rule_suggestions import suggest_rules


@pytest.mark.parametrize(
    ("description", "key", "pattern"),
    [
        ("PAYU/AR/UBER", "PAYU AR UBER", "PAYU/AR/UBER"),
        ("DROPBOX/1YYYHRLQ MECYNGY8", "DROPBOX", "DROPBOX"),
        (
            "MERPAGO*FERRETERIA EJEMPLO 2",
            "MERPAGO FERRETERIA EJEMPLO",
            "MERPAGO*FERRETERIA EJEMPLO",
        ),
        (
            "COMPRA CON TARJETA DE DEBITO KIOSCO EJEMPLO - TARJ NRO. 1234",
            "KIOSCO EJEMPLO",
            "KIOSCO EJEMPLO",
        ),
        # A word with digits between key words ends the pattern: it changes every time.
        ("STOCK 182 GENERAL PAZ (13/33)", "STOCK GENERAL PAZ", "STOCK"),
        ("TRANSFERENCIA NO GRAVADA A JUANA PEREZ", "JUANA PEREZ", "JUANA PEREZ"),
        ("TRANSFERENCIA RECIBIDA DE JUANA PEREZ", "JUANA PEREZ", "JUANA PEREZ"),
    ],
)
def test_merchant_key_and_pattern(description: str, key: str, pattern: str) -> None:
    assert merchant_key(description) == key
    assert pattern_for([description], key) == pattern


def test_nothing_but_codes_has_no_key() -> None:
    assert merchant_key("1234 5678 X") is None


def test_pattern_is_the_most_frequent_form() -> None:
    printed = ["MERPAGO*TIENDA EJEMPLO", "MERPAGO/TIENDA EJEMPLO", "MERPAGO/TIENDA EJEMPLO"]
    assert pattern_for(printed, "MERPAGO TIENDA EJEMPLO") == "MERPAGO/TIENDA EJEMPLO"


def _account(session: Session, name: str, currency: Currency) -> Account:
    account = Account(name=name, institution="Banco", kind=AccountKind.BANK, currency=currency)
    session.add(account)
    session.flush()
    return account


def _tx(
    session: Session,
    account: Account,
    day: int,
    cents: int,
    description: str,
    **extra: object,
) -> Transaction:
    kind = TransactionKind.INCOME if cents > 0 else TransactionKind.EXPENSE
    tx = Transaction(
        account_id=account.id,
        date=date(2026, 3, day),
        amount_cents=cents,
        description_raw=description.title(),
        description_norm=description,
        kind=extra.pop("kind", kind),
        fingerprint=f"{account.id}-{day}-{cents}-{description}",
        **extra,
    )
    session.add(tx)
    session.flush()
    return tx


def _seed(session: Session) -> None:
    bank, card = (
        _account(session, "Banco pesos", Currency.ARS),
        _account(session, "Tarjeta", Currency.USD),
    )
    session.add(
        FxRate(
            rate_type=RateType.MEP,
            date=date(2026, 3, 1),
            buy=Decimal(990),
            sell=Decimal(1000),
            source="t",
        )
    )
    for day, cents in ((2, -10000), (3, -20000), (4, -30000)):
        _tx(session, bank, day, cents, "PAYU/AR/UBER")
    _tx(session, bank, 5, 5000, "PAYU/AR/UBER")  # a refund: its own group
    _tx(session, card, 6, -1000, "DROPBOX/AB12CD34 XY9")  # USD 10 at 1000
    _tx(session, card, 7, -1000, "DROPBOX/ZZ99YY88 QW1")
    _tx(session, bank, 8, -10000, "SUPER EJEMPLO SA")
    groceries = Category(name="Almacén")
    session.add(groceries)
    session.flush()
    _tx(session, bank, 9, -50000, "SUPER EJEMPLO SA SUCURSAL", category_id=groceries.id)
    _tx(session, bank, 10, -40000, "COMPRA DIVISAS", kind=TransactionKind.FX)
    first = _tx(session, bank, 11, -70000, "TRANSFERENCIA A CUENTA PROPIA")
    second = _tx(session, card, 11, 70, "SU PAGO EN USD")
    first.transfer_pair_id, second.transfer_pair_id = second.id, first.id
    first.kind = second.kind = TransactionKind.TRANSFER
    session.commit()


def test_suggestions_rank_by_pesos_and_skip_what_is_settled(session: Session) -> None:
    _seed(session)
    found = [(s.pattern, s.sign, s.count, s.total_ars) for s in suggest_rules(session)]
    assert found == [
        ("DROPBOX", AmountSign.DEBIT, 2, Decimal("-20000.00")),  # dollars, at MEP
        ("PAYU/AR/UBER", AmountSign.DEBIT, 3, Decimal("-600.00")),
        ("SUPER EJEMPLO SA", AmountSign.DEBIT, 1, Decimal("-100.00")),
        ("PAYU/AR/UBER", AmountSign.CREDIT, 1, Decimal("50.00")),
    ]  # categorized, fx and transfer movements are not suggested


def test_suggestions_say_what_the_rule_would_do(session: Session) -> None:
    _seed(session)
    by_pattern = {(s.pattern, s.sign): s for s in suggest_rules(session)}
    uber = by_pattern[("PAYU/AR/UBER", AmountSign.DEBIT)]
    assert (uber.preview.would_categorize, uber.preview.conflicts) == (3, 0)
    assert (uber.first_date, uber.last_date, uber.accounts) == (
        date(2026, 3, 2),
        date(2026, 3, 4),
        ["Banco pesos"],
    )
    super_ = by_pattern[("SUPER EJEMPLO SA", AmountSign.DEBIT)]
    assert (super_.preview.would_categorize, super_.preview.conflicts) == (1, 1)


def test_api_suggest_preview_and_create(client: TestClient, session: Session) -> None:
    _seed(session)
    suggestions = client.get("/api/rules/suggestions").json()
    assert suggestions[1]["pattern"] == "PAYU/AR/UBER" and suggestions[1]["sign"] == "debit"
    preview = client.get("/api/rules/preview", params={"pattern": "UBER", "sign": "debit"})
    assert preview.json() == {"would_categorize": 3, "conflicts": 0}
    bad = client.get("/api/rules/preview", params={"pattern": "(", "match_type": "regex"})
    assert bad.status_code == 422
    transport = session.scalar(select(Category).where(Category.name == "Transporte"))
    assert transport is not None  # a starter category
    rule = {"category_id": transport.id, "pattern": "PAYU/AR/UBER", "sign": "debit"}
    assert client.post("/api/rules", json=rule).status_code == 201
    assert client.post("/api/rules/apply").json() == {"categorized": 3}
    left = [(s["pattern"], s["sign"]) for s in client.get("/api/rules/suggestions").json()]
    assert ("PAYU/AR/UBER", "debit") not in left and ("PAYU/AR/UBER", "credit") in left
