"""The migrations must produce exactly the schema the models describe."""

from pathlib import Path

from alembic import command

from mis_finanzas.core.migrate import alembic_config, upgrade_to_head


def test_migrations_match_models(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'm.db'}"
    upgrade_to_head(url)
    # Raises if autogenerate would emit any operation.
    command.check(alembic_config(url))
