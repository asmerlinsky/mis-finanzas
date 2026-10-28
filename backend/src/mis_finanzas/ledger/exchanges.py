"""Currency exchanges between the owner's own accounts: dollars sold for pesos, or bought.

Both sides are movements of kind `fx`; a category with that kind ("Cambio de moneda") makes
them so. They fall on the same day, one going out in one currency and the other coming in in
the other. A linked exchange shares `transfer_pair_id`, like a transfer, but keeps kind `fx`
and its category: it's money changing currency, neither income nor expense.

On a day with several of each, the pairs whose implied rate (pesos per dollar) is closest to
that day's MEP are taken first. A pair more than `MAX_GAP` away from the MEP is not proposed:
it's not a real exchange (one sale settled in several debits, for instance), and its sides stay
unpaired, still out of income and expenses. Without a MEP rate, sides pair in order.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from mis_finanzas.core.money import CENT
from mis_finanzas.ledger.models import Currency, Transaction, TransactionKind

MepRate = Callable[[date], Decimal | None]
MAX_GAP = Decimal("0.10")  # 10% from the day's MEP


@dataclass(frozen=True)
class ExchangeCandidate:
    outgoing: Transaction
    incoming: Transaction

    @property
    def rate(self) -> Decimal:
        """Pesos per dollar this exchange implies."""
        return pesos_per_dollar(self.outgoing, self.incoming)


def pesos_per_dollar(one: Transaction, other: Transaction) -> Decimal:
    pesos, dollars = (one, other) if one.account.currency is Currency.ARS else (other, one)
    return (Decimal(abs(pesos.amount_cents)) / abs(dollars.amount_cents)).quantize(CENT)


def _is_side(tx: Transaction) -> bool:
    return tx.kind is TransactionKind.FX and tx.transfer_pair_id is None and tx.amount_cents != 0


def _pairs(outgoing: Transaction, incoming: Transaction) -> bool:
    return (
        outgoing.amount_cents < 0 < incoming.amount_cents
        and outgoing.date == incoming.date
        and outgoing.account.currency is not incoming.account.currency
    )


def _gap(outgoing: Transaction, incoming: Transaction, mep: Decimal | None) -> Decimal:
    """How far the pair's rate is from the MEP, as a fraction; 0 without a MEP rate."""
    return abs(pesos_per_dollar(outgoing, incoming) / mep - 1) if mep else Decimal(0)


def _day_pairs(sides: list[Transaction], mep: Decimal | None) -> list[ExchangeCandidate]:
    options = sorted(
        (
            (_gap(out, inc, mep), out.id, inc.id, out, inc)
            for out in sides
            for inc in sides
            if _pairs(out, inc)
        ),
        key=lambda option: option[:3],
    )
    used: set[int] = set()
    found = []
    for gap, _, _, out, inc in options:
        if gap <= MAX_GAP and out.id not in used and inc.id not in used:
            used |= {out.id, inc.id}
            found.append(ExchangeCandidate(out, inc))
    return sorted(found, key=lambda c: c.outgoing.id)


def find_exchange_candidates(
    transactions: Sequence[Transaction], mep_on: MepRate
) -> list[ExchangeCandidate]:
    by_day: dict[date, list[Transaction]] = {}
    for tx in transactions:
        if _is_side(tx):
            by_day.setdefault(tx.date, []).append(tx)
    return [pair for day in sorted(by_day) for pair in _day_pairs(by_day[day], mep_on(day))]


def link_exchange(outgoing: Transaction, incoming: Transaction) -> None:
    """Raises `ValueError` unless both are unlinked `fx` movements that form an exchange."""
    if not (_is_side(outgoing) and _is_side(incoming) and _pairs(outgoing, incoming)):
        raise ValueError("not an exchange: two unlinked fx movements, same day, other currency")
    outgoing.transfer_pair_id = incoming.id
    incoming.transfer_pair_id = outgoing.id
