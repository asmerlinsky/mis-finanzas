"""The 6-month monotributo projection, and when to ask about the projected amount."""

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from arca_fixtures import comprobantes_csv, invoice_row
from mis_finanzas.monotributo import service
from mis_finanzas.monotributo.categories import Category, CategoryTable
from mis_finanzas.monotributo.status import project

TABLE = CategoryTable(
    date(2026, 8, 1),
    (Category("A", Decimal(1000), Decimal(1)), Category("B", Decimal(2000), Decimal(2))),
)


def test_projection_months_rolling_totals_and_first_month_over() -> None:
    invoices = [
        (date(2026, 5, 15), Decimal(300)),
        (date(2026, 10, 5), Decimal(50)),  # this month: only the rest up to 100 is projected
    ]
    projected = project(invoices, TABLE, "A", date(2026, 10, 28), Decimal(200))
    assert [(m.month, m.invoiced, m.rolling) for m in projected.months] == [
        ("2026-10", Decimal(200), Decimal(500)),
        ("2026-11", Decimal(200), Decimal(700)),
        ("2026-12", Decimal(200), Decimal(900)),
        ("2027-01", Decimal(200), Decimal(1100)),
        ("2027-02", Decimal(200), Decimal(1300)),
        ("2027-03", Decimal(200), Decimal(1500)),
    ]
    assert [m.level for m in projected.months][:4] == [None, None, Decimal("0.9"), Decimal(1)]
    assert projected.first_over == "2027-01"
    # The February recategorization looks at 2026: May, October to December, projected.
    assert projected.recategorization_income == Decimal(900)
    assert projected.implied is not None and projected.implied.letter == "A"


def _seed(client: TestClient) -> None:
    rows = [
        invoice_row("2026-08-10", 19, 7, "3000,00", rate="900,00"),
        invoice_row("2026-09-10", 19, 8, "3000,00", rate="1000,00"),
    ]
    files = {"file": ("c.csv", comprobantes_csv(rows), "text/csv")}
    assert client.post("/api/imports", files=files).status_code == 201


def test_projection_follows_last_month_in_the_latest_currency(
    client: TestClient, session: Session
) -> None:
    _seed(client)
    basis = service.projection_basis(session, date(2026, 10, 28))
    assert (basis.amount, basis.currency, basis.rate, basis.manual, basis.ask) == (
        Decimal("3000.00"),
        "USD",
        Decimal("1000.00"),  # the latest invoice's rate
        False,
        False,
    )
    assert basis.monthly_ars == Decimal("3000000.0000")


def test_owner_amount_is_asked_about_once_when_a_month_differs(
    client: TestClient, session: Session
) -> None:
    _seed(client)
    service.set_projection(session, Decimal(3500), "USD", date(2026, 10, 28))
    october = service.projection_basis(session, date(2026, 10, 28))
    assert (october.amount, october.manual, october.ask) == (Decimal(3500), True, False)
    # November: October had no invoice, which differs from 3500: ask.
    november = service.projection_basis(session, date(2026, 11, 5))
    assert (november.last_month, november.last_month_amount, november.ask) == (
        "2026-10",
        Decimal(0),
        True,
    )
    service.set_projection(session, Decimal(3500), "USD", date(2026, 11, 5))  # "Mantener"
    assert service.projection_basis(session, date(2026, 11, 5)).ask is False
    service.set_projection(session, Decimal(0), "USD", date(2026, 11, 5))
    assert service.projection_basis(session, date(2026, 11, 5)).amount == Decimal(0)
    service.clear_projection(session)
    assert service.projection_basis(session, date(2026, 11, 5)).manual is False


def test_projection_api(client: TestClient) -> None:
    _seed(client)
    assert (
        client.put(
            "/api/monotributo/projection", json={"amount": "-1", "currency": "USD"}
        ).status_code
        == 422
    )
    assert (
        client.put(
            "/api/monotributo/projection", json={"amount": "3500", "currency": "USD"}
        ).status_code
        == 204
    )
    body = client.get("/api/monotributo/status").json()["projection"]
    assert (body["amount"], body["currency"], body["manual"]) == ("3500", "USD", True)
    assert len(body["months"]) == 6
    assert client.delete("/api/monotributo/projection").status_code == 204
    assert client.get("/api/monotributo/status").json()["projection"]["manual"] is False
