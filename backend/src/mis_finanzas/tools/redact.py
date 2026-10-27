"""Make a statement safe to use as a parser sample. Nothing is written if anything leaks.

python -m mis_finanzas.tools.redact statement.xlsx --name "Full Name"
    -> samples/statement.redacted.xlsx
python -m mis_finanzas.tools.redact resumen.pdf --name "Full Name" [--ask-password]
    -> samples/resumen.redacted.json   (positioned words, as PDF parsers read them)
"""

import argparse
import getpass
import logging
import sys
from pathlib import Path

from mis_finanzas.core.logging import configure_logging
from mis_finanzas.tools.pdf_columns import KEEP_WORDS, ColumnSpec
from mis_finanzas.tools.redact_csv import redact_csv_file
from mis_finanzas.tools.redact_pdf import redact_pdf_file
from mis_finanzas.tools.redact_xlsx import redact_xlsx_file
from mis_finanzas.tools.redaction import LeakError, compact_text

logger = logging.getLogger(__name__)

OUTPUT_SUFFIX = {".xlsx": ".xlsx", ".pdf": ".json", ".csv": ".csv"}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Redact a statement into samples/.")
    parser.add_argument("source", type=Path, help=".xlsx, .csv or .pdf")
    parser.add_argument(
        "--name",
        action="append",
        default=[],
        help="name to replace with XXXX (repeatable); give every spelling",
    )
    parser.add_argument("--out", type=Path, help="default: samples/<name>.redacted.<xlsx|json>")
    parser.add_argument(
        "--ask-password", action="store_true", help="prompt for the password of an encrypted PDF"
    )
    parser.add_argument(
        "--instrument-column",
        action="append",
        default=[],
        metavar="HEADER",
        help="PDF: give each value in this column a stable code, everywhere (e.g. Especie)",
    )
    parser.add_argument(
        "--text-column",
        action="append",
        default=[],
        metavar="HEADER",
        help="PDF: in this column keep operation words and mask the rest (e.g. Descripción)",
    )
    parser.add_argument(
        "--keep",
        action="append",
        default=[],
        metavar="WORD",
        help="PDF: extra word to keep in text columns (repeatable)",
    )
    return parser.parse_args(argv)


def _redact(args: argparse.Namespace, target: Path) -> None:
    if args.source.suffix.lower() == ".pdf":
        password = getpass.getpass("PDF password: ") if args.ask_password else None
        columns = [ColumnSpec(h, "instrument") for h in args.instrument_column]
        columns += [ColumnSpec(h, "text") for h in args.text_column]
        keep = KEEP_WORDS | {compact_text(w) for w in args.keep}
        redact_pdf_file(args.source, target, args.name, password, columns=columns, keep=keep)
    elif args.source.suffix.lower() == ".csv":
        redact_csv_file(args.source, target, args.name)
    else:
        redact_xlsx_file(args.source, target, args.name)


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    args = parse_args(sys.argv[1:] if argv is None else argv)
    suffix = OUTPUT_SUFFIX.get(args.source.suffix.lower())
    if suffix is None:
        logger.error("Only .xlsx, .csv and .pdf are supported", extra={"source": str(args.source)})
        return 2
    if not args.source.is_file():
        logger.error("File not found", extra={"source": str(args.source)})
        return 1
    target = args.out or Path("samples") / f"{args.source.stem}.redacted{suffix}"
    try:
        _redact(args, target)
    except (LeakError, ValueError) as exc:  # ImportFileError is a ValueError
        logger.error("Redaction failed; nothing was written", extra={"error": str(exc)})
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
