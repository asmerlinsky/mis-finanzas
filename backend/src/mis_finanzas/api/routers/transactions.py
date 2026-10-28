from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import Select, func, select

from mis_finanzas.api.common import get_or_404
from mis_finanzas.api.deps import SessionDep
from mis_finanzas.api.schemas import (
    ExchangeCandidateOut,
    TransactionOut,
    TransactionPage,
    TransactionPatch,
    TransferCandidateOut,
    TransferLinkIn,
)
from mis_finanzas.core.money import from_cents
from mis_finanzas.ledger.categorize import set_category
from mis_finanzas.ledger.exchanges import (
    ExchangeCandidate,
    find_exchange_candidates,
    link_exchange,
)
from mis_finanzas.ledger.models import Category, Transaction, TransactionKind
from mis_finanzas.ledger.transfers import (
    TransferCandidate,
    find_transfer_candidates,
    link_transfer,
    unlink_transfer,
)
from mis_finanzas.market.fx import RateTable, load_rate_table

router = APIRouter(tags=["transactions"])


def to_out(tx: Transaction) -> TransactionOut:
    return TransactionOut(
        id=tx.id,
        account_id=tx.account_id,
        account_name=tx.account.name,
        currency=tx.account.currency,
        date=tx.date,
        amount=from_cents(tx.amount_cents),
        description=tx.description_raw,
        category_id=tx.category_id,
        category_name=tx.category.name if tx.category else None,
        kind=tx.kind,
        transfer_pair_id=tx.transfer_pair_id,
        import_batch_id=tx.import_batch_id,
    )


def _filtered(
    query: Select[Transaction],
    account_id: int | None,
    start: date | None,
    end: date | None,
    kind: TransactionKind | None,
    uncategorized: bool,
    search: str | None,
    category_id: int | None = None,
) -> Select[Transaction]:
    if account_id is not None:
        query = query.where(Transaction.account_id == account_id)
    if start is not None:
        query = query.where(Transaction.date >= start)
    if end is not None:
        query = query.where(Transaction.date <= end)
    if kind is not None:
        query = query.where(Transaction.kind == kind)
    if uncategorized:
        query = query.where(Transaction.category_id.is_(None))
    if category_id is not None:
        query = query.where(Transaction.category_id == category_id)
    if search:
        query = query.where(Transaction.description_norm.contains(search.strip().upper()))
    return query


@router.get("/transactions", response_model=TransactionPage)
def list_transactions(
    session: SessionDep,
    account_id: int | None = None,
    start: date | None = None,
    end: date | None = None,
    kind: TransactionKind | None = None,
    uncategorized: bool = False,
    search: str | None = None,
    category_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TransactionPage:
    query = _filtered(
        select(Transaction), account_id, start, end, kind, uncategorized, search, category_id
    )
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    page = query.order_by(Transaction.date.desc(), Transaction.id.desc()).limit(limit)
    items = session.scalars(page.offset(offset)).unique()
    return TransactionPage(items=[to_out(t) for t in items], total=total)


@router.patch("/transactions/{tx_id}", response_model=TransactionOut)
def update_transaction(tx_id: int, body: TransactionPatch, session: SessionDep) -> TransactionOut:
    tx = get_or_404(session, Transaction, tx_id)
    if tx.transfer_pair_id is not None and body.category_id is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "unlink the transfer before categorizing")
    category = get_or_404(session, Category, body.category_id) if body.category_id else None
    set_category(tx, category)
    session.commit()
    return to_out(tx)


def _transfer_candidates(session: SessionDep) -> list[TransferCandidate]:
    unpaired = session.scalars(
        select(Transaction).where(
            Transaction.transfer_pair_id.is_(None),
            Transaction.kind.in_([TransactionKind.INCOME, TransactionKind.EXPENSE]),
        )
    ).unique()
    return find_transfer_candidates(list(unpaired))


@router.get("/transfers/candidates", response_model=list[TransferCandidateOut])
def transfer_candidates(session: SessionDep) -> list[TransferCandidateOut]:
    """Unlinked opposite-amount pairs across accounts. Nothing changes until confirmed."""
    return [
        TransferCandidateOut(
            outgoing=to_out(c.outgoing), incoming=to_out(c.incoming), days_apart=c.days_apart
        )
        for c in _transfer_candidates(session)
    ]


@router.post("/transfers/all")
def link_all_transfers(session: SessionDep) -> dict[str, int]:
    """Confirm every current suggestion; returns how many transfers were linked."""
    found = _transfer_candidates(session)
    for candidate in found:
        link_transfer(candidate.outgoing, candidate.incoming)
    session.commit()
    return {"linked": len(found)}


@router.post("/transfers", status_code=status.HTTP_204_NO_CONTENT)
def link(body: TransferLinkIn, session: SessionDep) -> None:
    outgoing = get_or_404(session, Transaction, body.outgoing_id)
    incoming = get_or_404(session, Transaction, body.incoming_id)
    if outgoing.transfer_pair_id or incoming.transfer_pair_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "a side is already linked")
    try:
        link_transfer(outgoing, incoming)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    session.commit()


@router.delete("/transfers/{tx_id}", status_code=status.HTTP_204_NO_CONTENT)
def unlink(tx_id: int, session: SessionDep) -> None:
    tx = get_or_404(session, Transaction, tx_id)
    pair = session.get(Transaction, tx.transfer_pair_id) if tx.transfer_pair_id else None
    unlink_transfer(tx, pair)
    session.commit()


def _exchange_candidates(session: SessionDep) -> tuple[list[ExchangeCandidate], RateTable]:
    sides = session.scalars(
        select(Transaction).where(
            Transaction.transfer_pair_id.is_(None), Transaction.kind == TransactionKind.FX
        )
    ).unique()
    rates = load_rate_table(session)
    return find_exchange_candidates(list(sides), rates.rate_on), rates


@router.get("/exchanges/candidates", response_model=list[ExchangeCandidateOut])
def exchange_candidates(session: SessionDep) -> list[ExchangeCandidateOut]:
    """Same-day pairs of currency-exchange movements, to link as one exchange each."""
    found, rates = _exchange_candidates(session)
    return [
        ExchangeCandidateOut(
            outgoing=to_out(c.outgoing),
            incoming=to_out(c.incoming),
            rate=c.rate,
            mep=rates.rate_on(c.outgoing.date),
        )
        for c in found
    ]


@router.post("/exchanges", status_code=status.HTTP_204_NO_CONTENT)
def link_one_exchange(body: TransferLinkIn, session: SessionDep) -> None:
    outgoing = get_or_404(session, Transaction, body.outgoing_id)
    incoming = get_or_404(session, Transaction, body.incoming_id)
    try:
        link_exchange(outgoing, incoming)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    session.commit()


@router.post("/exchanges/all")
def link_all_exchanges(session: SessionDep) -> dict[str, int]:
    """Link every current candidate; returns how many exchanges were linked."""
    found, _ = _exchange_candidates(session)
    for candidate in found:
        link_exchange(candidate.outgoing, candidate.incoming)
    session.commit()
    return {"linked": len(found)}
