"""Run every dedicated importer over the samples and report, without printing any content.

For each sample: which importer recognized it, rows per target, row errors, and each
statement check's result. Redacted PDF samples are JSON words and run through the page
importers; CSV/Excel samples through the file importers. Preview PDFs (`*.redacted.pdf`) are
skipped, since they are renders of the JSON samples.

Usage: python -m mis_finanzas.tools.sample_check [samples_dir]
"""

import logging
import sys
from collections import Counter
from pathlib import Path

from mis_finanzas.core.logging import configure_logging
from mis_finanzas.importers import registry
from mis_finanzas.importers.base import ImportFileError
from mis_finanzas.importers.catalog import register_builtin_importers
from mis_finanzas.importers.pdf_words import load_pages
from mis_finanzas.investments.records import InvestmentData

logger = logging.getLogger(__name__)

SAMPLE_SUFFIXES = {".json", ".csv", ".xlsx", ".pdf"}


def _parse(path: Path) -> registry.Parsed | None:
    if path.suffix.lower() == ".json":
        return registry.parse_pages(load_pages(path))
    return registry.parse_file(path.name, path.read_bytes())


def check_sample(path: Path) -> bool:
    """Log one sample's report; False when it has errors or failed checks."""
    try:
        parsed = _parse(path)
    except (ImportFileError, ValueError, KeyError) as exc:
        logger.error("Sample unreadable", extra={"sample": path.name, "error": str(exc)})
        return False
    if parsed is None:
        logger.info("No importer recognizes sample", extra={"sample": path.name})
        return True
    result = parsed.result
    targets = Counter(row.target for row in result.rows)
    logger.info(
        "Sample parsed",
        extra={
            "sample": path.name,
            "importer": parsed.importer,
            "rows": len(result.rows),
            "targets": dict(targets),
            "errors": len(result.errors),
            "checks_ok": sum(c.ok for c in result.checks),
            "checks_failed": [c.name for c in result.failed_checks],
            **_investment_counts(result.investments),
        },
    )
    return not result.errors and not result.failed_checks


def _investment_counts(data: InvestmentData | None) -> dict[str, int]:
    """Counts only: tickers and quantities are the owner's holdings."""
    if data is None:
        return {}
    snapshot = data.snapshot
    return {
        "operations": len(data.operations),
        "positions": len(snapshot.positions) if snapshot else 0,
        "cash_lines": len(snapshot.cash) if snapshot else 0,
    }


def _is_sample(path: Path) -> bool:
    return (
        path.is_file()
        and path.suffix.lower() in SAMPLE_SUFFIXES
        and not path.name.endswith(".redacted.pdf")
    )


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    register_builtin_importers()
    args = sys.argv[1:] if argv is None else argv
    folder = Path(args[0]) if args else Path("samples")
    if not folder.is_dir():
        logger.error("No samples folder", extra={"folder": str(folder)})
        return 1
    results = [check_sample(path) for path in sorted(folder.iterdir()) if _is_sample(path)]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
