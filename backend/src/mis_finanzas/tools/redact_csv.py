"""Redact a `.csv` export into a `.csv` sample (rules in `tools.redaction`).

The delimiter and encoding are kept, so the sample parses exactly like the original.
"""

import codecs
import csv
import io
import logging
import random
from pathlib import Path

from mis_finanzas.tools.redaction import (
    MAX_ATTEMPTS,
    Redactor,
    check_paths,
    leak_error,
    text_leaks,
)

logger = logging.getLogger(__name__)

ENCODINGS = ("utf-8-sig", "cp1252")


def _decode(content: bytes) -> tuple[str, str]:
    """Text and the encoding to write it back with (a byte-order mark only if it had one)."""
    for encoding in ENCODINGS:
        try:
            text = content.decode(encoding)
        except UnicodeDecodeError:
            continue
        if encoding == "utf-8-sig" and not content.startswith(codecs.BOM_UTF8):
            encoding = "utf-8"
        return text, encoding
    raise ValueError("file is not UTF-8 or Windows-1252 text")


def _delimiter(text: str) -> str:
    try:
        return csv.Sniffer().sniff(text[:4096], delimiters=";,\t|").delimiter
    except csv.Error:
        return ","


def redact_rows(rows: list[list[str]], redactor: Redactor) -> list[list[str]]:
    return [[redactor.text(cell) for cell in row] for row in rows]


def _write(rows: list[list[str]], delimiter: str) -> str:
    buffer = io.StringIO()
    csv.writer(buffer, delimiter=delimiter, lineterminator="\n").writerows(rows)
    return buffer.getvalue()


def redact_csv_file(
    source: Path, target: Path, names: list[str], rng: random.Random | None = None
) -> None:
    """Write a redacted copy of `source` to `target`, or raise `LeakError` and write nothing."""
    check_paths(source, target)
    rng = rng or random.Random()
    text, encoding = _decode(source.read_bytes())
    delimiter = _delimiter(text)
    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    cells = [cell for row in rows for cell in row]
    leaks: list[str] = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        redacted = redact_rows(rows, Redactor(names, rng))
        leaks = text_leaks(cells, [cell for row in redacted for cell in row], names)
        if not leaks:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(_write(redacted, delimiter).encode(encoding))
            logger.info("Redacted copy saved", extra={"target": str(target), "attempt": attempt})
            return
    raise leak_error(leaks)
