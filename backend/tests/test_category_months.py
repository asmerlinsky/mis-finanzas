"""Expenses per category and month, and the movements behind each cell. Invented values."""

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from mis_finanzas.ledger.models import (
    Account,
    AccountKind,
    Category,
    Currency,
    Transaction,
    TransactionKind,
)
from mis_finanzas.market.models import FxRate, RateType


def _seed(session: Session) -> dict[str, int]:
    bank = Account(name="Banco", institution="B", kind=AccountKind.BANK, currency=Currency.ARS)
    food, home = Category(name="Comida"), Category(name="Hogar")
    session.add_all([bank, food, home])
    session.add(
        FxRate(
            rate_type=RateType.MEP,
            date=date(2026, 1, 1),
            buy=Decimal(990),
            sell=Decimal(1000),
            source="t",
        )
    )
    session.flush()
    rows = [
        (date(2026, 1, 5), -10000, food, TransactionKind.EXPENSE),
        (date(2026, 1, 20), -5000, food, TransactionKind.EXPENSE),
        (date(2026, 2, 3), -30000, food, TransactionKind.EXPENSE),
        (date(2026, 2, 4), 2000, food, TransactionKind.EXPENSE),  # a refund: reduces February
        (date(2026, 2, 10), -100000, home, TransactionKind.EXPENSE),
        (date(2026, 2, 11), -700, None, TransactionKind.EXPENSE),
        (date(2026, 2, 12), 500000, None, TransactionKind.INCOME),  # income: not an expense
    ]
    for i, (day, cents, category, kind) in enumerate(rows):
        session.add(
            Transaction(
                account_id=bank.id,
                date=day,
                amount_cents=cents,
                description_raw=f"m{i}",
                description_norm=f"M{i}",
                kind=kind,
                category_id=category.id if category else None,
                fingerprint=f"f{i}",
            )
        )
    session.commit()
    return {"food": food.id, "home": home.id}


def test_expenses_per_category_and_month(client: TestClient, session: Session) -> None:
    _seed(session)
    params = {"start": "2026-01-01", "end": "2026-02-28"}
    found = client.get("/api/reports/categories/monthly", params=params).json()
    summary = [
        (c["category"], [(m["month"], m["ars"]) for m in c["months"]], c["total_ars"])
        for c in found
    ]
    assert summary == [
        ("Hogar", [("2026-02", "1000.00")], "1000.00"),  # largest first
        ("Comida", [("2026-01", "150.00"), ("2026-02", "280.00")], "430.00"),
        ("Sin categoría", [("2026-02", "7.00")], "7.00"),
    ]
    assert found[1]["months"][1]["usd"] == "0.28"
    assert found[2]["category_id"] is None


def test_a_cell_lists_the_movements_it_sums(client: TestClient, session: Session) -> None:
    ids = _seed(session)
    february = {"start": "2026-02-01", "end": "2026-02-28", "kind": "expense"}
    food = client.get("/api/transactions", params={**february, "category_id": ids["food"]}).json()
    assert sorted(t["amount"] for t in food["items"]) == ["-300.00", "20.00"]  # 280 net
    none = client.get("/api/transactions", params={**february, "uncategorized": True}).json()
    assert [t["amount"] for t in none["items"]] == ["-7.00"]
