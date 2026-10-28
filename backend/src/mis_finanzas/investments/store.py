"""Write what a broker statement says about investments: instruments, operations, snapshots.

Operations dedupe like ledger rows: by a fingerprint of what identifies them, counting
identical ones within the file, so overlapping statements add nothing twice. A snapshot is
keyed by (broker, date, source); a later file for the same key replaces it.
"""

import hashlib
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from mis_finanzas.investments.models import (
    HoldingCash,
    HoldingPosition,
    HoldingSnapshot,
    Instrument,
    InvestmentOperation,
)
from mis_finanzas.investments.records import (
    InstrumentRef,
    InvestmentData,
    ParsedOperation,
    ParsedSnapshot,
    SnapshotSource,
)

logger = logging.getLogger(__name__)

_QUANTUM = Decimal("0.000001")


@dataclass(frozen=True)
class InvestmentSummary:
    """What committing the data would do, for the import preview."""

    as_of: date | None
    source: SnapshotSource | None
    positions: int
    cash: int
    operations: int
    new_operations: int
    replaces_snapshot: bool


def _amount_key(value: Decimal | None) -> str:
    return "" if value is None else str(value.quantize(_QUANTUM))


def operation_fingerprints(broker: str, operations: Sequence[ParsedOperation]) -> list[str]:
    seen: dict[tuple[str, ...], int] = {}
    prints = []
    for op in operations:
        key = (
            broker,
            op.instrument.ticker,
            op.trade_date.isoformat(),
            _amount_key(op.quantity),
            _amount_key(op.net),
        )
        occurrence = seen.get(key, 0)
        seen[key] = occurrence + 1
        raw = "|".join(["op1", *key, str(occurrence)])
        prints.append(hashlib.sha256(raw.encode()).hexdigest())
    return prints


def _existing_operations(session: Session, prints: list[str]) -> set[str]:
    if not prints:
        return set()
    query = select(InvestmentOperation.fingerprint).where(
        InvestmentOperation.fingerprint.in_(prints)
    )
    return set(session.scalars(query))


def _snapshot_row(
    session: Session, broker: str, snapshot: ParsedSnapshot
) -> HoldingSnapshot | None:
    query = select(HoldingSnapshot).where(
        HoldingSnapshot.broker == broker,
        HoldingSnapshot.as_of == snapshot.as_of,
        HoldingSnapshot.source == snapshot.source,
    )
    return session.scalar(query)


def summarize(session: Session, data: InvestmentData) -> InvestmentSummary:
    prints = operation_fingerprints(data.broker, data.operations)
    new_operations = len(set(prints) - _existing_operations(session, prints))
    snapshot = data.snapshot
    if snapshot is None:
        return InvestmentSummary(None, None, 0, 0, len(prints), new_operations, False)
    return InvestmentSummary(
        as_of=snapshot.as_of,
        source=snapshot.source,
        positions=len(snapshot.positions),
        cash=len(snapshot.cash),
        operations=len(prints),
        new_operations=new_operations,
        replaces_snapshot=_snapshot_row(session, data.broker, snapshot) is not None,
    )


def _instrument(session: Session, cache: dict[str, Instrument], ref: InstrumentRef) -> Instrument:
    """Find or create by ticker; fill in what a statement adds (class, broker code)."""
    instrument = cache.get(ref.ticker) or session.scalar(
        select(Instrument).where(Instrument.ticker == ref.ticker)
    )
    if instrument is None:
        instrument = Instrument(ticker=ref.ticker, name=ref.name)
        session.add(instrument)
    instrument.asset_class = instrument.asset_class or ref.asset_class
    instrument.broker_code = instrument.broker_code or ref.broker_code
    cache[ref.ticker] = instrument
    return instrument


def _store_operations(
    session: Session, batch_id: int | None, data: InvestmentData, cache: dict[str, Instrument]
) -> int:
    prints = operation_fingerprints(data.broker, data.operations)
    existing = _existing_operations(session, prints)
    written = 0
    for op, print_ in zip(data.operations, prints, strict=True):
        if print_ in existing:
            continue
        session.add(
            InvestmentOperation(
                broker=data.broker,
                instrument=_instrument(session, cache, op.instrument),
                trade_date=op.trade_date,
                settle_date=op.settle_date,
                description=op.description,
                quantity=op.quantity,
                price=op.price,
                gross=op.gross,
                fees=op.fees,
                net=op.net,
                fingerprint=print_,
                import_batch_id=batch_id,
            )
        )
        written += 1
    return written


def _store_snapshot(
    session: Session,
    batch_id: int | None,
    broker: str,
    snapshot: ParsedSnapshot,
    cache: dict[str, Instrument],
) -> None:
    previous = _snapshot_row(session, broker, snapshot)
    if previous is not None:
        session.delete(previous)
        session.flush()
    row = HoldingSnapshot(
        broker=broker, as_of=snapshot.as_of, source=snapshot.source, import_batch_id=batch_id
    )
    row.positions = [
        HoldingPosition(
            instrument=_instrument(session, cache, p.instrument),
            quantity=p.quantity,
            price=p.price,
            value=p.value,
            currency=p.currency,
        )
        for p in snapshot.positions
    ]
    row.cash = [
        HoldingCash(label=c.label, currency=c.currency, amount=c.amount) for c in snapshot.cash
    ]
    session.add(row)


def store(session: Session, batch_id: int | None, data: InvestmentData) -> None:
    """Add to the session; the caller commits, together with the ledger rows."""
    cache: dict[str, Instrument] = {}
    written = _store_operations(session, batch_id, data, cache)
    if data.snapshot is not None:
        _store_snapshot(session, batch_id, data.broker, data.snapshot, cache)
    logger.info(
        "Investment data stored",
        extra={
            "batch_id": batch_id,
            "operations": written,
            "positions": len(data.snapshot.positions) if data.snapshot else 0,
        },
    )
