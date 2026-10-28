"""Daily backup: a consistent copy of the SQLite database, and every uploaded original.

Layout under the backup folder:
- `db/finanzas-YYYY-MM-DD.db`: one copy per day, made with SQLite's online backup, so it is
  consistent even while the app writes. Copies beyond `keep_days` are deleted, oldest first.
- `uploads/<sha256><ext>`: the originals never change once stored, so each is copied once.

Point the folder at another disk, or a folder another tool syncs off the machine.
"""

import logging
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

PREFIX = "finanzas-"


@dataclass(frozen=True)
class BackupResult:
    database: Path
    uploads_copied: int
    pruned: int


def database_copy(target: Path, day: date) -> Path:
    return target / "db" / f"{PREFIX}{day.isoformat()}.db"


def backed_up_on(target: Path, day: date) -> bool:
    return database_copy(target, day).is_file()


def _copy_database(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(".partial")
    with sqlite3.connect(source) as src, sqlite3.connect(partial) as dst:
        src.backup(dst)
    partial.replace(destination)


def _copy_uploads(source: Path, destination: Path) -> int:
    if not source.is_dir():
        return 0
    destination.mkdir(parents=True, exist_ok=True)
    copied = 0
    for original in source.iterdir():
        if original.is_file() and not (destination / original.name).exists():
            shutil.copy2(original, destination / original.name)
            copied += 1
    return copied


def _prune(target: Path, keep_days: int) -> int:
    copies = sorted((target / "db").glob(f"{PREFIX}*.db"))
    old = copies[: max(0, len(copies) - keep_days)]
    for copy in old:
        copy.unlink()
    return len(old)


def run_backup(
    database: Path, uploads: Path, target: Path, day: date, keep_days: int
) -> BackupResult:
    """Raises `OSError` or `sqlite3.Error` when the copy can't be made."""
    copy = database_copy(target, day)
    _copy_database(database, copy)
    result = BackupResult(
        copy, _copy_uploads(uploads, target / "uploads"), _prune(target, keep_days)
    )
    logger.info(
        "Backup written",
        extra={"day": day.isoformat(), "uploads": result.uploads_copied, "pruned": result.pruned},
    )
    return result
