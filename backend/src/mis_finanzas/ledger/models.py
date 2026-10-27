"""Ledger tables: accounts, categories, rules, transactions and the imports that created them."""

import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mis_finanzas.core.db import Base, str_enum


class AccountKind(enum.StrEnum):
    BANK = "bank"
    CARD = "card"
    WALLET = "wallet"
    BROKER = "broker"


class Currency(enum.StrEnum):
    ARS = "ARS"
    USD = "USD"


class TransactionKind(enum.StrEnum):
    INCOME = "income"
    EXPENSE = "expense"
    TRANSFER = "transfer"
    FX = "fx"
    INVESTMENT = "investment"


class MatchType(enum.StrEnum):
    CONTAINS = "contains"
    REGEX = "regex"


class AmountSign(enum.StrEnum):
    ANY = "any"
    DEBIT = "debit"
    CREDIT = "credit"


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    institution: Mapped[str] = mapped_column(String(100))
    kind: Mapped[AccountKind] = mapped_column(str_enum(AccountKind))
    currency: Mapped[Currency] = mapped_column(str_enum(Currency))


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    # When set, a transaction in this category takes this kind (e.g. "Compra MEP" -> fx).
    kind: Mapped[TransactionKind | None] = mapped_column(str_enum(TransactionKind), default=None)


class CategoryRule(Base):
    __tablename__ = "category_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    pattern: Mapped[str] = mapped_column(String(200))
    match_type: Mapped[MatchType] = mapped_column(str_enum(MatchType), default=MatchType.CONTAINS)
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), default=None
    )
    sign: Mapped[AmountSign] = mapped_column(str_enum(AmountSign), default=AmountSign.ANY)
    priority: Mapped[int] = mapped_column(Integer, default=100)


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    importer: Mapped[str] = mapped_column(String(100))
    importer_version: Mapped[str] = mapped_column(String(20))
    filename: Mapped[str] = mapped_column(String(255))
    file_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    stored_path: Mapped[str] = mapped_column(String(500))
    rows_imported: Mapped[int] = mapped_column(Integer)
    rows_duplicate: Mapped[int] = mapped_column(Integer)
    rows_skipped: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    description_raw: Mapped[str] = mapped_column(String(500))
    description_norm: Mapped[str] = mapped_column(String(500))
    kind: Mapped[TransactionKind] = mapped_column(str_enum(TransactionKind))
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), default=None
    )
    import_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_batches.id"), default=None
    )
    transfer_pair_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL"), default=None
    )
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True)

    account: Mapped[Account] = relationship(lazy="joined")
    category: Mapped[Category | None] = relationship(lazy="joined")
