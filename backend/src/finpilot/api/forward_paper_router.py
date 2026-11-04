"""FastAPI Router for Forward Paper Trading & Live-Data Validation (Layer 16).

Governed by:
- ACCEPTANCE_GATES.md §2 (Layer 16 Gate)
- SECURITY_CHECKLIST.md SEC-01, SEC-06, SEC-15, SEC-16, SEC-18, SEC-19
- PROJECT_SPEC.md §4, §5, §7, §9, §11
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session as DBSession

from finpilot.db.enums import DataMode
from finpilot.db.models import User
from finpilot.forward.engine import ForwardPaperTradingEngine
from finpilot.forward.models import (
    DriftMonitorMetrics,
    ForwardDecision,
    ForwardPaperStatus,
    ForwardPerformanceMetrics,
    PredictionEventRecord,
    VirtualCapitalTier,
    VirtualPortfolioConfig,
)
from finpilot.schemas.candles import CandleBar

from .dependencies import get_current_user, get_db, require_csrf

router = APIRouter(prefix="/forward-paper", tags=["forward-paper"])

# In-memory engine store keyed by user identifier
_user_engines: dict[str, ForwardPaperTradingEngine] = {}


def get_user_engine(user: User) -> ForwardPaperTradingEngine:
    """Retrieve or create the authoritative ForwardPaperTradingEngine for the authenticated user."""
    key = str(user.id)
    if key not in _user_engines:
        cfg = VirtualPortfolioConfig(
            tier=VirtualCapitalTier.TIER_30K,
            initial_capital=Decimal("30000.00"),
            max_open_positions=1,
            portfolio_name=f"User-{user.id}-Forward-Paper",
        )
        _user_engines[key] = ForwardPaperTradingEngine(config=cfg)
    return _user_engines[key]


class ConfigurePortfolioRequest(BaseModel):
    """Request payload to configure virtual portfolio capital and parameters."""

    model_config = ConfigDict(extra="forbid")

    initial_capital: Decimal = Field(
        default=Decimal("30000.00"),
        ge=Decimal("1000.00"),
        le=Decimal("10000000.00"),
        description="User-selected virtual capital (integer-share cash constrained)",
    )
    tier: VirtualCapitalTier = Field(
        default=VirtualCapitalTier.TIER_30K,
        description="Standard capital tier or custom",
    )
    max_open_positions: int = Field(
        default=1,
        ge=1,
        le=5,
        description="Maximum concurrent open positions allowed by risk policy",
    )
    portfolio_name: str = Field(
        default="Forward Paper Portfolio",
        min_length=1,
        max_length=100,
    )


class FeedCandleRequest(BaseModel):
    """Payload to feed a live market candle into the 10-step forward pipeline."""

    model_config = ConfigDict(extra="forbid")

    instrument_id: int = Field(..., ge=1)
    symbol: str = Field(..., min_length=1, max_length=20)
    timestamp: datetime = Field(..., description="Candle start timestamp")
    open: Decimal = Field(..., gt=Decimal("0.0"))
    high: Decimal = Field(..., gt=Decimal("0.0"))
    low: Decimal = Field(..., gt=Decimal("0.0"))
    close: Decimal = Field(..., gt=Decimal("0.0"))
    volume: int = Field(..., ge=0)
    features: dict[str, float] | None = Field(default=None)
    wall_clock_time: datetime | None = Field(default=None)


class FeedCandleResponse(BaseModel):
    """Response containing prediction ledger event details."""

    model_config = ConfigDict(extra="forbid")

    processed: bool
    event: PredictionEventRecord | None = None
    decision: ForwardDecision | None = None
    reason: str


@router.post("/configure", response_model=ForwardPaperStatus)
def configure_portfolio(
    request: ConfigurePortfolioRequest,
    current_user: User = Depends(get_current_user),
    _csrf: None = Depends(require_csrf),
) -> ForwardPaperStatus:
    """Configure or reset the user's virtual paper trading portfolio."""
    key = str(current_user.id)
    cfg = VirtualPortfolioConfig(
        tier=request.tier,
        initial_capital=request.initial_capital,
        max_open_positions=request.max_open_positions,
        portfolio_name=request.portfolio_name,
    )
    engine = ForwardPaperTradingEngine(config=cfg)
    _user_engines[key] = engine
    return engine.get_status()


@router.get("/status", response_model=ForwardPaperStatus)
def get_forward_paper_status(
    current_user: User = Depends(get_current_user),
) -> ForwardPaperStatus:
    """Retrieve the current forward paper trading engine status."""
    engine = get_user_engine(current_user)
    return engine.get_status()


@router.get("/prediction-ledger", response_model=list[PredictionEventRecord])
def get_prediction_ledger(
    symbol: str | None = Query(default=None, max_length=20),
    decision: ForwardDecision | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
) -> list[PredictionEventRecord]:
    """Retrieve pre-outcome recorded predictions from the append-only ledger."""
    engine = get_user_engine(current_user)
    events = engine.ledger.get_events(symbol=symbol)
    if decision is not None:
        events = [e for e in events if e.decision == decision]
    return events[:limit]


@router.get("/performance", response_model=ForwardPerformanceMetrics)
def get_forward_performance(
    current_user: User = Depends(get_current_user),
) -> ForwardPerformanceMetrics:
    """Retrieve empirical performance metrics for forward paper trading."""
    engine = get_user_engine(current_user)
    return engine.get_performance_metrics()


@router.get("/monitoring", response_model=DriftMonitorMetrics)
def get_drift_and_health_monitoring(
    current_user: User = Depends(get_current_user),
) -> DriftMonitorMetrics:
    """Retrieve real-time drift, latency, and data health telemetry."""
    engine = get_user_engine(current_user)
    return engine.get_drift_metrics()


@router.post("/feed-candle", response_model=FeedCandleResponse)
def feed_candle(
    request: FeedCandleRequest,
    current_user: User = Depends(get_current_user),
    _csrf: None = Depends(require_csrf),
    db: DBSession = Depends(get_db),
) -> FeedCandleResponse:
    """Ingest a fresh market candle through the 10-step forward paper pipeline."""
    engine = get_user_engine(current_user)
    candle = CandleBar(
        symbol=request.symbol,
        timestamp=request.timestamp,
        open=request.open,
        high=request.high,
        low=request.low,
        close=request.close,
        volume=request.volume,
        mode=DataMode.FORWARD_PAPER,
    )
    event = engine.process_completed_candle(bar=candle)
    if event is None:
        return FeedCandleResponse(
            processed=False,
            event=None,
            decision=None,
            reason="Candle rejected by market hours filter or data anomaly check",
        )
    return FeedCandleResponse(
        processed=True,
        event=event,
        decision=event.decision,
        reason=event.decision_reason,
    )
