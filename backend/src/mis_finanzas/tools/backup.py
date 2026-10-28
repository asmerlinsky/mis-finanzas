"""Back up the database and the uploaded originals now.

Usage: python -m mis_finanzas.tools.backup [folder]   (default: MIS_FINANZAS_BACKUP_DIR)
"""

import logging
import sys
from datetime import date
from pathlib import Path

from mis_finanzas.core.backup import run_backup
from mis_finanzas.core.config import get_settings
from mis_finanzas.core.logging import configure_logging

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    settings = get_settings()
    args = sys.argv[1:] if argv is None else argv
    target = Path(args[0]).expanduser() if args else settings.backup_dir
    if target is None:
        logger.error("No backup folder: pass one, or set MIS_FINANZAS_BACKUP_DIR")
        return 1
    if not settings.db_path.is_file():
        logger.error("No database to back up", extra={"data_dir": str(settings.data_dir)})
        return 1
    run_backup(
        settings.db_path, settings.uploads_dir, target, date.today(), settings.backup_keep_days
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
