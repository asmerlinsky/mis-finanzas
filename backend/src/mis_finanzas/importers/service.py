"""Import flow: parse -> preview (duplicates, categories, errors) -> commit in one transaction.

Preview and commit both re-parse the uploaded bytes, so the server keeps no state between
them and the commit always writes exactly what the file contains.
"""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path, PurePath

from sqlalchemy import select
from sqlalchemy.orm import Session

from mis_finanzas.core.money import to_cents
from mis_finanzas.importers.base import ParsedRow, RowError
from mis_finanzas.importers.models import ImportMapping
from mis_finanzas.importers.tabular import GenericTabularImporter, TabularMapping
from mis_finanzas.ledger.dedup import fingerprint, occurrence_indexes
from mis_finanzas.ledger.models import (
    Account,
    Category,
    CategoryRule,
    ImportBatch,
    Transaction,
    TransactionKind,
)
from mis_finanzas.ledger.rules import first_matching_rule, infer_kind
from mis_finanzas.ledger.text import normalize_description

logger = logging.getLogger(__name__)


class ImportRejectedError(ValueError):
    pass


@dataclass(frozen=True)
class PreviewRow:
    line_number: int
    date: date
    amount: Decimal
    description: str
    description_norm: str
    fingerprint: str
    duplicate: bool
    category: Category | None
    kind: TransactionKind


@dataclass
class ImportPreview:
    filename: str
    sha256: str
    already_imported: bool
    rows: list[PreviewRow] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)

    @property
    def new_rows(self) -> list[PreviewRow]:
        return [r for r in self.rows if not r.duplicate]


def _existing_fingerprints(session: Session, fingerprints: list[str]) -> set[str]:
    if not fingerprints:
        return set()
    query = select(Transaction.fingerprint).where(Transaction.fingerprint.in_(fingerprints))
    return set(session.scalars(query))


def _fingerprints(account_id: int, rows: list[ParsedRow], norms: list[str]) -> list[str]:
    keys = [(r.date, to_cents(r.amount), n) for r, n in zip(rows, norms, strict=True)]
    return [
        fingerprint(account_id, d, cents, norm, occ)
        for (d, cents, norm), occ in zip(keys, occurrence_indexes(keys), strict=True)
    ]


def prepare_rows(session: Session, account: Account, rows: list[ParsedRow]) -> list[PreviewRow]:
    """Normalize, fingerprint, flag duplicates and categorize parsed rows."""
    norms = [normalize_description(r.description) for r in rows]
    prints = _fingerprints(account.id, rows, norms)
    existing = _existing_fingerprints(session, prints)
    rules = list(session.scalars(select(CategoryRule)))
    categories = {c.id: c for c in session.scalars(select(Category))}
    prepared = []
    for row, norm, print_ in zip(rows, norms, prints, strict=True):
        cents = to_cents(row.amount)
        rule = first_matching_rule(rules, norm, account.id, cents)
        category = categories.get(rule.category_id) if rule else None
        prepared.append(
            PreviewRow(
                line_number=row.line_number,
                date=row.date,
                amount=row.amount,
                description=row.description,
                description_norm=norm,
                fingerprint=print_,
                duplicate=print_ in existing,
                category=category,
                kind=infer_kind(cents, category),
            )
        )
    return prepared


def build_preview(
    session: Session, mapping: ImportMapping, content: bytes, filename: str
) -> ImportPreview:
    """Raises `ImportFileError` if the file can't be read at all."""
    account = session.get_one(Account, mapping.account_id)
    importer = GenericTabularImporter(TabularMapping.model_validate(mapping.config))
    result = importer.parse(content, filename)
    sha256 = hashlib.sha256(content).hexdigest()
    batch = session.scalar(select(ImportBatch.id).where(ImportBatch.file_sha256 == sha256))
    return ImportPreview(
        filename=filename,
        sha256=sha256,
        already_imported=batch is not None,
        rows=prepare_rows(session, account, result.rows),
        errors=result.errors,
    )


def _check_committable(preview: ImportPreview, skip_invalid_rows: bool) -> None:
    if preview.already_imported:
        raise ImportRejectedError("this file was already imported")
    if preview.errors and not skip_invalid_rows:
        raise ImportRejectedError(
            f"{len(preview.errors)} rows have errors; fix the mapping or skip them explicitly"
        )
    if not preview.rows:
        raise ImportRejectedError("the file has no rows to import")


def _store_original(uploads_dir: Path, sha256: str, filename: str, content: bytes) -> Path:
    uploads_dir.mkdir(parents=True, exist_ok=True)
    path = uploads_dir / f"{sha256}{PurePath(filename).suffix.lower()}"
    if not path.exists():
        path.write_bytes(content)
    return path


def commit_import(
    session: Session,
    mapping: ImportMapping,
    content: bytes,
    filename: str,
    uploads_dir: Path,
    skip_invalid_rows: bool = False,
) -> ImportBatch:
    """Write all new rows and the batch record in one transaction, or nothing."""
    preview = build_preview(session, mapping, content, filename)
    _check_committable(preview, skip_invalid_rows)
    stored = _store_original(uploads_dir, preview.sha256, filename, content)
    new_rows = preview.new_rows
    batch = ImportBatch(
        account_id=mapping.account_id,
        importer=GenericTabularImporter.name,
        importer_version=GenericTabularImporter.version,
        filename=filename,
        file_sha256=preview.sha256,
        stored_path=str(stored),
        rows_imported=len(new_rows),
        rows_duplicate=len(preview.rows) - len(new_rows),
        rows_skipped=len(preview.errors),
    )
    session.add(batch)
    session.flush()
    session.add_all(_to_transaction(mapping.account_id, batch.id, row) for row in new_rows)
    session.commit()
    logger.info(
        "Import committed",
        extra={"batch_id": batch.id, "rows": len(new_rows), "duplicates": batch.rows_duplicate},
    )
    return batch


def _to_transaction(account_id: int, batch_id: int, row: PreviewRow) -> Transaction:
    return Transaction(
        account_id=account_id,
        date=row.date,
        amount_cents=to_cents(row.amount),
        description_raw=row.description,
        description_norm=row.description_norm,
        kind=row.kind,
        category_id=row.category.id if row.category else None,
        import_batch_id=batch_id,
        fingerprint=row.fingerprint,
    )
