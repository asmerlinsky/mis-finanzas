"""Set (or change) the login password. Once set, every API request needs a login, and the
server may listen on addresses other than localhost. Changing it logs every browser out.

Usage: mis-finanzas-password    (asks for the password twice; nothing is echoed)
"""

import getpass
import logging
import sys

from mis_finanzas.auth import service as auth
from mis_finanzas.core.config import get_settings
from mis_finanzas.core.db import make_engine, make_session_factory
from mis_finanzas.core.logging import configure_logging
from mis_finanzas.core.migrate import upgrade_to_head

logger = logging.getLogger(__name__)


def main() -> int:
    configure_logging()
    settings = get_settings()
    password = getpass.getpass("New password: ")
    if password != getpass.getpass("Repeat it: "):
        logger.error("The passwords don't match; nothing changed")
        return 1
    try:
        auth.write_password(settings.auth_file, password)
    except ValueError as exc:
        logger.error("Password not set", extra={"error": str(exc)})
        return 1
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    upgrade_to_head(settings.database_url)
    with make_session_factory(make_engine(settings.database_url))() as session:
        ended = auth.end_all_sessions(session)
    logger.info("Password set", extra={"sessions_ended": ended})
    return 0


if __name__ == "__main__":
    sys.exit(main())
