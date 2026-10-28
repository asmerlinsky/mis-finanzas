"""Description normalization, shared by rule matching and deduplication."""

import html
import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")
# A UTF-8 lead byte read as Latin-1 (`Ã`, `Â`) followed by a continuation byte. Banks also
# lowercase such text afterwards, which turns the lead byte into `ã`/`â`.
_MOJIBAKE = re.compile("[\u00c2\u00c3\u00e2\u00e3][\u0080-\u00bf]")


def strip_invisible(text: str) -> str:
    """Drop control and format characters (`\x8d`, soft hyphens) that split words silently."""
    return "".join(
        ch for ch in text if ch in "\t\n\r" or unicodedata.category(ch) not in ("Cc", "Cf")
    )


def _repair_pair(match: re.Match[str]) -> str:
    pair = match.group()
    lead, continuation = pair[0], pair[1]
    try:
        repaired = (lead.upper() + continuation).encode("latin-1").decode("utf-8")
    except UnicodeDecodeError:
        return match.group()
    return repaired.lower() if lead.islower() else repaired


def repair_mojibake(text: str) -> str:
    """UTF-8 bytes that were decoded as Latin-1 somewhere: `martÃ\xadn` -> `martín`, and,
    lowercased after the damage, `MARTÍN` -> `martã\x8dn` -> `martín`.

    Each damaged pair is repaired on its own; anything else is left as is.
    """
    return _MOJIBAKE.sub(_repair_pair, text)


def clean_description(text: str) -> str:
    """A description fit to show: HTML entities decoded, double-encoded accents repaired,
    invisible characters dropped, spaces collapsed. Case and accents are kept."""
    repaired = strip_invisible(repair_mojibake(html.unescape(text)))
    return _WHITESPACE.sub(" ", repaired).strip()


def normalize_description(text: str) -> str:
    """Uppercase, strip accents and collapse whitespace: `" Pagó  Rappi "` -> `"PAGO RAPPI"`.

    HTML entities are decoded and double-encoded accents repaired first: bank PDFs print
    `mart&#237;n` and `martÃ\xadn` literally.
    """
    decomposed = unicodedata.normalize("NFKD", clean_description(text))
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _WHITESPACE.sub(" ", without_accents).strip().upper()
