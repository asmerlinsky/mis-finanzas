"""Which incoming movement paid each invoice. The owner confirms every link.

- **Candidates** for an invoice: money in (a credit) on an account in the invoice's currency,
  dated from `DAYS_BEFORE` days before the issue date to `DAYS_AFTER` after, counted as income
  or expense (not a transfer between own accounts, an FX or an investment movement), and not
  already linked to another invoice. Credit notes are never matched.
- **Exact:** the credit is the invoice total, to the cent, in the invoice's currency.
- **Suggestions:** unpaid invoices, oldest first, each take the exact candidate closest in date
  that no earlier invoice took. Monthly invoices for the same amount pair with their own month.
- **Choices:** for "Elegir movimiento", every candidate, any amount, closest amount first.
- **Linking** stores the movement on the invoice; a movement with no category gets
  `INCOME_CATEGORY` (an income category, created if missing).
"""

import logging
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from mis_finanzas.ledger.categorize import set_category
from mis_finanzas.ledger.models import Category, Transaction, TransactionKind
from mis_finanzas.monotributo.models import Invoice
from mis_finanzas.monotributo.records import INVOICE_TYPES

logger = logging.getLogger(__name__)

DAYS_BEFORE = 15
DAYS_AFTER = 90
INCOME_CATEGORY = "Facturación"
_COUNTED = (TransactionKind.INCOME, TransactionKind.EXPENSE)


class PaymentLinkError(ValueError):
    pass


@dataclass(frozen=True)
class Candidate:
    transaction: Transaction
    exact: bool


def _is_credit_note(invoice: Invoice) -> bool:
    return INVOICE_TYPES[invoice.type_code][1] < 0


def _credits(session: Session) -> list[Transaction]:
    query = select(Transaction).where(
        Transaction.amount_cents > 0,
        Transaction.transfer_pair_id.is_(None),
        Transaction.kind.in_(_COUNTED),
    )
    return list(session.scalars(query))


def _taken(session: Session) -> dict[int, int]:
    """Movement id -> the invoice it's linked to."""
    query = select(Invoice.payment_transaction_id, Invoice.id).where(
        Invoice.payment_transaction_id.is_not(None)
    )
    return {tx_id: invoice_id for tx_id, invoice_id in session.execute(query) if tx_id is not None}


def _fits(invoice: Invoice, tx: Transaction) -> bool:
    start = invoice.issued_on - timedelta(days=DAYS_BEFORE)
    end = invoice.issued_on + timedelta(days=DAYS_AFTER)
    return tx.account.currency.value == invoice.currency and start <= tx.date <= end


def _days(invoice: Invoice, tx: Transaction) -> int:
    return abs((tx.date - invoice.issued_on).days)


def candidates(session: Session, invoice: Invoice) -> list[Candidate]:
    """Every movement that could have paid `invoice`, the likeliest first."""
    if _is_credit_note(invoice):
        return []
    taken = _taken(session)
    found = [
        Candidate(tx, tx.amount_cents == invoice.total_cents)
        for tx in _credits(session)
        if _fits(invoice, tx) and taken.get(tx.id, invoice.id) == invoice.id
    ]
    return sorted(
        found,
        key=lambda c: (
            not c.exact,
            abs(c.transaction.amount_cents - invoice.total_cents),
            _days(invoice, c.transaction),
        ),
    )


def suggestions(session: Session, invoices: list[Invoice]) -> dict[int, Transaction]:
    """Invoice id -> the exact movement suggested for it, for unpaid invoices."""
    used = set(_taken(session))
    credits = _credits(session)
    suggested: dict[int, Transaction] = {}
    unpaid = [i for i in invoices if i.payment_transaction_id is None and not _is_credit_note(i)]
    for invoice in sorted(unpaid, key=lambda i: (i.issued_on, i.id)):
        exact = [
            tx
            for tx in credits
            if tx.id not in used and tx.amount_cents == invoice.total_cents and _fits(invoice, tx)
        ]
        if exact:
            best = min(exact, key=lambda tx: (_days(invoice, tx), tx.id))
            suggested[invoice.id] = best
            used.add(best.id)
    return suggested


def _income_category(session: Session) -> Category:
    category = session.scalar(select(Category).where(Category.name == INCOME_CATEGORY))
    if category is None:
        category = Category(name=INCOME_CATEGORY, kind=TransactionKind.INCOME)
        session.add(category)
        session.flush()
    return category


def link(session: Session, invoice: Invoice, tx: Transaction) -> None:
    """Raises `PaymentLinkError` when `tx` can't have paid `invoice`."""
    if all(c.transaction.id != tx.id for c in candidates(session, invoice)):
        raise PaymentLinkError(
            "that movement can't pay this invoice: it must be money in, in the invoice's "
            "currency, near its date, and not linked to another invoice"
        )
    invoice.payment_transaction_id = tx.id
    if tx.category_id is None:
        set_category(tx, _income_category(session))
    session.commit()
    logger.info("Invoice payment linked", extra={"invoice_id": invoice.id, "transaction_id": tx.id})


def unlink(session: Session, invoice: Invoice) -> None:
    """The movement keeps its category: the owner may have set it on purpose."""
    invoice.payment_transaction_id = None
    session.commit()
    logger.info("Invoice payment unlinked", extra={"invoice_id": invoice.id})
