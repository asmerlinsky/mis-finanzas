"""Seed starter categories, names only: somewhere to put the first rule suggestions.

No patterns: those come from the owner's own movements, through the rule suggestions on the
Categorías page. Only missing names are inserted, so a category the owner already has is left
as is.

Revision ID: 0011
Revises: 0010
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NAMES = (
    "Supermercado",
    "Transporte",
    "Servicios",
    "Salud",
    "Suscripciones",
    "Impuestos y comisiones",
    "Monotributo",
)


def upgrade() -> None:
    bind = op.get_bind()
    for name in NAMES:
        exists = bind.execute(
            sa.text("SELECT 1 FROM categories WHERE name = :name"), {"name": name}
        ).first()
        if exists is None:
            bind.execute(
                sa.text("INSERT INTO categories (name, kind) VALUES (:name, NULL)"), {"name": name}
            )


def downgrade() -> None:
    """Seeded rows may have been used since, so they are left in place."""
