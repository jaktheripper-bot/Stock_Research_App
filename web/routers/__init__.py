"""FastAPI modular routers package for Moatnomics."""

from web.routers.auth_billing import router as auth_billing_router
from web.routers.dossier import router as dossier_router
from web.routers.markets import router as markets_router
from web.routers.admin import router as admin_router

__all__ = [
    "auth_billing_router",
    "dossier_router",
    "markets_router",
    "admin_router",
]
