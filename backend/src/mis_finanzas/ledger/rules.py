"""Rule-based categorization: the first matching rule, by priority, assigns the category."""

import re
from collections.abc import Iterable

from mis_finanzas.ledger.models import (
    AmountSign,
    Category,
    CategoryRule,
    MatchType,
    TransactionKind,
)


def rule_matches(
    rule: CategoryRule, description_norm: str, account_id: int, amount_cents: int
) -> bool:
    if rule.account_id is not None and rule.account_id != account_id:
        return False
    if rule.sign is AmountSign.DEBIT and amount_cents >= 0:
        return False
    if rule.sign is AmountSign.CREDIT and amount_cents <= 0:
        return False
    if rule.match_type is MatchType.REGEX:
        return re.search(rule.pattern, description_norm, re.IGNORECASE) is not None
    return rule.pattern.upper() in description_norm


def first_matching_rule(
    rules: Iterable[CategoryRule], description_norm: str, account_id: int, amount_cents: int
) -> CategoryRule | None:
    """Rules are tried by ascending priority, then by id (older rules first)."""
    ordered = sorted(rules, key=lambda r: (r.priority, r.id or 0))
    for rule in ordered:
        if rule_matches(rule, description_norm, account_id, amount_cents):
            return rule
    return None


def infer_kind(amount_cents: int, category: Category | None) -> TransactionKind:
    """A category with a kind wins; otherwise money in is income and money out is expense."""
    if category is not None and category.kind is not None:
        return category.kind
    return TransactionKind.INCOME if amount_cents > 0 else TransactionKind.EXPENSE


def validate_pattern(pattern: str, match_type: MatchType) -> None:
    """Raise `ValueError` for an empty pattern or an invalid regex."""
    if not pattern.strip():
        raise ValueError("pattern must not be empty")
    if match_type is MatchType.REGEX:
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueError(f"invalid regex: {exc}") from exc
