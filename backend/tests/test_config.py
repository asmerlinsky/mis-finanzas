from pathlib import Path

import pytest

from mis_finanzas.core.config import Settings


def test_data_dir_from_env_expands_home(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIS_FINANZAS_DATA_DIR", "~/finanzas-test")
    settings = Settings(_env_file=None)
    assert settings.data_dir == Path.home() / "finanzas-test"
    assert settings.db_path == Path.home() / "finanzas-test" / "finanzas.db"


def test_defaults_bind_to_localhost_only() -> None:
    settings = Settings(_env_file=None)
    assert settings.host == "127.0.0.1"
    assert settings.public_hosts == ["api.argentinadatos.com", "data912.com"]
