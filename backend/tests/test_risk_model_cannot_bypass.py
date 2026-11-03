"""Tests verifying ML models cannot bypass risk rules and simulator rejects un-authorized proposals.

Governed by:
- PROJECT_SPEC.md §4, §5, §7
- SECURITY_CHECKLIST.md SEC-06, SEC-19
- Layer 11 Gate: The ML model can propose a trade but cannot authorize it or bypass risk rules.
  The simulator must reject any proposal without valid risk authorization for proposal/model/policy.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from finpilot.data.models import MarketDataRecord
from finpilot.decision.models import (
    DecisionDiagnostics,
    DecisionState,
    SelectiveDecision,
)
from finpilot.execution.models import OrderRejectionReason
from finpilot.execution.portfolio import PortfolioManager
from finpilot.risk.evaluator import RiskEvaluator
from finpilot.risk.models import (
    RiskAuthorization,
    RiskConfig,
    RiskDecisionStatus,
    RiskRejectionReason,
)
from finpilot.schemas.trade_policy import TradeProposal

IST = ZoneInfo("Asia/Kolkata")


@pytest.fixture
def risk_evaluator() -> RiskEvaluator:
    return RiskEvaluator(config=RiskConfig())


@pytest.fixture
def valid_candle() -> MarketDataRecord:
    ts = datetime(2026, 1, 15, 10, 0, tzinfo=IST).astimezone(UTC)
    return MarketDataRecord(
        source="HISTORICAL_SIM",
        retrieval_time=ts,
        instrument_id=101,
        symbol="RELIANCE",
        timestamp=ts,
        open=Decimal("2500.00"),
        high=Decimal("2510.00"),
        low=Decimal("2490.00"),
        close=Decimal("2505.00"),
        volume=10000,
    )


@pytest.fixture
def valid_proposal(
    high_confidence_decision: tuple[TradeProposal, SelectiveDecision],
) -> TradeProposal:
    return high_confidence_decision[0]


@pytest.fixture
def high_confidence_decision(
    valid_candle: MarketDataRecord,
) -> tuple[TradeProposal, SelectiveDecision]:
    """Returns a TradeProposal accompanied by a 99.9% confidence ML candidate decision."""
    proposal = TradeProposal(
        proposal_id="PROP-HIGH-CONF-001",
        instrument_id=101,
        symbol="RELIANCE",
        decision_timestamp=valid_candle.timestamp,
        earliest_entry_timestamp=datetime(2026, 1, 15, 4, 35, tzinfo=UTC),
        entry_price=Decimal("2500.00"),
        stop_loss=Decimal("2475.00"),
        target_price=Decimal("2550.00"),
        quantity=5,
    )

    decision = SelectiveDecision(
        decision_id="DEC-HIGH-CONF-999",
        decision_state=DecisionState.ACCEPTED_CANDIDATE,
        proposal_id=proposal.proposal_id,
        symbol=proposal.symbol,
        timestamp=proposal.decision_timestamp,
        model_id="MODEL-LOGREG-V1",
        policy_id="DECISION-POLICY-V1",
        diagnostics=DecisionDiagnostics(
            predicted_probability=0.9990,
            calibrated_probability=0.9990,
            bin_index=9,
            bin_sample_support=41,
            bin_observed_frequency=0.9760,
            coverage_rate=0.3350,
            estimated_net_expectancy=Decimal("61.41"),
        ),
        is_portfolio_entry_authorized=False,  # Invariant
        created_at=datetime.now(UTC),
    )
    return proposal, decision


def test_model_high_confidence_cannot_override_insufficient_cash(
    risk_evaluator: RiskEvaluator,
    high_confidence_decision: tuple[TradeProposal, SelectiveDecision],
    valid_candle: MarketDataRecord,
) -> None:
    """A model with 99.9% win probability cannot override cash affordability denial."""
    proposal, decision = high_confidence_decision
    assert decision.diagnostics.calibrated_probability == 0.9990

    # Risk evaluation with only ₹1,000 available cash (order requires ~₹12,500)
    risk_result = risk_evaluator.evaluate_entry_proposal(
        proposal=proposal,
        candle=valid_candle,
        available_cash=Decimal("1000.00"),
        total_equity=Decimal("30000.00"),
        model_id=decision.model_id,
    )

    assert risk_result.status == RiskDecisionStatus.REJECTED
    assert risk_result.authorization is None
    assert RiskRejectionReason.INSUFFICIENT_AVAILABLE_CASH in risk_result.rejection_reasons


def test_model_high_confidence_cannot_override_kill_switch(
    valid_candle: MarketDataRecord,
    high_confidence_decision: tuple[TradeProposal, SelectiveDecision],
) -> None:
    """A model cannot bypass an active emergency kill switch regardless of score."""
    proposal, decision = high_confidence_decision
    cfg = RiskConfig(kill_switch_active=True)
    evaluator = RiskEvaluator(config=cfg)

    risk_result = evaluator.evaluate_entry_proposal(
        proposal=proposal,
        candle=valid_candle,
        available_cash=Decimal("30000.00"),
        total_equity=Decimal("30000.00"),
        model_id=decision.model_id,
    )

    assert risk_result.status == RiskDecisionStatus.REJECTED
    assert RiskRejectionReason.KILL_SWITCH_ACTIVE in risk_result.rejection_reasons


def test_simulator_rejects_proposal_without_risk_authorization(
    valid_proposal: TradeProposal,
) -> None:
    """Simulator with enforce_risk_authorization=True must reject un-authorized proposal."""
    pm = PortfolioManager(
        initial_capital=Decimal("30000.00"),
        enforce_risk_authorization=True,
    )

    # Submit without risk_authorization
    order = pm.submit_proposal(proposal=valid_proposal, risk_authorization=None)

    assert order is None
    assert len(pm.rejected_proposals) == 1
    rejected_prop, reason = pm.rejected_proposals[0]
    assert rejected_prop.proposal_id == valid_proposal.proposal_id
    assert reason == OrderRejectionReason.UNAUTHORIZED

    # Verify ledger event
    ledger_events = pm.ledger_events
    assert any(e.event_type == "PROPOSAL_REJECTED_UNAUTHORIZED" for e in ledger_events)


def test_simulator_rejects_mismatched_risk_authorization(
    valid_proposal: TradeProposal,
) -> None:
    """Simulator must reject an authorization issued for a different proposal ID."""
    pm = PortfolioManager(
        initial_capital=Decimal("30000.00"),
        enforce_risk_authorization=True,
    )

    # Valid authorization but for a different proposal ID
    foreign_auth = RiskAuthorization.create(
        authorization_id="AUTH-FOREIGN-999",
        proposal_id="PROP-DIFFERENT-ID",
        model_id="MODEL-LOGREG-V1",
        symbol="RELIANCE",
        instrument_id=101,
        authorized_quantity=5,
        allocated_capital=Decimal("12600.00"),
        max_adverse_entry_price=Decimal("2510.00"),
        stop_loss_limit=Decimal("2475.00"),
        target_price_limit=Decimal("2550.00"),
        authorized_at=datetime.now(UTC),
        expires_at=datetime(2026, 1, 15, 5, 0, tzinfo=UTC),
    )

    order = pm.submit_proposal(proposal=valid_proposal, risk_authorization=foreign_auth)

    assert order is None
    assert len(pm.rejected_proposals) == 1
    assert pm.rejected_proposals[0][1] == OrderRejectionReason.UNAUTHORIZED


def test_simulator_rejects_tampered_risk_authorization_signature(
    valid_proposal: TradeProposal,
) -> None:
    """Simulator must reject an authorization with a forged or tampered cryptographic seal."""
    pm = PortfolioManager(
        initial_capital=Decimal("30000.00"),
        enforce_risk_authorization=True,
    )

    valid_auth = RiskAuthorization.create(
        authorization_id="AUTH-GENUINE-001",
        proposal_id=valid_proposal.proposal_id,
        model_id="MODEL-LOGREG-V1",
        symbol="RELIANCE",
        instrument_id=101,
        authorized_quantity=5,
        allocated_capital=Decimal("12600.00"),
        max_adverse_entry_price=Decimal("2510.00"),
        stop_loss_limit=Decimal("2475.00"),
        target_price_limit=Decimal("2550.00"),
        authorized_at=datetime.now(UTC),
        expires_at=datetime(2026, 1, 15, 5, 0, tzinfo=UTC),
    )

    # Tamper with the authorized quantity after signature computation
    tampered_auth = valid_auth.model_copy(update={"authorized_quantity": 500})
    assert tampered_auth.verify_signature() is False

    order = pm.submit_proposal(proposal=valid_proposal, risk_authorization=tampered_auth)

    assert order is None
    assert len(pm.rejected_proposals) == 1
    assert pm.rejected_proposals[0][1] == OrderRejectionReason.UNAUTHORIZED


def test_simulator_accepts_valid_risk_authorization(
    valid_proposal: TradeProposal,
) -> None:
    """Simulator accepts proposal with a valid, cryptographically verified RiskAuthorization."""
    pm = PortfolioManager(
        initial_capital=Decimal("30000.00"),
        enforce_risk_authorization=True,
    )

    valid_auth = RiskAuthorization.create(
        authorization_id="AUTH-GENUINE-001",
        proposal_id=valid_proposal.proposal_id,
        model_id="MODEL-LOGREG-V1",
        symbol="RELIANCE",
        instrument_id=101,
        authorized_quantity=5,
        allocated_capital=Decimal("12600.00"),
        max_adverse_entry_price=Decimal("2510.00"),
        stop_loss_limit=Decimal("2475.00"),
        target_price_limit=Decimal("2550.00"),
        authorized_at=datetime.now(UTC),
        expires_at=datetime(2026, 1, 15, 5, 0, tzinfo=UTC),
    )

    order = pm.submit_proposal(proposal=valid_proposal, risk_authorization=valid_auth)

    assert order is not None
    assert order.status.value == "PENDING"
    assert order.risk_authorization_id == "AUTH-GENUINE-001"
    assert len(pm.open_orders) == 1
