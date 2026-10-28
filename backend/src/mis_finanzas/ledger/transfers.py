"""Transfer pairing between the owner's own accounts.

Money that leaves one account and arrives in another (bank -> broker, bank -> card payment)
is neither income nor expense. Candidates are pairs with opposite amounts in the same
currency, in different accounts, at most `MAX_DAYS_APART` days apart.

Not supported: paying a card's USD balance in pesos. The bank row is ARS and the card row is
USD, so they never pair, and both sides count in totals until linked or recategorized by hand.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from mis_finanzas.ledger.models import Transaction, TransactionKind

MAX_DAYS_APART = 3


@dataclass(frozen=True)
class TransferCandidate:
    outgoing: Transaction
    incoming: Transaction

    @property
    def days_apart(self) -> int:
        return abs((self.incoming.date - self.outgoing.date).days)


def _is_pairable(outgoing: Transaction, incoming: Transaction) -> bool:
    return (
        outgoing.account_id != incoming.account_id
        and outgoing.account.currency == incoming.account.currency
        and outgoing.amount_cents == -incoming.amount_cents
        and abs((incoming.date - outgoing.date).days) <= MAX_DAYS_APART
    )


def find_transfer_candidates(transactions: Sequence[Transaction]) -> list[TransferCandidate]:
    """Greedy pairing: each outgoing row takes the closest-in-date unused incoming row."""
    unpaired = [t for t in transactions if t.transfer_pair_id is None]
    outgoing = sorted((t for t in unpaired if t.amount_cents < 0), key=lambda t: (t.date, t.id))
    incoming = [t for t in unpaired if t.amount_cents > 0]
    used: set[int] = set()
    candidates = []
    for out in outgoing:
        matches = [i for i in incoming if i.id not in used and _is_pairable(out, i)]
        if not matches:
            continue
        best = min(matches, key=lambda i: (abs((i.date - out.date).days), i.id))
        used.add(best.id)
        candidates.append(TransferCandidate(outgoing=out, incoming=best))
    return candidates


def link_transfer(outgoing: Transaction, incoming: Transaction) -> None:
    """Mark both sides as one transfer. Raises `ValueError` if they don't form a pair."""
    if outgoing.amount_cents >= 0 or not _is_pairable(outgoing, incoming):
        raise ValueError("transactions are not a valid transfer pair")
    for side, other in ((outgoing, incoming), (incoming, outgoing)):
        side.kind = TransactionKind.TRANSFER
        side.transfer_pair_id = other.id
        side.category_id = None


def unlink_transfer(transaction: Transaction, pair: Transaction | None) -> None:
    """Undo a transfer link; each side goes back to income/expense by sign."""
    for side in (transaction, pair):
        if side is None:
            continue
        side.transfer_pair_id = None
        side.kind = TransactionKind.INCOME if side.amount_cents > 0 else TransactionKind.EXPENSE
