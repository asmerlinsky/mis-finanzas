"""Single-user login: one password (its argon2 hash in the data dir) and session tokens.

- The password is set with `mis-finanzas-password`; until then the app only listens on
  localhost and needs no login.
- A login returns a random token for a cookie; the database keeps only its sha256, so a copy
  of the database (a backup) can't be used to log in.
- Repeated wrong passwords lock logins for a while (`LoginThrottle`).
"""

import hashlib
import json
import logging
import os
import secrets
from collections import deque
from datetime import UTC, datetime, timedelta
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from mis_finanzas.auth.models import AuthSession

logger = logging.getLogger(__name__)

COOKIE = "mf_session"
MIN_PASSWORD_LENGTH = 12
_hasher = PasswordHasher()


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def login_required(auth_file: Path) -> bool:
    return auth_file.is_file()


def write_password(auth_file: Path, password: str) -> None:
    """Raises `ValueError` for a password shorter than `MIN_PASSWORD_LENGTH`."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"the password needs at least {MIN_PASSWORD_LENGTH} characters")
    auth_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = auth_file.with_suffix(".tmp")
    temporary.write_text(json.dumps({"argon2": _hasher.hash(password)}))
    os.chmod(temporary, 0o600)
    temporary.replace(auth_file)


def check_password(auth_file: Path, password: str) -> bool:
    try:
        stored = json.loads(auth_file.read_text())["argon2"]
        return _hasher.verify(stored, password)
    except (OSError, KeyError, ValueError, VerificationError, InvalidHashError):
        return False


def start_session(session: Session, days: int) -> str:
    """A new session's token (for the cookie). Also drops expired sessions."""
    now = _now()
    session.execute(delete(AuthSession).where(AuthSession.expires_at <= now))
    token = secrets.token_urlsafe(32)
    session.add(
        AuthSession(
            token_hash=_digest(token), created_at=now, expires_at=now + timedelta(days=days)
        )
    )
    session.commit()
    return token


def session_valid(session: Session, token: str | None) -> bool:
    if not token:
        return False
    query = select(AuthSession.id).where(
        AuthSession.token_hash == _digest(token), AuthSession.expires_at > _now()
    )
    return session.scalar(query) is not None


def end_session(session: Session, token: str | None) -> None:
    if token:
        session.execute(delete(AuthSession).where(AuthSession.token_hash == _digest(token)))
        session.commit()


def end_all_sessions(session: Session) -> int:
    """After a password change: everyone logs in again. Returns how many were ended."""
    ended = session.scalar(select(func.count()).select_from(AuthSession)) or 0
    session.execute(delete(AuthSession))
    session.commit()
    return ended


class LoginThrottle:
    """After `limit` wrong passwords within `window`, refuse logins until the oldest expires."""

    def __init__(self, limit: int = 5, window: timedelta = timedelta(minutes=15)) -> None:
        self.limit, self.window = limit, window
        self._failures: deque[datetime] = deque()

    def _forget_old(self, now: datetime) -> None:
        while self._failures and now - self._failures[0] > self.window:
            self._failures.popleft()

    def locked(self, now: datetime | None = None) -> bool:
        now = now or _now()
        self._forget_old(now)
        return len(self._failures) >= self.limit

    def failed(self, now: datetime | None = None) -> None:
        self._failures.append(now or _now())
        logger.warning("Login failed", extra={"recent_failures": len(self._failures)})

    def succeeded(self) -> None:
        self._failures.clear()
