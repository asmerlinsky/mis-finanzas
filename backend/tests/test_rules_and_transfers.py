from datetime import date

import pytest

from mis_finanzas.ledger.models import (
    Account,
    AccountKind,
    AmountSign,
    Category,
    CategoryRule,
    Currency,
    MatchType,
    Transaction,
    TransactionKind,
)
from mis_finanzas.ledger.rules import first_matching_rule, infer_kind, validate_pattern
from mis_finanzas.ledger.transfers import find_transfer_candidates, link_transfer, unlink_transfer


def _rule(rule_id: int, pattern: str, **kwargs: object) -> CategoryRule:
    fields: dict[str, object] = {
        "category_id": rule_id,
        "match_type": MatchType.CONTAINS,
        "sign": AmountSign.ANY,
        "priority": 100,
        "account_id": None,
    }
    fields.update(kwargs)
    return CategoryRule(id=rule_id, pattern=pattern, **fields)


def test_first_rule_by_priority_wins() -> None:
    rules = [_rule(1, "RAPPI"), _rule(2, "RAPPI PRIME", priority=10)]
    match = first_matching_rule(rules, "RAPPI PRIME SUSCRIPCION", account_id=1, amount_cents=-1)
    assert match is not None and match.id == 2


def test_rule_contains_is_case_insensitive() -> None:
    match = first_matching_rule([_rule(1, "rappi")], "PAGO RAPPI", 1, -100)
    assert match is not None


@pytest.mark.parametrize(
    ("sign", "amount", "matches"),
    [
        (AmountSign.DEBIT, -100, True),
        (AmountSign.DEBIT, 100, False),
        (AmountSign.CREDIT, 100, True),
        (AmountSign.CREDIT, -100, False),
    ],
)
def test_rule_sign_filter(sign: AmountSign, amount: int, matches: bool) -> None:
    rule = _rule(1, "TRANSFERENCIA", sign=sign)
    assert (first_matching_rule([rule], "TRANSFERENCIA", 1, amount) is not None) is matches


def test_rule_account_filter_and_regex() -> None:
    rule = _rule(1, r"^SUELDO \d+", match_type=MatchType.REGEX, account_id=7)
    assert first_matching_rule([rule], "SUELDO 202601", 7, 100) is not None
    assert first_matching_rule([rule], "SUELDO 202601", 8, 100) is None
    assert first_matching_rule([rule], "PAGO SUELDO 202601", 7, 100) is None


def test_infer_kind() -> None:
    assert infer_kind(100, None) is TransactionKind.INCOME
    assert infer_kind(-100, None) is TransactionKind.EXPENSE
    fx = Category(id=1, name="Compra MEP", kind=TransactionKind.FX)
    assert infer_kind(-100, fx) is TransactionKind.FX


@pytest.mark.parametrize(
    ("pattern", "match_type"),
    [
        ("  ", MatchType.CONTAINS),
        ("(unclosed", MatchType.REGEX),
    ],
)
def test_validate_pattern_rejects(pattern: str, match_type: MatchType) -> None:
    with pytest.raises(ValueError):
        validate_pattern(pattern, match_type)


def _account(account_id: int, currency: Currency = Currency.ARS) -> Account:
    return Account(
        id=account_id,
        name=f"a{account_id}",
        institution="x",
        kind=AccountKind.BANK,
        currency=currency,
    )


def _tx(tx_id: int, account: Account, day: int, cents: int) -> Transaction:
    kind = TransactionKind.INCOME if cents > 0 else TransactionKind.EXPENSE
    return Transaction(
        id=tx_id,
        account=account,
        account_id=account.id,
        date=date(2026, 3, day),
        amount_cents=cents,
        kind=kind,
        transfer_pair_id=None,
        description_raw="",
        description_norm="",
        fingerprint=str(tx_id),
    )


def test_transfer_candidates_pair_closest_opposite_amounts() -> None:
    bank, broker = _account(1), _account(2)
    out = _tx(1, bank, 10, -50000)
    far = _tx(2, broker, 13, 50000)
    near = _tx(3, broker, 11, 50000)
    candidates = find_transfer_candidates([out, far, near])
    assert [(c.outgoing.id, c.incoming.id, c.days_apart) for c in candidates] == [(1, 3, 1)]


@pytest.mark.parametrize(
    "other",
    [
        _tx(2, _account(1), 10, 50000),  # same account
        _tx(2, _account(2), 14, 50000),  # 4 days apart
        _tx(2, _account(2), 10, 49999),  # different amount
        _tx(2, _account(2, Currency.USD), 10, 50000),  # different currency
    ],
)
def test_transfer_candidates_reject(other: Transaction) -> None:
    assert find_transfer_candidates([_tx(1, _account(1), 10, -50000), other]) == []


def test_link_and_unlink_transfer() -> None:
    out, inc = _tx(1, _account(1), 10, -500), _tx(2, _account(2), 11, 500)
    out.category_id = 9
    link_transfer(out, inc)
    assert (out.kind, inc.kind) == (TransactionKind.TRANSFER, TransactionKind.TRANSFER)
    assert (out.transfer_pair_id, inc.transfer_pair_id) == (2, 1)
    assert out.category_id is None
    unlink_transfer(out, inc)
    assert (out.kind, inc.kind) == (TransactionKind.EXPENSE, TransactionKind.INCOME)
    assert out.transfer_pair_id is None and inc.transfer_pair_id is None


def test_link_transfer_rejects_wrong_direction() -> None:
    with pytest.raises(ValueError):
        link_transfer(_tx(1, _account(1), 10, 500), _tx(2, _account(2), 10, -500))
