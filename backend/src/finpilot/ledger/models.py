"""Domain schemas for the append-only prediction, execution, and outcome audit ledger (Layer 12).

Governed by:
- ARCHITECTURE.md §5
- PROJECT_SPEC.md §3, §10, §11
- SECURITY_CHECKLIST.md SEC-06, SEC-19
- Layer 12 Gate: Append-only ledger events, separation of hypothetical from paper outcomes,
  tamper-evident hash chaining, and deterministic replay.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from finpilot.db.enums import DataMode, LedgerEventType


class LedgerEventPayload(BaseModel):
    """Canonical structured payload stored within an append-only ledger event record."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(..., min_length=1, max_length=64)
    event_type: LedgerEventType
    timestamp: datetime
    mode: DataMode = Field(default=DataMode.HISTORICAL_REPLAY)
    portfolio_id: str | None = Field(default=None)
    account_id: str | None = Field(default=None)

    # Opportunity & Decision Metadata
    opportunity_id: str = Field(..., min_length=1, max_length=64)
    symbol: str = Field(..., min_length=1, max_length=20)
    instrument_id: int | None = Field(default=None)
    decision_state: str = Field(
        ..., description="e.g. ACCEPTED, NO_TRADE, INSUFFICIENT_DATA, RISK_REJECTED"
    )

    # Governance & Version Provenance
    policy_version: str = Field(default="TP-V1")
    model_id: str | None = Field(default=None)
    calibration_policy_id: str | None = Field(default=None)
    feature_set_version: str = Field(default="FS-V1")
    features_snapshot: dict[str, float] | None = Field(default=None)

    # Quantities, Predictions & Economics
    predicted_probability: float | None = Field(default=None)
    calibrated_probability: float | None = Field(default=None)
    estimated_expectancy: float | None = Field(default=None)

    # Risk Engine Decision
    risk_decision: dict[str, Any] | None = Field(
        default=None,
        description="Authorization token ID or machine-readable rejection reasons",
    )

    # Execution & Portfolio State
    order_id: str | None = Field(default=None)
    fill_details: dict[str, Any] | None = Field(
        default=None,
        description="e.g. fill_price, fill_quantity, fill_timestamp",
    )
    exit_details: dict[str, Any] | None = Field(
        default=None,
        description="e.g. exit_price, exit_quantity, exit_reason",
    )
    cost_breakdown: dict[str, Any] | None = Field(
        default=None,
        description="Statutory NSE fees, brokerage, STT",
    )
    gross_pnl: Decimal | None = Field(default=None)
    net_pnl: Decimal | None = Field(default=None)

    # Separation of Hypothetical from Paper Portfolio Outcomes
    is_hypothetical: bool = Field(
        default=False,
        description="True for counterfactual policy simulation; False for paper portfolio ledger",
    )

    # Corrections (Never silent mutation)
    prior_event_id: str | None = Field(
        default=None,
        description="ID of prior event being corrected by this new event",
    )
    correction_reason: str | None = Field(default=None)


class ReplayVerificationResult(BaseModel):
    """Audit outcome produced by deterministic ledger replay and hash-chain validation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    is_valid: bool
    events_replayed: int
    corrections_applied: int
    chain_verified: bool
    reconstructed_cash: Decimal
    reconstructed_positions: dict[str, int]
    reconstructed_realized_pnl: Decimal
    hypothetical_realized_pnl: Decimal = Field(default=Decimal("0.00"))
    tamper_detected: bool = Field(default=False)
    tamper_details: list[str] = Field(default_factory=list)
