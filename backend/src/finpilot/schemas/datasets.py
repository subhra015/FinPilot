"""Dataset manifest and provider metadata schemas (Layer 3).

Enforces:
- SHA-256 integrity checksum format (64-char lowercase hex).
- Time span bounds (start <= end).
- Non-negative row counts.
- Strict provenance tracking for external datasets.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from finpilot.db.enums import DataMode

from .common import normalize_to_utc
from .errors import DomainValidationError, ErrorCode

SHA256_REGEX = re.compile(r"^[a-f0-9]{64}$")


class DataSourceMetadata(BaseModel):
    """Metadata describing external data sources and legal/provenance status."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(..., min_length=1, max_length=100)
    provider_name: str = Field(..., min_length=1, max_length=100)
    terms_verified: bool = Field(default=False)
    license_reference: str = Field(..., min_length=1, max_length=200)
    fetch_timestamp: datetime = Field(...)
    provenance_hash: str = Field(..., min_length=64, max_length=64)

    @field_validator("fetch_timestamp", mode="before")
    @classmethod
    def normalize_fetch_ts(cls, v: Any) -> datetime:
        return normalize_to_utc(v)

    @field_validator("provenance_hash")
    @classmethod
    def validate_hash_format(cls, v: str) -> str:
        clean = v.strip()
        if not SHA256_REGEX.match(clean):
            raise DomainValidationError(
                f"Invalid provenance SHA-256 hash: {v!r}. Must be 64-char lowercase hex.",
                field="provenance_hash",
                code=ErrorCode.VALIDATION_ERROR,
            )
        return clean


class DatasetManifestBase(BaseModel):
    """Manifest for analytical Parquet/Arrow dataset files."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_name: str = Field(..., min_length=1, max_length=100)
    dataset_version: str = Field(..., min_length=1, max_length=50)
    mode: DataMode = Field(default=DataMode.HISTORICAL_REPLAY)
    provider_source: str = Field(..., min_length=1, max_length=100)
    file_path_or_uri: str = Field(..., min_length=1, max_length=500)
    sha256_checksum: str = Field(..., min_length=64, max_length=64)
    row_count: int = Field(..., ge=0, le=10_000_000_000)
    start_timestamp: datetime = Field(...)
    end_timestamp: datetime = Field(...)
    schema_version: str = Field(..., min_length=1, max_length=50)

    @field_validator("start_timestamp", "end_timestamp", mode="before")
    @classmethod
    def normalize_manifest_timestamps(cls, v: Any) -> datetime:
        return normalize_to_utc(v)

    @field_validator("sha256_checksum")
    @classmethod
    def validate_checksum(cls, v: str) -> str:
        clean = v.strip()
        if not SHA256_REGEX.match(clean):
            raise DomainValidationError(
                f"Invalid SHA-256 checksum: {v!r}. Must be 64-character lowercase hex.",
                field="sha256_checksum",
                code=ErrorCode.VALIDATION_ERROR,
            )
        return clean

    @model_validator(mode="after")
    def validate_timestamp_order(self) -> DatasetManifestBase:
        if self.start_timestamp > self.end_timestamp:
            raise DomainValidationError(
                f"start_timestamp ({self.start_timestamp.isoformat()}) must be "
                f"<= end_timestamp ({self.end_timestamp.isoformat()}).",
                field="start_timestamp",
                code=ErrorCode.VALIDATION_ERROR,
            )
        return self


class DatasetManifestCreate(DatasetManifestBase):
    """Payload to create a new dataset manifest."""


class DatasetManifestRead(DatasetManifestBase):
    """Read representation of a dataset manifest."""

    id: int
    created_at: datetime
