"""Portfolio valuation from stored snapshots, operations and public prices. Invented values."""

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from balanz_fixtures import movements_pdf
from mis_finanzas.investments import store
from mis_finanzas.investments.records import (
    InstrumentRef,
    InvestmentData,
    ParsedCash,
    ParsedOperation,
    ParsedPosition,
    ParsedSnapshot,
    SnapshotSource,
)
from mis_finanzas.investments.valuation import PriceOrigin, power_of_ten, value_portfolio
from mis_finanzas.market.models import FxRate, InstrumentPrice, RateType

TODAY = date(2026, 10, 28)
STOCK = InstrumentRef("DOS", "ACCION DOS S.A.", asset_class="Acciones")
BOND = InstrumentRef("BON1", "BONO UNO", asset_class="Bonos")
FUND = InstrumentRef("FCI1", "FONDO UNO", asset_class="Fondos")


@pytest.mark.parametrize(
    ("ratio", "expected"),
    [("1.04", "1"), ("0.91", "1"), ("0.0098", "0.01"), ("0.0103", "0.01"), ("98", "100")],
)
def test_power_of_ten(ratio: str, expected: str) -> None:
    assert power_of_ten(Decimal(ratio)) == Decimal(expected)


def _holdings(day: date) -> InvestmentData:
    """A bond priced per 100 nominal: 1000 nominal at 80 per 100 are worth 800."""
    positions = [
        ParsedPosition(STOCK, Decimal(100), Decimal(1000), Decimal(100000), "ARS"),
        ParsedPosition(BOND, Decimal(1000), Decimal(80), Decimal(800), "ARS"),
        ParsedPosition(FUND, Decimal(10), Decimal(50), Decimal(500), "ARS"),
    ]
    cash = [ParsedCash("Pesos", "ARS", Decimal(1000)), ParsedCash("Dólares", "USD", Decimal(10))]
    return InvestmentData(
        "balanz", snapshot=ParsedSnapshot(day, SnapshotSource.HOLDINGS, positions, cash)
    )


def _seed(session: Session) -> None:
    store.store(session, None, _holdings(date(2026, 10, 20)))
    bought = ParsedOperation(1, STOCK, date(2026, 10, 22), None, "Compra / DOS", Decimal(10))
    store.store(session, None, InvestmentData("balanz", operations=[bought]))
    session.add_all(
        [
            InstrumentPrice(symbol="DOS", date=TODAY, price=Decimal(1100), panel="p", source="t"),
            InstrumentPrice(symbol="BON1", date=TODAY, price=Decimal(82), panel="p", source="t"),
            FxRate(
                rate_type=RateType.MEP,
                date=TODAY,
                buy=Decimal(990),
                sell=Decimal(1000),
                source="t",
            ),
        ]
    )
    session.commit()


def test_portfolio_values_positions_cash_and_bond_units(session: Session) -> None:
    _seed(session)
    portfolio = value_portfolio(session, TODAY)
    by_ticker = {p.ticker: p for p in portfolio.positions}
    stock, bond, fund = by_ticker["DOS"], by_ticker["BON1"], by_ticker["FCI1"]
    # 100 from the statement + 10 bought after it, at today's market price.
    assert (stock.quantity, stock.value_ars, stock.value_usd) == (
        Decimal(110),
        Decimal("121000.00"),
        Decimal("121.00"),
    )
    assert stock.price is not None and stock.price.origin is PriceOrigin.MARKET
    # The panel quotes per 100 nominal: the statement's value sets the factor to 0.01.
    assert bond.value_ars == Decimal("820.00")
    # No public price: the statement's own price, dated on the statement.
    assert fund.price is not None
    assert (fund.price.origin, fund.price.day, fund.value_ars) == (
        PriceOrigin.STATEMENT,
        date(2026, 10, 20),
        Decimal("500.00"),
    )
    assert [(c.label, c.value_ars) for c in portfolio.cash] == [
        ("Pesos", Decimal(1000)),
        ("Dólares", Decimal("10000.00")),
    ]
    assert portfolio.allocation == {
        "Acciones": Decimal("121000.00"),
        "Bonos": Decimal("820.00"),
        "Fondos": Decimal("500.00"),
        "Monedas": Decimal("11000.00"),
    }
    assert portfolio.total_ars == Decimal("133320.00")
    assert portfolio.total_usd == Decimal("133.32")
    assert (portfolio.quantities_as_of, portfolio.cash_as_of) == (
        date(2026, 10, 20),
        date(2026, 10, 20),
    )


def test_a_newer_movements_snapshot_sets_quantities(session: Session) -> None:
    _seed(session)
    closing = [ParsedPosition(STOCK, Decimal(50))]  # sold 60 after the holdings statement
    snapshot = ParsedSnapshot(date(2026, 10, 31), SnapshotSource.MOVEMENTS, closing)
    store.store(session, None, InvestmentData("balanz", snapshot=snapshot))
    session.commit()
    portfolio = value_portfolio(session, date(2026, 11, 2))
    assert [(p.ticker, p.quantity) for p in portfolio.positions] == [("DOS", Decimal(50))]
    assert portfolio.cash_as_of == date(2026, 10, 20)  # cash still from the holdings statement


def test_empty_portfolio(client: TestClient) -> None:
    body = client.get("/api/investments/portfolio").json()
    assert (body["total_ars"], body["positions"], body["quantities_as_of"]) == ("0", [], None)


def test_dividends_per_month_net_of_fees(client: TestClient, session: Session) -> None:
    for key, name, currency in (
        ("balanz/ARS", "Balanz pesos", "ARS"),
        ("balanz/CABLE/USD", "Balanz cable", "USD"),
    ):
        body = {"name": name, "institution": "Balanz", "kind": "broker", "currency": currency}
        account = client.post("/api/accounts", json=body).json()["id"]
        client.put(f"/api/source-accounts/{key}", json={"account_id": account})
    files = {"file": ("movimientos.pdf", movements_pdf(), "application/pdf")}
    assert client.post("/api/imports", files=files).status_code == 201
    session.add(
        FxRate(
            rate_type=RateType.MEP,
            date=date(2026, 3, 2),
            buy=Decimal(990),
            sell=Decimal(1000),
            source="t",
        )
    )
    session.commit()
    months = client.get("/api/investments/dividends?start=2026-01-01&end=2026-12-31").json()
    # USD 2.50 at 1000, minus ARS 1.50 of fees.
    assert months == [{"month": "2026-03", "ars": "2498.50", "usd": "2.50", "missing_rate": 0}]
