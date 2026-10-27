from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from mis_finanzas.api.common import commit_or_409, get_or_404
from mis_finanzas.api.deps import SessionDep, SettingsDep
from mis_finanzas.api.schemas import (
    ImportBatchOut,
    MappingIn,
    MappingOut,
    PreviewOut,
    PreviewRowOut,
    RowErrorOut,
)
from mis_finanzas.importers.base import ImportFileError
from mis_finanzas.importers.models import ImportMapping
from mis_finanzas.importers.service import (
    ImportPreview,
    ImportRejectedError,
    build_preview,
    commit_import,
)
from mis_finanzas.ledger.models import Account, ImportBatch

router = APIRouter(tags=["imports"])

MAX_UPLOAD_BYTES = 20 * 1024 * 1024

Upload = Annotated[UploadFile, File()]
MappingId = Annotated[int, Form()]


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


def _preview_out(preview: ImportPreview) -> PreviewOut:
    rows = [
        PreviewRowOut(
            line_number=r.line_number,
            date=r.date,
            amount=r.amount,
            description=r.description,
            duplicate=r.duplicate,
            category_name=r.category.name if r.category else None,
            kind=r.kind,
        )
        for r in preview.rows
    ]
    errors = [RowErrorOut(line_number=e.line_number, message=e.message) for e in preview.errors]
    new_count = len(preview.new_rows)
    return PreviewOut(
        filename=preview.filename,
        already_imported=preview.already_imported,
        new_count=new_count,
        duplicate_count=len(rows) - new_count,
        rows=rows,
        errors=errors,
    )


@router.post("/imports/preview", response_model=PreviewOut)
async def preview_import(file: Upload, mapping_id: MappingId, session: SessionDep) -> PreviewOut:
    mapping = get_or_404(session, ImportMapping, mapping_id)
    content, filename = await _read_upload(file)
    try:
        preview = build_preview(session, mapping, content, filename)
    except ImportFileError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return _preview_out(preview)


@router.post("/imports", response_model=ImportBatchOut, status_code=status.HTTP_201_CREATED)
async def commit(
    file: Upload,
    mapping_id: MappingId,
    session: SessionDep,
    settings: SettingsDep,
    skip_invalid_rows: Annotated[bool, Form()] = False,
) -> Any:
    mapping = get_or_404(session, ImportMapping, mapping_id)
    content, filename = await _read_upload(file)
    try:
        return commit_import(
            session, mapping, content, filename, settings.uploads_dir, skip_invalid_rows
        )
    except ImportFileError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except ImportRejectedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.get("/imports", response_model=list[ImportBatchOut])
def list_imports(session: SessionDep) -> list[ImportBatch]:
    return list(session.scalars(select(ImportBatch).order_by(ImportBatch.id.desc())))
