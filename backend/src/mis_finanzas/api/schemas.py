"""Request and response bodies. Amounts are `Decimal`, serialized as strings to stay exact."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from mis_finanzas.importers.tabular import TabularMapping
from mis_finanzas.ledger.models import (
    AccountKind,
    AmountSign,
    Currency,
    MatchType,
    TransactionKind,
)


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class AccountIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    institution: str = Field(min_length=1, max_length=100)
    kind: AccountKind
    currency: Currency


class AccountOut(OrmModel, AccountIn):
    id: int


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    kind: TransactionKind | None = None


class CategoryOut(OrmModel, CategoryIn):
    id: int


class RuleIn(BaseModel):
    category_id: int
    pattern: str = Field(min_length=1, max_length=200)
    match_type: MatchType = MatchType.CONTAINS
    account_id: int | None = None
    sign: AmountSign = AmountSign.ANY
    priority: int = 100


class RuleOut(OrmModel, RuleIn):
    id: int


class TransactionOut(BaseModel):
    id: int
    account_id: int
    account_name: str
    currency: Currency
    date: date
    amount: Decimal
    description: str
    category_id: int | None
    category_name: str | None
    kind: TransactionKind
    transfer_pair_id: int | None
    import_batch_id: int | None


class TransactionPage(BaseModel):
    items: list[TransactionOut]
    total: int


class TransactionPatch(BaseModel):
    category_id: int | None


class TransferCandidateOut(BaseModel):
    outgoing: TransactionOut
    incoming: TransactionOut
    days_apart: int


class TransferLinkIn(BaseModel):
    outgoing_id: int
    incoming_id: int


class MappingIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    account_id: int
    config: TabularMapping


class MappingOut(MappingIn):
    id: int


class PreviewRowOut(BaseModel):
    line_number: int
    date: date
    amount: Decimal
    description: str
    duplicate: bool
    category_name: str | None
    kind: TransactionKind


class RowErrorOut(BaseModel):
    line_number: int
    message: str


class PreviewOut(BaseModel):
    filename: str
    already_imported: bool
    new_count: int
    duplicate_count: int
    rows: list[PreviewRowOut]
    errors: list[RowErrorOut]


class ImportBatchOut(OrmModel):
    id: int
    account_id: int
    importer: str
    filename: str
    rows_imported: int
    rows_duplicate: int
    rows_skipped: int


class MonthSummaryOut(BaseModel):
    month: str
    income_ars: Decimal
    income_usd: Decimal
    expense_ars: Decimal
    expense_usd: Decimal
    net_ars: Decimal
    net_usd: Decimal
    missing_rate: int


class CategoryTotalOut(BaseModel):
    category: str
    ars: Decimal
    usd: Decimal
    missing_rate: int


class MarketStatusOut(BaseModel):
    latest_rate_date: date | None
    latest_rate: Decimal | None
    stale: bool
