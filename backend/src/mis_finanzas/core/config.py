"""Runtime settings, read from `MIS_FINANZAS_*` environment variables or a `.env` file."""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DATA_DIR = Path.home() / ".local" / "share" / "mis-finanzas"


class Settings(BaseSettings):
    """All settings the app reads. Personal data lives only under `data_dir`."""

    model_config = SettingsConfigDict(env_prefix="MIS_FINANZAS_", env_file=".env", extra="ignore")

    data_dir: Path = DEFAULT_DATA_DIR
    host: str = "127.0.0.1"
    port: int = 8000
    # Only these hosts may be contacted, and only to download public data.
    public_hosts: list[str] = ["api.argentinadatos.com", "data912.com"]
    http_timeout_seconds: float = 15.0
    market_refresh_on_startup: bool = True
    frontend_dist: Path | None = None

    @field_validator("data_dir", "frontend_dist")
    @classmethod
    def _expand_home(cls, value: Path | None) -> Path | None:
        """`~/x` from an env var would otherwise become a literal `~` directory."""
        return value.expanduser() if value is not None else None

    @property
    def db_path(self) -> Path:
        return self.data_dir / "finanzas.db"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_path}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
