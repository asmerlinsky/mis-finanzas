"""Seed an "Inversiones" category (kind `investment`) for the cash side of broker trades.

Balanz prints a trade's cash movement as `Boleto / <n> / COMPRA / …` (or `VENTA`) and a fund
subscription as `Liquidación de Suscripción / …`. Money moving into or out of an investment is
neither income nor expense, so these rows don't count in totals. The rules are anchored
regexes, so a bank line that merely mentions a purchase doesn't match. Only what's missing is
inserted.

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CATEGORY = "Inversiones"
PATTERNS = (
    r"^BOLETO / \d+ / (COMPRA|VENTA) /",
    r"^LIQUIDACION DE (SUSCRIPCION|RESCATE) /",
)


def upgrade() -> None:
    bind = op.get_bind()
    find = sa.text("SELECT id FROM categories WHERE name = :name")
    category_id = bind.execute(find, {"name": CATEGORY}).scalar()
    if category_id is None:
        bind.execute(
            sa.text("INSERT INTO categories (name, kind) VALUES (:name, 'investment')"),
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
                    "sign, priority) VALUES (:c, :p, 'regex', NULL, 'any', 100)"
                ),
                {"c": category_id, "p": pattern},
            )


def downgrade() -> None:
    """Seeded rows may have been edited or used since, so they are left in place."""
