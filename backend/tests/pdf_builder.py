"""Synthetic statement PDFs: text placed by `top` (distance from the page top), like samples.

Only invented names and numbers go in here; real statement values never do.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from mis_finanzas.tools.render_sample import Page, TextOp, build_pdf

# Helvetica: a glyph box's top sits this many ems above the baseline.
ASCENT = 0.793
PAGE_WIDTH = 595.0
PAGE_HEIGHT = 842.0


@dataclass(frozen=True)
class Row:
    top: float
    cells: Sequence[tuple[float, str]]  # (x, text)
    size: float = 8.5
    bold: bool = False


def _ops(rows: Sequence[Row]) -> list[TextOp]:
    return [
        TextOp(
            x=x,
            y=PAGE_HEIGHT - row.top - ASCENT * row.size,
            text=text,
            size=row.size,
            bold=row.bold,
        )
        for row in rows
        for x, text in row.cells
    ]


def statement_pdf(pages: Sequence[Sequence[Row]]) -> bytes:
    return build_pdf([Page(PAGE_WIDTH, PAGE_HEIGHT, _ops(rows)) for rows in pages])


def header(top: float, labels: Sequence[tuple[float, str]]) -> Row:
    """Header labels in small type, so their printed spans don't overlap."""
    return Row(top, labels, size=6)
