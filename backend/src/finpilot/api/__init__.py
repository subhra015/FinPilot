"""API routers and dependencies package (Layer 12)."""

from __future__ import annotations

from .account_router import router as account_router
from .auth_router import router as auth_router
from .evaluation_router import router as evaluation_router
from .forward_paper_router import router as forward_paper_router
from .health_router import router as health_router
from .ledger_router import router as ledger_router
from .model_router import router as model_router
from .portfolio_router import router as portfolio_router
from .risk_router import router as risk_router

__all__ = [
    "auth_router",
    "account_router",
    "evaluation_router",
    "forward_paper_router",
    "health_router",
    "portfolio_router",
    "ledger_router",
    "risk_router",
    "model_router",
]
