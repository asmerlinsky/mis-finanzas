"""Seed "Cambio de moneda" (kind `fx`) for the bank's dollar sales and purchases.

Santander settles a sale of dollars through bonds as two movements on the same day:
`Liquidacion titulos debito` (dollars out of the dollar account) and `Liquidacion titulos
publicos credi` (pesos into the peso account). Counted by sign, they were an expense and an
income. With this category they are an exchange, which counts as neither. The rules catch
future imports; movements already imported with no category get it now.

Revision ID: 0014
Revises: 0013
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | Sequence[str] | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CATEGORY = "Cambio de moneda"
PATTERNS = ("LIQUIDACION TITULOS DEBITO", "LIQUIDACION TITULOS PUBLICOS CREDI")


def _category_id(bind: sa.Connection) -> int:
    find = sa.text("SELECT id FROM categories WHERE name = :name")
    found = bind.execute(find, {"name": CATEGORY}).scalar()
    if found is None:
        bind.execute(
            sa.text("INSERT INTO categories (name, kind) VALUES (:name, 'fx')"), {"name": CATEGORY}
        )
        found = bind.execute(find, {"name": CATEGORY}).scalar()
    return int(found)


def upgrade() -> None:
    bind = op.get_bind()
    category_id = _category_id(bind)
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
        bind.execute(
            sa.text(
                "UPDATE transactions SET category_id = :c, kind = 'fx' WHERE category_id IS NULL "
                "AND transfer_pair_id IS NULL AND description_norm LIKE :p"
            ),
            {"c": category_id, "p": f"%{pattern}%"},
        )


def downgrade() -> None:
    """Seeded rows and categorized movements may have been edited since: left in place."""
