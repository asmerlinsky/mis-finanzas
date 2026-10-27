"""Import configuration: saved column mappings and which account each statement target feeds."""

from typing import Any

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from mis_finanzas.core.db import Base


class ImportMapping(Base):
    """A generic CSV/Excel source (e.g. "Santander CA pesos"); its rows go to one account."""

    __tablename__ = "import_mappings"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    # A serialized `TabularMapping`.
    config: Mapped[dict[str, Any]] = mapped_column(JSON)


class SourceAccount(Base):
    """A dedicated importer's target (`santander/CA/ARS`, `visa/USD`) mapped to an account.

    Mapped once, it applies to every later statement with that target, from any importer.
    """

    __tablename__ = "source_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
