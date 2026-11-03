"""Out-of-Distribution (OOD) detection for selective decision logic (Layer 10).

Governed by:
- PROJECT_SPEC.md §4, §5, §7, §9
- DATA_AND_PERFORMANCE_POLICY.md §2, §7, §8
- Layer 10 Gate: Training-only fit for domain boundaries, deterministic bounds,
  explicit abstention/OUT_OF_SCOPE state for out-of-distribution inputs.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

import numpy as np

from finpilot.schemas.errors import DomainValidationError, ErrorCode


class OODDetector:
    """Detects when an inference feature vector lies outside the training support domain.

    Invariants:
    1. Training-Only Fit: Domain bounds are computed strictly on the TRAIN partition.
    2. Zero Extrapolation: When a feature vector contains values outside valid domain
       boundaries, the detector flags it, enabling the engine to abstain (OUT_OF_SCOPE).
    3. Reproducible & Serializable: Bounds can be exported to JSON/dict and rehydrated
       inside FrozenDecisionPolicy without re-fitting.
    """

    def __init__(
        self,
        feature_names: list[str],
        bounds: dict[str, tuple[float, float]] | None = None,
    ) -> None:
        self.feature_names = list(feature_names)
        self.bounds: dict[str, tuple[float, float]] = dict(bounds) if bounds is not None else {}
        self._is_fitted: bool = bounds is not None and len(bounds) > 0

    @property
    def is_fitted(self) -> bool:
        return self._is_fitted

    def fit(
        self,
        X_train: np.ndarray,
        iqr_multiplier: float = 3.0,
        lower_percentile: float = 0.5,
        upper_percentile: float = 99.5,
    ) -> OODDetector:
        """Fit empirical domain bounds strictly on training partition features."""
        if len(X_train) == 0:
            raise DomainValidationError(
                "Cannot fit OOD detector on empty training matrix.",
                field="X_train",
                code=ErrorCode.VALIDATION_ERROR,
            )

        if X_train.shape[1] != len(self.feature_names):
            raise DomainValidationError(
                f"Feature matrix columns ({X_train.shape[1]}) does not match "
                f"feature_names length ({len(self.feature_names)}).",
                field="X_train",
                code=ErrorCode.VALIDATION_ERROR,
            )

        self.bounds.clear()

        for col_idx, feat_name in enumerate(self.feature_names):
            col_vals = X_train[:, col_idx]
            valid_vals = col_vals[~np.isnan(col_vals)]

            if len(valid_vals) == 0:
                self.bounds[feat_name] = (-1e9, 1e9)
                continue

            # Compute percentiles and IQR
            p_low = float(np.percentile(valid_vals, lower_percentile))
            p_high = float(np.percentile(valid_vals, upper_percentile))
            q1 = float(np.percentile(valid_vals, 25.0))
            q3 = float(np.percentile(valid_vals, 75.0))
            iqr = q3 - q1

            if iqr > 0.0:
                # Conservative outer envelope combining percentiles and 3x IQR
                bound_low = min(p_low, q1 - iqr_multiplier * iqr)
                bound_high = max(p_high, q3 + iqr_multiplier * iqr)
            else:
                # Constant or low-variance feature: allow 10% relative slack or +/- 1.0
                margin = max(abs(p_low) * 0.1, 1.0)
                bound_low = p_low - margin
                bound_high = p_high + margin

            self.bounds[feat_name] = (bound_low, bound_high)

        self._is_fitted = True
        return self

    def check_sample(
        self, features_dict: dict[str, float | None]
    ) -> tuple[bool, list[str]]:
        """Check if a sample contains any feature value that is out-of-distribution.

        Returns:
            tuple[bool, list[str]]: (is_ood, list_of_outlier_features)
        """
        if not self._is_fitted:
            raise DomainValidationError(
                "OODDetector must be fitted before checking samples.",
                field="is_fitted",
                code=ErrorCode.VALIDATION_ERROR,
            )

        outliers: list[str] = []
        for feat in self.feature_names:
            val = features_dict.get(feat)
            if val is None or math.isnan(val) or math.isinf(val):
                # Missing or non-finite handled by data rejection, not OOD
                continue

            low, high = self.bounds.get(feat, (-float("inf"), float("inf")))
            if val < low or val > high:
                outliers.append(f"{feat}={val:.4f} (bounds: [{low:.4f}, {high:.4f}])")

        is_ood = len(outliers) > 0
        return is_ood, outliers

    def get_bounds_dict(self) -> dict[str, list[float]]:
        """Return serializable dictionary of feature bounds: {feature: [low, high]}."""
        return {feat: [float(low), float(high)] for feat, (low, high) in self.bounds.items()}

    @classmethod
    def from_bounds_dict(
        cls, bounds_dict: Mapping[str, Sequence[float]]
    ) -> OODDetector:
        """Instantiate a pre-fitted OODDetector directly from serializable bounds."""
        feature_names = list(bounds_dict.keys())
        parsed_bounds = {feat: (float(b[0]), float(b[1])) for feat, b in bounds_dict.items()}
        return cls(feature_names=feature_names, bounds=parsed_bounds)
