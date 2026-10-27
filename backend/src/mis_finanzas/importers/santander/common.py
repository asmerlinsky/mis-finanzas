"""Helpers shared by the Santander importers."""

import re
from datetime import date, datetime
from decimal import Decimal

from mis_finanzas.importers.amounts import money_in_text
from mis_finanzas.importers.pdf_layout import Line, lines, visible
from mis_finanzas.importers.pdf_words import PageWords

CURRENCIES = {"pesos": "ARS", "dólares": "USD"}
# Page numbers print as `5 - 30` at the foot of every page.
PAGE_NUMBER = re.compile(r"^\d+ - \d+$")
_SHORT_DATE = re.compile(r"^\d{2}/\d{2}/\d{2}$")


def parse_date(text: str) -> date:
    """`31/08/26` or `31/08/2026`. Raises `ValueError` otherwise."""
    text = text.strip()
    fmt = "%d/%m/%y" if _SHORT_DATE.match(text) else "%d/%m/%Y"
    return datetime.strptime(text, fmt).date()


def target(product: str, currency: str) -> str:
    """`santander/CA/ARS`, `santander/visa/USD`."""
    return f"santander/{product}/{currency}"


def page_lines(page: PageWords) -> list[Line]:
    return lines(visible(page.words))


def amounts_by_currency(text: str) -> dict[str, Decimal]:
    """`Saldo total $ 1,00 U$S 2,00` -> {"ARS": 1.00, "USD": 2.00}."""
    found: dict[str, Decimal] = {}
    for money in money_in_text(text):
        if money.currency is not None:
            found.setdefault(money.currency, money.amount)
    return found
