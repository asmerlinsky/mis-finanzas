"""Description normalization, shared by rule matching and deduplication."""

import html
import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")
# A UTF-8 lead byte read as Latin-1 (`Ã`, `Â`) followed by a continuation byte.
_MOJIBAKE = re.compile("[\u00c2\u00c3][\u0080-\u00bf]")


def strip_invisible(text: str) -> str:
    """Drop control and format characters (`\x8d`, soft hyphens) that split words silently."""
    return "".join(
        ch for ch in text if ch in "\t\n\r" or unicodedata.category(ch) not in ("Cc", "Cf")
    )


def repair_mojibake(text: str) -> str:
    """`martÃ\xadn` -> `martín`: UTF-8 bytes that were decoded as Latin-1 somewhere.

    Text that doesn't decode cleanly is returned unchanged.
    """
    if not _MOJIBAKE.search(text):
        return text
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def normalize_description(text: str) -> str:
    """Uppercase, strip accents and collapse whitespace: `" Pagó  Rappi "` -> `"PAGO RAPPI"`.

    HTML entities are decoded and double-encoded accents repaired first: bank PDFs print
    `mart&#237;n` and `martÃ\xadn` literally.
    """
    repaired = strip_invisible(repair_mojibake(html.unescape(text)))
    decomposed = unicodedata.normalize("NFKD", repaired)
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _WHITESPACE.sub(" ", without_accents).strip().upper()
