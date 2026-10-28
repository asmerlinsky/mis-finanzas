"""Seed a "Rendimientos" income category with rules for interest lines.

Mercado Pago prints account interest as `Rendimientos`; Santander as `Pago interes por saldo
en cuenta`. Only what's missing is inserted, so an existing category or rule is left as is.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CATEGORY = "Rendimientos"
PATTERNS = ("RENDIMIENTOS", "INTERES POR SALDO")


def upgrade() -> None:
    bind = op.get_bind()
    find = sa.text("SELECT id FROM categories WHERE name = :name")
    category_id = bind.execute(find, {"name": CATEGORY}).scalar()
    if category_id is None:
        bind.execute(sa.text("INSERT INTO categories (name, kind) VALUES (:name, 'income')"),
                     {"name": CATEGORY})
        category_id = bind.execute(find, {"name": CATEGORY}).scalar()
    for pattern in PATTERNS:
        exists = bind.execute(
            sa.text("SELECT 1 FROM category_rules WHERE category_id = :c AND pattern = :p"),
            {"c": category_id, "p": pattern},
        ).first()
        if exists is None:
            bind.execute(
                sa.text(
                    "INSERT INTO category_rules (category_id, pattern, match_type, account_id, "
                    "sign, priority) VALUES (:c, :p, 'contains', NULL, 'any', 100)"
                ),
                {"c": category_id, "p": pattern},
            )


def downgrade() -> None:
    """Seeded rows may have been edited or used since, so they are left in place."""
