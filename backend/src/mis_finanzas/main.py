"""FastAPI app factory. The API lives under `/api`; the built frontend, if configured, at `/`."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session, sessionmaker

from mis_finanzas.api.routers import accounts, categories, imports, reports, transactions
from mis_finanzas.core.config import Settings, get_settings
from mis_finanzas.core.db import make_engine, make_session_factory
from mis_finanzas.core.logging import configure_logging
from mis_finanzas.core.migrate import upgrade_to_head
from mis_finanzas.importers.catalog import register_builtin_importers
from mis_finanzas.market.http import PublicHttpClient
from mis_finanzas.market.models import RateType
from mis_finanzas.market.refresh import refresh_rates
from mis_finanzas.market.sources import ArgentinaDatosMepSource

logger = logging.getLogger(__name__)

REFRESH_CHECK_SECONDS = 3600


def run_daily_refresh(settings: Settings, factory: sessionmaker[Session]) -> None:
    """One refresh attempt. Skips by itself when today's download already succeeded."""
    client = PublicHttpClient(settings.public_hosts, settings.http_timeout_seconds)
    try:
        with factory() as session:
            refresh_rates(session, client, ArgentinaDatosMepSource(), RateType.MEP, date.today())
    except Exception as exc:
        logger.error("Daily refresh crashed", extra={"error": str(exc)})
    finally:
        client.close()


async def refresh_loop(settings: Settings, factory: sessionmaker[Session]) -> None:
    """Hourly check; the fetch log keeps actual downloads to at most one per day."""
    while True:
        await asyncio.to_thread(run_daily_refresh, settings, factory)
        await asyncio.sleep(REFRESH_CHECK_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    task = None
    if settings.market_refresh_on_startup:
        task = asyncio.create_task(refresh_loop(settings, app.state.session_factory))
    yield
    if task is not None:
        task.cancel()


def create_app(settings: Settings | None = None) -> FastAPI:
    configure_logging()
    settings = settings or get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    upgrade_to_head(settings.database_url)
    register_builtin_importers()
    app = FastAPI(title="mis-finanzas", lifespan=lifespan)
    app.state.settings = settings
    app.state.session_factory = make_session_factory(make_engine(settings.database_url))
    for module in (accounts, categories, transactions, imports, reports):
        app.include_router(module.router, prefix="/api")
    if settings.frontend_dist is not None and settings.frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=settings.frontend_dist, html=True), name="frontend")
    return app
