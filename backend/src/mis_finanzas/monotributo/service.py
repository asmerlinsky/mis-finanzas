"""Reads and the one write the monotributo page needs: status, invoices, the category."""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from mis_finanzas.core.money import from_cents
from mis_finanzas.monotributo.categories import CategoryTable, load_tables, table_on
from mis_finanzas.monotributo.models import Invoice, MonotributoProfile
from mis_finanzas.monotributo.records import INVOICE_TYPES
from mis_finanzas.monotributo.status import (
    Projection,
    Status,
    compute_status,
    monthly_totals,
    project,
)

PROFILE_ID = 1


class UnknownCategoryError(ValueError):
    pass


@dataclass(frozen=True)
class ProjectionBasis:
    """What the projection assumes each month, in the latest invoice's currency."""

    amount: Decimal
    currency: str
    rate: Decimal  # pesos per unit: the latest invoice's in that currency (1 for pesos)
    manual: bool  # the owner's own amount; otherwise last month's invoicing
    last_month: str  # "YYYY-MM"
    last_month_amount: Decimal  # invoiced last month, in `currency`
    ask: bool  # last month differs from the owner's amount, and they haven't answered yet

    @property
    def monthly_ars(self) -> Decimal:
        return self.amount * self.rate


@dataclass(frozen=True)
class Overview:
    status: Status
    monthly: list[tuple[str, Decimal]]  # invoiced pesos per month
    basis: ProjectionBasis
    projection: Projection


def current_table(today: date) -> CategoryTable:
    return table_on(load_tables(), today)


def current_category(session: Session) -> str | None:
    profile = session.get(MonotributoProfile, PROFILE_ID)
    return profile.category if profile else None


def _profile(session: Session) -> MonotributoProfile:
    profile = session.get(MonotributoProfile, PROFILE_ID)
    if profile is None:
        profile = MonotributoProfile(id=PROFILE_ID)
        session.add(profile)
    return profile


def set_category(session: Session, letter: str, today: date) -> None:
    """Raises `UnknownCategoryError` for a letter not in the current table."""
    if current_table(today).get(letter) is None:
        raise UnknownCategoryError(f"category {letter!r} is not in the current table")
    _profile(session).category = letter
    session.commit()


def _last_month(today: date) -> str:
    return (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")


def projection_basis(session: Session, today: date) -> ProjectionBasis:
    """The owner's amount, or else last month's invoicing in the latest invoice's currency."""
    profile = session.get(MonotributoProfile, PROFILE_ID)
    listed = invoices(session)  # newest first
    manual = profile is not None and profile.projected_amount is not None
    currency = (profile.projected_currency if manual and profile else None) or (
        listed[0].currency if listed else "ARS"
    )
    same = [i for i in listed if i.currency == currency]
    rate = Decimal(1) if currency == "ARS" or not same else same[0].fx_rate
    last_month = _last_month(today)
    last = sum(
        (
            INVOICE_TYPES[i.type_code][1] * from_cents(i.total_cents)
            for i in same
            if i.issued_on.strftime("%Y-%m") == last_month
        ),
        Decimal(0),
    )
    own = profile.projected_amount if profile else None
    amount = own if own is not None else last  # an amount of 0 is the owner's too
    reviewed = profile.projection_reviewed if profile else None
    ask = manual and last != amount and reviewed != last_month
    return ProjectionBasis(max(amount, Decimal(0)), currency, rate, manual, last_month, last, ask)


def set_projection(session: Session, amount: Decimal, currency: str, today: date) -> None:
    """The owner's monthly amount; it also answers this month's question, if any."""
    profile = _profile(session)
    profile.projected_amount, profile.projected_currency = amount, currency
    profile.projection_reviewed = _last_month(today)
    session.commit()


def clear_projection(session: Session) -> None:
    """Back to projecting last month's invoicing."""
    profile = _profile(session)
    profile.projected_amount = profile.projected_currency = profile.projection_reviewed = None
    session.commit()


def invoices(session: Session) -> list[Invoice]:
    query = select(Invoice).order_by(Invoice.issued_on.desc(), Invoice.number_from.desc())
    return list(session.scalars(query))


def overview(session: Session, today: date) -> Overview:
    totals = [(i.issued_on, from_cents(i.total_ars_cents)) for i in invoices(session)]
    table, letter = current_table(today), current_category(session)
    basis = projection_basis(session, today)
    return Overview(
        status=compute_status(totals, table, letter, today),
        monthly=monthly_totals(totals),
        basis=basis,
        projection=project(totals, table, letter, today, basis.monthly_ars),
    )
