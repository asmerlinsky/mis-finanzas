"""`uv run mis-finanzas` — start the server on the configured host and port."""

import uvicorn

from mis_finanzas.core.config import get_settings
from mis_finanzas.main import create_app


def main() -> None:
    settings = get_settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
