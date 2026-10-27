"""Generic CSV/Excel importer, on synthetic files shaped like typical bank exports."""

import io
from datetime import date, datetime
from decimal import Decimal

import pytest
from openpyxl import Workbook

from mis_finanzas.importers.base import ImportFileError
from mis_finanzas.importers.tabular import GenericTabularImporter, TabularMapping

AMOUNT_MAPPING = TabularMapping(
    date_column="Fecha", description_columns=["Concepto"], amount_column="Importe"
)

SPLIT_MAPPING = TabularMapping(
    date_column="Fecha",
    description_columns=["Concepto", "Detalle"],
    debit_column="Débito",
    credit_column="Crédito",
)


def test_csv_with_semicolons_and_argentine_amounts() -> None:
    content = (
        b"Fecha;Concepto;Importe\n02/01/2026;Supermercado;-12.345,67\n"
        b"03/01/2026;Sueldo;1.000.000,00\n"
    )
    result = GenericTabularImporter(AMOUNT_MAPPING).parse(content, "mov.csv")
    assert result.errors == []
    assert [(r.date, r.amount, r.description) for r in result.rows] == [
        (date(2026, 1, 2), Decimal("-12345.67"), "Supermercado"),
        (date(2026, 1, 3), Decimal("1000000.00"), "Sueldo"),
    ]


def test_debit_credit_columns_and_joined_description() -> None:
    content = (
        "Fecha,Concepto,Detalle,Débito,Crédito\n"
        '05/02/2026,Transferencia,a Broker,"50.000,00",\n'
        '06/02/2026,Transferencia,de Juan,,"1.500,50"\n'.encode()
    )
    result = GenericTabularImporter(SPLIT_MAPPING).parse(content, "mov.csv")
    assert [(r.amount, r.description) for r in result.rows] == [
        (Decimal("-50000.00"), "Transferencia a Broker"),
        (Decimal("1500.50"), "Transferencia de Juan"),
    ]


def test_preamble_lines_blank_rows_and_bad_rows() -> None:
    mapping = AMOUNT_MAPPING.model_copy(update={"header_row": 3})
    content = (
        b"Banco Ejemplo\nCuenta 123\nFecha;Concepto;Importe\n"
        b"01/03/2026;Cafe;-1.500,00\n;;\n31/02/2026;Fecha mala;-1,00\n"
        b"02/03/2026;Monto malo;abc\n"
    )
    result = GenericTabularImporter(mapping).parse(content, "mov.csv")
    assert [r.line_number for r in result.rows] == [4]
    assert [e.line_number for e in result.errors] == [6, 7]
    assert "bad date" in result.errors[0].message


def test_negate_flips_card_charges() -> None:
    mapping = AMOUNT_MAPPING.model_copy(update={"negate": True})
    content = b"Fecha;Concepto;Importe\n01/03/2026;Compra;100,00\n"
    result = GenericTabularImporter(mapping).parse(content, "card.csv")
    assert result.rows[0].amount == Decimal("-100.00")


def test_windows_1252_encoding() -> None:
    content = "Fecha;Concepto;Importe\n01/03/2026;Peluquería;-10,00\n".encode("cp1252")
    result = GenericTabularImporter(AMOUNT_MAPPING).parse(content, "mov.csv")
    assert result.rows[0].description == "Peluquería"


def test_xlsx_with_native_dates_and_numbers() -> None:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.append(["Fecha", "Concepto", "Importe"])
    sheet.append([datetime(2026, 4, 1), "Farmacia", -2500.5])
    sheet.append([None, None, None])
    buffer = io.BytesIO()
    workbook.save(buffer)
    result = GenericTabularImporter(AMOUNT_MAPPING).parse(buffer.getvalue(), "mov.xlsx")
    assert [(r.date, r.amount) for r in result.rows] == [(date(2026, 4, 1), Decimal("-2500.5"))]


def test_missing_column_is_a_file_error() -> None:
    with pytest.raises(ImportFileError, match="Importe"):
        GenericTabularImporter(AMOUNT_MAPPING).parse(b"Fecha;Concepto\n01/01/2026;x\n", "a.csv")


def test_unsupported_extension_is_a_file_error() -> None:
    with pytest.raises(ImportFileError, match="unsupported"):
        GenericTabularImporter(AMOUNT_MAPPING).parse(b"", "statement.pdf")


def test_mapping_requires_exactly_one_amount_mode() -> None:
    with pytest.raises(ValueError):
        TabularMapping(date_column="F", description_columns=["C"])
    with pytest.raises(ValueError):
        TabularMapping(
            date_column="F", description_columns=["C"], amount_column="I", debit_column="D"
        )
