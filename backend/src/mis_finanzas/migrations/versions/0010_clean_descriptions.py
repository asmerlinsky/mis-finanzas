"""Repair descriptions imported before the cleaning: HTML entities and double-encoded accents.

Banks print `agust&#227;&#141;n` (`AGUSTÍN`, encoded twice and then lowercased). Descriptions
were stored as printed, and their normalized form lost the letter (`AGUSTAN`). This rewrites
both columns with the cleaning as of this revision, frozen here so later changes to
`ledger/text.py` can't change what this migration did. Fingerprints don't use descriptions,
so deduplication is unaffected.

Revision ID: 0010
Revises: 0009
"""

import html
import re
import unicodedata
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_WHITESPACE = re.compile(r"\s+")
_MOJIBAKE = re.compile("[ÂÃâã][\u0080-¿]")


def _repair_pair(match: re.Match[str]) -> str:
    pair = match.group()
    lead, continuation = pair[0], pair[1]
    try:
        repaired = (lead.upper() + continuation).encode("latin-1").decode("utf-8")
    except UnicodeDecodeError:
        return match.group()
    return repaired.lower() if lead.islower() else repaired


def _clean(text: str) -> str:
    repaired = _MOJIBAKE.sub(_repair_pair, html.unescape(text))
    visible = "".join(
        ch for ch in repaired if ch in "\t\n\r" or unicodedata.category(ch) not in ("Cc", "Cf")
    )
    return _WHITESPACE.sub(" ", visible).strip()


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", _clean(text))
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _WHITESPACE.sub(" ", without_accents).strip().upper()


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, description_raw, description_norm FROM transactions"))
    update = sa.text(
        "UPDATE transactions SET description_raw = :raw, description_norm = :norm WHERE id = :id"
    )
    for tx_id, raw, norm in rows.all():
        cleaned, normalized = _clean(raw), _normalize(raw)
        if (cleaned, normalized) != (raw, norm):
            bind.execute(update, {"id": tx_id, "raw": cleaned, "norm": normalized})


def downgrade() -> None:
    """The printed text isn't kept anywhere else; the originals are in the stored uploads."""
