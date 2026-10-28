"""ARCA's category tables, from `categories.json` (edited by hand when ARCA updates them)."""

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from importlib import resources


@dataclass(frozen=True)
class Category:
    letter: str
    annual_cap: Decimal  # gross income over 12 months
    monthly_services: Decimal  # monthly payment for services


@dataclass(frozen=True)
class CategoryTable:
    valid_from: date
    categories: tuple[Category, ...]  # A first

    def get(self, letter: str) -> Category | None:
        return next((c for c in self.categories if c.letter == letter), None)

    def for_income(self, income: Decimal) -> Category | None:
        """The lowest category whose cap covers `income`; None above the highest."""
        return next((c for c in self.categories if income <= c.annual_cap), None)


def _table(raw: dict[str, object]) -> CategoryTable:
    rows = raw["categories"]
    if not isinstance(rows, list):
        raise ValueError("categories must be a list")
    categories = tuple(
        Category(r["letter"], Decimal(r["annual_cap"]), Decimal(r["monthly_services"]))
        for r in rows
    )
    return CategoryTable(date.fromisoformat(str(raw["valid_from"])), categories)


def load_tables(text: str | None = None) -> list[CategoryTable]:
    """Oldest first. Raises `ValueError` (or `KeyError`) on a malformed file."""
    if text is None:
        text = resources.files(__package__).joinpath("categories.json").read_text("utf-8")
    tables = sorted((_table(t) for t in json.loads(text)["tables"]), key=lambda t: t.valid_from)
    if not tables:
        raise ValueError("no category tables")
    return tables


def table_on(tables: list[CategoryTable], day: date) -> CategoryTable:
    """The table in force on `day`: the latest that started on or before it (else the oldest)."""
    current = [t for t in tables if t.valid_from <= day]
    return current[-1] if current else tables[0]
