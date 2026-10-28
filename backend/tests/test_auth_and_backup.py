"""Login, the localhost-only rule without a password, and daily backups."""

import sqlite3
import stat
from collections.abc import Iterator
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from mis_finanzas.__main__ import exposure_error
from mis_finanzas.auth import service as auth
from mis_finanzas.auth.models import AuthSession
from mis_finanzas.core.backup import backed_up_on, run_backup
from mis_finanzas.core.config import Settings
from mis_finanzas.main import create_app

PASSWORD = "correct horse battery"


@pytest.fixture
def locked(settings: Settings) -> Iterator[TestClient]:
    """A client of an app with a password set."""
    auth.write_password(settings.auth_file, PASSWORD)
    with TestClient(create_app(settings)) as client:
        yield client


def _login(client: TestClient, password: str) -> int:
    return int(client.post("/api/auth/login", json={"password": password}).status_code)


def test_without_a_password_the_api_is_open(client: TestClient) -> None:
    assert client.get("/api/accounts").status_code == 200
    assert client.get("/api/auth/status").json() == {"required": False, "authenticated": True}


def test_every_api_route_needs_a_login(locked: TestClient) -> None:
    assert locked.get("/api/accounts").status_code == 401
    assert locked.get("/api/monotributo/status").status_code == 401
    assert locked.get("/api/health").json() == {"status": "ok"}
    assert locked.get("/api/auth/status").json() == {"required": True, "authenticated": False}
    assert _login(locked, "wrong password!") == 401
    assert _login(locked, PASSWORD) == 204
    assert locked.get("/api/accounts").status_code == 200
    assert locked.get("/api/auth/status").json()["authenticated"] is True
    assert locked.post("/api/auth/logout").status_code == 204
    assert locked.get("/api/accounts").status_code == 401


def test_session_cookie_is_http_only_and_same_site(locked: TestClient) -> None:
    response = locked.post("/api/auth/login", json={"password": PASSWORD})
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie


def test_only_a_hash_of_the_token_is_stored(locked: TestClient, session: Session) -> None:
    _login(locked, PASSWORD)
    token = locked.cookies[auth.COOKIE]
    [stored] = session.scalars(select(AuthSession.token_hash)).all()
    assert token not in stored and len(stored) == 64


def test_expired_sessions_are_refused(locked: TestClient, session: Session) -> None:
    _login(locked, PASSWORD)
    session.execute(update(AuthSession).values(expires_at=datetime(2000, 1, 1)))
    session.commit()
    assert locked.get("/api/accounts").status_code == 401


def test_repeated_wrong_passwords_lock_logins(locked: TestClient) -> None:
    for _ in range(5):
        assert _login(locked, "not the password") == 401
    assert _login(locked, PASSWORD) == 429  # even the right one, for a while


def test_throttle_forgets_old_failures() -> None:
    throttle = auth.LoginThrottle(limit=2, window=timedelta(minutes=15))
    start = datetime(2026, 1, 1, 12)
    throttle.failed(start)
    throttle.failed(start)
    assert throttle.locked(start + timedelta(minutes=1))
    assert not throttle.locked(start + timedelta(minutes=16))


def test_password_file(tmp_path: Path) -> None:
    file = tmp_path / "auth.json"
    with pytest.raises(ValueError):
        auth.write_password(file, "short")
    auth.write_password(file, PASSWORD)
    assert stat.S_IMODE(file.stat().st_mode) == 0o600
    assert PASSWORD not in file.read_text()
    assert auth.check_password(file, PASSWORD) and not auth.check_password(file, "nope")


def test_listening_beyond_localhost_needs_a_password(tmp_path: Path) -> None:
    exposed = Settings(data_dir=tmp_path, host="0.0.0.0")
    assert exposure_error(exposed) is not None
    assert exposure_error(Settings(data_dir=tmp_path, host="127.0.0.1")) is None
    auth.write_password(exposed.auth_file, PASSWORD)
    assert exposure_error(exposed) is None


def test_backup_copies_the_database_and_new_uploads(
    client: TestClient, settings: Settings, tmp_path: Path
) -> None:
    client.post(
        "/api/accounts",
        json={"name": "Caja", "institution": "Banco", "kind": "bank", "currency": "ARS"},
    )
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    (settings.uploads_dir / "abc.pdf").write_bytes(b"%PDF original")
    target = tmp_path / "backups"
    first = run_backup(settings.db_path, settings.uploads_dir, target, date(2026, 3, 1), 2)
    assert first.uploads_copied == 1 and backed_up_on(target, date(2026, 3, 1))
    with sqlite3.connect(first.database) as copy:
        assert copy.execute("SELECT name FROM accounts").fetchall() == [("Caja",)]
    for day in (2, 3):
        again = run_backup(settings.db_path, settings.uploads_dir, target, date(2026, 3, day), 2)
        assert again.uploads_copied == 0  # originals never change: copied once
    kept = sorted(p.name for p in (target / "db").iterdir())
    assert kept == ["finanzas-2026-03-02.db", "finanzas-2026-03-03.db"]
