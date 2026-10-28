"""Reads and the one write the monotributo page needs: status, invoices, the category."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from mis_finanzas.core.money import from_cents
from mis_finanzas.monotributo.categories import CategoryTable, load_tables, table_on
from mis_finanzas.monotributo.models import Invoice, MonotributoProfile
from mis_finanzas.monotributo.status import Status, compute_status, monthly_totals

PROFILE_ID = 1


class UnknownCategoryError(ValueError):
    pass


@dataclass(frozen=True)
class Overview:
    status: Status
    monthly: list[tuple[str, Decimal]]  # invoiced pesos per month


def current_table(today: date) -> CategoryTable:
    return table_on(load_tables(), today)


def current_category(session: Session) -> str | None:
    profile = session.get(MonotributoProfile, PROFILE_ID)
    return profile.category if profile else None


def set_category(session: Session, letter: str, today: date) -> None:
    """Raises `UnknownCategoryError` for a letter not in the current table."""
    if current_table(today).get(letter) is None:
        raise UnknownCategoryError(f"category {letter!r} is not in the current table")
    profile = session.get(MonotributoProfile, PROFILE_ID)
    if profile is None:
        session.add(MonotributoProfile(id=PROFILE_ID, category=letter))
    else:
        profile.category = letter
    session.commit()


def invoices(session: Session) -> list[Invoice]:
    query = select(Invoice).order_by(Invoice.issued_on.desc(), Invoice.number_from.desc())
    return list(session.scalars(query))


def overview(session: Session, today: date) -> Overview:
    totals = [(i.issued_on, from_cents(i.total_ars_cents)) for i in invoices(session)]
    status = compute_status(totals, current_table(today), current_category(session), today)
    return Overview(status=status, monthly=monthly_totals(totals))
