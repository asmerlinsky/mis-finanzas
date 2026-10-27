"""Shared fixtures. Each test gets its own data dir and SQLite file; no network."""

from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from mis_finanzas.core.config import Settings
from mis_finanzas.main import create_app
from mis_finanzas.tools.render_sample import Page, TextOp, build_pdf


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        market_refresh_on_startup=False,
        public_hosts=["api.argentinadatos.com"],
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def session(app: FastAPI) -> Iterator[Session]:
    """A session on the same database the app uses."""
    with app.state.session_factory() as db_session:
        yield db_session


TextItem = tuple[float, float, str]


def make_pdf(items: Sequence[TextItem], width: int = 595, height: int = 842) -> bytes:
    """A one-page PDF with 10pt Helvetica text at `(x, y_from_bottom, text)`."""
    return build_pdf([Page(width, height, [TextOp(x, y, text) for x, y, text in items])])
