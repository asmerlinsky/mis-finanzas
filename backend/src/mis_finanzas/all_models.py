"""Every table module, imported so `Base.metadata` is complete (for Alembic and tests)."""

from mis_finanzas.core.db import Base
from mis_finanzas.importers import models as importer_models
from mis_finanzas.investments import models as investment_models
from mis_finanzas.ledger import models as ledger_models
from mis_finanzas.market import models as market_models

__all__ = ["Base", "importer_models", "investment_models", "ledger_models", "market_models"]
