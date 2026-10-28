"""Rule suggestions from the owner's uncategorized movements, ranked by how much they cover.

Candidates are income and expense movements with no category that aren't paired transfers.
They group by merchant (`ledger/suggestions.py`) and by sign, so refunds stay apart from
charges. For each group's pattern, `would_categorize` and `conflicts` come from the real rule
matcher, so they are what creating that rule will do.
"""

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from mis_finanzas.ledger.models import (
    AmountSign,
    CategoryRule,
    MatchType,
    Transaction,
    TransactionKind,
)
from mis_finanzas.ledger.rules import rule_matches
from mis_finanzas.ledger.suggestions import Group, group, pattern_for
from mis_finanzas.market.fx import RateTable, load_rate_table
from mis_finanzas.reports.summary import to_dual

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 30
_COUNTED = (TransactionKind.INCOME, TransactionKind.EXPENSE)


@dataclass(frozen=True)
class RulePreview:
    would_categorize: int  # uncategorized movements the rule would catch
    conflicts: int  # movements already in a category that it also matches


@dataclass(frozen=True)
class RuleSuggestion:
    pattern: str
    example: str
    sign: AmountSign  # DEBIT (money out) or CREDIT (money in)
    count: int
    first_date: date
    last_date: date
    accounts: list[str]
    total_ars: Decimal
    missing_rate: int
    preview: RulePreview


def _is_candidate(tx: Transaction) -> bool:
    return tx.category_id is None and tx.transfer_pair_id is None and tx.kind in _COUNTED


def _sign(tx: Transaction) -> AmountSign:
    return AmountSign.DEBIT if tx.amount_cents < 0 else AmountSign.CREDIT


def _preview(
    movements: list[Transaction], pattern: str, match_type: MatchType, sign: AmountSign
) -> RulePreview:
    rule = CategoryRule(pattern=pattern, match_type=match_type, account_id=None, sign=sign)
    matching = [
        tx
        for tx in movements
        if tx.transfer_pair_id is None
        and rule_matches(rule, tx.description_norm, tx.account_id, tx.amount_cents)
    ]
    return RulePreview(
        would_categorize=sum(_is_candidate(tx) for tx in matching),
        conflicts=sum(tx.category_id is not None for tx in matching),
    )


def _movements(session: Session) -> list[Transaction]:
    return list(session.scalars(select(Transaction).order_by(Transaction.date)))


def _suggestion(
    found: Group[Transaction, AmountSign], movements: list[Transaction], rates: RateTable
) -> RuleSuggestion:
    items = found.items
    pattern = pattern_for([tx.description_norm for tx in items], found.key)
    amounts = [to_dual(tx, rates).ars for tx in items]
    return RuleSuggestion(
        pattern=pattern,
        example=items[-1].description_raw,
        sign=found.extra,
        count=len(items),
        first_date=items[0].date,
        last_date=items[-1].date,
        accounts=sorted({tx.account.name for tx in items}),
        total_ars=sum((a for a in amounts if a is not None), Decimal(0)),
        missing_rate=sum(a is None for a in amounts),
        preview=_preview(movements, pattern, MatchType.CONTAINS, found.extra),
    )


def suggest_rules(session: Session, limit: int = DEFAULT_LIMIT) -> list[RuleSuggestion]:
    """The groups covering the most money, largest first (by absolute total in pesos)."""
    movements = _movements(session)
    candidates = [(tx.description_norm, _sign(tx), tx) for tx in movements if _is_candidate(tx)]
    rates = load_rate_table(session)
    suggestions = [_suggestion(found, movements, rates) for found in group(candidates)]
    suggestions.sort(key=lambda s: (-abs(s.total_ars), -s.count, s.pattern))
    logger.info(
        "Rule suggestions built",
        extra={"candidates": len(candidates), "groups": len(suggestions)},
    )
    return suggestions[:limit]


def preview_rule(
    session: Session, pattern: str, match_type: MatchType, sign: AmountSign
) -> RulePreview:
    return _preview(_movements(session), pattern, match_type, sign)
