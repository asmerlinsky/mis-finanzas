"""PDF → positioned words. The single extraction step shared by PDF parsers and redaction.

Parsers are pure functions over `PageWords`, so redacted JSON samples (`dump_pages`) and live
PDFs (`extract_pages`) feed them the same structure. Overlapping duplicate characters (bold
emulated by drawing text twice) are collapsed before words are formed.
"""

import io
import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pdfplumber

from mis_finanzas.importers.base import ImportFileError

logger = logging.getLogger(__name__)

SAMPLE_FORMAT = "mis-finanzas/pdf-words"
SAMPLE_VERSION = 1


@dataclass(frozen=True)
class Word:
    text: str
    x0: float
    top: float
    x1: float
    bottom: float
    fontname: str
    size: float


@dataclass(frozen=True)
class PageWords:
    number: int
    width: float
    height: float
    words: list[Word]


def _word(raw: dict[str, Any]) -> Word:
    return Word(
        text=str(raw["text"]),
        x0=round(float(raw["x0"]), 2),
        top=round(float(raw["top"]), 2),
        x1=round(float(raw["x1"]), 2),
        bottom=round(float(raw["bottom"]), 2),
        fontname=str(raw.get("fontname", "")),
        size=round(float(raw.get("size", 0)), 2),
    )


def extract_pages(content: bytes, password: str | None = None) -> list[PageWords]:
    """Raises `ImportFileError` when the file isn't a readable PDF (or the password is wrong)."""
    try:
        pdf = pdfplumber.open(io.BytesIO(content), password=password)
    except Exception as exc:
        raise ImportFileError(f"could not open PDF (encrypted or damaged?): {exc!r}") from exc
    with pdf:
        pages = []
        for page in pdf.pages:
            raw_words = page.dedupe_chars().extract_words(extra_attrs=["fontname", "size"])
            pages.append(
                PageWords(
                    number=page.page_number,
                    width=round(float(page.width), 2),
                    height=round(float(page.height), 2),
                    words=[_word(w) for w in raw_words],
                )
            )
    logger.info(
        "PDF words extracted",
        extra={"pages": len(pages), "words": sum(len(p.words) for p in pages)},
    )
    return pages


def dump_pages(pages: list[PageWords]) -> str:
    payload = {
        "format": SAMPLE_FORMAT,
        "version": SAMPLE_VERSION,
        "pages": [asdict(page) for page in pages],
    }
    return json.dumps(payload, ensure_ascii=False, indent=1)


def load_pages(path: Path) -> list[PageWords]:
    """Read a sample written by `dump_pages`, e.g. a redacted statement in `samples/`."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("format") != SAMPLE_FORMAT or payload.get("version") != SAMPLE_VERSION:
        raise ImportFileError(f"{path.name} is not a {SAMPLE_FORMAT} v{SAMPLE_VERSION} sample")
    return [
        PageWords(
            number=p["number"],
            width=p["width"],
            height=p["height"],
            words=[Word(**w) for w in p["words"]],
        )
        for p in payload["pages"]
    ]
