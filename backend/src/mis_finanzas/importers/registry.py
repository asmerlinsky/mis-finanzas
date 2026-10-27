"""Dedicated importers: each one recognizes its own statement format by content.

A file import needs no column mapping when exactly one importer recognizes it. PDFs are
turned into positioned words once (`importers.pdf_words`) and offered to page importers, so
the same importer also runs on the redacted JSON samples in `samples/`.
"""

import logging
from dataclasses import dataclass
from pathlib import PurePath
from typing import Protocol

from mis_finanzas.importers.base import ImportFileError, ParseResult
from mis_finanzas.importers.pdf_words import PageWords, extract_pages

logger = logging.getLogger(__name__)


class FileImporter(Protocol):
    """Reads a file's bytes (CSV, Excel)."""

    name: str
    version: str

    def detect(self, filename: str, content: bytes) -> bool: ...

    def parse(self, content: bytes, filename: str) -> ParseResult: ...


class PageImporter(Protocol):
    """Reads a PDF's positioned words."""

    name: str
    version: str

    def detect_pages(self, pages: list[PageWords]) -> bool: ...

    def parse_pages(self, pages: list[PageWords]) -> ParseResult: ...


@dataclass(frozen=True)
class Parsed:
    importer: str
    version: str
    result: ParseResult


_FILE_IMPORTERS: list[FileImporter] = []
_PAGE_IMPORTERS: list[PageImporter] = []


def register_file_importer(importer: FileImporter) -> None:
    _FILE_IMPORTERS.append(importer)


def register_page_importer(importer: PageImporter) -> None:
    _PAGE_IMPORTERS.append(importer)


def _detects_file(importer: FileImporter, filename: str, content: bytes) -> bool:
    try:
        return importer.detect(filename, content)
    except Exception as exc:  # a detector must never break detection for the others
        logger.warning(
            "Importer detection failed", extra={"importer": importer.name, "error": str(exc)}
        )
        return False


def _detects_pages(importer: PageImporter, pages: list[PageWords]) -> bool:
    try:
        return importer.detect_pages(pages)
    except Exception as exc:  # same as above
        logger.warning(
            "Importer detection failed", extra={"importer": importer.name, "error": str(exc)}
        )
        return False


def _ambiguous(names: list[str]) -> ImportFileError:
    return ImportFileError(f"several importers recognize this file: {', '.join(names)}")


def parse_pages(pages: list[PageWords]) -> Parsed | None:
    """Parse with the one page importer that recognizes `pages`; None if none does."""
    matches = [i for i in _PAGE_IMPORTERS if _detects_pages(i, pages)]
    if len(matches) > 1:
        raise _ambiguous([i.name for i in matches])
    if not matches:
        return None
    return Parsed(matches[0].name, matches[0].version, matches[0].parse_pages(pages))


def parse_file(filename: str, content: bytes) -> Parsed | None:
    """Parse with the one importer that recognizes the file; None if none does.

    Raises `ImportFileError` when several importers claim it, or a PDF can't be read.
    """
    if PurePath(filename).suffix.lower() == ".pdf":
        return parse_pages(extract_pages(content)) if _PAGE_IMPORTERS else None
    matches = [i for i in _FILE_IMPORTERS if _detects_file(i, filename, content)]
    if len(matches) > 1:
        raise _ambiguous([i.name for i in matches])
    if not matches:
        return None
    return Parsed(matches[0].name, matches[0].version, matches[0].parse(content, filename))
