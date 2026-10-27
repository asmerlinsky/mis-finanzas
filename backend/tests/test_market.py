"""Outbound network guard, rate source parsing, daily refresh limits and rate lookup."""

import json
from datetime import date
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mis_finanzas.market.fx import RateTable, rate_status
from mis_finanzas.market.http import DisallowedHostError, PublicHttpClient
from mis_finanzas.market.models import FetchLog, FxRate, RateType
from mis_finanzas.market.refresh import refresh_rates
from mis_finanzas.market.sources import ArgentinaDatosMepSource

ALLOWED = ["api.argentinadatos.com"]
PAYLOAD = [
    {"casa": "bolsa", "compra": 1000.5, "venta": 1010.25, "fecha": "2026-03-02"},
    {"casa": "bolsa", "compra": 1001, "venta": 1011, "fecha": "2026-03-03"},
    {"casa": "bolsa", "fecha": "broken"},
]


class RecordingHandler:
    """Serves a fixed JSON payload and records every requested URL."""

    def __init__(self, payload: object, calls: list[str]) -> None:
        self.payload, self.calls = payload, calls

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(str(request.url))
        return httpx.Response(200, content=json.dumps(self.payload))


def _client(transport: httpx.MockTransport) -> PublicHttpClient:
    return PublicHttpClient(ALLOWED, timeout_seconds=1, transport=transport)


def _serving(payload: object, calls: list[str]) -> httpx.MockTransport:
    return httpx.MockTransport(RecordingHandler(payload, calls))


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/data",
        "http://api.argentinadatos.com/v1/x",  # plain HTTP
        "https://api.argentinadatos.com.evil.io/v1/x",
        "https://user@evil.io/?h=api.argentinadatos.com",
    ],
)
def test_client_refuses_anything_but_allowlisted_https(url: str) -> None:
    with pytest.raises(DisallowedHostError):
        _client(_serving([], [])).get_json(url)


def test_source_parses_and_skips_malformed_rows() -> None:
    quotes = ArgentinaDatosMepSource().fetch(_client(_serving(PAYLOAD, [])))
    assert [(q.date, q.buy, q.sell) for q in quotes] == [
        (date(2026, 3, 2), Decimal("1000.5"), Decimal("1010.25")),
        (date(2026, 3, 3), Decimal("1001"), Decimal("1011")),
    ]


def test_refresh_downloads_at_most_once_per_day(session: Session) -> None:
    calls: list[str] = []
    client = _client(_serving(PAYLOAD, calls))
    source = ArgentinaDatosMepSource()
    first = refresh_rates(session, client, source, RateType.MEP, date(2026, 3, 3))
    second = refresh_rates(session, client, source, RateType.MEP, date(2026, 3, 3))
    third = refresh_rates(session, client, source, RateType.MEP, date(2026, 3, 4))
    assert (first.status, first.rows) == ("ok", 2)
    assert second.status == "skipped"
    assert (third.status, third.rows) == ("ok", 0)
    assert len(calls) == 2
    assert session.scalar(select(func.count()).select_from(FxRate)) == 2


def test_failed_refresh_is_logged_and_retried(session: Session) -> None:
    failing = httpx.MockTransport(lambda request: httpx.Response(503))
    source = ArgentinaDatosMepSource()
    result = refresh_rates(session, _client(failing), source, RateType.MEP, date(2026, 3, 3))
    assert result.status == "failed"
    assert session.scalars(select(FetchLog.status)).all() == ["failed"]
    retry = refresh_rates(
        session, _client(_serving(PAYLOAD, [])), source, RateType.MEP, date(2026, 3, 3)
    )
    assert retry.status == "ok"


def test_rate_table_uses_closest_earlier_day() -> None:
    table = RateTable([(date(2026, 3, 6), Decimal("1000")), (date(2026, 3, 9), Decimal("1100"))])
    assert table.rate_on(date(2026, 3, 5)) is None
    assert table.rate_on(date(2026, 3, 8)) == Decimal("1000")  # Sunday -> Friday
    assert table.ars_to_usd(Decimal("2500"), date(2026, 3, 9)) == Decimal("2.27")


def test_rate_status_staleness(session: Session) -> None:
    assert rate_status(session, date(2026, 3, 10)).stale
    session.add(
        FxRate(
            rate_type=RateType.MEP,
            date=date(2026, 3, 6),
            buy=Decimal(1),
            sell=Decimal(1),
            source="test",
        )
    )
    session.commit()
    assert not rate_status(session, date(2026, 3, 9)).stale
    assert rate_status(session, date(2026, 3, 11)).stale
