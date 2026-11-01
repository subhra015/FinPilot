"""Trade policy contract, trade proposals, and cost breakdown tests (Layer 3)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from finpilot.db.enums import DataMode, OrderSide
from finpilot.schemas import (
    CostBreakdown,
    DomainValidationError,
    TradePolicyV1Contract,
    TradeProposal,
)


def test_trade_policy_v1_contract_defaults() -> None:
    policy = TradePolicyV1Contract()
    assert policy.policy_version == "TP-V1"
    assert policy.decision_timestamp_rule == "completed_5m_candle"
    assert policy.mode == DataMode.HISTORICAL_REPLAY


def test_valid_trade_proposal_creation() -> None:
    t_decision = datetime(2026, 10, 30, 9, 20, 0, tzinfo=UTC)
    t_entry = datetime(2026, 10, 30, 9, 25, 0, tzinfo=UTC)

    prop = TradeProposal(
        proposal_id="prop_001",
        instrument_id=101,
        symbol="RELIANCE",
        decision_timestamp=t_decision,
        earliest_entry_timestamp=t_entry,
        entry_price=Decimal("2500.0000"),
        stop_loss=Decimal("2480.0000"),  # < entry
        target_price=Decimal("2540.0000"),  # > entry
        quantity=10,  # integer
        side=OrderSide.BUY,
    )
    assert prop.stop_loss < prop.entry_price < prop.target_price
    assert prop.earliest_entry_timestamp > prop.decision_timestamp
    assert prop.quantity == 10


def test_long_only_proposal_price_violations_rejected() -> None:
    t_decision = datetime(2026, 10, 30, 9, 20, 0, tzinfo=UTC)
    t_entry = datetime(2026, 10, 30, 9, 25, 0, tzinfo=UTC)

    # Stop loss >= Entry price rejected
    with pytest.raises((DomainValidationError, ValidationError)) as exc_stop:
        TradeProposal(
            proposal_id="prop_bad_stop",
            instrument_id=101,
            symbol="RELIANCE",
            decision_timestamp=t_decision,
            earliest_entry_timestamp=t_entry,
            entry_price=Decimal("2500.0000"),
            stop_loss=Decimal("2510.0000"),  # >= entry price
            target_price=Decimal("2550.0000"),
            quantity=10,
        )
    assert "stop loss" in str(exc_stop.value).lower()

    # Target price <= Entry price rejected
    with pytest.raises((DomainValidationError, ValidationError)) as exc_target:
        TradeProposal(
            proposal_id="prop_bad_target",
            instrument_id=101,
            symbol="RELIANCE",
            decision_timestamp=t_decision,
            earliest_entry_timestamp=t_entry,
            entry_price=Decimal("2500.0000"),
            stop_loss=Decimal("2480.0000"),
            target_price=Decimal("2490.0000"),  # <= entry price
            quantity=10,
        )
    assert "target price" in str(exc_target.value).lower()


def test_proposal_entry_timing_violation_rejected() -> None:
    t_decision = datetime(2026, 10, 30, 9, 20, 0, tzinfo=UTC)
    # Entry at or before decision candle completion rejected
    with pytest.raises((DomainValidationError, ValidationError)) as exc_time:
        TradeProposal(
            proposal_id="prop_bad_time",
            instrument_id=101,
            symbol="RELIANCE",
            decision_timestamp=t_decision,
            earliest_entry_timestamp=t_decision,  # Not strictly after
            entry_price=Decimal("2500.0000"),
            stop_loss=Decimal("2480.0000"),
            target_price=Decimal("2550.0000"),
            quantity=10,
        )
    assert "timing violation" in str(exc_time.value).lower()


def test_cost_breakdown_computation() -> None:
    costs = CostBreakdown(
        brokerage=Decimal("20.0000"),
        stt=Decimal("25.0000"),
        exchange_charges=Decimal("3.4500"),
        sebi_turnover_fee=Decimal("0.1000"),
        stamp_duty=Decimal("3.0000"),
        gst=Decimal("4.2390"),
        modelled_slippage=Decimal("15.0000"),
    )
    expected_total = (
        Decimal("20.0000")
        + Decimal("25.0000")
        + Decimal("3.4500")
        + Decimal("0.1000")
        + Decimal("3.0000")
        + Decimal("4.2390")
        + Decimal("15.0000")
    )
    assert costs.total_costs == expected_total
