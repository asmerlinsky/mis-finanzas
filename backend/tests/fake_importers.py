"""Fake dedicated importers for tests, until real ones exist. Synthetic data only.

The fake statement format is plain text:

    FAKE-STATEMENT
    TOTAL;<target>;<expected sum>        (optional, any number)
    <dd/mm/yyyy>;<amount>;<target>;<description>;<reference>;<n/m or empty>
"""

from datetime import datetime
from decimal import Decimal

from mis_finanzas.importers.base import Check, ParsedRow, ParseResult, RowError
from mis_finanzas.importers.pdf_words import PageWords

MAGIC = b"FAKE-STATEMENT"


def _installment(text: str) -> tuple[int, int] | None:
    if not text:
        return None
    number, total = text.split("/")
    return int(number), int(total)


def _row(line_number: int, fields: list[str]) -> ParsedRow:
    day, amount, target, description, reference, installment = fields
    return ParsedRow(
        line_number=line_number,
        date=datetime.strptime(day, "%d/%m/%Y").date(),
        amount=Decimal(amount),
        description=description,
        target=target,
        reference=reference or None,
        installment=_installment(installment),
    )


def _checks(totals: dict[str, Decimal], rows: list[ParsedRow]) -> list[Check]:
    return [
        Check(
            f"total {target}",
            expected,
            sum((r.amount for r in rows if r.target == target), Decimal(0)),
        )
        for target, expected in totals.items()
    ]


class FakeStatementImporter:
    name = "fake_statement"
    version = "1"

    def detect(self, filename: str, content: bytes) -> bool:
        return content.startswith(MAGIC)

    def parse(self, content: bytes, filename: str) -> ParseResult:
        result = ParseResult(metadata={"bank": "Banco de Prueba"})
        totals: dict[str, Decimal] = {}
        for number, line in enumerate(content.decode().splitlines()[1:], start=2):
            fields = line.split(";")
            if fields[0] == "TOTAL":
                totals[fields[1]] = Decimal(fields[2])
                continue
            try:
                result.rows.append(_row(number, fields))
            except ValueError as exc:
                result.errors.append(RowError(number, str(exc)))
        result.checks = _checks(totals, result.rows)
        return result


class GreedyImporter(FakeStatementImporter):
    """Claims the same files as `FakeStatementImporter`, to test ambiguity."""

    name = "greedy"


class BrokenDetector(FakeStatementImporter):
    name = "broken"

    def detect(self, filename: str, content: bytes) -> bool:
        raise RuntimeError("detector bug")


class FakePageImporter:
    name = "fake_pages"
    version = "1"

    def detect_pages(self, pages: list[PageWords]) -> bool:
        return any(w.text == "FAKEBANK" for p in pages for w in p.words)

    def parse_pages(self, pages: list[PageWords]) -> ParseResult:
        return ParseResult(metadata={"pages": str(len(pages))})
