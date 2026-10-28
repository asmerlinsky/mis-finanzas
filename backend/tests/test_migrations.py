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


def test_0010_repairs_imported_descriptions(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'm.db'}"
    command.upgrade(alembic_config(url), "0009")
    engine = create_engine(url)
    damaged = "Transf. a mart&#227;\x8dn  gomez"  # MARTÍN, double-encoded, then lowercased
    with engine.begin() as db:
        db.execute(text("INSERT INTO accounts VALUES (1, 'Banco', 'X', 'bank', 'ARS')"))
        db.execute(
            text(
                "INSERT INTO transactions (id, account_id, date, amount_cents, description_raw, "
                "description_norm, kind, fingerprint) VALUES "
                "(1, 1, '2026-01-05', -100, :raw, 'TRANSF. A MARTAN GOMEZ', 'expense', 'f1'), "
                "(2, 1, '2026-01-06', -200, 'Pagó Rappi', 'PAGO RAPPI', 'expense', 'f2')"
            ),
            {"raw": damaged},
        )
    upgrade_to_head(url)
    with engine.connect() as db:
        rows = db.execute(
            text("SELECT description_raw, description_norm FROM transactions ORDER BY id")
        ).all()
    assert rows == [
        ("Transf. a martín gomez", "TRANSF. A MARTIN GOMEZ"),
        ("Pagó Rappi", "PAGO RAPPI"),  # already clean: untouched
    ]


def test_0011_seeds_starter_categories_once(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'm.db'}"
    command.upgrade(alembic_config(url), "0010")
    engine = create_engine(url)
    with engine.begin() as db:
        db.execute(text("INSERT INTO categories (name, kind) VALUES ('Salud', 'expense')"))
    upgrade_to_head(url)
    upgrade_to_head(url)
    with engine.connect() as db:
        names = db.execute(text("SELECT name, kind FROM categories ORDER BY name")).all()
        rules = db.execute(
            text(
                "SELECT count(*) FROM category_rules r JOIN categories c ON c.id = r.category_id "
                "WHERE c.name IN ('Supermercado', 'Transporte', 'Salud')"
            )
        ).scalar()
    assert ("Salud", "expense") in names  # the owner's own category is kept
    assert {"Supermercado", "Transporte", "Impuestos y comisiones", "Monotributo"} <= {
        n for n, _ in names
    }
    assert rules == 0  # names only: patterns come from the owner's data


def test_0014_takes_existing_dollar_sales_out_of_income_and_expense(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'm.db'}"
    command.upgrade(alembic_config(url), "0013")
    engine = create_engine(url)
    with engine.begin() as db:
        db.execute(text("INSERT INTO accounts VALUES (1, 'Banco', 'X', 'bank', 'ARS')"))
        db.execute(text("INSERT INTO categories (id, name, kind) VALUES (50, 'Mía', NULL)"))
        db.execute(
            text(
                "INSERT INTO transactions (id, account_id, date, amount_cents, description_raw, "
                "description_norm, kind, category_id, fingerprint) VALUES "
                "(1, 1, '2026-05-08', 100, 'x', 'LIQUIDACION TITULOS PUBLICOS CREDI', 'income', "
                "NULL, 'a'), "
                "(2, 1, '2026-05-08', -100, 'x', 'LIQUIDACION TITULOS DEBITO', 'expense', 50, 'b')"
            )
        )
    upgrade_to_head(url)
    with engine.connect() as db:
        rows = db.execute(
            text(
                "SELECT t.id, t.kind, c.name FROM transactions t "
                "LEFT JOIN categories c ON c.id = t.category_id ORDER BY t.id"
            )
        ).all()
    assert rows == [(1, "fx", "Cambio de moneda"), (2, "expense", "Mía")]  # owner's own kept
