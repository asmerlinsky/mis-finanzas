"""Import flow: parse -> preview (targets, duplicates, categories, checks) -> commit.

A file is read either with a saved column mapping (generic CSV/Excel; one target, the
mapping's account) or by the dedicated importer that recognizes it (several targets, each
mapped once to an account in `source_accounts`).

Preview and commit both re-parse the uploaded bytes, so the server keeps no state between
them and the commit always writes exactly what the file contains. The commit is refused
while a statement total doesn't match, a target has no account, or rows have errors (unless
explicitly skipped); it writes everything in one transaction or nothing.

A broker statement also carries investment data (operations, a holdings snapshot), written
by `investments.store` in the same transaction. A holdings statement has no ledger rows.
"""

import hashlib
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path, PurePath

from sqlalchemy import select
from sqlalchemy.orm import Session

from mis_finanzas.core.money import to_cents
from mis_finanzas.importers import registry
from mis_finanzas.importers.base import (
    DEFAULT_TARGET,
    Check,
    ImportFileError,
    ParsedRow,
    ParseResult,
    RowError,
)
from mis_finanzas.importers.models import ImportMapping, SourceAccount
from mis_finanzas.importers.tabular import GenericTabularImporter, TabularMapping
from mis_finanzas.investments import store as investment_store
from mis_finanzas.investments.records import InvestmentData
from mis_finanzas.ledger.dedup import fingerprint, occurrence_indexes
from mis_finanzas.ledger.models import (
    Category,
    CategoryRule,
    ImportBatch,
    Transaction,
    TransactionKind,
)
from mis_finanzas.ledger.rules import first_matching_rule, infer_kind
from mis_finanzas.ledger.text import normalize_description

logger = logging.getLogger(__name__)

# An existing movement this close in date, same account and amount, may be the same one.
NEAR_DUPLICATE_DAYS = 3


class ImportRejectedError(ValueError):
    pass


@dataclass(frozen=True)
class PreviewRow:
    line_number: int
    date: date
    amount: Decimal
    description: str
    description_norm: str
    target: str
    account_id: int | None  # None while the target isn't mapped to an account
    reference: str | None
    installment: tuple[int, int] | None
    fingerprint: str | None
    duplicate: bool
    near_duplicate: bool
    category: Category | None
    kind: TransactionKind


@dataclass
class ImportPreview:
    importer: str
    importer_version: str
    filename: str
    sha256: str
    already_imported: bool
    target_accounts: dict[str, int | None]
    rows: list[PreviewRow] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)
    investments: investment_store.InvestmentSummary | None = None
    investment_data: InvestmentData | None = None

    @property
    def new_rows(self) -> list[PreviewRow]:
        return [r for r in self.rows if not r.duplicate]

    @property
    def unmapped_targets(self) -> list[str]:
        return [t for t, account in self.target_accounts.items() if account is None]

    @property
    def failed_checks(self) -> list[Check]:
        return [c for c in self.checks if not c.ok]


@dataclass(frozen=True)
class _Parsed:
    importer: str
    version: str
    result: ParseResult
    target_accounts: dict[str, int | None]


def _parse(
    session: Session, content: bytes, filename: str, mapping: ImportMapping | None
) -> _Parsed:
    """Raises `ImportFileError` when the file can't be read or no importer recognizes it."""
    if mapping is not None:
        importer = GenericTabularImporter(TabularMapping.model_validate(mapping.config))
        return _Parsed(
            importer.name,
            importer.version,
            importer.parse(content, filename),
            {DEFAULT_TARGET: mapping.account_id},
        )
    parsed = registry.parse_file(filename, content)
    if parsed is None:
        raise ImportFileError("no importer recognizes this file; choose a column mapping")
    targets = sorted({row.target for row in parsed.result.rows})
    known = {
        s.key: s.account_id
        for s in session.scalars(select(SourceAccount).where(SourceAccount.key.in_(targets)))
    }
    return _Parsed(
        parsed.importer, parsed.version, parsed.result, {t: known.get(t) for t in targets}
    )


def _fingerprints(rows: list[ParsedRow], accounts: list[int | None]) -> list[str | None]:
    """Occurrences count identical (account, date, amount) within this file."""
    keys = [(a, r.date, to_cents(r.amount)) for r, a in zip(rows, accounts, strict=True)]
    return [
        None if account is None else fingerprint(account, day, cents, occurrence)
        for (account, day, cents), occurrence in zip(keys, occurrence_indexes(keys), strict=True)
    ]


def _existing(session: Session, prints: list[str | None]) -> set[str]:
    wanted = [p for p in prints if p is not None]
    if not wanted:
        return set()
    query = select(Transaction.fingerprint).where(Transaction.fingerprint.in_(wanted))
    return set(session.scalars(query))


def _nearby(
    session: Session, rows: list[ParsedRow], accounts: list[int | None], exact: set[str]
) -> dict[tuple[int, int], list[date]]:
    """Dates of existing movements by (account, cents) around the file's period.

    Movements this file matches exactly are left out: they are this file's own rows, not
    look-alikes of its other rows.
    """
    mapped = [a for a in accounts if a is not None]
    if not mapped or not rows:
        return {}
    margin = timedelta(days=NEAR_DUPLICATE_DAYS)
    query = select(Transaction).where(
        Transaction.account_id.in_(set(mapped)),
        Transaction.date >= min(r.date for r in rows) - margin,
        Transaction.date <= max(r.date for r in rows) + margin,
    )
    nearby: dict[tuple[int, int], list[date]] = defaultdict(list)
    for tx in session.scalars(query).unique():
        if tx.fingerprint not in exact:
            nearby[(tx.account_id, tx.amount_cents)].append(tx.date)
    return nearby


def _is_near(
    nearby: dict[tuple[int, int], list[date]], account: int | None, cents: int, day: date
) -> bool:
    if account is None:
        return False
    return any(abs((d - day).days) <= NEAR_DUPLICATE_DAYS for d in nearby.get((account, cents), []))


@dataclass(frozen=True)
class _Rules:
    rules: list[CategoryRule]
    categories: dict[int, Category]

    def categorize(self, norm: str, account: int | None, cents: int) -> Category | None:
        if account is None:
            return None
        rule = first_matching_rule(self.rules, norm, account, cents)
        return self.categories.get(rule.category_id) if rule else None


def prepare_rows(
    session: Session, rows: list[ParsedRow], target_accounts: dict[str, int | None]
) -> list[PreviewRow]:
    """Fingerprint, flag exact and near duplicates, and categorize parsed rows."""
    accounts = [target_accounts.get(r.target) for r in rows]
    prints = _fingerprints(rows, accounts)
    existing = _existing(session, prints)
    nearby = _nearby(session, rows, accounts, existing)
    rules = _Rules(
        list(session.scalars(select(CategoryRule))),
        {c.id: c for c in session.scalars(select(Category))},
    )
    prepared = []
    for row, account, print_ in zip(rows, accounts, prints, strict=True):
        cents, norm = to_cents(row.amount), normalize_description(row.description)
        duplicate = print_ is not None and print_ in existing
        category = rules.categorize(norm, account, cents)
        prepared.append(
            PreviewRow(
                line_number=row.line_number,
                date=row.date,
                amount=row.amount,
                description=row.description,
                description_norm=norm,
                target=row.target,
                account_id=account,
                reference=row.reference,
                installment=row.installment,
                fingerprint=print_,
                duplicate=duplicate,
                near_duplicate=not duplicate and _is_near(nearby, account, cents, row.date),
                category=category,
                kind=infer_kind(cents, category),
            )
        )
    return prepared


def build_preview(
    session: Session, content: bytes, filename: str, mapping: ImportMapping | None = None
) -> ImportPreview:
    """With `mapping`, read the file by its columns; without, by the importer that knows it.

    Raises `ImportFileError` if the file can't be read at all.
    """
    parsed = _parse(session, content, filename, mapping)
    sha256 = hashlib.sha256(content).hexdigest()
    batch = session.scalar(select(ImportBatch.id).where(ImportBatch.file_sha256 == sha256))
    data = parsed.result.investments
    return ImportPreview(
        importer=parsed.importer,
        importer_version=parsed.version,
        filename=filename,
        sha256=sha256,
        already_imported=batch is not None,
        target_accounts=parsed.target_accounts,
        rows=prepare_rows(session, parsed.result.rows, parsed.target_accounts),
        errors=parsed.result.errors,
        checks=parsed.result.checks,
        metadata=parsed.result.metadata,
        investments=investment_store.summarize(session, data) if data else None,
        investment_data=data,
    )


def _check_committable(
    preview: ImportPreview, skip_invalid_rows: bool, skip_lines: frozenset[int]
) -> None:
    if preview.already_imported:
        raise ImportRejectedError("this file was already imported")
    if preview.failed_checks:
        names = ", ".join(c.name for c in preview.failed_checks)
        raise ImportRejectedError(f"the statement's totals don't match what was read: {names}")
    if preview.unmapped_targets:
        targets = ", ".join(preview.unmapped_targets)
        raise ImportRejectedError(f"choose an account for: {targets}")
    if preview.errors and not skip_invalid_rows:
        raise ImportRejectedError(
            f"{len(preview.errors)} rows have errors; fix the mapping or skip them explicitly"
        )
    unknown = skip_lines - {r.line_number for r in preview.rows}
    if unknown:
        raise ImportRejectedError(f"lines to skip are not rows of this file: {sorted(unknown)}")
    if not preview.rows and preview.investment_data is None:
        raise ImportRejectedError("the file has no rows to import")


def _store_original(uploads_dir: Path, sha256: str, filename: str, content: bytes) -> Path:
    uploads_dir.mkdir(parents=True, exist_ok=True)
    path = uploads_dir / f"{sha256}{PurePath(filename).suffix.lower()}"
    if not path.exists():
        path.write_bytes(content)
    return path


def _batch(
    preview: ImportPreview, to_write: list[PreviewRow], stored: Path, skipped: int
) -> ImportBatch:
    accounts = {r.account_id for r in preview.rows}
    return ImportBatch(
        account_id=next(iter(accounts)) if len(accounts) == 1 else None,
        importer=preview.importer,
        importer_version=preview.importer_version,
        filename=preview.filename,
        file_sha256=preview.sha256,
        stored_path=str(stored),
        rows_imported=len(to_write),
        rows_duplicate=len(preview.rows) - len(preview.new_rows),
        rows_skipped=len(preview.errors) + skipped,
    )


def commit_import(
    session: Session,
    content: bytes,
    filename: str,
    uploads_dir: Path,
    mapping: ImportMapping | None = None,
    skip_invalid_rows: bool = False,
    skip_lines: frozenset[int] = frozenset(),
) -> ImportBatch:
    """Write all new rows, minus `skip_lines`, and the batch record; all or nothing."""
    preview = build_preview(session, content, filename, mapping)
    _check_committable(preview, skip_invalid_rows, skip_lines)
    to_write = [r for r in preview.new_rows if r.line_number not in skip_lines]
    skipped = len(preview.new_rows) - len(to_write)
    stored = _store_original(uploads_dir, preview.sha256, filename, content)
    batch = _batch(preview, to_write, stored, skipped)
    session.add(batch)
    session.flush()
    session.add_all(_to_transaction(batch.id, row) for row in to_write)
    if preview.investment_data is not None:
        investment_store.store(session, batch.id, preview.investment_data)
    session.commit()
    logger.info(
        "Import committed",
        extra={
            "batch_id": batch.id,
            "importer": preview.importer,
            "rows": len(to_write),
            "duplicates": batch.rows_duplicate,
            "skipped": batch.rows_skipped,
        },
    )
    return batch


def _to_transaction(batch_id: int, row: PreviewRow) -> Transaction:
    if row.account_id is None or row.fingerprint is None:
        raise ImportRejectedError(f"line {row.line_number} has no account")
    number, total = row.installment or (None, None)
    return Transaction(
        account_id=row.account_id,
        date=row.date,
        amount_cents=to_cents(row.amount),
        description_raw=row.description,
        description_norm=row.description_norm,
        kind=row.kind,
        category_id=row.category.id if row.category else None,
        import_batch_id=batch_id,
        fingerprint=row.fingerprint,
        reference=row.reference,
        installment_number=number,
        installment_total=total,
    )
