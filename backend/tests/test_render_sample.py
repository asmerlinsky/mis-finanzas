from pathlib import Path

from conftest import make_pdf
from mis_finanzas.importers.pdf_words import PageWords, Word, dump_pages, extract_pages
from mis_finanzas.tools.render_sample import main, render_pages


def test_rendered_sample_extracts_back_to_the_same_layout() -> None:
    original = extract_pages(
        make_pdf([(72, 800, "Fecha Descripción Importe"), (72, 780, "02/03/2026 Compra -1.234,56")])
    )
    again = extract_pages(render_pages(original))
    for before, after in zip(original[0].words, again[0].words, strict=True):
        assert before.text == after.text
        assert abs(before.x0 - after.x0) < 0.5 and abs(before.top - after.top) < 0.5


def test_bold_fonts_and_longer_replacements() -> None:
    page = PageWords(
        1,
        300,
        200,
        [
            Word("TOTAL", 10, 50, 40, 60, "ABCDEF+Arial-BoldMT", 10),
            Word("ESPECIE_01", 100, 50, 125, 60, "ArialMT", 10),  # was a 4-letter ticker
        ],
    )
    words = extract_pages(render_pages([page]))[0].words
    assert words[0].fontname == "Helvetica-Bold"
    assert words[1].text == "ESPECIE_01" and words[1].x1 < 100 + 0.5 * 10 * 10


def test_cli_writes_pdf_next_to_sample(tmp_path: Path) -> None:
    sample = tmp_path / "x.redacted.json"
    sample.write_text(dump_pages(extract_pages(make_pdf([(72, 800, "Saldo 1,00")]))))
    assert main([str(sample)]) == 0
    assert extract_pages((tmp_path / "x.redacted.pdf").read_bytes())[0].words[0].text == "Saldo"
    (tmp_path / "bad.json").write_text("{}")
    assert main([str(tmp_path / "bad.json")]) == 1
