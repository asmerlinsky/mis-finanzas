"""Invoices: where each came from (export or PDF), and the movement that paid it.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-28 15:09:39.222801

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0012'
down_revision: Union[str, Sequence[str], None] = '0011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


UNIQUE = "uq_invoices_payment_transaction_id"
FOREIGN_KEY = "fk_invoices_payment_transaction_id"


def upgrade() -> None:
    with op.batch_alter_table("invoices", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("source", sa.String(length=10), server_default="export", nullable=False)
        )
        batch_op.add_column(sa.Column("payment_transaction_id", sa.Integer(), nullable=True))
        batch_op.create_unique_constraint(UNIQUE, ["payment_transaction_id"])
        batch_op.create_foreign_key(
            FOREIGN_KEY, "transactions", ["payment_transaction_id"], ["id"], ondelete="SET NULL"
        )


def downgrade() -> None:
    with op.batch_alter_table("invoices", schema=None) as batch_op:
        batch_op.drop_constraint(FOREIGN_KEY, type_="foreignkey")
        batch_op.drop_constraint(UNIQUE, type_="unique")
        batch_op.drop_column("payment_transaction_id")
        batch_op.drop_column("source")
