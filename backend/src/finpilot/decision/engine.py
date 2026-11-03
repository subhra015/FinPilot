"""Selective decision engine executing hierarchical trade candidate screening (Layer 10).

Governed by:
- PROJECT_SPEC.md §4, §5, §7, §9
- DATA_AND_PERFORMANCE_POLICY.md §2, §7, §8
- Layer 10 Gate: Probability calibration, 5-state selective decision logic, sample support
  and OOD abstention, non-double-counted net expectancy, and frozen decision policy.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal

from finpilot.features.definitions import FEATURE_CATALOG_V1
from finpilot.ml.pipeline import MLSelectionPipeline
from finpilot.schemas.errors import DomainValidationError
from finpilot.schemas.trade_policy import TradeProposal

from .models import (
    CalibrationBin,
    DecisionDiagnostics,
    DecisionState,
    FrozenDecisionPolicy,
    SelectiveDecision,
)
from .ood import OODDetector


class SelectiveDecisionEngine:
    """Executes multi-stage selective evaluation of trade proposals.

    Hierarchy:
    1. Data Quality & Schema: Reject unapproved, missing, NaN/Inf features or invalid proposals
       (DATA_REJECTED).
    2. Out-of-Distribution (OOD): Reject inputs outside training distribution domain
       (OUT_OF_SCOPE).
    3. Sample Support: Abstain if the matching calibration bin lacks sufficient historical support
       (< N_min) to avoid false precision (INSUFFICIENT_EVIDENCE).
    4. Economic Expectancy & Threshold: Accept candidate only if calibrated probability >= threshold
       AND estimated net expectancy > 0.00 (ACCEPTED_CANDIDATE); otherwise (NO_TRADE).

    Invariants:
    1. Independent Authorization: A model decision alone NEVER authorizes an entry.
       is_portfolio_entry_authorized is always False; downstream execution handles entry.
    2. No Double Cost Subtraction: Approach A labels already factor in ₹30k sizing, 2 bps slippage,
       and NSE statutory fees. Expectancy uses empirical bin net P&Ls directly without double fees.
    3. Separation of Concerns: Probability, expected net value, and downside risk are explicitly
       separated in DecisionDiagnostics. Probability is never interpreted as epistemic confidence.
    """

    def __init__(
        self,
        pipeline: MLSelectionPipeline,
        policy: FrozenDecisionPolicy,
        ood_detector: OODDetector | None = None,
    ) -> None:
        self.pipeline = pipeline
        self.policy = policy
        self.ood_detector = ood_detector or (
            OODDetector.from_bounds_dict(policy.ood_bounds) if policy.ood_bounds else None
        )

    def _find_calibration_bin(self, prob: float) -> tuple[int, CalibrationBin]:
        """Find the calibration bin corresponding to a predicted probability."""
        bins = self.policy.calibration_bins
        n_bins = len(bins)
        b_idx = min(int(prob * n_bins), n_bins - 1)
        return b_idx, bins[b_idx]

    def _calculate_expectancy(
        self, prob: float, cal_bin: CalibrationBin
    ) -> tuple[Decimal, Decimal, Decimal]:
        """Calculate estimated net expectancy, downside max loss, and 95% CVaR.

        Formula:
            E[Net PnL] = p_bin * avg_net_win + (1 - p_bin) * avg_net_loss
        where avg_net_win and avg_net_loss are derived from historical Approach A labels
        (statutory fees and slippage are already deducted).
        """
        if cal_bin.sample_count == 0:
            return Decimal("0.00"), Decimal("0.00"), Decimal("0.00")

        p_win = Decimal(str(cal_bin.empirical_probability))
        p_loss = Decimal("1.00") - p_win

        expectancy = (p_win * cal_bin.avg_net_win) + (p_loss * cal_bin.avg_net_loss)
        return expectancy.quantize(Decimal("0.01")), cal_bin.max_loss, cal_bin.cvar_95

    def evaluate_proposal(
        self,
        proposal: TradeProposal,
        features_dict: dict[str, float | None],
        ambiguity_flags: list[str] | None = None,
    ) -> SelectiveDecision:
        """Evaluate a single TradeProposal against causal features and frozen decision policy."""
        now_utc = datetime.now(UTC)
        amb_flags = list(ambiguity_flags or [])
        data_flags: list[str] = []

        # ------------------------------------------------------------------
        # Stage 1: Data Quality & Server-Side Contract Check
        # ------------------------------------------------------------------
        missing_features = [f for f in self.pipeline.feature_names if f not in features_dict]
        if missing_features:
            data_flags.append(f"Missing required features: {missing_features}")

        unapproved_features = [
            f for f in features_dict
            if f not in self.pipeline.feature_names and f not in FEATURE_CATALOG_V1
        ]
        if unapproved_features:
            data_flags.append(f"Unapproved feature names: {unapproved_features}")

        for f_name, f_val in features_dict.items():
            if f_val is not None and (math.isnan(f_val) or math.isinf(f_val)):
                data_flags.append(f"Non-finite value {f_val} in feature '{f_name}'")

        if data_flags:
            return SelectiveDecision(
                decision_id=f"DEC-{uuid.uuid4().hex[:12]}",
                decision_state=DecisionState.DATA_REJECTED,
                proposal_id=proposal.proposal_id,
                symbol=proposal.symbol,
                timestamp=proposal.decision_timestamp,
                model_id=self.policy.model_id,
                policy_id=self.policy.policy_id,
                diagnostics=DecisionDiagnostics(
                    predicted_probability=0.0,
                    calibrated_probability=0.0,
                    bin_index=None,
                    bin_sample_support=0,
                    bin_observed_frequency=None,
                    coverage_rate=self.policy.coverage_rate,
                    sample_support_warning=False,
                    ood_warning=False,
                    ood_outlier_features=[],
                    estimated_net_expectancy=Decimal("0.00"),
                    downside_max_loss=Decimal("0.00"),
                    downside_cvar_95=Decimal("0.00"),
                    ambiguity_flags=amb_flags,
                    data_quality_flags=data_flags,
                    notes="Rejected by server-side data quality check prior to ML inference.",
                ),
                is_portfolio_entry_authorized=False,
                created_at=now_utc,
            )

        # ------------------------------------------------------------------
        # Stage 2: Out-of-Distribution (OOD) Domain Support Check
        # ------------------------------------------------------------------
        if self.ood_detector is not None:
            is_ood, outlier_features = self.ood_detector.check_sample(features_dict)
            if is_ood:
                return SelectiveDecision(
                    decision_id=f"DEC-{uuid.uuid4().hex[:12]}",
                    decision_state=DecisionState.OUT_OF_SCOPE,
                    proposal_id=proposal.proposal_id,
                    symbol=proposal.symbol,
                    timestamp=proposal.decision_timestamp,
                    model_id=self.policy.model_id,
                    policy_id=self.policy.policy_id,
                    diagnostics=DecisionDiagnostics(
                        predicted_probability=0.0,
                        calibrated_probability=0.0,
                        bin_index=None,
                        bin_sample_support=0,
                        bin_observed_frequency=None,
                        coverage_rate=self.policy.coverage_rate,
                        sample_support_warning=False,
                        ood_warning=True,
                        ood_message="Features fall outside the training support distribution.",
                        ood_outlier_features=outlier_features,
                        estimated_net_expectancy=Decimal("0.00"),
                        downside_max_loss=Decimal("0.00"),
                        downside_cvar_95=Decimal("0.00"),
                        ambiguity_flags=amb_flags,
                        data_quality_flags=[],
                        notes="Abstention: model refuses to extrapolate outside training domain.",
                    ),
                    is_portfolio_entry_authorized=False,
                    created_at=now_utc,
                )

        # ------------------------------------------------------------------
        # Stage 3: Predict Calibrated Probability
        # ------------------------------------------------------------------
        try:
            cal_prob = self.pipeline.predict_proba_single(features_dict)
        except DomainValidationError as e:
            data_flags.append(str(e))
            return SelectiveDecision(
                decision_id=f"DEC-{uuid.uuid4().hex[:12]}",
                decision_state=DecisionState.DATA_REJECTED,
                proposal_id=proposal.proposal_id,
                symbol=proposal.symbol,
                timestamp=proposal.decision_timestamp,
                model_id=self.policy.model_id,
                policy_id=self.policy.policy_id,
                diagnostics=DecisionDiagnostics(
                    predicted_probability=0.0,
                    calibrated_probability=0.0,
                    coverage_rate=self.policy.coverage_rate,
                    data_quality_flags=data_flags,
                    notes=f"Pipeline prediction failed: {e}",
                ),
                is_portfolio_entry_authorized=False,
                created_at=now_utc,
            )

        bin_idx, cal_bin = self._find_calibration_bin(cal_prob)
        expectancy, max_loss, cvar_95 = self._calculate_expectancy(cal_prob, cal_bin)

        # ------------------------------------------------------------------
        # Stage 4: Calibration Sample Support Check (Abstention on low support)
        # ------------------------------------------------------------------
        if cal_bin.sample_count < self.policy.min_bin_sample_support:
            return SelectiveDecision(
                decision_id=f"DEC-{uuid.uuid4().hex[:12]}",
                decision_state=DecisionState.INSUFFICIENT_EVIDENCE,
                proposal_id=proposal.proposal_id,
                symbol=proposal.symbol,
                timestamp=proposal.decision_timestamp,
                model_id=self.policy.model_id,
                policy_id=self.policy.policy_id,
                diagnostics=DecisionDiagnostics(
                    predicted_probability=cal_prob,
                    calibrated_probability=cal_prob,
                    bin_index=bin_idx,
                    bin_sample_support=cal_bin.sample_count,
                    bin_observed_frequency=cal_bin.empirical_probability,
                    coverage_rate=self.policy.coverage_rate,
                    sample_support_warning=True,
                    sample_support_message=(
                        f"Calibration bin {bin_idx} has {cal_bin.sample_count} samples, "
                        f"below required support {self.policy.min_bin_sample_support}."
                    ),
                    ood_warning=False,
                    ood_outlier_features=[],
                    estimated_net_expectancy=expectancy,
                    downside_max_loss=max_loss,
                    downside_cvar_95=cvar_95,
                    ambiguity_flags=amb_flags,
                    data_quality_flags=[],
                    notes="Abstention: insufficient empirical sample support in calibration bin.",
                ),
                is_portfolio_entry_authorized=False,
                created_at=now_utc,
            )

        # ------------------------------------------------------------------
        # Stage 5: Threshold & Net Expectancy Check
        # ------------------------------------------------------------------
        passes_prob_threshold = cal_prob >= self.policy.decision_threshold
        passes_expectancy = expectancy > self.policy.min_expectancy

        if passes_prob_threshold and passes_expectancy:
            decision_state = DecisionState.ACCEPTED_CANDIDATE
            notes = (
                f"Candidate accepted: P(Net>0)={cal_prob:.4f} >= "
                f"{self.policy.decision_threshold:.4f} and "
                f"Expectancy=₹{expectancy:.2f} > ₹{self.policy.min_expectancy:.2f}."
            )
        else:
            decision_state = DecisionState.NO_TRADE
            reasons = []
            if not passes_prob_threshold:
                reasons.append(
                    f"P(Net>0)={cal_prob:.4f} < threshold={self.policy.decision_threshold:.4f}"
                )
            if not passes_expectancy:
                reasons.append(
                    f"Expectancy=₹{expectancy:.2f} <= min=₹{self.policy.min_expectancy:.2f}"
                )
            notes = f"No trade authorized: {', '.join(reasons)}."

        return SelectiveDecision(
            decision_id=f"DEC-{uuid.uuid4().hex[:12]}",
            decision_state=decision_state,
            proposal_id=proposal.proposal_id,
            symbol=proposal.symbol,
            timestamp=proposal.decision_timestamp,
            model_id=self.policy.model_id,
            policy_id=self.policy.policy_id,
            diagnostics=DecisionDiagnostics(
                predicted_probability=cal_prob,
                calibrated_probability=cal_prob,
                bin_index=bin_idx,
                bin_sample_support=cal_bin.sample_count,
                bin_observed_frequency=cal_bin.empirical_probability,
                coverage_rate=self.policy.coverage_rate,
                sample_support_warning=False,
                sample_support_message=None,
                ood_warning=False,
                ood_outlier_features=[],
                estimated_net_expectancy=expectancy,
                downside_max_loss=max_loss,
                downside_cvar_95=cvar_95,
                ambiguity_flags=amb_flags,
                data_quality_flags=[],
                notes=notes,
            ),
            is_portfolio_entry_authorized=False,
            created_at=now_utc,
        )

    def evaluate_sample(
        self,
        symbol: str,
        timestamp: datetime,
        features_dict: dict[str, float | None],
        proposal_id: str | None = None,
        entry_price: Decimal = Decimal("2500.00"),
        stop_loss: Decimal = Decimal("2475.00"),
        target_price: Decimal = Decimal("2550.00"),
        quantity: int = 10,
        ambiguity_flags: list[str] | None = None,
    ) -> SelectiveDecision:
        """Convenience method to evaluate a sample using a synthetic or generated proposal."""
        prop_id = proposal_id or f"PROP-{uuid.uuid4().hex[:8]}"
        proposal = TradeProposal(
            proposal_id=prop_id,
            instrument_id=1,
            symbol=symbol,
            decision_timestamp=timestamp,
            earliest_entry_timestamp=timestamp.replace(minute=(timestamp.minute + 5) % 60),
            entry_price=entry_price,
            stop_loss=stop_loss,
            target_price=target_price,
            quantity=quantity,
        )
        return self.evaluate_proposal(proposal, features_dict, ambiguity_flags)

    def evaluate_batch(
        self,
        items: Sequence[tuple[TradeProposal, dict[str, float | None]]],
    ) -> list[SelectiveDecision]:
        """Evaluate a batch of proposals with their respective features."""
        return [self.evaluate_proposal(prop, f_dict) for prop, f_dict in items]
