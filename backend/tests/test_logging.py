import logging

from mis_finanzas.core.logging import ContextFormatter


def _format(**extra: object) -> str:
    record = logging.makeLogRecord({"msg": "Import committed", "levelname": "INFO", **extra})
    return ContextFormatter("%(message)s").format(record)


def test_extra_fields_are_appended_sorted() -> None:
    assert _format(rows=5, batch_id=1) == "Import committed batch_id=1 rows=5"


def test_no_extra_fields_leaves_line_unchanged() -> None:
    assert _format() == "Import committed"
