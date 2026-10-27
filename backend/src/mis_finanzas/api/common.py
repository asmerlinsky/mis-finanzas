"""Shared helpers for routers."""

import logging

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mis_finanzas.core.db import Base

logger = logging.getLogger(__name__)


def get_or_404[T: Base](session: Session, model: type[T], item_id: int) -> T:
    item = session.get(model, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{model.__name__} {item_id} not found")
    return item


def commit_or_409(session: Session, what: str) -> None:
    """Commit; a unique or foreign-key violation becomes a 409 for the caller."""
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        logger.info("Integrity conflict", extra={"entity": what, "error": str(exc.orig)})
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"{what} conflicts with existing data"
        ) from exc
