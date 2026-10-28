"""The migrations must produce exactly the schema the models describe."""

import re
from datetime import date
from pathlib import Path

from alembic import command
from sqlalchemy import create_engine, text

from mis_finanzas.core.migrate import alembic_config, upgrade_to_head
from mis_finanzas.ledger.dedup import fingerprint
from mis_finanzas.ledger.text import normalize_description


def test_migrations_match_models(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'm.db'}"
    upgrade_to_head(url)
    # Raises if autogenerate would emit any operation.
    command.check(alembic_config(url))


def test_0002_recomputes_fingerprints_without_losing_rows(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'm.db'}"
    command.upgrade(alembic_config(url), "0001")
    engine = create_engine(url)
    with engine.begin() as db:
        db.execute(text("INSERT INTO accounts VALUES (1, 'Banco', 'X', 'bank', 'ARS')"))
        for batch_id in (1, 2):
            db.execute(
                text(
                    "INSERT INTO import_batches (id, account_id, importer, importer_version, "
                    "filename, file_sha256, stored_path, rows_imported, rows_duplicate, "
                    f"rows_skipped) VALUES ({batch_id}, 1, 'generic_tabular', '1', 'f', "
                    f"'sha{batch_id}', 'p', 1, 0, 0)"
                )
            )
        # The same movement imported twice under the old, description-based rule.
        for tx_id, batch_id, description in ((1, 1, "COMPRA DIA"), (2, 2, "DIA COMPRA SUPER")):
            db.execute(
                text(
                    "INSERT INTO transactions (id, account_id, date, amount_cents, "
                    "description_raw, description_norm, kind, import_batch_id, fingerprint) VALUES "
                    f"({tx_id}, 1, '2026-01-05', -100000, '{description}', '{description}', "
                    f"'expense', {batch_id}, 'old{tx_id}')"
                )
            )
    upgrade_to_head(url)
    with engine.connect() as db:
        prints = db.execute(text("SELECT fingerprint FROM transactions ORDER BY id")).scalars()
        assert list(prints) == [
            fingerprint(1, date(2026, 1, 5), -100000, 0),
            fingerprint(1, date(2026, 1, 5), -100000, 1),  # kept, as the next occurrence
        ]


def test_0003_seeds_rendimientos_once_and_keeps_existing(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'm.db'}"
    command.upgrade(alembic_config(url), "0002")
    engine = create_engine(url)
    with engine.begin() as db:
        db.execute(text("INSERT INTO categories (name, kind) VALUES ('Rendimientos', NULL)"))
    command.upgrade(alembic_config(url), "0003")
    command.upgrade(alembic_config(url), "0003")
    with engine.connect() as db:
        categories = db.execute(text("SELECT name, kind FROM categories")).all()
        patterns = db.execute(text("SELECT pattern FROM category_rules ORDER BY pattern")).scalars()
        assert categories == [("Rendimientos", None)]  # the owner's own category is kept
        assert list(patterns) == ["INTERES POR SALDO", "RENDIMIENTOS"]


def test_0005_seeds_dividendos_as_income(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'm.db'}"
    upgrade_to_head(url)
    with create_engine(url).connect() as db:
        rows = db.execute(
            text(
                "SELECT c.kind, r.pattern FROM categories c "
                "JOIN category_rules r ON r.category_id = c.id WHERE c.name = 'Dividendos'"
            )
        ).all()
    assert rows == [("income", "DIVIDENDO")]


def test_0007_seeds_inversiones_for_trades_only(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'm.db'}"
    upgrade_to_head(url)
    with create_engine(url).connect() as db:
        rows = db.execute(
            text(
                "SELECT c.kind, r.match_type, r.pattern FROM categories c "
                "JOIN category_rules r ON r.category_id = c.id WHERE c.name = 'Inversiones'"
            )
        ).all()
    assert {(kind, match) for kind, match, _ in rows} == {("investment", "regex")}
    patterns = [re.compile(pattern) for _, _, pattern in rows]
    trade = normalize_description("Boleto / 1234567 / COMPRA / 2 / EJM / usd")
    subscription = normalize_description("Liquidación de Suscripción / 123456 / FONDO A")
    assert all(any(p.search(line) for p in patterns) for line in (trade, subscription))
    assert not any(p.search("COMPRA CON TARJETA DE DEBITO BOLETO") for p in patterns)
