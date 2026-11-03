"""Typed data models and immutable configuration schemas for Baseline Strategies (Layer 7).

Governed by:
- PROJECT_SPEC.md §4, §5 (Comparators: No-trade reference & Predeclared simple strategy)
- DATA_AND_PERFORMANCE_POLICY.md §5 (Performance metrics)
- docs/experiment-register.md (Immutable experiment IDs and registration schema)
- Layer 7 Gate: Reproducibility, execution simulator parity, ledger reconciliation.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from finpilot.db.enums import DataMode


class BaselineStrategyType(StrEnum):
    """Supported baseline strategy identifiers for Layer 7."""

    NO_TRADE_REFERENCE = "NO_TRADE_REFERENCE"
    PREDECLARED_SIMPLE_STRATEGY = "PREDECLARED_SIMPLE_STRATEGY"


class MarketRegime(StrEnum):
    """Categorical intraday/daily market regime classification."""

    TRENDING_BULLISH = "TRENDING_BULLISH"
    TRENDING_BEARISH = "TRENDING_BEARISH"
    SIDEWAYS_CHOPPY = "SIDEWAYS_CHOPPY"


class ExperimentConfig(BaseModel):
    """Immutable configuration defining an evaluation experiment."""

    model_config = ConfigDict(frozen=True)

    experiment_id: str = Field(
        ..., description="Stable, unique experiment identifier (e.g. EXP-0001)"
    )
    strategy_type: BaselineStrategyType = Field(..., description="Type of baseline strategy")
    strategy_id: str = Field(
        ..., description="Frozen strategy version string (e.g. REF-NOTRADE-V1 or STRAT-SIMPLE-V1)"
    )
    policy_version: str = Field(default="TP-V1", description="Trade policy contract version")
    fee_schedule_version: str = Field(
        default="NSE_EQUITY_INTRADAY_V1", description="Statutory fee schedule version"
    )
    universe: tuple[str, ...] = Field(
        default=("RELIANCE", "TCS", "INFY"),
        description="Instrument symbols in the simulation universe",
    )
    start_date: date = Field(..., description="Simulation start date (inclusive)")
    end_date: date = Field(..., description="Simulation end date (inclusive)")
    initial_capital: Decimal = Field(
        default=Decimal("30000.00"), description="Starting scenario capital (default ₹30,000)"
    )
    max_risk_pct_per_trade: Decimal = Field(
        default=Decimal("0.02"), description="Risk capital fraction per trade (default 2%)"
    )
    max_single_position_exposure_pct: Decimal = Field(
        default=Decimal("0.50"), description="Max single position exposure limit (default 50%)"
    )
    volume_participation_cap: Decimal = Field(
        default=Decimal("0.10"),
        description="Max participation fraction of bar volume (default 10%)",
    )
    modelled_slippage_bps: Decimal = Decimal("2.0")
    mode: DataMode = Field(default=DataMode.SYNTHETIC_DEMO, description="Data provenance mode")
    description: str = Field(default="", description="Falsifiable hypothesis or run description")

    def compute_config_hash(self) -> str:
        """Compute deterministic SHA-256 digest of this experiment configuration."""
        canonical = {
            "experiment_id": self.experiment_id,
            "strategy_type": self.strategy_type.value,
            "strategy_id": self.strategy_id,
            "policy_version": self.policy_version,
            "fee_schedule_version": self.fee_schedule_version,
            "universe": sorted(self.universe),
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "initial_capital": str(self.initial_capital),
            "max_risk_pct_per_trade": str(self.max_risk_pct_per_trade),
            "max_single_position_exposure_pct": str(self.max_single_position_exposure_pct),
            "volume_participation_cap": str(self.volume_participation_cap),
            "modelled_slippage_bps": str(self.modelled_slippage_bps),
            "mode": self.mode.value,
        }
        encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


class DailyPerformanceRecord(BaseModel):
    """Daily performance snapshot for a single market session."""

    model_config = ConfigDict(frozen=True)

    session_date: date
    session_trades: int
    gross_pnl: Decimal
    fees: Decimal
    net_pnl: Decimal
    ending_cash: Decimal
    ending_equity: Decimal
    daily_return: Decimal
    capital_utilized_pct: Decimal
    regime: MarketRegime


class PeriodPerformanceRecord(BaseModel):
    """Aggregated periodic performance metrics (e.g. monthly)."""

    model_config = ConfigDict(frozen=True)

    period_label: str
    trades: int
    wins: int
    losses: int
    win_rate_pct: float
    gross_pnl: Decimal
    fees: Decimal
    net_pnl: Decimal


class InstrumentPerformanceRecord(BaseModel):
    """Per-instrument performance metrics across the simulation period."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    trades: int
    wins: int
    losses: int
    win_rate_pct: float
    gross_pnl: Decimal
    fees: Decimal
    net_pnl: Decimal


class RegimePerformanceRecord(BaseModel):
    """Performance metrics stratified by market regime."""

    model_config = ConfigDict(frozen=True)

    regime: MarketRegime
    sessions_count: int
    trades_count: int
    gross_pnl: Decimal
    fees: Decimal
    net_pnl: Decimal
    win_rate_pct: float


class ExperimentResult(BaseModel):
    """Immutable experiment result artifact containing metrics and ledger reconciliation."""

    model_config = ConfigDict(frozen=True)

    experiment_id: str
    config_hash: str
    strategy_id: str
    total_sessions: int
    active_sessions: int
    coverage_pct: float
    total_proposals: int
    approved_orders: int
    filled_orders: int
    partial_fills: int
    unfilled_orders: int
    total_trades: int
    winning_trades: int
    losing_trades: int
    scratch_trades: int
    win_rate_pct: float
    gross_pnl: Decimal
    total_fees: Decimal
    net_pnl: Decimal
    expectancy: Decimal
    profit_factor: float
    max_drawdown_amount: Decimal
    max_drawdown_pct: float
    daily_returns_mean: float
    daily_returns_std: float
    average_capital_utilization_pct: float
    peak_capital_utilization_pct: float
    ambiguity_rate_pct: float
    rejection_reasons: dict[str, int]
    daily_records: tuple[DailyPerformanceRecord, ...]
    period_records: tuple[PeriodPerformanceRecord, ...]
    instrument_records: tuple[InstrumentPerformanceRecord, ...]
    regime_records: tuple[RegimePerformanceRecord, ...]
    ledger_reconciled: bool
    ledger_discrepancy: Decimal
    result_hash: str

    @classmethod
    def calculate_result_hash(cls, payload: dict[str, Any]) -> str:
        """Compute deterministic SHA-256 digest of core result metrics."""
        summary = {
            "experiment_id": payload.get("experiment_id"),
            "config_hash": payload.get("config_hash"),
            "strategy_id": payload.get("strategy_id"),
            "total_sessions": payload.get("total_sessions"),
            "active_sessions": payload.get("active_sessions"),
            "total_trades": payload.get("total_trades"),
            "win_rate_pct": payload.get("win_rate_pct"),
            "gross_pnl": str(payload.get("gross_pnl")),
            "total_fees": str(payload.get("total_fees")),
            "net_pnl": str(payload.get("net_pnl")),
            "expectancy": str(payload.get("expectancy")),
            "profit_factor": payload.get("profit_factor"),
            "max_drawdown_amount": str(payload.get("max_drawdown_amount")),
            "ledger_reconciled": payload.get("ledger_reconciled"),
            "ledger_discrepancy": str(payload.get("ledger_discrepancy")),
        }
        encoded = json.dumps(summary, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
