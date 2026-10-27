"""Column-aware redaction for PDF samples, e.g. a broker statement's Especie and Descripción.

Columns are found by their header word. A column spans from halfway between the previous
header and its own, up to where the next header starts (text columns are left-aligned under
their header), for every row below the header line. A page without the header reuses the
previous page's columns.

- **instrument** columns: each distinct word becomes a stable code (`ESPECIE_01`), replaced
  everywhere in the document, so the same instrument keeps one code and a ticker mentioned
  elsewhere is covered too.
- **text** columns: operation words in `KEEP_WORDS` stay; instrument words get their code; any
  other word with letters becomes `XXXX`. Pure numbers are left to the digit scrambling.
"""

import math
from dataclasses import dataclass, field, replace
from typing import Literal

from mis_finanzas.importers.pdf_words import PageWords, Word
from mis_finanzas.tools.redaction import DATE_TEXT, MASK, compact_text

ColumnKind = Literal["instrument", "text"]
LINE_TOLERANCE = 2.0

# Words a text column keeps: connectives, operation types, instrument and currency kinds.
_KEEP = (
    "a",
    "al",
    "con",
    "de",
    "del",
    "el",
    "en",
    "la",
    "las",
    "los",
    "para",
    "por",
    "sin",
    "y",
    "o",
    "compra",
    "venta",
    "suscripcion",
    "rescate",
    "dividendo",
    "dividendos",
    "renta",
    "amortizacion",
    "cupon",
    "caucion",
    "colocadora",
    "tomadora",
    "deposito",
    "extraccion",
    "transferencia",
    "retiro",
    "ingreso",
    "egreso",
    "pago",
    "cobro",
    "credito",
    "debito",
    "acreditacion",
    "liquidacion",
    "concertacion",
    "operacion",
    "boleto",
    "arancel",
    "comision",
    "derechos",
    "mercado",
    "iva",
    "impuesto",
    "percepcion",
    "retencion",
    "ganancias",
    "bienes",
    "personales",
    "sellos",
    "interes",
    "intereses",
    "ajuste",
    "saldo",
    "total",
    "parcial",
    "dolar",
    "dolares",
    "pesos",
    "mep",
    "ccl",
    "cable",
    "usd",
    "ars",
    "u$s",
    "$",
    "moneda",
    "cedear",
    "cedears",
    "bono",
    "bonos",
    "on",
    "letra",
    "letras",
    "accion",
    "acciones",
    "fci",
    "cuotapartes",
    "contado",
    "inmediato",
    "plazo",
    "vto",
    "vencimiento",
    "anterior",
    "efectivo",
    "cartera",
    "disponible",
    "instrumentos",
    "monedas",
    "corriente",
    "comitente",
)
KEEP_WORDS = frozenset(compact_text(w) for w in _KEEP)


@dataclass(frozen=True)
class ColumnSpec:
    header: str
    kind: ColumnKind


@dataclass(frozen=True)
class Span:
    """A column of one table section: rows between its header row and the next one."""

    spec: ColumnSpec
    left: float
    right: float
    below: float
    until: float = math.inf
    reused: bool = False  # carried over to a page without its own header row


@dataclass
class ColumnPlan:
    """Which column each word falls in, plus the instrument codes. Built from the original.

    `codes` holds every instrument word; `global_tokens` the ones seen under a real header,
    which are replaced everywhere. Words first seen on a page without a header row are only
    replaced inside the column, so a carried-over column can't spread codes across the
    document.
    """

    kinds: list[list[ColumnKind | None]]
    keep: frozenset[str]
    codes: dict[str, str] = field(default_factory=dict)
    global_tokens: set[str] = field(default_factory=set)

    @property
    def protected(self) -> frozenset[str]:
        """Replacement texts the digit scrambling must leave alone (`ESPECIE_01`, `XXXX`)."""
        return frozenset(self.codes.values()) | {MASK}


def _line_of(page: PageWords, word: Word) -> list[Word]:
    return sorted(
        (w for w in page.words if abs(w.top - word.top) <= LINE_TOLERANCE), key=lambda w: w.x0
    )


def _span(page: PageWords, header: Word, spec: ColumnSpec, below: float) -> Span:
    line = _line_of(page, header)
    index = line.index(header)
    left = (line[index - 1].x1 + header.x0) / 2 if index > 0 else 0.0
    right = line[index + 1].x0 if index + 1 < len(line) else page.width
    return Span(spec=spec, left=left, right=right, below=below)


def _header_rows(page: PageWords, specs: list[ColumnSpec]) -> list[list[tuple[Word, ColumnSpec]]]:
    """Header words grouped by line, top to bottom. A page can hold several tables."""
    targets = {compact_text(s.header): s for s in specs}
    headers = sorted(
        ((w, targets[compact_text(w.text)]) for w in page.words if compact_text(w.text) in targets),
        key=lambda pair: pair[0].top,
    )
    rows: list[list[tuple[Word, ColumnSpec]]] = []
    for word, spec in headers:
        if rows and abs(rows[-1][0][0].top - word.top) <= LINE_TOLERANCE:
            rows[-1].append((word, spec))
        else:
            rows.append([(word, spec)])
    return rows


def find_spans(page: PageWords, specs: list[ColumnSpec]) -> list[Span]:
    """Each header row starts a section that ends where the next header row begins."""
    rows = _header_rows(page, specs)
    spans = []
    for index, row in enumerate(rows):
        below = max(word.bottom for word, _ in row)
        until = rows[index + 1][0][0].top if index + 1 < len(rows) else math.inf
        spans += [replace(_span(page, w, spec, below), until=until) for w, spec in row]
    return spans


def _span_at(word: Word, spans: list[Span]) -> Span | None:
    center = (word.x0 + word.x1) / 2
    return next(
        (s for s in spans if s.below < word.top < s.until and s.left <= center < s.right), None
    )


def _carried_over(spans: list[Span]) -> list[Span]:
    """The last section's columns, applied to a whole page that has no header row."""
    last = [s for s in spans if s.until == math.inf]
    return [replace(s, below=-math.inf, reused=True) for s in last]


def _record_code(plan: ColumnPlan, word: Word, span: Span) -> None:
    token = compact_text(word.text)
    # Dates stay readable: coded globally they'd erase the same date in every date column.
    if span.spec.kind != "instrument" or not token or token in plan.keep:
        return
    if DATE_TEXT.match(word.text):
        return
    plan.codes.setdefault(token, f"{compact_text(span.spec.header)}_{len(plan.codes) + 1:02d}")
    if not span.reused:
        plan.global_tokens.add(token)


def plan_columns(
    pages: list[PageWords], specs: list[ColumnSpec], keep: frozenset[str] = KEEP_WORDS
) -> ColumnPlan:
    """Raises `ValueError` when a header never appears, so nothing goes unredacted silently.

    Header names are always kept, so a repeated header row is never coded or masked.
    """
    plan = ColumnPlan(kinds=[], keep=keep | {compact_text(s.header) for s in specs})
    found: set[str] = set()
    spans: list[Span] = []
    for page in pages:
        spans = find_spans(page, specs) or _carried_over(spans)
        found.update(s.spec.header for s in spans if not s.reused)
        kinds: list[ColumnKind | None] = []
        for word in page.words:
            span = _span_at(word, spans)
            kinds.append(span.spec.kind if span else None)
            if span is not None:
                _record_code(plan, word, span)
        plan.kinds.append(kinds)
    missing = [s.header for s in specs if s.header not in found]
    if missing:
        raise ValueError(f"column header not found: {', '.join(missing)}")
    return plan


def _has_letters(token: str) -> bool:
    return any(c.isalpha() for c in token)


def _masked(text: str, kind: ColumnKind | None, plan: ColumnPlan) -> str:
    token = compact_text(text)
    if token in plan.global_tokens or (kind == "instrument" and token in plan.codes):
        return plan.codes[token]
    if kind == "text" and token not in plan.keep and _has_letters(token):
        return MASK
    return text


def apply_columns(pages: list[PageWords], plan: ColumnPlan) -> list[PageWords]:
    return [
        replace(
            page,
            words=[
                replace(w, text=_masked(w.text, kind, plan))
                for w, kind in zip(page.words, kinds, strict=True)
            ],
        )
        for page, kinds in zip(pages, plan.kinds, strict=True)
    ]


def _leaked(old: Word, new: Word, kind: ColumnKind | None, plan: ColumnPlan) -> bool:
    token = compact_text(new.text)
    unchanged = token == compact_text(old.text)
    return (
        token in plan.global_tokens
        or (kind == "instrument" and unchanged and token in plan.codes)
        or (kind == "text" and unchanged and token not in plan.keep and _has_letters(token))
    )


def column_leaks(
    original: list[PageWords], redacted: list[PageWords], plan: ColumnPlan
) -> list[str]:
    """Instrument words left anywhere they must be coded, or unmasked text. Never log these."""
    return [
        new.text
        for before, after, kinds in zip(original, redacted, plan.kinds, strict=True)
        for old, new, kind in zip(before.words, after.words, kinds, strict=True)
        if _leaked(old, new, kind, plan)
    ]
