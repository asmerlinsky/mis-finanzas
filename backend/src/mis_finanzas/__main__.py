"""`uv run mis-finanzas` — start the server on the configured host and port.

It refuses to listen beyond localhost until a login password is set (`mis-finanzas-password`):
the data must never be reachable without one.
"""

import logging
import sys

import uvicorn

from mis_finanzas.auth.service import login_required
from mis_finanzas.core.config import Settings, get_settings
from mis_finanzas.core.logging import configure_logging
from mis_finanzas.main import create_app

logger = logging.getLogger(__name__)


def exposure_error(settings: Settings) -> str | None:
    """Why the server must not start with these settings, if it mustn't."""
    if settings.is_local_only or login_required(settings.auth_file):
        return None
    return (
        f"refusing to listen on {settings.host} without a login password: "
        "run mis-finanzas-password first, or listen on 127.0.0.1"
    )


def main() -> None:
    configure_logging()
    settings = get_settings()
    error = exposure_error(settings)
    if error is not None:
        logger.error("Not starting", extra={"reason": error})
        sys.exit(2)
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
