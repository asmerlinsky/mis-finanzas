"""Seed a "Dividendos" income category with a rule for dividend lines.

Balanz prints `Dividendo en efectivo / <TICKER>`: the dividend in its currency section, and
its fees, negative, in `Pesos`. Both take this category, so the fees reduce dividend income
instead of counting as expenses. Only what's missing is inserted.

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CATEGORY = "Dividendos"
PATTERNS = ("DIVIDENDO",)


def upgrade() -> None:
    bind = op.get_bind()
    find = sa.text("SELECT id FROM categories WHERE name = :name")
    category_id = bind.execute(find, {"name": CATEGORY}).scalar()
    if category_id is None:
        bind.execute(
            sa.text("INSERT INTO categories (name, kind) VALUES (:name, 'income')"),
            {"name": CATEGORY},
        )
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
