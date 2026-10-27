"""Redact a PDF statement into a JSON sample of positioned words (rules in `tools.redaction`).

The PDF itself is never edited: words are extracted the way parsers read them
(`importers.pdf_words`), redacted, and saved as JSON. Besides the shared identifier and name
checks, every word with 4+ digits must have changed in place.
"""

import logging
import random
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from mis_finanzas.importers.pdf_words import PageWords, dump_pages, extract_pages
from mis_finanzas.tools.pdf_columns import (
    KEEP_WORDS,
    ColumnPlan,
    ColumnSpec,
    apply_columns,
    column_leaks,
    plan_columns,
)
from mis_finanzas.tools.redaction import (
    DATE_TEXT,
    MASK,
    MAX_ATTEMPTS,
    Redactor,
    check_paths,
    compact_text,
    leak_error,
    text_leaks,
)

logger = logging.getLogger(__name__)

MIN_CHECKED_DIGITS = 4


def mask_name_sequences(texts: list[str], names: list[str]) -> list[str]:
    """Replace words spelling a name with `XXXX`: a run of consecutive words (`Juana`,
    `Pérez,`) or a single word with the name run together (`JuanaPérez`)."""
    masked = list(texts)
    tokens = [compact_text(t) for t in texts]
    for name in names:
        parts = [p for p in (compact_text(part) for part in name.split()) if p]
        masked = [
            MASK if parts and token == "".join(parts) else text
            for token, text in zip(tokens, masked, strict=True)
        ]
        for start in range(len(tokens) - len(parts) + 1) if parts else ():
            if tokens[start : start + len(parts)] == parts:
                masked[start : start + len(parts)] = [MASK] * len(parts)
    return masked


def redact_pages(
    pages: list[PageWords],
    names: list[str],
    rng: random.Random,
    plan: ColumnPlan | None = None,
) -> list[PageWords]:
    """Columns first (codes and masks), then names, then digits everywhere else."""
    redactor = Redactor(names, rng)
    protected = plan.protected if plan else frozenset({MASK})
    redacted = []
    for page in apply_columns(pages, plan) if plan else pages:
        masked = mask_name_sequences([w.text for w in page.words], names)
        words = [
            replace(w, text=m if m in protected else redactor.text(m))
            for w, m in zip(page.words, masked, strict=True)
        ]
        redacted.append(replace(page, words=words))
    return redacted


def _unchanged_numbers(original: list[PageWords], redacted: list[PageWords]) -> list[str]:
    unchanged = []
    for before, after in zip(original, redacted, strict=True):
        for old, new in zip(before.words, after.words, strict=True):
            digits = sum(c.isdigit() for c in old.text)
            if digits >= MIN_CHECKED_DIGITS and not DATE_TEXT.match(old.text) and old == new:
                unchanged.append(old.text)
    return unchanged


def find_pdf_leaks(
    original: list[PageWords],
    redacted: list[PageWords],
    names: list[str],
    plan: ColumnPlan | None = None,
) -> list[str]:
    """Never log the result: it holds the original values."""
    original_words = [w.text for page in original for w in page.words]
    # One string per page, so names split across words are still found.
    redacted_pages = [" ".join(w.text for w in page.words) for page in redacted]
    leaks = text_leaks(original_words, redacted_pages, names)
    leaks += _unchanged_numbers(original, redacted)
    if plan is not None:
        leaks += column_leaks(original, redacted, plan)
    return leaks


def redact_pdf_file(
    source: Path,
    target: Path,
    names: list[str],
    password: str | None = None,
    rng: random.Random | None = None,
    columns: Sequence[ColumnSpec] = (),
    keep: frozenset[str] = KEEP_WORDS,
) -> None:
    """Write a redacted JSON sample of `source`, or raise `LeakError` and write nothing.

    Raises `ValueError` if a requested column header isn't found anywhere.
    """
    check_paths(source, target)
    rng = rng or random.Random()
    pages = extract_pages(source.read_bytes(), password)
    plan = plan_columns(pages, list(columns), keep) if columns else None
    leaks: list[str] = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        redacted = redact_pages(pages, names, rng, plan)
        leaks = find_pdf_leaks(pages, redacted, names, plan)
        if not leaks:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(dump_pages(redacted), encoding="utf-8")
            logger.info("Redacted sample saved", extra={"target": str(target), "attempt": attempt})
            return
    raise leak_error(leaks)
