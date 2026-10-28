from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from mis_finanzas.api.common import commit_or_409, get_or_404
from mis_finanzas.api.deps import SessionDep, SettingsDep
from mis_finanzas.api.schemas import (
    CheckOut,
    ImportBatchOut,
    InvestmentSummaryOut,
    InvoiceSummaryOut,
    MappingIn,
    MappingOut,
    PreviewOut,
    PreviewRowOut,
    RowErrorOut,
    SourceAccountIn,
    SourceAccountOut,
    TargetOut,
)
from mis_finanzas.importers.base import ImportFileError
from mis_finanzas.importers.models import ImportMapping, SourceAccount
from mis_finanzas.importers.service import (
    ImportPreview,
    ImportRejectedError,
    PreviewRow,
    build_preview,
    commit_import,
)
from mis_finanzas.investments.store import InvestmentSummary
from mis_finanzas.ledger.models import Account, ImportBatch
from mis_finanzas.monotributo.store import InvoiceSummary

router = APIRouter(tags=["imports"])

MAX_UPLOAD_BYTES = 20 * 1024 * 1024

Upload = Annotated[UploadFile, File()]
# Without a mapping, the importer that recognizes the file reads it.
MappingId = Annotated[int | None, Form()]


@router.get("/mappings", response_model=list[MappingOut])
def list_mappings(session: SessionDep) -> list[ImportMapping]:
    return list(session.scalars(select(ImportMapping).order_by(ImportMapping.name)))


def _apply(mapping: ImportMapping, body: MappingIn, session: Session) -> None:
    get_or_404(session, Account, body.account_id)
    mapping.name = body.name
    mapping.account_id = body.account_id
    mapping.config = body.config.model_dump()


@router.post("/mappings", response_model=MappingOut, status_code=status.HTTP_201_CREATED)
def create_mapping(body: MappingIn, session: SessionDep) -> ImportMapping:
    mapping = ImportMapping()
    _apply(mapping, body, session)
    session.add(mapping)
    commit_or_409(session, "mapping")
    return mapping


@router.put("/mappings/{mapping_id}", response_model=MappingOut)
def update_mapping(mapping_id: int, body: MappingIn, session: SessionDep) -> ImportMapping:
    mapping = get_or_404(session, ImportMapping, mapping_id)
    _apply(mapping, body, session)
    commit_or_409(session, "mapping")
    return mapping


@router.delete("/mappings/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_mapping(mapping_id: int, session: SessionDep) -> None:
    session.delete(get_or_404(session, ImportMapping, mapping_id))
    session.commit()


async def _read_upload(upload: UploadFile) -> tuple[bytes, str]:
    content = await upload.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "file is larger than 20 MB")
    return content, upload.filename or "upload"


def _row_out(row: PreviewRow) -> PreviewRowOut:
    return PreviewRowOut(
        line_number=row.line_number,
        date=row.date,
        amount=row.amount,
        description=row.description,
        target=row.target,
        account_id=row.account_id,
        reference=row.reference,
        installment=f"{row.installment[0]}/{row.installment[1]}" if row.installment else None,
        duplicate=row.duplicate,
        near_duplicate=row.near_duplicate,
        category_name=row.category.name if row.category else None,
        kind=row.kind,
    )


def _preview_out(preview: ImportPreview) -> PreviewOut:
    rows = [_row_out(r) for r in preview.rows]
    counts = {t: sum(r.target == t for r in preview.rows) for t in preview.target_accounts}
    new_count = len(preview.new_rows)
    return PreviewOut(
        importer=preview.importer,
        filename=preview.filename,
        already_imported=preview.already_imported,
        new_count=new_count,
        duplicate_count=len(rows) - new_count,
        near_duplicate_count=sum(r.near_duplicate for r in preview.rows),
        targets=[
            TargetOut(target=t, account_id=a, rows=counts[t])
            for t, a in preview.target_accounts.items()
        ],
        unmapped_targets=preview.unmapped_targets,
        checks=[
            CheckOut(name=c.name, expected=c.expected, actual=c.actual, ok=c.ok)
            for c in preview.checks
        ],
        metadata=preview.metadata,
        rows=rows,
        errors=[RowErrorOut(line_number=e.line_number, message=e.message) for e in preview.errors],
        investments=_investments_out(preview.investments),
        invoices=_invoices_out(preview.invoices),
    )


def _invoices_out(summary: InvoiceSummary | None) -> InvoiceSummaryOut | None:
    if summary is None:
        return None
    return InvoiceSummaryOut(
        invoices=summary.invoices,
        new=summary.new,
        changed=summary.changed,
        pdf_for=summary.pdf_for,
        pdf_creates=summary.pdf_creates,
    )


def _investments_out(summary: InvestmentSummary | None) -> InvestmentSummaryOut | None:
    if summary is None:
        return None
    return InvestmentSummaryOut(
        as_of=summary.as_of,
        source=summary.source.value if summary.source else None,
        positions=summary.positions,
        cash=summary.cash,
        operations=summary.operations,
        new_operations=summary.new_operations,
        replaces_snapshot=summary.replaces_snapshot,
    )


def _mapping(session: Session, mapping_id: int | None) -> ImportMapping | None:
    return None if mapping_id is None else get_or_404(session, ImportMapping, mapping_id)


def _lines(text: str) -> frozenset[int]:
    """`"4, 7"` -> `{4, 7}`."""
    try:
        return frozenset(int(part) for part in text.split(",") if part.strip())
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "skip_lines must be line numbers like 4,7"
        ) from exc


@router.post("/imports/preview", response_model=PreviewOut)
async def preview_import(
    file: Upload, session: SessionDep, mapping_id: MappingId = None
) -> PreviewOut:
    mapping = _mapping(session, mapping_id)
    content, filename = await _read_upload(file)
    try:
        preview = build_preview(session, content, filename, mapping)
    except ImportFileError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return _preview_out(preview)


@router.post("/imports", response_model=ImportBatchOut, status_code=status.HTTP_201_CREATED)
async def commit(
    file: Upload,
    session: SessionDep,
    settings: SettingsDep,
    mapping_id: MappingId = None,
    skip_invalid_rows: Annotated[bool, Form()] = False,
    skip_lines: Annotated[str, Form()] = "",
) -> Any:
    """`skip_lines`: comma-separated line numbers to leave out, e.g. near-duplicates."""
    mapping = _mapping(session, mapping_id)
    lines_to_skip = _lines(skip_lines)
    content, filename = await _read_upload(file)
    try:
        return commit_import(
            session,
            content,
            filename,
            settings.uploads_dir,
            mapping,
            skip_invalid_rows,
            lines_to_skip,
        )
    except ImportFileError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except ImportRejectedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.get("/imports", response_model=list[ImportBatchOut])
def list_imports(session: SessionDep) -> list[ImportBatch]:
    return list(session.scalars(select(ImportBatch).order_by(ImportBatch.id.desc())))


@router.get("/source-accounts", response_model=list[SourceAccountOut])
def list_source_accounts(session: SessionDep) -> list[SourceAccount]:
    return list(session.scalars(select(SourceAccount).order_by(SourceAccount.key)))


@router.put("/source-accounts/{key:path}", response_model=SourceAccountOut)
def map_source_account(key: str, body: SourceAccountIn, session: SessionDep) -> SourceAccount:
    """Map a statement target (e.g. `santander/CA/ARS`) to an account, for all later imports."""
    get_or_404(session, Account, body.account_id)
    source = session.scalar(select(SourceAccount).where(SourceAccount.key == key))
    if source is None:
        source = SourceAccount(key=key, account_id=body.account_id)
        session.add(source)
    else:
        source.account_id = body.account_id
    commit_or_409(session, "source account")
    return source


@router.delete("/source-accounts/{key:path}", status_code=status.HTTP_204_NO_CONTENT)
def unmap_source_account(key: str, session: SessionDep) -> None:
    source = session.scalar(select(SourceAccount).where(SourceAccount.key == key))
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no account mapped for {key}")
    session.delete(source)
    session.commit()
