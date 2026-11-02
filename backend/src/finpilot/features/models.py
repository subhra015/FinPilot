"""Pydantic V2 domain models for features and point-in-time universe (Layer 5).

Governed by:
- ARCHITECTURE.md §2 (Feature Pipeline)
- DATA_AND_PERFORMANCE_POLICY.md §2, §3
- Layer 5 Gate & Security Controls (SEC-06, SEC-19)
"""

from __future__ import annotations

import math
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from finpilot.db.enums import DataMode
from finpilot.schemas.common import normalize_to_utc
from finpilot.schemas.errors import DomainValidationError, ErrorCode


class WarmupStatus(StrEnum):
    """Warm-up state of an indicator or feature calculation."""

    WARMED_UP = "WARMED_UP"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    SESSION_RESET = "SESSION_RESET"


class FeatureVector(BaseModel):
    """Immutable point-in-time feature vector for an instrument at a completed 5m candle.

    SEC-06 & SEC-19: Features are strictly causal, derived from completed bars up to
    `timestamp`. Client-side timestamps are normalized to UTC. NaN/Infinity are rejected.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    instrument_id: int = Field(..., ge=1, description="Stable internal instrument ID")
    symbol: str = Field(..., min_length=1, max_length=20, description="Active NSE ticker symbol")
    timestamp: datetime = Field(
        ...,
        description="Completed bar timestamp in UTC (decision point)",
    )
    feature_set_version: str = Field(
        ..., min_length=1, max_length=20, description="Feature set version (e.g. FS-V1)"
    )
    features: dict[str, float | None] = Field(
        ...,
        description="Feature key-value map. None indicates insufficient history/warm-up.",
    )
    is_fully_warmed_up: bool = Field(
        ...,
        description="True if all features in the catalog have sufficient history and are not None",
    )
    mode: DataMode = Field(
        default=DataMode.HISTORICAL_REPLAY,
        description="Execution mode (HISTORICAL_REPLAY, FORWARD_PAPER, SYNTHETIC_DEMO)",
    )
    bar_count_in_session: int = Field(
        ..., ge=0, le=74, description="0-indexed bar index within the trading session (0..74)"
    )
    metadata: dict[str, str] = Field(
        default_factory=dict,
        description="Mandatory proxy disclosures and provenance notes",
    )

    @field_validator("timestamp", mode="before")
    @classmethod
    def validate_and_normalize_timestamp(cls, v: Any) -> datetime:
        return normalize_to_utc(v)

    @field_validator("features")
    @classmethod
    def validate_no_nan_or_inf(cls, v: dict[str, float | None]) -> dict[str, float | None]:
        for k, val in v.items():
            if val is not None and (math.isnan(val) or math.isinf(val)):
                raise DomainValidationError(
                    f"Feature {k!r} has invalid non-finite value: {val!r}",
                    field=f"features.{k}",
                    code=ErrorCode.VALIDATION_ERROR,
                )
        return v


class FeatureBatch(BaseModel):
    """Batch of chronological feature vectors for an instrument."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    feature_set_version: str = Field(..., description="Feature set version")
    symbol: str = Field(..., description="Active NSE symbol")
    records: list[FeatureVector] = Field(..., description="Chronological feature vectors")


class UniverseMember(BaseModel):
    """Point-in-time universe member representation with historical eligibility."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    instrument_id: int = Field(..., ge=1)
    isin: str = Field(..., min_length=12, max_length=12)
    symbol: str = Field(..., min_length=1, max_length=20)
    valid_from: datetime
    valid_to: datetime | None = None
    status: str
    listing_date: datetime
    delisting_date: datetime | None = None
    historical_median_daily_turnover_inr: float | None = None
    is_eligible: bool = Field(..., description="True if eligible as of queried timestamp")
    ineligibility_reason: str | None = None

    @field_validator("valid_from", "valid_to", "listing_date", "delisting_date", mode="before")
    @classmethod
    def normalize_dates(cls, v: Any) -> datetime | None:
        if v is None:
            return None
        return normalize_to_utc(v)


class PointInTimeUniverseSnapshot(BaseModel):
    """Point-in-time universe snapshot at a specific evaluation timestamp.

    Guarantees no survivorship bias: companies listed after `as_of_timestamp` are excluded,
    while companies active at `as_of_timestamp` but delisted later remain eligible.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    as_of_timestamp: datetime = Field(..., description="Point-in-time query timestamp in UTC")
    universe_name: str = Field(..., min_length=1, max_length=100)
    members: list[UniverseMember] = Field(..., description="Universe candidate members")
    eligible_count: int = Field(..., ge=0, description="Count of eligible instruments")

    @field_validator("as_of_timestamp", mode="before")
    @classmethod
    def validate_timestamp(cls, v: Any) -> datetime:
        return normalize_to_utc(v)
