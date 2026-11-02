"""Unit tests for the TP-V1 Trade Policy Engine (Layer 6)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from finpilot.execution.models import OrderRejectionReason
from finpilot.execution.policy import TradePolicyEngine
from finpilot.schemas.errors import DomainValidationError
from finpilot.schemas.trade_policy import TradePolicyV1Contract, TradeProposal

IST = ZoneInfo("Asia/Kolkata")


def test_trade_policy_engine_creates_valid_order() -> None:
    engine = TradePolicyEngine()
    decision_ts = datetime(2026, 11, 2, 9, 20, tzinfo=IST)
    earliest_entry = datetime(2026, 11, 2, 9, 25, tzinfo=IST)

    proposal = TradeProposal(
        proposal_id="prop_pol_1",
        policy_version="TP-V1",
        instrument_id=10,
        symbol="RELIANCE",
        decision_timestamp=decision_ts,
        earliest_entry_timestamp=earliest_entry,
        entry_price=Decimal("2500.00"),
        stop_loss=Decimal("2450.00"),
        target_price=Decimal("2600.00"),
        quantity=5,
    )

    order, rejection = engine.create_order_from_proposal(proposal, portfolio_id=1)
    assert rejection is None
    assert order is not None
    assert order.symbol == "RELIANCE"
    assert order.quantity == 5
    assert order.earliest_entry_timestamp == earliest_entry
    assert order.signal_timestamp == decision_ts


def test_trade_policy_engine_rejects_session_cutoff() -> None:
    engine = TradePolicyEngine()
    # 15:05 IST is past the 15:00 entry cutoff
    late_decision = datetime(2026, 11, 2, 15, 0, tzinfo=IST)
    late_entry = datetime(2026, 11, 2, 15, 5, tzinfo=IST)

    proposal = TradeProposal(
        proposal_id="prop_late_1",
        policy_version="TP-V1",
        instrument_id=10,
        symbol="TCS",
        decision_timestamp=late_decision,
        earliest_entry_timestamp=late_entry,
        entry_price=Decimal("3500.00"),
        stop_loss=Decimal("3450.00"),
        target_price=Decimal("3600.00"),
        quantity=2,
    )

    order, rejection = engine.create_order_from_proposal(proposal, portfolio_id=1)
    assert order is None
    assert rejection == OrderRejectionReason.OUTSIDE_SESSION_HOURS


def test_trade_policy_engine_policy_version_mismatch_rejected() -> None:
    engine = TradePolicyEngine(contract=TradePolicyV1Contract(policy_version="TP-V1"))

    # Proposal specifies a different policy version
    proposal = TradeProposal(
        proposal_id="prop_v2_1",
        policy_version="TP-V1",
        instrument_id=10,
        symbol="INFY",
        decision_timestamp=datetime(2026, 11, 2, 9, 20, tzinfo=IST),
        earliest_entry_timestamp=datetime(2026, 11, 2, 9, 25, tzinfo=IST),
        entry_price=Decimal("1500.00"),
        stop_loss=Decimal("1470.00"),
        target_price=Decimal("1560.00"),
        quantity=10,
    )
    # Manually configure engine contract to a different version to verify version gating
    engine.contract = TradePolicyV1Contract(policy_version="TP-V2-FUTURE")
    with pytest.raises(DomainValidationError) as exc:
        engine.create_order_from_proposal(proposal, portfolio_id=1)
    assert "Policy version mismatch" in str(exc.value)


def test_trade_policy_engine_risk_based_sizing() -> None:
    engine = TradePolicyEngine()
    equity = Decimal("30000.00")
    # Risk 1% of 30,000 = ₹300
    # Entry = ₹2500, Stop = ₹2450 -> Risk per share = ₹50
    # Shares = 300 / 50 = 6 shares
    shares = engine.calculate_risk_based_quantity(
        account_equity=equity,
        entry_price=Decimal("2500.00"),
        stop_loss=Decimal("2450.00"),
        risk_fraction=Decimal("0.01"),
    )
    assert shares == 6
    assert isinstance(shares, int)
