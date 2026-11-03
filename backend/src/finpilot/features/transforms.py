"""Deterministic learned transforms with training-only fit (Layer 5).

Governed by:
- DATA_AND_PERFORMANCE_POLICY.md §7 (Evaluation Hygiene & No Leakage)
- ARCHITECTURE.md §2 (Feature Pipeline)
- Layer 5 Gate: Deterministic transforms with training-only fit for learned preprocessing.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from typing import Any

from finpilot.schemas.errors import DomainValidationError, ErrorCode


@dataclass(frozen=True)
class ScalerFeatureStats:
    """Fitted scaling statistics for an individual feature."""

    mean: float
    std: float
    min_val: float
    max_val: float


class DeterministicFeatureScaler:
    """Standard z-score scaler with strict training-only fit and frozen transform.

    Guarantees:
    - Parameters are computed strictly during `fit` on training data.
    - `transform` applies frozen parameters without modifying scaler state.
    - Zero variance (constant feature) is guarded by defaulting std to 1.0.
    - Serialization and checksumming to guarantee identical replay across runs.
    - Rejection of non-finite values (NaN / Infinity).
    """

    def __init__(self, feature_names: list[str] | None = None) -> None:
        self.feature_names = feature_names
        self.stats: dict[str, ScalerFeatureStats] = {}
        self.is_fitted: bool = False
        self.fit_sample_count: int = 0
        self.fit_checksum: str | None = None

    def fit(self, records: list[dict[str, float | None]]) -> DeterministicFeatureScaler:
        """Fit scaler parameters on training records only."""
        if not records:
            raise DomainValidationError(
                "Cannot fit scaler on empty dataset.",
                field="records",
                code=ErrorCode.VALIDATION_ERROR,
            )

        # Determine features to fit
        if self.feature_names is not None:
            features_to_fit = self.feature_names
        else:
            # Union of all keys present in records
            feature_set: set[str] = set()
            for r in records:
                feature_set.update(r.keys())
            features_to_fit = sorted(list(feature_set))

        stats: dict[str, ScalerFeatureStats] = {}

        for fname in features_to_fit:
            valid_values: list[float] = []
            for r in records:
                val = r.get(fname)
                if val is not None:
                    if math.isnan(val) or math.isinf(val):
                        raise DomainValidationError(
                            f"Non-finite value {val!r} encountered during fit "
                            f"for feature {fname!r}.",
                            field=fname,
                            code=ErrorCode.VALIDATION_ERROR,
                        )
                    valid_values.append(float(val))

            if not valid_values:
                # If no valid values in training, set unit standard stats
                stats[fname] = ScalerFeatureStats(mean=0.0, std=1.0, min_val=0.0, max_val=0.0)
                continue

            n = len(valid_values)
            mean_val = sum(valid_values) / float(n)
            variance = sum((x - mean_val) ** 2 for x in valid_values) / float(n)
            std_val = math.sqrt(variance)

            # Avoid division by zero for constant features
            if std_val < 1e-8:
                std_val = 1.0

            stats[fname] = ScalerFeatureStats(
                mean=mean_val,
                std=std_val,
                min_val=min(valid_values),
                max_val=max(valid_values),
            )

        self.stats = stats
        self.is_fitted = True
        self.fit_sample_count = len(records)
        self.fit_checksum = self._compute_checksum()
        return self

    def transform(
        self,
        records: list[dict[str, float | None]],
    ) -> list[dict[str, float | None]]:
        """Transform records using frozen fitted parameters."""
        if not self.is_fitted:
            raise DomainValidationError(
                "Scaler must be fitted on training data before transform can be called.",
                field="is_fitted",
                code=ErrorCode.INVALID_STATE_TRANSITION,
            )

        transformed_records: list[dict[str, float | None]] = []

        for r in records:
            transformed_row: dict[str, float | None] = {}
            for k, val in r.items():
                if val is None:
                    transformed_row[k] = None
                elif k in self.stats:
                    s = self.stats[k]
                    if math.isnan(val) or math.isinf(val):
                        raise DomainValidationError(
                            f"Non-finite value {val!r} encountered in transform for feature {k!r}.",
                            field=k,
                            code=ErrorCode.VALIDATION_ERROR,
                        )
                    # z-score normalization
                    scaled = (float(val) - s.mean) / s.std
                    transformed_row[k] = scaled
                else:
                    transformed_row[k] = val
            transformed_records.append(transformed_row)

        return transformed_records

    def fit_transform(
        self,
        records: list[dict[str, float | None]],
    ) -> list[dict[str, float | None]]:
        """Fit on training records and transform them."""
        return self.fit(records).transform(records)

    def _compute_checksum(self) -> str:
        """Compute SHA-256 fingerprint of the fitted scaler statistics."""
        serialized = json.dumps(
            {k: asdict(v) for k, v in sorted(self.stats.items())},
            sort_keys=True,
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        """Serialize fitted parameters for persistent reproducibility."""
        if not self.is_fitted:
            raise DomainValidationError(
                "Cannot serialize unfitted scaler.",
                code=ErrorCode.INVALID_STATE_TRANSITION,
            )
        return {
            "is_fitted": self.is_fitted,
            "fit_sample_count": self.fit_sample_count,
            "fit_checksum": self.fit_checksum,
            "stats": {k: asdict(v) for k, v in self.stats.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DeterministicFeatureScaler:
        """Deserialize fitted parameters."""
        scaler = cls()
        scaler.is_fitted = data["is_fitted"]
        scaler.fit_sample_count = data["fit_sample_count"]
        scaler.fit_checksum = data["fit_checksum"]
        scaler.stats = {k: ScalerFeatureStats(**v) for k, v in data["stats"].items()}
        # Verify checksum integrity
        expected_checksum = scaler._compute_checksum()
        if scaler.fit_checksum != expected_checksum:
            raise DomainValidationError(
                f"Checksum mismatch in scaler parameters: "
                f"{scaler.fit_checksum} != {expected_checksum}",
                code=ErrorCode.VALIDATION_ERROR,
            )
        return scaler
