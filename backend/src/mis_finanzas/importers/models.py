"""Saved column mappings, one per export source (e.g. "Santander CA pesos")."""

from typing import Any

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from mis_finanzas.core.db import Base


class ImportMapping(Base):
    __tablename__ = "import_mappings"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    # A serialized `TabularMapping`.
    config: Mapped[dict[str, Any]] = mapped_column(JSON)
