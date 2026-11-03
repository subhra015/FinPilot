"""Probability calibration evaluation, reliability diagrams, and scoring rules (Layer 10).

Governed by:
- PROJECT_SPEC.md §4, §5, §7, §9
- DATA_AND_PERFORMANCE_POLICY.md §2, §7, §8
- Layer 10 Gate: Reliability diagrams, proper scoring rule decomposition (Murphy 1973),
  Expected Calibration Error (ECE), and empirical calibration bin tables.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from decimal import Decimal

import numpy as np

from finpilot.schemas.errors import DomainValidationError, ErrorCode

from .models import BrierDecomposition, CalibrationBin, ReliabilityDiagramData


class ReliabilityEvaluator:
    """Evaluates probability calibration quality, reliability diagrams, and scoring rules.

    Invariants:
    1. Proper Scoring Rules: Computes sample-level Brier Score and log loss.
    2. Murphy (1973) Decomposition: Decomposes Brier score into Reliability, Resolution,
       and Uncertainty:
           BS = Reliability - Resolution + Uncertainty
    3. Scientific Disclosure: Documents that Brier score combines calibration and discrimination;
       high discrimination can mask poor calibration.
    4. Expected Calibration Error (ECE): Computes weighted absolute difference between
       mean predicted probability and observed empirical win rate.
    5. Cost-Integrated Bin Statistics: Aggregates empirical net wins and losses from Approach A
       labels without subtracting fees a second time.
    """

    def __init__(self, n_bins: int = 10, min_bin_support: int = 10) -> None:
        if n_bins < 2:
            raise DomainValidationError(
                f"n_bins must be at least 2, got {n_bins}.",
                field="n_bins",
                code=ErrorCode.VALIDATION_ERROR,
            )
        self.n_bins = n_bins
        self.min_bin_support = min_bin_support

    def evaluate(
        self,
        y_true: Sequence[int] | np.ndarray,
        y_prob: Sequence[float] | np.ndarray,
        net_pnls: Sequence[Decimal | float] | np.ndarray | None = None,
        model_id: str = "MODEL-UNKNOWN",
        partition_name: str = "CALIBRATION",
    ) -> ReliabilityDiagramData:
        """Compute calibration bins, reliability diagram statistics, and proper scoring rules."""
        y_true_arr = np.asarray(y_true, dtype=np.int32)
        y_prob_arr = np.asarray(y_prob, dtype=np.float64)

        if len(y_true_arr) == 0:
            raise DomainValidationError(
                "Cannot evaluate calibration on empty dataset.",
                field="y_true",
                code=ErrorCode.VALIDATION_ERROR,
            )

        if len(y_true_arr) != len(y_prob_arr):
            raise DomainValidationError(
                f"Length mismatch: y_true ({len(y_true_arr)}) vs y_prob ({len(y_prob_arr)}).",
                field="y_true",
                code=ErrorCode.VALIDATION_ERROR,
            )

        if np.any((y_prob_arr < 0.0) | (y_prob_arr > 1.0)):
            raise DomainValidationError(
                "Predicted probabilities must be within [0.0, 1.0].",
                field="y_prob",
                code=ErrorCode.VALIDATION_ERROR,
            )

        if np.any((y_true_arr != 0) & (y_true_arr != 1)):
            raise DomainValidationError(
                "Binary labels must be strictly 0 or 1.",
                field="y_true",
                code=ErrorCode.VALIDATION_ERROR,
            )

        net_pnls_arr: list[Decimal] | None = None
        if net_pnls is not None:
            if len(net_pnls) != len(y_true_arr):
                raise DomainValidationError(
                    f"Length mismatch: net_pnls ({len(net_pnls)}) vs y_true ({len(y_true_arr)}).",
                    field="net_pnls",
                    code=ErrorCode.VALIDATION_ERROR,
                )
            net_pnls_arr = [
                Decimal(str(round(float(p), 4))) if not isinstance(p, Decimal) else p
                for p in net_pnls
            ]

        n_total = len(y_true_arr)
        base_rate = float(np.mean(y_true_arr))

        # Assign each sample to a calibration bin [0, n_bins - 1]
        # Bins are [0.0, 0.1), [0.1, 0.2), ..., [0.9, 1.0]
        bin_assignments = np.minimum(
            (y_prob_arr * self.n_bins).astype(np.int32),
            self.n_bins - 1,
        )

        calibration_bins: list[CalibrationBin] = []
        reliability_components: list[float] = []
        resolution_components: list[float] = []
        ece_components: list[float] = []
        calibration_errors: list[float] = []

        for b_idx in range(self.n_bins):
            bin_lower = b_idx / self.n_bins
            bin_upper = (b_idx + 1) / self.n_bins
            mask = bin_assignments == b_idx
            bin_count = int(np.sum(mask))

            if bin_count > 0:
                pos_count = int(np.sum(y_true_arr[mask]))
                emp_prob = float(pos_count / bin_count)
                mean_pred = float(np.mean(y_prob_arr[mask]))

                # Compute economic downside and expectancy from Approach A labels
                avg_win = Decimal("0.00")
                avg_loss = Decimal("0.00")
                max_loss = Decimal("0.00")
                cvar_95 = Decimal("0.00")

                if net_pnls_arr is not None:
                    bin_pnls = [net_pnls_arr[i] for i in range(n_total) if mask[i]]
                    win_pnls = [p for p in bin_pnls if p > Decimal("0.00")]
                    loss_pnls = [p for p in bin_pnls if p <= Decimal("0.00")]

                    if win_pnls:
                        avg_win = sum(win_pnls) / Decimal(len(win_pnls))
                    if loss_pnls:
                        avg_loss = sum(loss_pnls) / Decimal(len(loss_pnls))

                    if bin_pnls:
                        max_loss = min(bin_pnls)
                        sorted_pnls = sorted(bin_pnls)
                        cutoff_idx = max(1, int(math.ceil(0.05 * len(sorted_pnls))))
                        worst_tail = sorted_pnls[:cutoff_idx]
                        cvar_95 = sum(worst_tail) / Decimal(len(worst_tail))

                weight = bin_count / n_total
                rel_term = weight * ((mean_pred - emp_prob) ** 2)
                res_term = weight * ((emp_prob - base_rate) ** 2)
                ece_term = weight * abs(mean_pred - emp_prob)
                cal_err = abs(mean_pred - emp_prob)

                reliability_components.append(rel_term)
                resolution_components.append(res_term)
                ece_components.append(ece_term)
                calibration_errors.append(cal_err)

                has_support = bin_count >= self.min_bin_support

                calibration_bins.append(
                    CalibrationBin(
                        bin_index=b_idx,
                        bin_lower=round(bin_lower, 4),
                        bin_upper=round(bin_upper, 4),
                        sample_count=bin_count,
                        positive_count=pos_count,
                        empirical_probability=round(emp_prob, 4),
                        mean_predicted_probability=round(mean_pred, 4),
                        avg_net_win=avg_win.quantize(Decimal("0.01")),
                        avg_net_loss=avg_loss.quantize(Decimal("0.01")),
                        max_loss=max_loss.quantize(Decimal("0.01")),
                        cvar_95=cvar_95.quantize(Decimal("0.01")),
                        has_sufficient_support=has_support,
                    )
                )
            else:
                calibration_bins.append(
                    CalibrationBin(
                        bin_index=b_idx,
                        bin_lower=round(bin_lower, 4),
                        bin_upper=round(bin_upper, 4),
                        sample_count=0,
                        positive_count=0,
                        empirical_probability=0.0,
                        mean_predicted_probability=round((bin_lower + bin_upper) / 2.0, 4),
                        avg_net_win=Decimal("0.00"),
                        avg_net_loss=Decimal("0.00"),
                        max_loss=Decimal("0.00"),
                        cvar_95=Decimal("0.00"),
                        has_sufficient_support=False,
                    )
                )

        # 1. Sample-level Brier Score
        brier_score = float(np.mean((y_prob_arr - y_true_arr) ** 2))

        # 2. Murphy (1973) Decomposition components
        reliability = float(sum(reliability_components))
        resolution = float(sum(resolution_components))
        uncertainty = float(base_rate * (1.0 - base_rate))

        rel_r = round(reliability, 6)
        res_r = round(resolution, 6)
        unc_r = round(uncertainty, 6)
        decomp_sum_r = round(rel_r - res_r + unc_r, 6)

        # 3. ECE & MCE
        ece = float(sum(ece_components))
        mce = float(max(calibration_errors)) if calibration_errors else 0.0

        # 4. Log Loss (clipped to avoid log(0))
        eps = 1e-15
        y_prob_clipped = np.clip(y_prob_arr, eps, 1.0 - eps)
        log_loss_val = float(
            -np.mean(
                y_true_arr * np.log(y_prob_clipped) + (1 - y_true_arr) * np.log(1 - y_prob_clipped)
            )
        )

        return ReliabilityDiagramData(
            model_id=model_id,
            partition_name=partition_name,
            bins=calibration_bins,
            brier_score=round(brier_score, 4),
            brier_decomposition=BrierDecomposition(
                reliability=rel_r,
                resolution=res_r,
                uncertainty=unc_r,
                decomposition_sum=decomp_sum_r,
            ),
            expected_calibration_error=round(ece, 4),
            maximum_calibration_error=round(mce, 4),
            log_loss=round(log_loss_val, 4),
            total_samples=n_total,
            base_rate=round(base_rate, 4),
        )
