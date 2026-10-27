"""Apply category rules to transactions already in the ledger."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from mis_finanzas.ledger.models import Category, CategoryRule, Transaction
from mis_finanzas.ledger.rules import first_matching_rule, infer_kind


def apply_rules_to_uncategorized(session: Session) -> int:
    """Categorize rows that have no category and aren't transfers. Returns rows changed."""
    rules = list(session.scalars(select(CategoryRule)))
    if not rules:
        return 0
    categories = {c.id: c for c in session.scalars(select(Category))}
    query = select(Transaction).where(
        Transaction.category_id.is_(None), Transaction.transfer_pair_id.is_(None)
    )
    changed = 0
    for tx in session.scalars(query):
        rule = first_matching_rule(rules, tx.description_norm, tx.account_id, tx.amount_cents)
        if rule is None:
            continue
        set_category(tx, categories.get(rule.category_id))
        changed += 1
    session.commit()
    return changed


def set_category(tx: Transaction, category: Category | None) -> None:
    """Assign a category and re-derive the kind. Transfer-linked rows keep kind `transfer`."""
    tx.category_id = category.id if category else None
    tx.category = category
    if tx.transfer_pair_id is None:
        tx.kind = infer_kind(tx.amount_cents, category)
