"""Column redaction on a synthetic broker statement: Especie gets codes, Descripción is masked."""

import random
from pathlib import Path

import pytest

from conftest import make_pdf
from mis_finanzas.importers.pdf_words import PageWords, Word, extract_pages, load_pages
from mis_finanzas.tools.pdf_columns import (
    ColumnSpec,
    apply_columns,
    column_leaks,
    plan_columns,
)
from mis_finanzas.tools.redact import main
from mis_finanzas.tools.redact_pdf import redact_pages, redact_pdf_file

COLUMNS = [ColumnSpec("Especie", "instrument"), ColumnSpec("Descripción", "text")]
X = {"fecha": 40, "desc": 110, "especie": 300, "cantidad": 380, "importe": 470}


def _row(
    y: int, fecha: str, desc: str, especie: str, cantidad: str, importe: str
) -> list[tuple[int, int, str]]:
    values = [fecha, desc, especie, cantidad, importe]
    return [(x, y, v) for x, v in zip(X.values(), values, strict=True)]


STATEMENT = [
    (40, 760, "Resumen de cuenta"),
    *_row(700, "Fecha", "Descripción", "Especie", "Cantidad", "Importe"),
    *_row(680, "02/03/2026", "Compra AL30 Bono Rep Arg", "AL30", "1.000", "-650.000,00"),
    *_row(660, "05/03/2026", "Renta GD30", "GD30", "0", "12.345,67"),
    *_row(640, "06/03/2026", "Venta AL30", "AL30", "500", "330.000,00"),
    (40, 100, "Tenencia AL30"),
]


def _texts(page: PageWords) -> list[str]:
    return [w.text for w in page.words]


def _redacted_page() -> PageWords:
    pages = extract_pages(make_pdf(STATEMENT))
    plan = plan_columns(pages, COLUMNS)
    return redact_pages(pages, [], random.Random(1), plan)[0]


def test_instruments_get_stable_codes_everywhere() -> None:
    texts = _texts(_redacted_page())
    assert texts.count("ESPECIE_01") == 5  # 2 in Especie, 2 in Descripción, 1 in the footer
    assert texts.count("ESPECIE_02") == 2
    assert not {"AL30", "GD30"} & set(texts)


def test_descriptions_keep_operation_words_and_mask_the_rest() -> None:
    texts = _texts(_redacted_page())
    start = texts.index("Compra")
    assert texts[start : start + 5] == ["Compra", "ESPECIE_01", "Bono", "XXXX", "XXXX"]
    assert "Renta" in texts and "Venta" in texts


def test_headers_dates_and_other_columns_are_untouched_except_digits() -> None:
    texts = _texts(_redacted_page())
    for kept in ("Resumen", "Fecha", "Descripción", "Especie", "Cantidad", "Tenencia"):
        assert kept in texts
    assert "02/03/2026" in texts and "-650.000,00" not in texts


def test_missing_header_is_an_error() -> None:
    pages = extract_pages(make_pdf([(40, 700, "Fecha Concepto")]))
    with pytest.raises(ValueError, match="Especie"):
        plan_columns(pages, COLUMNS)


def _word(text: str, x0: float, top: float) -> Word:
    return Word(text=text, x0=x0, top=top, x1=x0 + 30, bottom=top + 10, fontname="F", size=10)


def test_page_without_header_reuses_previous_columns() -> None:
    header = [_word("Fecha", 40, 100), _word("Especie", 300, 100), _word("Cantidad", 380, 100)]
    first = PageWords(1, 595, 842, [*header, _word("AL30", 300, 120), _word("Cuenta", 40, 60)])
    second = PageWords(
        2, 595, 842, [_word("Cuenta", 300, 20), _word("GD30", 300, 300), _word("Nota", 40, 300)]
    )
    plan = plan_columns([first, second], [ColumnSpec("Especie", "instrument")])
    redacted = apply_columns([first, second], plan)
    assert _texts(redacted[1]) == ["ESPECIE_02", "ESPECIE_03", "Nota"]
    # Words first seen on a carried-over page stay coded only inside the column.
    assert _texts(redacted[0])[-1] == "Cuenta"


def test_repeated_header_rows_start_new_sections_and_stay_readable() -> None:
    second_table = [
        *_row(600, "Fecha", "Descripción", "Especie", "Cantidad", "Importe"),
        *_row(580, "09/03/2026", "Compra YPFD", "YPFD", "10", "-45.000,00"),
    ]
    pages = extract_pages(make_pdf([*STATEMENT, *second_table]))
    redacted = apply_columns(pages, plan_columns(pages, COLUMNS))
    texts = _texts(redacted[0])
    assert texts.count("Especie") == 2 and texts.count("Descripción") == 2
    assert "YPFD" not in texts and texts.count("ESPECIE_03") == 2


def test_column_leaks_flags_unredacted_columns() -> None:
    pages = extract_pages(make_pdf(STATEMENT))
    plan = plan_columns(pages, COLUMNS)
    leaks = column_leaks(pages, pages, plan)
    assert "AL30" in leaks and "Rep" in leaks


def test_redact_pdf_file_with_columns(tmp_path: Path) -> None:
    source = tmp_path / "balanz.pdf"
    source.write_bytes(make_pdf(STATEMENT))
    target = tmp_path / "balanz.redacted.json"
    redact_pdf_file(source, target, [], rng=random.Random(2), columns=COLUMNS)
    assert "AL30" not in target.read_text(encoding="utf-8")
    assert len(load_pages(target)[0].words) == len(extract_pages(source.read_bytes())[0].words)


def test_cli_columns_and_keep(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "balanz.pdf").write_bytes(make_pdf(STATEMENT))
    args = ["balanz.pdf", "--instrument-column", "Especie", "--text-column", "Descripción"]
    assert main([*args, "--keep", "Rep"]) == 0
    texts = _texts(load_pages(tmp_path / "samples" / "balanz.redacted.json")[0])
    assert "Rep" in texts and "Arg" not in texts
    assert main(["balanz.pdf", "--out", "x.json", "--instrument-column", "Ticker"]) == 1
    assert not (tmp_path / "x.json").exists()


def test_dates_in_an_instrument_column_are_not_coded() -> None:
    header = [_word("Fecha", 40, 100), _word("Descripción", 100, 100), _word("Neto", 400, 100)]
    rows = [
        _word("Saldo", 100, 120),
        _word("al", 135, 120),
        _word("05/03/25", 160, 120),
        _word("05/03/25", 40, 140),
        _word("AL30", 100, 140),
        _word("5/3/2025", 160, 160),
    ]
    page = PageWords(1, 595, 842, [*header, *rows])
    plan = plan_columns([page], [ColumnSpec("Descripción", "instrument")])
    texts = _texts(apply_columns([page], plan)[0])
    assert texts.count("05/03/25") == 2 and "5/3/2025" in texts and "AL30" not in texts
