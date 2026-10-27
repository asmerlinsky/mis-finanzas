from pathlib import Path

import pytest

from conftest import make_pdf
from fake_importers import MAGIC, FakeStatementImporter
from mis_finanzas.importers import registry
from mis_finanzas.importers.pdf_words import dump_pages, extract_pages
from mis_finanzas.tools.sample_check import main


def test_reports_without_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(registry, "_FILE_IMPORTERS", [FakeStatementImporter()])
    (tmp_path / "ok.txt.csv").write_bytes(
        MAGIC + b"\nTOTAL;bank/ARS;-5.00\n01/02/2026;-5.00;bank/ARS;Kiosco Secreto;R1;\n"
    )
    pages = extract_pages(make_pdf([(72, 800, "otro banco")]))
    (tmp_path / "x.redacted.json").write_text(dump_pages(pages), encoding="utf-8")
    (tmp_path / "x.redacted.pdf").write_bytes(b"not read")
    with caplog.at_level("INFO"):
        assert main([str(tmp_path)]) == 0
    assert "Kiosco" not in caplog.text
    parsed = next(r for r in caplog.records if r.getMessage() == "Sample parsed")
    assert parsed.__dict__["targets"] == {"bank/ARS": 1}
    assert parsed.__dict__["checks_failed"] == []


def test_failed_checks_make_it_fail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry, "_FILE_IMPORTERS", [FakeStatementImporter()])
    (tmp_path / "bad.csv").write_bytes(
        MAGIC + b"\nTOTAL;bank/ARS;-1.00\n01/02/2026;-5.00;bank/ARS;Kiosco;R1;\n"
    )
    assert main([str(tmp_path)]) == 1
    assert main([str(tmp_path / "missing")]) == 1
