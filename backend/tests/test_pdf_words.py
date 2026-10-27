from pathlib import Path

import pytest

from conftest import make_pdf
from mis_finanzas.importers.base import ImportFileError
from mis_finanzas.importers.pdf_words import dump_pages, extract_pages, load_pages


def test_extracts_words_with_positions_and_fonts() -> None:
    pages = extract_pages(make_pdf([(72, 800, "02/03/2026 Peluquería -1.234,56")]))
    assert len(pages) == 1 and (pages[0].width, pages[0].height) == (595, 842)
    words = pages[0].words
    assert [w.text for w in words] == ["02/03/2026", "Peluquería", "-1.234,56"]
    assert words[0].x0 == 72 and words[0].fontname == "Helvetica" and words[0].size == 10
    assert words[0].x1 < words[1].x0 < words[2].x0


def test_fake_bold_duplicates_collapse() -> None:
    # Bold emulated by drawing the same text twice, shifted by a fraction of a point.
    pages = extract_pages(make_pdf([(72, 100, "TOTAL 9.876,54"), (72.3, 100, "TOTAL 9.876,54")]))
    assert [w.text for w in pages[0].words] == ["TOTAL", "9.876,54"]


def test_not_a_pdf_is_a_file_error() -> None:
    with pytest.raises(ImportFileError):
        extract_pages(b"definitely not a pdf")


def test_sample_round_trip(tmp_path: Path) -> None:
    pages = extract_pages(make_pdf([(72, 800, "Saldo 1.000,00")]))
    path = tmp_path / "s.json"
    path.write_text(dump_pages(pages), encoding="utf-8")
    assert load_pages(path) == pages


def test_load_rejects_other_json(tmp_path: Path) -> None:
    path = tmp_path / "x.json"
    path.write_text('{"pages": []}', encoding="utf-8")
    with pytest.raises(ImportFileError):
        load_pages(path)
