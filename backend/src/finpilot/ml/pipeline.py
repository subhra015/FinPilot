"""Leakage-safe ML selection pipeline with training-only preprocessing and calibration (Layer 9).

Governed by:
- DATA_AND_PERFORMANCE_POLICY.md §2, §7, §8
- Layer 9 Gate: Training-only fit for scalers and imputers, deterministic seeds,
  schema validation fail-closed, and probability calibration.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from sklearn.calibration import CalibratedClassifierCV  # type: ignore[import-untyped]

try:
    from sklearn.frozen import FrozenEstimator  # type: ignore[import-untyped]
except ImportError:
    FrozenEstimator = None  # type: ignore[assignment, misc]
from sklearn.impute import SimpleImputer  # type: ignore[import-untyped]
from sklearn.preprocessing import StandardScaler  # type: ignore[import-untyped]

from finpilot.features.definitions import FEATURE_CATALOG_V1
from finpilot.schemas.errors import DomainValidationError, ErrorCode

from .models import CalibrationMethod, ModelArtifactMetadata, ModelFamily


class SchemaMismatchError(DomainValidationError):
    """Raised when inference input feature dictionary fails the required feature contract."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message=message,
            field="feature_vector",
            code=ErrorCode.VALIDATION_ERROR,
        )


class MLSelectionPipeline:
    """Encapsulates learned preprocessing, base classifier, and calibration for trade selection.

    Invariants:
    1. Training-Only Fit: Imputers and scalers are fitted strictly on the TRAIN partition.
       Validation, calibration, and test data are only transformed.
    2. Schema Enforcement: Inputs must strictly provide all features named in feature_names.
       Missing or malformed features fail closed via SchemaMismatchError.
    3. Calibration: Probability scores are calibrated against empirical win rates
       using a held-out CALIBRATION split with cv='prefit'.
    4. Thresholded Authorization: Evaluates whether P(profitable) >= decision_threshold.
    """

    def __init__(
        self,
        model_id: str,
        model_family: ModelFamily,
        feature_names: list[str],
        base_estimator: Any,
        use_scaler: bool = True,
        calibration_method: CalibrationMethod = CalibrationMethod.NONE,
        decision_threshold: float = 0.50,
        metadata: ModelArtifactMetadata | None = None,
    ) -> None:
        if not feature_names:
            raise DomainValidationError(
                "Feature names list cannot be empty.",
                field="feature_names",
                code=ErrorCode.VALIDATION_ERROR,
            )

        self.model_id = model_id
        self.model_family = model_family
        self.feature_names = list(feature_names)
        self.base_estimator = base_estimator
        self.use_scaler = use_scaler
        self.calibration_method = calibration_method
        self.decision_threshold = decision_threshold
        self.metadata = metadata

        # Learned preprocessing components (fitted strictly during fit())
        self.imputer: SimpleImputer | None = SimpleImputer(strategy="median")
        self.scaler: StandardScaler | None = StandardScaler() if use_scaler else None
        self.calibrated_estimator: CalibratedClassifierCV | None = None
        self._is_fitted: bool = False

    @property
    def is_fitted(self) -> bool:
        return self._is_fitted

    def fit(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_cal: np.ndarray | None = None,
        y_cal: np.ndarray | None = None,
    ) -> MLSelectionPipeline:
        """Fit preprocessing and base estimator strictly on TRAIN; calibrate on CALIBRATION."""
        if len(X_train) == 0 or len(y_train) == 0:
            raise DomainValidationError(
                "Cannot fit pipeline on empty training arrays.",
                field="X_train",
                code=ErrorCode.VALIDATION_ERROR,
            )

        # 1. Fit learned imputer strictly on TRAIN
        assert self.imputer is not None
        X_train_imp = self.imputer.fit_transform(X_train)

        # 2. Fit learned scaler strictly on TRAIN
        if self.scaler is not None:
            X_train_proc = self.scaler.fit_transform(X_train_imp)
        else:
            X_train_proc = X_train_imp

        # 3. Fit base estimator strictly on TRAIN
        self.base_estimator.fit(X_train_proc, y_train)

        # 4. Fit probability calibration on CALIBRATION split if provided
        if (
            self.calibration_method != CalibrationMethod.NONE
            and X_cal is not None
            and y_cal is not None
            and len(X_cal) > 0
        ):
            # Transform CALIBRATION data using training-fitted imputer & scaler
            X_cal_imp = self.imputer.transform(X_cal)
            X_cal_proc = self.scaler.transform(X_cal_imp) if self.scaler is not None else X_cal_imp

            is_sig = self.calibration_method == CalibrationMethod.SIGMOID
            cal_method_str = "sigmoid" if is_sig else "isotonic"
            if FrozenEstimator is not None:
                self.calibrated_estimator = CalibratedClassifierCV(
                    estimator=FrozenEstimator(self.base_estimator),
                    method=cal_method_str,
                )
            else:
                self.calibrated_estimator = CalibratedClassifierCV(
                    estimator=self.base_estimator,
                    method=cal_method_str,
                    cv="prefit",
                )
            self.calibrated_estimator.fit(X_cal_proc, y_cal)

        self._is_fitted = True
        return self

    def tune_threshold_on_validation(
        self,
        X_val: np.ndarray,
        y_val: np.ndarray,
        net_pnls: np.ndarray | None = None,
        min_threshold: float = 0.30,
        max_threshold: float = 0.70,
        step: float = 0.02,
    ) -> float:
        """Tune decision threshold on THRESHOLD_SELECTION split to maximize economic utility."""
        if not self._is_fitted:
            raise DomainValidationError(
                "Pipeline must be fitted before tuning threshold.",
                field="is_fitted",
                code=ErrorCode.VALIDATION_ERROR,
            )

        probs = self.predict_proba_matrix(X_val)

        best_threshold = 0.50
        best_score = -float("inf")

        threshold_grid = np.arange(min_threshold, max_threshold + 1e-5, step)

        for thresh in threshold_grid:
            accepted_mask = probs >= thresh
            if not np.any(accepted_mask):
                continue

            if net_pnls is not None and len(net_pnls) == len(y_val):
                # Economic utility: sum of net P&L on authorized trades
                score = float(np.sum(net_pnls[accepted_mask]))
            else:
                # Precision under cost penalty
                true_positives = np.sum((y_val == 1) & accepted_mask)
                total_accepted = np.sum(accepted_mask)
                precision = true_positives / total_accepted if total_accepted > 0 else 0.0
                score = float(precision)

            if score > best_score:
                best_score = score
                best_threshold = float(thresh)

        self.decision_threshold = best_threshold
        return best_threshold

    def _transform_features_matrix(self, X: np.ndarray) -> np.ndarray:
        """Transform an input numpy feature matrix using training-fitted preprocessors."""
        if not self._is_fitted:
            raise DomainValidationError(
                "Cannot predict with an un-fitted pipeline.",
                field="is_fitted",
                code=ErrorCode.VALIDATION_ERROR,
            )

        assert self.imputer is not None
        X_imp = self.imputer.transform(X)
        if self.scaler is not None:
            return self.scaler.transform(X_imp)
        return X_imp

    def predict_proba_matrix(self, X: np.ndarray) -> np.ndarray:
        """Predict positive class probabilities for a 2D numpy matrix."""
        X_proc = self._transform_features_matrix(X)
        if self.calibrated_estimator is not None:
            probs = self.calibrated_estimator.predict_proba(X_proc)
        else:
            probs = self.base_estimator.predict_proba(X_proc)

        # Return probability of positive class (column 1)
        if probs.shape[1] == 2:
            return probs[:, 1]
        return probs[:, 0]

    predict_proba_batch = predict_proba_matrix

    def _extract_and_validate_dict(self, features_dict: dict[str, float | None]) -> np.ndarray:
        """Validate feature schema and extract ordered 1D vector. Fails closed on mismatch."""
        missing = [f for f in self.feature_names if f not in features_dict]
        if missing:
            raise SchemaMismatchError(
                f"Missing required features: {missing}. Expected: {self.feature_names}"
            )
        extra = [
            f for f in features_dict if f not in self.feature_names and f not in FEATURE_CATALOG_V1
        ]
        if extra:
            raise SchemaMismatchError(
                f"Unexpected features: {extra}. Allowed: {self.feature_names}"
            )

        row = []
        for f in self.feature_names:
            val = features_dict[f]
            if val is not None and (math.isnan(val) or math.isinf(val)):
                raise SchemaMismatchError(f"Non-finite feature value {val!r} in feature {f!r}.")
            row.append(np.nan if val is None else float(val))

        return np.array([row], dtype=np.float64)

    def predict_proba_single(self, features_dict: dict[str, float | None]) -> float:
        """Predict probability for a single sample dictionary after strict schema check."""
        X = self._extract_and_validate_dict(features_dict)
        return float(self.predict_proba_matrix(X)[0])

    predict_dict = predict_proba_single

    def should_authorize_proposal(
        self,
        features_or_proposal: Any,
        features_dict: dict[str, float | None] | None = None,
    ) -> tuple[bool, float]:
        """Evaluate if candidate proposal passes the ML selection filter.

        Accepts either:
        - should_authorize_proposal(features_dict)
        - should_authorize_proposal(proposal, features_dict)

        Returns:
            tuple[bool, float]: (is_authorized, predicted_win_probability)
        """
        if features_dict is not None:
            f_dict = features_dict
        elif isinstance(features_or_proposal, dict):
            f_dict = features_or_proposal
        else:
            raise DomainValidationError(
                "Missing feature dictionary for proposal authorization.",
                field="features_dict",
                code=ErrorCode.VALIDATION_ERROR,
            )
        prob = self.predict_proba_single(f_dict)
        is_authorized = prob >= self.decision_threshold
        return is_authorized, prob
