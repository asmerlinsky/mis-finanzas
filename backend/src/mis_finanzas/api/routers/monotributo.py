from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from mis_finanzas.api.common import get_or_404
from mis_finanzas.api.deps import SessionDep
from mis_finanzas.api.schemas import (
    InvoiceOut,
    MonotributoCategoryOut,
    MonotributoStatusOut,
    MonthAmountArsOut,
    ProfileIn,
    RecategorizationOut,
)
from mis_finanzas.core.money import from_cents
from mis_finanzas.ledger.models import ImportBatch
from mis_finanzas.monotributo import service
from mis_finanzas.monotributo.categories import Category
from mis_finanzas.monotributo.models import Invoice
from mis_finanzas.monotributo.records import INVOICE_TYPES

router = APIRouter(tags=["monotributo"])


def _category(category: Category | None) -> MonotributoCategoryOut | None:
    if category is None:
        return None
    return MonotributoCategoryOut(
        letter=category.letter,
        annual_cap=category.annual_cap,
        monthly_services=category.monthly_services,
    )


@router.get("/monotributo/status", response_model=MonotributoStatusOut)
def monotributo_status(session: SessionDep) -> MonotributoStatusOut:
    overview = service.overview(session, date.today())
    s = overview.status
    return MonotributoStatusOut(
        today=s.today,
        table_valid_from=s.table.valid_from,
        categories=[c for c in map(_category, s.table.categories) if c is not None],
        category=_category(s.category),
        window_start=s.last_12_months.start,
        window_end=s.last_12_months.end,
        income=s.income,
        usage=s.usage,
        level=s.level,
        margin=s.margin,
        next=RecategorizationOut(
            deadline=s.next.deadline,
            window_start=s.next.window.start,
            window_end=s.next.window.end,
            income=s.next.income,
            implied=_category(s.next.implied),
        ),
        monthly=[MonthAmountArsOut(month=m, ars=ars) for m, ars in overview.monthly],
    )


def _invoice_out(invoice: Invoice) -> InvoiceOut:
    return InvoiceOut(
        id=invoice.id,
        type_code=invoice.type_code,
        type_label=INVOICE_TYPES[invoice.type_code][0],
        number=f"{invoice.point_of_sale:05d}-{invoice.number_from:08d}",
        issued_on=invoice.issued_on,
        receiver_name=invoice.receiver_name,
        currency=invoice.currency,
        total=from_cents(invoice.total_cents),
        fx_rate=invoice.fx_rate,
        total_ars=from_cents(invoice.total_ars_cents),
        has_pdf=invoice.pdf_batch_id is not None,
    )


@router.get("/monotributo/invoices", response_model=list[InvoiceOut])
def list_invoices(session: SessionDep) -> list[InvoiceOut]:
    return [_invoice_out(i) for i in service.invoices(session)]


@router.get("/monotributo/invoices/{invoice_id}/pdf")
def invoice_pdf(invoice_id: int, session: SessionDep) -> FileResponse:
    invoice = get_or_404(session, Invoice, invoice_id)
    batch = session.get(ImportBatch, invoice.pdf_batch_id) if invoice.pdf_batch_id else None
    if batch is None or not Path(batch.stored_path).is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "this invoice has no PDF attached")
    return FileResponse(batch.stored_path, media_type="application/pdf")


@router.put("/monotributo/profile", status_code=status.HTTP_204_NO_CONTENT)
def set_profile(body: ProfileIn, session: SessionDep) -> None:
    try:
        service.set_category(session, body.category.strip().upper(), date.today())
    except service.UnknownCategoryError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
