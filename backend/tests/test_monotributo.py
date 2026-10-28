"""Monotributo: ARCA's export and invoice PDFs, category tables and status. Invented values."""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from arca_fixtures import DEFAULT_ROWS, comprobantes_csv, invoice_pdf, invoice_row
from mis_finanzas.importers.arca.invoice_pdf import ArcaInvoicePdf
from mis_finanzas.importers.arca.mis_comprobantes import MisComprobantesCsv
from mis_finanzas.importers.pdf_words import extract_pages
from mis_finanzas.monotributo.categories import Category, CategoryTable, load_tables, table_on
from mis_finanzas.monotributo.status import compute_status, next_recategorization_window

TABLE = CategoryTable(
    date(2026, 8, 1),
    (
        Category("A", Decimal(1000), Decimal(10)),
        Category("B", Decimal(2000), Decimal(20)),
        Category("C", Decimal(4000), Decimal(40)),
    ),
)


def test_export_is_read_by_column_name() -> None:
    importer = MisComprobantesCsv()
    content = comprobantes_csv(DEFAULT_ROWS)
    assert importer.detect("comprobantes.csv", content)
    result = importer.parse(content, "comprobantes.csv")
    assert result.errors == [] and result.rows == []
    assert result.invoices is not None
    invoices = result.invoices.invoices
    assert [(i.key.type_code, i.key.number, i.currency, i.total_ars) for i in invoices] == [
        (19, 7, "USD", Decimal("3000000.0000")),
        (11, 3, "ARS", Decimal("500000.00")),
        (21, 2, "USD", Decimal("-1000000.0000")),  # a credit note subtracts
    ]
    assert invoices[0].receiver_name == "Cliente Ejemplo SRL"
    assert result.metadata == {"periodo": "10/03/2026 - 10/05/2026"}


def test_arca_download_with_quoted_names_and_values() -> None:
    """ARCA's own CSV quotes every column name and value."""
    importer = MisComprobantesCsv()
    content = comprobantes_csv(DEFAULT_ROWS, quoted=True)
    assert importer.detect("comprobantes.csv", content)
    result = importer.parse(content, "comprobantes.csv")
    assert result.errors == []
    assert result.invoices is not None
    assert [(i.key.type_code, i.key.number) for i in result.invoices.invoices] == [
        (19, 7),
        (11, 3),
        (21, 2),
    ]


def test_type_with_its_name_is_read() -> None:
    row = invoice_row("2026-03-10", 19, 9, "100,00")
    row[1] = "11 - Factura C"
    result = MisComprobantesCsv().parse(comprobantes_csv([row], quoted=True), "c.csv")
    assert result.errors == [] and result.invoices is not None
    assert result.invoices.invoices[0].key.type_code == 11


@pytest.mark.parametrize(
    ("row", "message"),
    [
        (invoice_row("2026-03-10", 19, 8, "100,00", imp_total="1"), "not the sum of its parts"),
        (invoice_row("2026-03-10", 6, 8, "100,00"), "type 6 is not supported"),
        (invoice_row("2026-03-10", 19, 8, "100,00", currency="EUR"), "currency"),
    ],
)
def test_rows_that_dont_add_up_or_arent_supported_are_errors(row: list[str], message: str) -> None:
    result = MisComprobantesCsv().parse(comprobantes_csv([row]), "c.csv")
    [error] = result.errors
    assert message in error.message


def test_invoice_pdf_is_read_from_page_1() -> None:
    pages = extract_pages(invoice_pdf())
    importer = ArcaInvoicePdf()
    assert importer.detect_pages(pages)
    result = importer.parse_pages(pages)
    assert result.failed_checks == []
    assert result.invoices is not None and result.invoices.pdf is not None
    pdf = result.invoices.pdf
    assert (pdf.key.type_code, pdf.key.point_of_sale, pdf.key.number) == (19, 1, 7)
    assert (pdf.issued_on, pdf.currency, pdf.total) == (
        date(2026, 3, 10),
        "USD",
        Decimal("3000.00"),
    )
    assert result.metadata == {"comprobante": "Factura E 00001-00000007", "fecha": "10/03/2026"}
    # Read so that the PDF can create its invoice when the export doesn't have it yet.
    assert (pdf.fx_rate, pdf.receiver_name) == (Decimal("1000.000000"), "Cliente Ejemplo SRL")


def test_invoice_pdf_code_must_match_title_and_letter() -> None:
    result = ArcaInvoicePdf().parse_pages(extract_pages(invoice_pdf(code="11")))
    assert [c.name for c in result.failed_checks] == ["código del comprobante"]


def _upload(client: TestClient, path: str, name: str, content: bytes) -> Any:
    return client.post(path, files={"file": (name, content, "application/octet-stream")})


def test_newer_export_updates_and_adds(client: TestClient) -> None:
    assert (
        _upload(client, "/api/imports", "c1.csv", comprobantes_csv(DEFAULT_ROWS)).status_code == 201
    )
    newer = [
        *DEFAULT_ROWS[:2],
        invoice_row("2026-05-10", 21, 2, "1000,00", receiver="Cliente Renombrado SA"),
        invoice_row("2026-06-10", 19, 8, "2000,00"),
    ]
    preview = _upload(client, "/api/imports/preview", "c2.csv", comprobantes_csv(newer)).json()
    assert preview["invoices"] == {
        "invoices": 4,
        "new": 1,
        "changed": ["Nota de Crédito E 00001-00000002"],
        "pdf_for": None,
        "pdf_creates": False,
    }
    assert _upload(client, "/api/imports", "c2.csv", comprobantes_csv(newer)).status_code == 201
    listed = client.get("/api/monotributo/invoices").json()
    assert [(i["number"], i["total_ars"]) for i in listed] == [
        ("00001-00000008", "2000000.00"),
        ("00001-00000002", "-1000000.00"),
        ("00001-00000003", "500000.00"),
        ("00001-00000007", "3000000.00"),
    ]


def test_pdf_alone_creates_its_invoice_and_the_export_confirms_it(client: TestClient) -> None:
    preview = _upload(client, "/api/imports/preview", "f.pdf", invoice_pdf()).json()
    assert preview["importer"] == "arca_invoice_pdf"
    assert preview["invoices"]["pdf_creates"] is True
    assert [c["name"] for c in preview["checks"] if not c["ok"]] == []
    assert _upload(client, "/api/imports", "f.pdf", invoice_pdf()).status_code == 201
    [created] = client.get("/api/monotributo/invoices").json()
    assert (created["source"], created["has_pdf"], created["total_ars"]) == (
        "pdf",
        True,
        "3000000.00",
    )
    assert created["receiver_name"] == "Cliente Ejemplo SRL"
    # The export takes over the same invoice: confirmed, PDF still attached, no duplicate.
    _upload(client, "/api/imports", "c.csv", comprobantes_csv(DEFAULT_ROWS))
    listed = client.get("/api/monotributo/invoices").json()
    [confirmed] = [i for i in listed if i["number"] == "00001-00000007"]
    assert (confirmed["source"], confirmed["has_pdf"], len(listed)) == ("export", True, 3)
    response = client.get(f"/api/monotributo/invoices/{confirmed['id']}/pdf")
    assert response.status_code == 200 and response.content.startswith(b"%PDF")


def test_pdf_of_a_known_invoice_must_agree_with_it(client: TestClient) -> None:
    _upload(client, "/api/imports", "c.csv", comprobantes_csv(DEFAULT_ROWS))
    wrong = invoice_pdf(total="USD 3100,00")
    preview = _upload(client, "/api/imports/preview", "g.pdf", wrong).json()
    assert preview["invoices"]["pdf_creates"] is False
    assert [c["name"] for c in preview["checks"] if not c["ok"]] == ["importe total"]
    assert _upload(client, "/api/imports", "g.pdf", wrong).status_code == 409
    assert _upload(client, "/api/imports", "f.pdf", invoice_pdf()).status_code == 201


def test_category_is_validated_and_shown_in_status(client: TestClient) -> None:
    assert client.put("/api/monotributo/profile", json={"category": "Z"}).status_code == 422
    assert client.put("/api/monotributo/profile", json={"category": "d"}).status_code == 204
    body = client.get("/api/monotributo/status").json()
    assert body["category"]["letter"] == "D"
    assert body["income"] == "0"


@pytest.mark.parametrize(
    ("today", "deadline", "window"),
    [
        (date(2026, 2, 5), date(2026, 2, 5), (date(2025, 1, 1), date(2025, 12, 31))),
        (date(2026, 2, 6), date(2026, 8, 5), (date(2025, 7, 1), date(2026, 6, 30))),
        (date(2026, 10, 28), date(2027, 2, 5), (date(2026, 1, 1), date(2026, 12, 31))),
    ],
)
def test_next_recategorization(today: date, deadline: date, window: tuple[date, date]) -> None:
    got_deadline, got_window = next_recategorization_window(today)
    assert (got_deadline, (got_window.start, got_window.end)) == (deadline, window)


def test_status_last_12_months_warnings_and_implied_category() -> None:
    invoices = [
        (date(2025, 10, 28), Decimal(500)),  # a year ago today: outside the last 12 months
        (date(2025, 12, 1), Decimal(600)),
        (date(2026, 7, 1), Decimal(1000)),
        (date(2026, 9, 1), Decimal(-100)),  # credit note
    ]
    status = compute_status(invoices, TABLE, "B", date(2026, 10, 28))
    assert (status.income, status.margin, status.usage) == (
        Decimal(1500),
        Decimal(500),
        Decimal("0.75"),
    )
    assert status.level is None  # below 80%
    assert status.next.income == Decimal(900)  # 2026 so far
    assert status.next.implied is not None and status.next.implied.letter == "A"
    over = compute_status(invoices, TABLE, "A", date(2026, 10, 28))
    assert (over.level, over.margin) == (Decimal(1), Decimal(-500))


def test_status_above_the_highest_category() -> None:
    status = compute_status([(date(2026, 3, 1), Decimal(5000))], TABLE, None, date(2026, 10, 28))
    assert (status.category, status.usage, status.level) == (None, None, None)
    assert status.next.implied is None


def test_shipped_category_table() -> None:
    tables = load_tables()
    table = table_on(tables, date(2026, 10, 28))
    assert [c.letter for c in table.categories] == list("ABCDEFGHIJK")
    caps = [c.annual_cap for c in table.categories]
    assert caps == sorted(caps)
