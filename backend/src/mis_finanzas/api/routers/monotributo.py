from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from mis_finanzas.api.common import get_or_404
from mis_finanzas.api.deps import SessionDep
from mis_finanzas.api.schemas import (
    InvoiceOut,
    InvoicePaymentOut,
    MonotributoCategoryOut,
    MonotributoStatusOut,
    MonthAmountArsOut,
    PaymentLinkIn,
    ProfileIn,
    ProjectedMonthOut,
    ProjectionIn,
    ProjectionOut,
    RecategorizationOut,
)
from mis_finanzas.core.money import from_cents
from mis_finanzas.ledger.models import Currency, ImportBatch, Transaction
from mis_finanzas.monotributo import payments, service
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
        projection=_projection_out(overview),
    )


def _projection_out(overview: service.Overview) -> ProjectionOut:
    basis, projected = overview.basis, overview.projection
    return ProjectionOut(
        amount=basis.amount,
        currency=Currency(basis.currency),
        rate=basis.rate,
        manual=basis.manual,
        last_month=basis.last_month,
        last_month_amount=basis.last_month_amount,
        ask=basis.ask,
        monthly_ars=basis.monthly_ars,
        months=[
            ProjectedMonthOut(
                month=m.month, invoiced=m.invoiced, rolling=m.rolling, usage=m.usage, level=m.level
            )
            for m in projected.months
        ],
        first_over=projected.first_over,
        recategorization_income=projected.recategorization_income,
        implied=_category(projected.implied),
    )


@router.put("/monotributo/projection", status_code=status.HTTP_204_NO_CONTENT)
def set_projection(body: ProjectionIn, session: SessionDep) -> None:
    """The owner's monthly amount; also answers whether to update it after a different month."""
    service.set_projection(session, body.amount, body.currency.value, date.today())


@router.delete("/monotributo/projection", status_code=status.HTTP_204_NO_CONTENT)
def clear_projection(session: SessionDep) -> None:
    """Back to projecting last month's invoicing."""
    service.clear_projection(session)


def _payment_out(invoice: Invoice, tx: Transaction | None) -> InvoicePaymentOut | None:
    if tx is None:
        return None
    return InvoicePaymentOut(
        transaction_id=tx.id,
        date=tx.date,
        amount=from_cents(tx.amount_cents),
        currency=tx.account.currency,
        account_name=tx.account.name,
        description=tx.description_raw,
        exact=tx.amount_cents == invoice.total_cents,
    )


def _invoice_out(
    invoice: Invoice, payment: Transaction | None, suggestion: Transaction | None
) -> InvoiceOut:
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
        source=invoice.source,
        payment=_payment_out(invoice, payment),
        suggestion=_payment_out(invoice, suggestion),
    )


@router.get("/monotributo/invoices", response_model=list[InvoiceOut])
def list_invoices(session: SessionDep) -> list[InvoiceOut]:
    invoices = service.invoices(session)
    suggested = payments.suggestions(session, invoices)
    return [
        _invoice_out(
            i,
            session.get(Transaction, i.payment_transaction_id)
            if i.payment_transaction_id
            else None,
            suggested.get(i.id),
        )
        for i in invoices
    ]


@router.get("/monotributo/invoices/{invoice_id}/candidates", response_model=list[InvoicePaymentOut])
def payment_candidates(invoice_id: int, session: SessionDep) -> list[InvoicePaymentOut]:
    """Movements that could have paid the invoice, the likeliest first."""
    invoice = get_or_404(session, Invoice, invoice_id)
    found = [_payment_out(invoice, c.transaction) for c in payments.candidates(session, invoice)]
    return [c for c in found if c is not None]


@router.put("/monotributo/invoices/{invoice_id}/payment", status_code=status.HTTP_204_NO_CONTENT)
def link_payment(invoice_id: int, body: PaymentLinkIn, session: SessionDep) -> None:
    invoice = get_or_404(session, Invoice, invoice_id)
    tx = get_or_404(session, Transaction, body.transaction_id)
    try:
        payments.link(session, invoice, tx)
    except payments.PaymentLinkError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@router.delete("/monotributo/invoices/{invoice_id}/payment", status_code=status.HTTP_204_NO_CONTENT)
def unlink_payment(invoice_id: int, session: SessionDep) -> None:
    payments.unlink(session, get_or_404(session, Invoice, invoice_id))


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
