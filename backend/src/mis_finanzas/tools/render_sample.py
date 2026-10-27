"""Render a JSON words sample back into a PDF, to review a redacted sample by eye.

Only the words are drawn, at their original positions and sizes, in Helvetica (bold where the
original font was bold). Lines, boxes and images aren't part of a sample. Words that grew
longer through redaction (`AL30` -> `ESPECIE_01`) are squeezed toward their original width.

Usage: python -m mis_finanzas.tools.render_sample samples/x.redacted.json [--out x.pdf]
"""

import argparse
import logging
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from mis_finanzas.core.logging import configure_logging
from mis_finanzas.importers.pdf_words import PageWords, Word, load_pages

logger = logging.getLogger(__name__)

# Helvetica metrics: baseline sits 0.207 em above a glyph box's bottom; ~0.5 em per character.
DESCENT = 0.207
AVERAGE_CHAR_WIDTH = 0.5
MIN_SCALE = 60.0
FONTS = {False: "F1", True: "F2"}


@dataclass(frozen=True)
class TextOp:
    """Text drawn with its baseline at `(x, y)`, y measured from the page bottom."""

    x: float
    y: float
    text: str
    size: float = 10.0
    bold: bool = False
    scale: float = 100.0  # horizontal scaling, percent


@dataclass(frozen=True)
class Page:
    width: float
    height: float
    ops: Sequence[TextOp]


def _escape(text: str) -> bytes:
    raw = text.encode("latin-1", errors="replace")
    return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def _content(ops: Sequence[TextOp]) -> bytes:
    lines = [
        b"BT /%s %.2f Tf %.1f Tz %.2f %.2f Td (%s) Tj ET"
        % (FONTS[op.bold].encode(), op.size, op.scale, op.x, op.y, _escape(op.text))
        for op in ops
    ]
    return b"\n".join(lines)


def _objects(pages: Sequence[Page]) -> list[bytes]:
    """Catalog, page tree, two fonts, then a (page, content) pair per page."""
    first_page = 5
    kids = b" ".join(b"%d 0 R" % (first_page + 2 * i) for i in range(len(pages)))
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, len(pages)),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
    ]
    for index, page in enumerate(pages):
        content = _content(page.ops)
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %.2f %.2f] "
            b"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents %d 0 R >>"
            % (page.width, page.height, first_page + 2 * index + 1)
        )
        objects.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content))
    return objects


def build_pdf(pages: Sequence[Page]) -> bytes:
    """A minimal valid PDF (Latin-1 text; other characters become `?`)."""
    objects = _objects(pages)
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    return bytes(out)


def _op(word: Word, page_height: float) -> TextOp:
    estimated = len(word.text) * AVERAGE_CHAR_WIDTH * word.size
    box = word.x1 - word.x0
    scale = max(MIN_SCALE, 100 * box / estimated) if estimated > box > 0 else 100.0
    bold = any(mark in word.fontname.lower() for mark in ("bold", "black", "heavy"))
    return TextOp(
        x=word.x0,
        y=page_height - word.bottom + DESCENT * word.size,
        # A real space keeps adjacent words apart when the PDF is read again.
        text=word.text + " ",
        size=word.size or 10.0,
        bold=bold,
        scale=scale,
    )


def render_pages(pages: Sequence[PageWords]) -> bytes:
    return build_pdf([Page(p.width, p.height, [_op(w, p.height) for w in p.words]) for p in pages])


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(description="Render a JSON words sample as a PDF.")
    parser.add_argument("sample", type=Path)
    parser.add_argument("--out", type=Path, help="default: the sample path with .pdf")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    target = args.out or args.sample.with_suffix(".pdf")
    try:
        pages = load_pages(args.sample)
    except (OSError, ValueError, KeyError, TypeError) as exc:  # ImportFileError is a ValueError
        logger.error("Not a readable sample", extra={"sample": str(args.sample), "error": str(exc)})
        return 1
    target.write_bytes(render_pages(pages))
    logger.info("Sample rendered", extra={"target": str(target), "pages": len(pages)})
    return 0


if __name__ == "__main__":
    sys.exit(main())
