"""Domain models and schemas for trade-policy labeling and temporal splits (Layer 8).

Governed by:
- docs/trade-policy-contract-v1.md (TP-V1 Policy Contract)
- docs/execution-policy.md (Layer 6 Matching & Fee Engine)
- DATA_AND_PERFORMANCE_POLICY.md §2, §7, §8
- ARCHITECTURE.md §2 (Feature & Label Pipeline)
- Layer 8 Gate: Labeling under realistic execution, globally chronological splits,
  purge/embargo, locked final test.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from finpilot.schemas.common import normalize_to_utc


class LabelingApproach(StrEnum):
    """Methodological approach for trade outcome labeling and cost treatment.

    FinPilot MVP establishes Approach A as the authoritative standard:
    - APPROACH_A_SHARED_SIZING: A quantity/sizing convention shared by label generation
      and portfolio simulation (₹30k scenario, 1% risk = ₹300, integer shares, 2 bps slippage,
      and full NSE statutory fees applied during label computation).
    - APPROACH_B_GROSS_MODELING: Model gross outcomes with quantity-specific costs deferred
      to downstream economics. (Documented for completeness; never mixed with A).
    """

    APPROACH_A_SHARED_SIZING = "APPROACH_A_SHARED_SIZING"
    APPROACH_B_GROSS_MODELING = "APPROACH_B_GROSS_MODELING"


class PartitionType(StrEnum):
    """Strictly sequential chronological validation partitions."""

    TRAIN = "TRAIN"
    DEV_MODEL_SELECTION = "DEV_MODEL_SELECTION"
    CALIBRATION = "CALIBRATION"
    THRESHOLD_SELECTION = "THRESHOLD_SELECTION"
    LOCKED_FINAL_TEST = "LOCKED_FINAL_TEST"


class TradeOutcomeReason(StrEnum):
    """Terminal reason for simulated trade outcome under TP-V1."""

    TARGET_HIT = "TARGET_HIT"
    STOP_LOSS_HIT = "STOP_LOSS_HIT"
    GAP_STOP_HIT = "GAP_STOP_HIT"
    SAME_BAR_AMBIGUOUS_STOP = "SAME_BAR_AMBIGUOUS_STOP"
    MAX_HOLDING_EXPIRY = "MAX_HOLDING_EXPIRY"
    SESSION_SQUARE_OFF = "SESSION_SQUARE_OFF"
    DATA_FEED_INTERRUPTED = "DATA_FEED_INTERRUPTED"


class TradePolicyLabel(BaseModel):
    """Immutable labeled sample representing an executable trade opportunity under TP-V1.

    SEC-06 & SEC-19: Features are causal and derived strictly up to decision_time.
    Fills execute at next-bar open (t_entry >= decision_time + 5m). P&L and binary label
    account for statutory fees, slippage, and integer share sizing.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    sample_id: str = Field(..., min_length=5, max_length=100, description="Unique sample ID")
    instrument_id: int = Field(..., ge=1, description="Stable internal instrument ID")
    symbol: str = Field(..., min_length=1, max_length=20, description="NSE ticker symbol")
    decision_time: datetime = Field(
        ..., description="Timestamp of completed 5m decision candle (UTC)"
    )
    entry_time: datetime = Field(..., description="Timestamp of next-candle open entry fill (UTC)")
    exit_time: datetime = Field(
        ..., description="Timestamp of candle where trade exit occurred (UTC)"
    )
    holding_bars: int = Field(..., ge=1, description="Number of 5-minute bars position was held")
    entry_price: Decimal = Field(..., gt=Decimal("0.00"), description="Effective entry fill price")
    exit_price: Decimal = Field(..., gt=Decimal("0.00"), description="Effective exit fill price")
    quantity: int = Field(..., ge=1, description="Integer share quantity allocated")
    gross_pnl: Decimal = Field(..., description="Gross trade P&L in INR")
    fees: Decimal = Field(
        ..., ge=Decimal("0.00"), description="Total statutory & broker fees in INR"
    )
    net_pnl: Decimal = Field(..., description="Net trade P&L in INR after all costs")
    gross_return: Decimal = Field(..., description="Gross return on trade notional")
    net_return: Decimal = Field(..., description="Net return on trade notional")
    binary_label: int = Field(
        ...,
        ge=0,
        le=1,
        description="1 if net_pnl > 0.00 else 0 (Net-positive under executable trade policy)",
    )
    outcome_reason: TradeOutcomeReason = Field(
        ..., description="Primary reason for trade exit resolution"
    )
    is_ambiguous_exit: bool = Field(
        default=False,
        description="True if stop and target hit same bar (conservative stop applied)",
    )
    is_gap_fill: bool = Field(
        default=False,
        description="True if gapped through stop loss resulting in worse exit fill",
    )
    pit_universe_eligible: bool = Field(
        default=True,
        description="True if instrument was eligible in point-in-time universe at decision_time",
    )
    features: dict[str, float | None] = Field(
        ..., description="Point-in-time causal feature values at decision_time"
    )
    policy_version: str = Field(default="TP-V1", max_length=20)
    labeling_approach: LabelingApproach = Field(default=LabelingApproach.APPROACH_A_SHARED_SIZING)

    @field_validator("decision_time", "entry_time", "exit_time", mode="before")
    @classmethod
    def validate_utc(cls, v: Any) -> datetime:
        return normalize_to_utc(v)


class PartitionManifest(BaseModel):
    """Metadata and statistics for a single temporal partition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    partition_type: PartitionType = Field(..., description="Partition identifier")
    start_time: datetime = Field(..., description="Earliest decision timestamp in partition (UTC)")
    end_time: datetime = Field(..., description="Latest decision timestamp in partition (UTC)")
    sample_count: int = Field(..., ge=0, description="Total labeled samples in partition")
    symbol_counts: dict[str, int] = Field(
        default_factory=dict, description="Number of samples per symbol"
    )
    positive_count: int = Field(..., ge=0, description="Count of positive labels (net_pnl > 0)")
    negative_count: int = Field(
        ..., ge=0, description="Count of non-positive labels (net_pnl <= 0)"
    )
    win_rate: float = Field(..., ge=0.0, le=1.0, description="Fraction of net-profitable trades")
    mean_net_pnl: Decimal = Field(..., description="Average net P&L per trade in INR")
    purged_count: int = Field(
        default=0,
        ge=0,
        description="Number of candidate samples purged due to boundary overlap",
    )
    embargo_bars: int = Field(
        default=0,
        ge=0,
        description="Number of embargoed bars following this partition",
    )
    sample_ids_hash: str = Field(
        ...,
        description="SHA-256 digest of sorted sample_ids ensuring partition immutability",
    )

    @field_validator("start_time", "end_time", mode="before")
    @classmethod
    def validate_utc(cls, v: Any) -> datetime:
        return normalize_to_utc(v)


class SplitManifest(BaseModel):
    """Complete provenance and audit record for globally chronological dataset splits.

    Guarantees:
    - Global chronological ordering across all instruments (no time-inversion).
    - Boundary purge and embargo accounting.
    - Locked final test partition with cryptographic SHA-256 digest.
    - Explicit limitation disclosures regarding historical universe/survivorship data.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    manifest_id: str = Field(
        ..., min_length=5, max_length=100, description="Unique split manifest ID"
    )
    created_at: datetime = Field(..., description="Manifest generation timestamp (UTC)")
    policy_version: str = Field(default="TP-V1", max_length=20)
    dataset_hash: str = Field(..., description="SHA-256 digest of input market dataset")
    labeling_approach: LabelingApproach = Field(default=LabelingApproach.APPROACH_A_SHARED_SIZING)
    partitions: dict[PartitionType, PartitionManifest] = Field(
        ..., description="Manifests for all 5 partitions"
    )
    total_samples: int = Field(..., ge=0, description="Total active labeled samples across splits")
    total_purged: int = Field(..., ge=0, description="Total samples purged across all boundaries")
    excluded_rows_count: int = Field(
        default=0,
        ge=0,
        description="Total raw rows excluded due to cutoff, warmup, or universe ineligibility",
    )
    locked_final_test_hash: str = Field(
        ..., description="SHA-256 hash of LOCKED_FINAL_TEST partition sample IDs"
    )
    is_final_test_locked: bool = Field(
        default=True,
        description="Flag indicating that final test set is locked against routine tuning",
    )
    embargo_justification: str = Field(
        ...,
        description="Scientific justification for the chosen embargo horizon",
    )
    survivorship_bias_limitation: str = Field(
        ...,
        description="Formal documentation of historical universe and survivorship limitations",
    )

    @field_validator("created_at", mode="before")
    @classmethod
    def validate_utc(cls, v: Any) -> datetime:
        return normalize_to_utc(v)

    def calculate_manifest_hash(self) -> str:
        """Compute deterministic SHA-256 hash of this split manifest."""
        manifest_dict = self.model_dump(mode="json")
        canonical_json = json.dumps(manifest_dict, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
