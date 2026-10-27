"""PDF redaction works on extracted words: formats and positions survive, values don't."""

import random
import re
from pathlib import Path

import pytest

from conftest import make_pdf
from mis_finanzas.importers.pdf_words import extract_pages, load_pages
from mis_finanzas.tools.redact import main
from mis_finanzas.tools.redact_pdf import (
    find_pdf_leaks,
    mask_name_sequences,
    redact_pages,
    redact_pdf_file,
)
from mis_finanzas.tools.redaction import LeakError

NAME = "Juana Pérez"
STATEMENT = [
    (72, 800, "Titular: Juana Pérez, CUIT 27-30405060-7"),
    (72, 780, "Cuenta 4567890123"),
    (72, 700, "02/03/2026 TRANSF 20304050607 -12.345,67"),
    (72, 100, "TOTAL 9.876,54"),
    (72.3, 100, "TOTAL 9.876,54"),  # fake bold
]


def _shape(text: str) -> str:
    return re.sub(r"\d", "9", text)


@pytest.mark.parametrize(
    ("texts", "expected"),
    [
        (["Titular:", "Juana", "Pérez,", "CUIT"], ["Titular:", "XXXX", "XXXX", "CUIT"]),
        (["JUANA", "PEREZ"], ["XXXX", "XXXX"]),
        (["Sra.JuanaPérez"], ["Sra.JuanaPérez"]),  # not a whole word: left to the leak check
        (["JuanaPérez"], ["XXXX"]),
        (["Juana", "Gómez"], ["Juana", "Gómez"]),
    ],
)
def test_mask_name_sequences(texts: list[str], expected: list[str]) -> None:
    assert mask_name_sequences(texts, [NAME]) == expected


def test_redact_pages_keeps_layout_dates_and_number_shapes() -> None:
    original = extract_pages(make_pdf(STATEMENT))
    redacted = redact_pages(original, [NAME], random.Random(1))
    for before, after in zip(original[0].words, redacted[0].words, strict=True):
        assert (before.x0, before.top, before.fontname) == (after.x0, after.top, after.fontname)
        if before.text in ("Juana", "Pérez,"):
            assert after.text == "XXXX"
        else:
            assert _shape(after.text) == _shape(before.text)
    texts = [w.text for w in redacted[0].words]
    assert "02/03/2026" in texts and "9.876,54" not in texts
    assert find_pdf_leaks(original, redacted, [NAME]) == []


def test_find_pdf_leaks_reports_unchanged_numbers_and_names() -> None:
    original = extract_pages(make_pdf(STATEMENT))
    assert find_pdf_leaks(original, original, [NAME]) == [
        "20304050607",
        "30405060",
        "4567890123",
        NAME,
        "JUANA",
        "PEREZ",
        "27-30405060-7",
        "4567890123",
        "20304050607",
        "-12.345,67",
        "9.876,54",
    ]


def test_redact_pdf_file_writes_loadable_sample(tmp_path: Path) -> None:
    source = tmp_path / "resumen.pdf"
    source.write_bytes(make_pdf(STATEMENT))
    target = tmp_path / "samples" / "resumen.redacted.json"
    redact_pdf_file(source, target, [NAME], rng=random.Random(2))
    pages = load_pages(target)
    assert len(pages[0].words) == len(extract_pages(source.read_bytes())[0].words)
    assert "Juana" not in target.read_text(encoding="utf-8")


def test_name_inside_a_longer_word_blocks_the_sample(tmp_path: Path) -> None:
    source = tmp_path / "resumen.pdf"
    source.write_bytes(make_pdf([(72, 800, "Sra.JuanaPerez 1.000,00")]))
    target = tmp_path / "out.json"
    with pytest.raises(LeakError):
        redact_pdf_file(source, target, [NAME], rng=random.Random(3))
    assert not target.exists()


def test_cli_dispatches_pdf_to_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "resumen.pdf").write_bytes(make_pdf(STATEMENT))
    assert main(["resumen.pdf", "--name", NAME]) == 0
    assert (tmp_path / "samples" / "resumen.redacted.json").exists()
    assert main(["broken.pdf"]) == 1
    assert main(["statement.ods"]) == 2
