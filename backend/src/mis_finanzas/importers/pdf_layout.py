"""Reading tables out of positioned PDF words. Shared by every PDF parser; pure functions.

A table is found by its header row: a line holding **all** of the expected labels. Only rows
below such a header are data, so words elsewhere on the page (page headers, legal text,
summaries) are never read as rows.

Words on a line are first grouped into chunks, splitting where the gap is wider than a
space; a chunk is one cell value (`-$ 1.234,56`, a whole description). Each chunk goes to the
column whose header label it overlaps most. A chunk under no label falls back to the column
range holding its center: ranges run from each label's left edge to the next label's left
edge. So `$ 9.000,00` stays together under `Saldo` even when its `$` starts left of the
label, and a long description can run on toward the next column.
"""

import math
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from mis_finanzas.importers.pdf_words import PageWords, Word
from mis_finanzas.ledger.text import normalize_description

# Smaller text is invisible (some banks print 0.1pt markers inside tables).
MIN_VISIBLE_SIZE = 2.0
LINE_TOLERANCE = 2.0
COLUMN_TOLERANCE = 2.0
# Wider than the space between words of one value, narrower than the gap between columns.
CHUNK_GAP = 6.0

_NOT_WORD = re.compile(r"\W")


def _token(text: str) -> str:
    return _NOT_WORD.sub("", normalize_description(text))


@dataclass(frozen=True)
class Line:
    words: tuple[Word, ...]  # left to right

    @property
    def top(self) -> float:
        return min(w.top for w in self.words)

    @property
    def bottom(self) -> float:
        return max(w.bottom for w in self.words)

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


@dataclass(frozen=True)
class Column:
    label: str
    left: float  # fallback range, for chunks under no label
    right: float
    label_x0: float  # where the header label itself is printed
    label_x1: float

    def holds(self, x0: float, x1: float) -> bool:
        return self.left <= (x0 + x1) / 2 < self.right

    def overlap(self, x0: float, x1: float) -> float:
        return max(0.0, min(x1, self.label_x1) - max(x0, self.label_x0))


@dataclass(frozen=True)
class HeaderRow:
    line: Line
    columns: tuple[Column, ...]  # left to right

    @property
    def bottom(self) -> float:
        return self.line.bottom

    def column_of(self, x0: float, x1: float) -> Column | None:
        """The column a value spanning `x0..x1` belongs to."""
        best = max(self.columns, key=lambda c: c.overlap(x0, x1))
        if best.overlap(x0, x1) > 0:
            return best
        return next((c for c in self.columns if c.holds(x0, x1)), None)


@dataclass
class TableRow:
    top: float
    cells: dict[str, str]  # column label -> text
    lines: list[Line] = field(default_factory=list)

    def cell(self, label: str) -> str:
        return self.cells.get(label, "")


def visible(words: Sequence[Word], min_size: float = MIN_VISIBLE_SIZE) -> list[Word]:
    return [w for w in words if w.size >= min_size and w.x1 > w.x0]


def lines(words: Sequence[Word], tolerance: float = LINE_TOLERANCE) -> list[Line]:
    """Words grouped into lines, top to bottom."""
    groups: list[list[Word]] = []
    for word in sorted(words, key=lambda w: (w.top, w.x0)):
        if groups and abs(groups[-1][0].top - word.top) <= tolerance:
            groups[-1].append(word)
        else:
            groups.append([word])
    return [Line(tuple(sorted(group, key=lambda w: w.x0))) for group in groups]


def _label_span(line: Line, label: str) -> tuple[float, float] | None:
    """`(x0, x1)` of `label`'s words, consecutive on `line`; case, accents and dots ignored."""
    wanted = [t for t in (_token(part) for part in label.split()) if t]
    tokens = [_token(w.text) for w in line.words]
    for start in range(len(tokens) - len(wanted) + 1):
        if tokens[start : start + len(wanted)] == wanted:
            return line.words[start].x0, line.words[start + len(wanted) - 1].x1
    return None


def _columns(spans: list[tuple[str, float, float]], page_width: float) -> tuple[Column, ...]:
    ordered = sorted(spans, key=lambda span: span[1])
    lefts = [0.0] + [x0 - COLUMN_TOLERANCE for _, x0, _ in ordered[1:]]
    rights = [*lefts[1:], page_width]
    return tuple(
        Column(label, left, right, x0, x1)
        for (label, x0, x1), left, right in zip(ordered, lefts, rights, strict=True)
    )


def find_header_rows(page: PageWords, labels: Sequence[str]) -> list[HeaderRow]:
    """Every line holding all `labels` (a label may span words: "Caja de Ahorro")."""
    headers = []
    for line in lines(visible(page.words)):
        found = [(label, _label_span(line, label)) for label in labels]
        if all(span is not None for _, span in found):
            spans = [(label, span[0], span[1]) for label, span in found if span is not None]
            headers.append(HeaderRow(line, _columns(spans, page.width)))
    return headers


def chunks(line: Line, gap: float = CHUNK_GAP) -> list[list[Word]]:
    """The line's words split into values wherever the space between words exceeds `gap`."""
    groups: list[list[Word]] = []
    for word in line.words:
        if groups and word.x0 - groups[-1][-1].x1 <= gap:
            groups[-1].append(word)
        else:
            groups.append([word])
    return groups


def _cells(line: Line, header: HeaderRow) -> dict[str, str]:
    cells: dict[str, list[str]] = {}
    for chunk in chunks(line):
        column = header.column_of(chunk[0].x0, chunk[-1].x1)
        if column is not None:
            cells.setdefault(column.label, []).extend(w.text for w in chunk)
    return {label: " ".join(texts) for label, texts in cells.items()}


def _extend(row: TableRow, line: Line, cells: dict[str, str]) -> None:
    for label, text in cells.items():
        row.cells[label] = f"{row.cells[label]} {text}" if row.cells.get(label) else text
    row.lines.append(line)


def table_rows(
    page: PageWords,
    header: HeaderRow,
    key_columns: Sequence[str],
    until: float = math.inf,
    stop: Callable[[Line], bool] | None = None,
) -> list[TableRow]:
    """Rows below `header` and above `until`, ending early at the first line `stop` accepts.

    A line with text in any `key_columns` starts a row; any other line continues the
    previous row (e.g. a description's second line). Lines before the first row are skipped.
    """
    rows: list[TableRow] = []
    for line in lines(visible(page.words)):
        if line.top <= header.bottom or line.top >= until:
            continue
        if stop is not None and stop(line):
            break
        cells = _cells(line, header)
        if any(cells.get(key) for key in key_columns):
            rows.append(TableRow(top=line.top, cells=dict(cells), lines=[line]))
        elif rows:
            _extend(rows[-1], line, cells)
    return rows
