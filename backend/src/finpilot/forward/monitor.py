"""Real-time performance, data quality, and drift monitoring (Layer 16).

Governed by:
- ACCEPTANCE_GATES.md §2 (Layer 16 Gate)
- DATA_AND_PERFORMANCE_POLICY.md §7, §8
- PROJECT_SPEC.md §4, §5, §7, §9
- SECURITY_CHECKLIST.md SEC-01, SEC-06, SEC-19
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from finpilot.forward.models import DriftMonitorMetrics, PredictionEventRecord


class DriftAndPerformanceMonitor:
    """Monitors live data latency, stale feeds, feature bounds, and calibration drift.

    Invariants:
    1. Zero Silent Retraining: Drift alerts NEVER silently modify, retrain, or adjust model thresholds.
    2. Safe No-New-Entry Mode: If data quality fails, latency exceeds threshold, or drawdown breaches
       limits, trips a safe 'no-new-entry' switch while preserving existing protective exits.
    """

    def __init__(
        self,
        max_acceptable_latency_seconds: float = 300.0,
        max_drawdown_threshold_pct: float = 10.0,
        max_consecutive_stale_incidents: int = 3,
        max_drawdown_pct_limit: float | None = None,
        max_stale_incidents: int | None = None,
    ) -> None:
        self.max_acceptable_latency_seconds = max_acceptable_latency_seconds
        self.max_drawdown_threshold_pct = (
            max_drawdown_pct_limit if max_drawdown_pct_limit is not None else max_drawdown_threshold_pct
        )
        self.max_consecutive_stale_incidents = (
            max_stale_incidents if max_stale_incidents is not None else max_consecutive_stale_incidents
        )

        # Counters & State
        self.candles_processed: int = 0
        self.latencies: list[float] = []
        self.stale_feed_incidents: int = 0
        self.abnormal_geometry_incidents: int = 0
        self.out_of_distribution_count: int = 0
        self.rolling_drawdown_pct: float = 0.0

        # Safe Mode Flags
        self.safe_no_new_entry_mode: bool = False
        self.safe_mode_trigger_reason: str | None = None

        # Empirical calibration tracking
        self.predicted_probabilities: list[float] = []
        self.observed_outcomes: list[int] = []

    def record_candle_check(
        self,
        candle_timestamp: datetime,
        current_time: datetime | None = None,
        is_geometry_valid: bool = True,
        is_ood: bool = False,
    ) -> bool:
        """Record candle latency, geometry, and OOD status. Returns True if candle is healthy."""
        self.candles_processed += 1
        now = current_time or datetime.now(UTC)
        c_ts = candle_timestamp if candle_timestamp.tzinfo else candle_timestamp.replace(tzinfo=UTC)
        now_ts = now if now.tzinfo else now.replace(tzinfo=UTC)

        latency = (now_ts - c_ts).total_seconds()
        self.latencies.append(max(0.0, latency))

        # 1. Stale feed check
        if latency > self.max_acceptable_latency_seconds:
            self.stale_feed_incidents += 1
            if self.stale_feed_incidents >= self.max_consecutive_stale_incidents:
                self._trip_safe_mode(
                    f"Stale data feed threshold exceeded ({self.stale_feed_incidents} incidents; lag {latency:.1f}s > {self.max_acceptable_latency_seconds}s)"
                )
            return False

        # 2. Geometry check
        if not is_geometry_valid:
            self.abnormal_geometry_incidents += 1
            if self.abnormal_geometry_incidents >= 3:
                self._trip_safe_mode(
                    f"Multiple abnormal candle geometries detected ({self.abnormal_geometry_incidents} incidents)"
                )
            return False

        # 3. OOD check
        if is_ood:
            self.out_of_distribution_count += 1

        return True

    def record_prediction_evaluation(
        self,
        predicted_prob: float | None,
        is_positive_outcome: bool | None = None,
    ) -> None:
        """Record predicted probability and terminal outcome for calibration drift tracking."""
        if predicted_prob is not None:
            self.predicted_probabilities.append(predicted_prob)
            if is_positive_outcome is not None:
                self.observed_outcomes.append(1 if is_positive_outcome else 0)

    def update_drawdown(self, current_drawdown_pct: float) -> None:
        """Update drawdown and trip safe mode if threshold breached."""
        self.rolling_drawdown_pct = current_drawdown_pct
        if current_drawdown_pct >= self.max_drawdown_threshold_pct:
            self._trip_safe_mode(
                f"Maximum drawdown threshold breached ({current_drawdown_pct:.2f}% >= {self.max_drawdown_threshold_pct:.2f}%)"
            )

    def _trip_safe_mode(self, reason: str) -> None:
        """Activate safe no-new-entry mode."""
        self.safe_no_new_entry_mode = True
        self.safe_mode_trigger_reason = reason

    def reset_safe_mode(self) -> None:
        """Administratively reset safe mode once operational feed is restored."""
        self.safe_no_new_entry_mode = False
        self.safe_mode_trigger_reason = None
        self.stale_feed_incidents = 0

    def compute_calibration_drift(self) -> tuple[float, float, float]:
        """Compute empirical win rate, mean predicted probability, and calibration delta."""
        if not self.observed_outcomes or not self.predicted_probabilities:
            return 0.0, 0.0, 0.0

        n_eval = min(len(self.observed_outcomes), len(self.predicted_probabilities))
        emp_win_rate = (sum(self.observed_outcomes[:n_eval]) / n_eval) * 100.0
        mean_pred = (sum(self.predicted_probabilities[:n_eval]) / n_eval) * 100.0
        drift_delta = abs(emp_win_rate - mean_pred)
        return round(emp_win_rate, 2), round(mean_pred, 2), round(drift_delta, 2)

    def get_metrics(self) -> DriftMonitorMetrics:
        """Compile snapshot of live monitoring metrics."""
        max_lat = max(self.latencies) if self.latencies else 0.0
        avg_lat = (sum(self.latencies) / len(self.latencies)) if self.latencies else 0.0
        emp_wr, pred_wr, delta = self.compute_calibration_drift()

        return DriftMonitorMetrics(
            candles_processed=self.candles_processed,
            data_latency_seconds_max=round(max_lat, 2),
            data_latency_seconds_avg=round(avg_lat, 2),
            stale_feed_incidents=self.stale_feed_incidents,
            abnormal_geometry_incidents=self.abnormal_geometry_incidents,
            out_of_distribution_count=self.out_of_distribution_count,
            safe_no_new_entry_mode=self.safe_no_new_entry_mode,
            safe_mode_trigger_reason=self.safe_mode_trigger_reason,
            rolling_drawdown_pct=round(self.rolling_drawdown_pct, 2),
            empirical_win_rate_pct=emp_wr,
            calibrated_predicted_win_rate_pct=pred_wr,
            calibration_drift_delta=delta,
            accounting_discrepancy=Decimal("0.00"),
        )
