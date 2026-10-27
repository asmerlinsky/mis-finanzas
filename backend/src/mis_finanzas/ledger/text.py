"""Description normalization, shared by rule matching and deduplication."""

import html
import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")


def normalize_description(text: str) -> str:
    """Uppercase, strip accents and collapse whitespace: `" Pagó  Rappi "` -> `"PAGO RAPPI"`.

    HTML entities are decoded first: some bank PDFs print `agust&#237;n` literally.
    """
    decomposed = unicodedata.normalize("NFKD", html.unescape(text))
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _WHITESPACE.sub(" ", without_accents).strip().upper()
