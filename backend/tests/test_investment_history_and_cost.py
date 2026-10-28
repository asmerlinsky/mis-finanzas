"""Cost basis, gain, value over time and dividends per instrument. Invented values only."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from mis_finanzas.investments import store
from mis_finanzas.investments.cost_basis import (
    cost_basis,
    opening_quantity,
    trade_currency,
)
from mis_finanzas.investments.records import (
    InstrumentRef,
    InvestmentData,
    ParsedOperation,
    ParsedPosition,
    ParsedSnapshot,
    SnapshotSource,
)
from mis_finanzas.investments.valuation import PriceOrigin, value_history, value_portfolio
from mis_finanzas.ledger.models import (
    Account,
    AccountKind,
    Category,
    Currency,
    Transaction,
    TransactionKind,
)
from mis_finanzas.market.models import FxRate, InstrumentPrice, RateType


@dataclass(frozen=True)
class T:
    trade_date: date
    description: str
    quantity: Decimal
    net: Decimal | None = None
    gross: Decimal | None = None
    fees: Decimal = Decimal(0)


def _rate(_: date) -> Decimal | None:
    return Decimal(1000)


@pytest.mark.parametrize(
    ("description", "currency"),
    [
        ("Boleto / 123 / COMPRA / 2 / EJM / usd", "USD"),
        ("Boleto / 123 / COMPRA / 2 / EJM / $", "ARS"),
        ("Liquidación de Suscripción / 5 / FONDO A", None),
        ("Compra", None),
    ],
)
def test_trade_currency(description: str, currency: str | None) -> None:
    assert trade_currency(description) == currency


def test_average_cost_in_both_currencies_and_a_partial_sell() -> None:
    trades = [
        T(date(2026, 1, 5), "Boleto / 1 / COMPRA / 1 / EJM / usd", Decimal(10), net=Decimal(-100)),
        T(date(2026, 2, 5), "Boleto / 2 / COMPRA / 1 / EJM / $", Decimal(10), net=Decimal(-300000)),
        T(date(2026, 3, 5), "Boleto / 3 / VENTA / 1 / EJM / usd", Decimal(-5), net=Decimal(80)),
    ]
    basis = cost_basis(trades, Decimal(0), _rate)
    # 100 USD (100.000 ARS) + 300.000 ARS (300 USD) for 20; a quarter sold.
    assert (basis.known_quantity, basis.unknown_quantity) == (Decimal(15), Decimal(0))
    assert (basis.cost_ars, basis.cost_usd) == (Decimal(300000), Decimal(300))
    assert basis.coverage == Decimal(1)


def test_unknown_opening_lot_and_trades_without_currency_give_partial_coverage() -> None:
    trades = [
        T(date(2026, 2, 5), "Boleto / 2 / COMPRA / 1 / EJM / usd", Decimal(10), net=Decimal(-100)),
        T(date(2026, 2, 6), "Liquidación de Suscripción / 5 / FONDO A", Decimal(10), net=None),
    ]
    snapshots = [(date(2026, 2, 28), Decimal(50))]  # 50 held at month end: 30 before the trades
    opening = opening_quantity(snapshots, trades)
    assert opening == Decimal(30)
    basis = cost_basis(trades, opening, _rate)
    assert (basis.known_quantity, basis.unknown_quantity) == (Decimal(10), Decimal(40))
    assert basis.coverage == Decimal("0.2")


STOCK = InstrumentRef("DOS", "ACCION DOS S.A.", asset_class="Acciones")


def _holdings(day: date, quantity: int, value: int) -> InvestmentData:
    position = ParsedPosition(
        STOCK, Decimal(quantity), Decimal(value // quantity), Decimal(value), "ARS"
    )
    return InvestmentData(
        "balanz", snapshot=ParsedSnapshot(day, SnapshotSource.HOLDINGS, [position])
    )


def _seed(session: Session) -> None:
    store.store(session, None, _holdings(date(2026, 9, 30), 100, 100000))
    bought = ParsedOperation(
        1,
        STOCK,
        date(2026, 10, 2),
        None,
        "Boleto / 9 / COMPRA / 1 / DOS / $",
        Decimal(100),
        net=Decimal(-110000),
    )
    store.store(session, None, InvestmentData("balanz", operations=[bought]))
    store.store(session, None, _holdings(date(2026, 10, 20), 200, 240000))
    for day, price in ((date(2026, 10, 21), 1300), (date(2026, 10, 28), 1500)):
        session.add(
            InstrumentPrice(symbol="DOS", date=day, price=Decimal(price), panel="p", source="t")
        )
    session.add(
        FxRate(
            rate_type=RateType.MEP,
            date=date(2026, 9, 1),
            buy=Decimal(990),
            sell=Decimal(1000),
            source="t",
        )
    )
    session.commit()


def test_a_past_date_uses_only_what_was_known_then(session: Session) -> None:
    _seed(session)
    october_1 = value_portfolio(session, date(2026, 10, 1))
    assert [(p.ticker, p.quantity) for p in october_1.positions] == [("DOS", Decimal(100))]
    assert october_1.quantities_as_of == date(2026, 9, 30)
    assert value_portfolio(session, date(2026, 9, 1)).positions == []


def test_gain_on_the_part_with_known_cost(session: Session) -> None:
    _seed(session)
    [position] = value_portfolio(session, date(2026, 10, 28)).positions
    # 200 held: 100 bought for 110.000 (known), 100 from before (unknown).
    assert (position.coverage, position.cost_ars) == (Decimal("0.5"), Decimal("110000.00"))
    assert position.value_ars == Decimal("300000.00")  # 200 at 1.500
    assert position.gain_ars == Decimal("40000.00")  # 150.000 minus 110.000


def test_history_has_statement_dates_and_price_days(session: Session) -> None:
    _seed(session)
    points = [(p.day, p.total_ars, p.source) for p in value_history(session, date(2026, 10, 28))]
    assert points == [
        (date(2026, 9, 30), Decimal("100000.00"), PriceOrigin.STATEMENT),
        (date(2026, 10, 20), Decimal("240000.00"), PriceOrigin.STATEMENT),
        (date(2026, 10, 21), Decimal("260000.00"), PriceOrigin.MARKET),
        (date(2026, 10, 28), Decimal("300000.00"), PriceOrigin.MARKET),
    ]


def test_dividends_per_instrument_net_of_fees(client: TestClient, session: Session) -> None:
    pesos = Account(
        name="Broker pesos", institution="B", kind=AccountKind.BROKER, currency=Currency.ARS
    )
    session.add(pesos)
    session.flush()
    seeded = session.query(Category).filter_by(name="Dividendos").one()
    store.store(
        session,
        None,
        InvestmentData(
            "balanz",
            snapshot=ParsedSnapshot(
                date(2026, 3, 1),
                SnapshotSource.HOLDINGS,
                [ParsedPosition(InstrumentRef("EJM", "CEDEAR EJEMPLO"), Decimal(1))],
            ),
        ),
    )
    rows = [
        ("DIVIDENDO EN EFECTIVO / EJM", 250000),
        ("DIVIDENDO EN EFECTIVO / EJM", -15000),  # its fees
        ("DIVIDENDO EN EFECTIVO / DOS", 50000),
        ("DIVIDENDO SIN TICKER", 1000),
    ]
    for i, (text, cents) in enumerate(rows):
        session.add(
            Transaction(
                account_id=pesos.id,
                date=date(2026, 3, 10),
                amount_cents=cents,
                description_raw=text,
                description_norm=text,
                kind=TransactionKind.INCOME,
                category_id=seeded.id,
                fingerprint=f"d{i}",
            )
        )
    session.commit()
    found = client.get(
        "/api/investments/dividends/by-instrument",
        params={"start": "2026-01-01", "end": "2026-12-31"},
    ).json()
    assert [(d["ticker"], d["name"], d["ars"], d["payments"]) for d in found] == [
        ("EJM", "CEDEAR EJEMPLO", "2350.00", 1),
        ("DOS", None, "500.00", 1),
        ("Otros", None, "10.00", 1),
    ]
