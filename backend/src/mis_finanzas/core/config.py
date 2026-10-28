"""Runtime settings, read from `MIS_FINANZAS_*` environment variables or a `.env` file."""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DATA_DIR = Path.home() / ".local" / "share" / "mis-finanzas"
LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


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
    # Login: a session lasts this long; mark the cookie Secure when served over HTTPS
    # (e.g. behind `tailscale serve`).
    session_days: int = 30
    cookie_secure: bool = False
    # Daily backups go here when set: the database and the uploaded originals.
    backup_dir: Path | None = None
    backup_keep_days: int = 14

    @field_validator("data_dir", "frontend_dist", "backup_dir")
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
    def auth_file(self) -> Path:
        """The login password's argon2 hash; login is required once it exists."""
        return self.data_dir / "auth.json"

    @property
    def is_local_only(self) -> bool:
        return self.host in LOCAL_HOSTS

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_path}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
