"""Database engine and session handling. SQLite, one file under the data dir."""

import enum
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

from sqlalchemy import Dialect, Engine, Enum, String, TypeDecorator, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


class DecimalText(TypeDecorator[Decimal]):
    """Exact decimals stored as text; SQLite has no native decimal type."""

    impl = String(40)
    cache_ok = True

    def process_bind_param(self, value: Decimal | None, dialect: Dialect) -> str | None:
        return None if value is None else str(value)

    def process_result_value(self, value: str | None, dialect: Dialect) -> Decimal | None:
        return None if value is None else Decimal(value)


def str_enum(enum_class: type[enum.StrEnum]) -> Enum:
    """Store a `StrEnum` by value (`"bank"`), as a plain string column."""
    return Enum(
        enum_class,
        native_enum=False,
        length=20,
        values_callable=lambda members: [m.value for m in members],
    )


def _enable_sqlite_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def make_engine(database_url: str) -> Engine:
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    if database_url.startswith("sqlite"):
        event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Yield a session; roll back and re-raise on error."""
    session = factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
