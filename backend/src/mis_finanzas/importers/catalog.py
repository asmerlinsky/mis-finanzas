"""The dedicated importers the app ships with. Registered once, at startup."""

from mis_finanzas.importers import registry
from mis_finanzas.importers.arca.invoice_pdf import ArcaInvoicePdf
from mis_finanzas.importers.arca.mis_comprobantes import MisComprobantesCsv
from mis_finanzas.importers.balanz.holdings_pdf import BalanzHoldingsPdf
from mis_finanzas.importers.balanz.movements_pdf import BalanzMovementsPdf
from mis_finanzas.importers.mercadopago.account_csv import MercadoPagoAccountCsv
from mis_finanzas.importers.santander.account_pdf import SantanderAccountPdf
from mis_finanzas.importers.santander.movements_xlsx import SantanderMovementsXlsx
from mis_finanzas.importers.santander.visa_pdf import SantanderVisaPdf

_registered = False


def register_builtin_importers() -> None:
    """Idempotent: the app factory and the command-line tools may both call it."""
    global _registered
    if _registered:
        return
    registry.register_file_importer(SantanderMovementsXlsx())
    registry.register_file_importer(MercadoPagoAccountCsv())
    registry.register_file_importer(MisComprobantesCsv())
    registry.register_page_importer(SantanderAccountPdf())
    registry.register_page_importer(SantanderVisaPdf())
    registry.register_page_importer(BalanzMovementsPdf())
    registry.register_page_importer(BalanzHoldingsPdf())
    registry.register_page_importer(ArcaInvoicePdf())
    _registered = True
