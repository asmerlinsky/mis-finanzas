"""Shared redaction rules for statement samples (Excel and PDF).

Every digit outside a date becomes a random digit, which keeps each value's format
(`-1.234,56` stays a negative amount with the same separators). Given names become `XXXX`.
A copy is only kept when no identifier (a run of 6+ digits: CBU, CUIT, account or card
number) and no given name from the original survives in it.
"""

import html
import random
import re
from collections.abc import Iterable
from pathlib import Path

from mis_finanzas.ledger.text import normalize_description

# Dates stay readable: `5/3/2025`, `05-03-25`, `2026-10-27`, `2026-10-27T12:30:00.000-03:00`.
DATE_TEXT = re.compile(
    r"^\s*(\d{1,2}([/-])\d{1,2}\2\d{2,4}|\d{4}-\d{2}-\d{2})"
    r"([ T]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?)?\s*$"
)
IDENTIFIER = re.compile(r"\d{6,}")
MASK = "XXXX"
_NOT_WORD = re.compile(r"\W")
_WORD = re.compile(r"\w+")
# Name parts this long are masked on their own: "MERLINSKY" alone still identifies.
MIN_NAME_PART = 3
# Banks truncate names ("merlins", "sanc"): a word this long that starts a name part is masked.
MIN_NAME_PREFIX = 4
# A random digit can recreate an original value by chance; such attempts are retried.
MAX_ATTEMPTS = 5


class LeakError(RuntimeError):
    """The redacted copy still contains an identifier or a name from the original."""


class Redactor:
    def __init__(self, names: Iterable[str], rng: random.Random) -> None:
        names = list(names)
        self._names = [re.compile(re.escape(n.strip()), re.IGNORECASE) for n in names if n.strip()]
        self._parts = name_parts(names)
        self._rng = rng

    def text(self, value: str) -> str:
        """Entities decoded, full names, then name parts and truncated parts, then digits."""
        value = html.unescape(value)
        for name in self._names:
            value = name.sub(MASK, value)
        value = _WORD.sub(self._mask_part, value)
        if DATE_TEXT.match(value):
            return value
        return re.sub(r"\d", self._digit, value)

    def number(self, value: int | float) -> int | float:
        return type(value)(re.sub(r"\d", self._digit, str(value)))

    def _digit(self, _match: re.Match[str]) -> str:
        return str(self._rng.randint(0, 9))

    def _mask_part(self, match: re.Match[str]) -> str:
        return MASK if is_name_part(compact_text(match.group()), self._parts) else match.group()


def is_name_part(token: str, parts: set[str]) -> bool:
    """A whole name part, or a truncation of one: `MERLINS` for `MERLINSKY`."""
    if token in parts:
        return True
    return len(token) >= MIN_NAME_PREFIX and any(part.startswith(token) for part in parts)


def name_parts(names: Iterable[str]) -> set[str]:
    """`["Agustín Sánchez de X"]` -> `{"AGUSTIN", "SANCHEZ"}`: parts of 3+ characters."""
    return {
        part
        for name in names
        for part in (compact_text(p) for p in name.split())
        if len(part) >= MIN_NAME_PART
    }


def identifiers(texts: Iterable[str]) -> set[str]:
    return {run for text in texts if not DATE_TEXT.match(text) for run in IDENTIFIER.findall(text)}


def text_leaks(original: Iterable[str], redacted: Iterable[str], names: Iterable[str]) -> list[str]:
    """Identifiers and names from `original` still present in `redacted`. Never log these.

    Names are compared without case, accents, spaces or punctuation, so `Pérez` and
    `JUANA-PEREZ` are caught when the name was given as `Juana Perez`. This can flag a
    coincidental match. Each part of a name (3+ characters) is also checked on its own, so
    `PEREZ, JUANA` or a lone `PEREZ` is caught in any order, and so is a truncation of 4+
    characters (`PERE`). HTML entities are decoded before comparing.
    """
    names = list(names)
    joined = html.unescape("\n".join(redacted))
    leaks = sorted(i for i in identifiers(original) if i in joined)
    compact = compact_text(joined)
    leaks += [n for n in names if compact_text(n) and compact_text(n) in compact]
    parts = name_parts(names)
    words = {compact_text(word) for word in _WORD.findall(joined)}
    leaks += sorted(word for word in words if is_name_part(word, parts))
    return leaks


def compact_text(text: str) -> str:
    """`"Juana Pérez,"` -> `"JUANAPEREZ"`."""
    return _NOT_WORD.sub("", normalize_description(text))


def check_paths(source: Path, target: Path) -> None:
    if source.resolve() == target.resolve():
        raise ValueError("refusing to overwrite the original file")


def leak_error(leaks: list[str]) -> LeakError:
    return LeakError(
        f"{len(leaks)} values survived redaction; add every spelling of the names "
        "(with and without accents, surname first) with --name and try again"
    )
