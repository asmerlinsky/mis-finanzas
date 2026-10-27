"""Logging setup. Messages never include descriptions or amounts from personal data."""

import logging

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"

# Attributes every LogRecord has; anything else on a record came from `extra=`.
_STANDARD_ATTRIBUTES = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


class ContextFormatter(logging.Formatter):
    """Appends `extra={...}` fields as sorted `key=value` pairs, so context reaches the line."""

    def format(self, record: logging.LogRecord) -> str:
        line = super().format(record)
        extras = {k: v for k, v in record.__dict__.items() if k not in _STANDARD_ATTRIBUTES}
        if not extras:
            return line
        return line + " " + " ".join(f"{k}={v}" for k, v in sorted(extras.items()))


def configure_logging(level: int = logging.INFO) -> None:
    """Idempotent: does nothing if the root logger already has handlers."""
    handler = logging.StreamHandler()
    handler.setFormatter(ContextFormatter(LOG_FORMAT))
    logging.basicConfig(level=level, handlers=[handler])
