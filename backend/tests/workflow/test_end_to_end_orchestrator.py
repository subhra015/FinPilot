"""Unit and integration tests for EndToEndPaperWorkflow orchestrator (Layer 14).

Verifies:
- End-to-end replay with reconciled portfolio and ledger balances
- Forward-paper mode cannot route real orders
- Bounded retries and transaction boundaries
- Safe crash recovery from immutable ledger
- Stale data fail-closed rejection
- Deterministic simultaneous candidate competition
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from finpilot.db.enums import DataMode
from finpilot.decision.models import DecisionState
from finpilot.schemas.candles import CandleBar
from finpilot.workflow.orchestrator import (
    CandidateSignal,
    EndToEndPaperWorkflow,
    WorkflowExecutionOutcome,
)

IST = ZoneInfo("Asia/Kolkata")


@pytest.fixture
def base_workflow() -> EndToEndPaperWorkflow:
    return EndToEndPaperWorkflow(initial_capital=Decimal("30000.00"), mode=DataMode.HISTORICAL_REPLAY)


def test_end_to_end_historical_replay_reconciles_ledger_balances(base_workflow: EndToEndPaperWorkflow) -> None:
    """Full cycle: entry proposal -> fill -> exit -> ledger audit reconciliation."""
    ts_entry = datetime(2024, 10, 18, 10, 15, tzinfo=IST)
    candle_entry = CandleBar(
        symbol="TCS",
        timestamp=ts_entry,
        open=3800.0,
        high=3810.0,
        low=3790.0,
        close=3805.0,
        volume=50000,
    )
    candidate = CandidateSignal(
        symbol="TCS",
        candle=candle_entry,
        features={"rsi": 55.0, "atr": 18.0},
        predicted_probability=0.62,
        calibrated_probability=0.59,
        estimated_expectancy=45.0,
        entry_price=Decimal("3800.00"),
        stop_loss_price=Decimal("3770.00"),
        profit_target_price=Decimal("3860.00"),
        quantity=7,
        signal_timestamp=ts_entry - timedelta(minutes=5),
        execution_timestamp=ts_entry,
    )

    # 1. Process Entry
    outcome = base_workflow.process_candidate(candidate)
    assert outcome.is_risk_approved is True
    assert outcome.decision_state == DecisionState.ACCEPTED_CANDIDATE.value
    assert outcome.fill_event is not None
    assert "TCS" in base_workflow.active_positions

    # 2. Process Target Exit
    ts_exit = datetime(2024, 10, 18, 10, 30, tzinfo=IST)
    candle_exit = CandleBar(
        symbol="TCS",
        timestamp=ts_exit,
        open=3850.0,
        high=3865.0,  # Breaches target at 3860.00
        low=3845.0,
        close=3862.0,
        volume=40000,
    )
    exit_fill = base_workflow.evaluate_position_exits(candle_exit)
    assert exit_fill is not None
    assert len(base_workflow.active_positions) == 0

    # 3. Verify Ledger Replay Reconciles 100%
    recovery_info = base_workflow.recover_from_crash()
    assert recovery_info["chain_verified"] is True
    assert recovery_info["events_replayed"] >= 2
    assert Decimal(recovery_info["recovered_cash"]) == base_workflow.available_cash


def test_forward_paper_mode_cannot_submit_real_orders() -> None:
    """Forward paper mode operates in simulated paper environment without real broker calls."""
    workflow = EndToEndPaperWorkflow(initial_capital=Decimal("30000.00"), mode=DataMode.FORWARD_PAPER)
    assert workflow.mode == DataMode.FORWARD_PAPER

    # Verify paper isolation check passes without routing real orders
    workflow._assert_paper_routing_isolated()


def test_bounded_retries_transient_failure_recovery(base_workflow: EndToEndPaperWorkflow) -> None:
    """Operations with transient glitches recover cleanly on bounded retry without duplicating state."""
    attempt_counter = 0

    def flaky_operation() -> str:
        nonlocal attempt_counter
        attempt_counter += 1
        if attempt_counter < 3:
            raise ConnectionResetError("Transient network glitch")
        return "SUCCESS"

    result = base_workflow.execute_with_retry(flaky_operation, operation_name="flaky_test", retries=3)
    assert result == "SUCCESS"
    assert attempt_counter == 3


def test_fail_closed_on_stale_data(base_workflow: EndToEndPaperWorkflow) -> None:
    """Proposals with stale candle timestamps are fail-closed and rejected."""
    ancient_ts = datetime.now(UTC) - timedelta(seconds=1200)  # 20 minutes ago
    ancient_bar = CandleBar(
        symbol="TCS",
        timestamp=ancient_ts,
        open=3800.0,
        high=3810.0,
        low=3790.0,
        close=3800.0,
        volume=50000,
    )
    candidate = CandidateSignal(
        symbol="TCS",
        candle=ancient_bar,
        features={"rsi": 50.0},
        predicted_probability=0.60,
        calibrated_probability=0.58,
        estimated_expectancy=30.0,
        entry_price=Decimal("3800.00"),
        stop_loss_price=Decimal("3770.00"),
        profit_target_price=Decimal("3860.00"),
        quantity=5,
        signal_timestamp=ancient_ts - timedelta(minutes=5),
        execution_timestamp=ancient_ts,
    )

    outcome = base_workflow.process_candidate(candidate)
    assert outcome.is_risk_approved is False
    assert "DATA_STALE" in outcome.rejection_reasons[0]


def test_simultaneous_candidates_deterministic_allocation(base_workflow: EndToEndPaperWorkflow) -> None:
    """When multiple candidates compete for cash, the highest calibrated probability wins deterministically."""
    ts = datetime(2024, 10, 18, 10, 15, tzinfo=IST)
    candle1 = CandleBar(symbol="TCS", timestamp=ts, open=3800.0, high=3810.0, low=3790.0, close=3805.0, volume=50000)
    candle2 = CandleBar(symbol="INFY", timestamp=ts, open=1700.0, high=1710.0, low=1690.0, close=1705.0, volume=40000)

    cand_tcs = CandidateSignal(
        symbol="TCS",
        candle=candle1,
        features={"rsi": 60.0},
        predicted_probability=0.65,
        calibrated_probability=0.62,
        estimated_expectancy=45.0,
        entry_price=Decimal("3800.00"),
        stop_loss_price=Decimal("3770.00"),
        profit_target_price=Decimal("3860.00"),
        quantity=7,
        signal_timestamp=ts - timedelta(minutes=5),
        execution_timestamp=ts,
    )

    cand_infy = CandidateSignal(
        symbol="INFY",
        candle=candle2,
        features={"rsi": 52.0},
        predicted_probability=0.58,
        calibrated_probability=0.55,
        estimated_expectancy=25.0,
        entry_price=Decimal("1700.00"),
        stop_loss_price=Decimal("1680.00"),
        profit_target_price=Decimal("1740.00"),
        quantity=15,
        signal_timestamp=ts - timedelta(minutes=5),
        execution_timestamp=ts,
    )

    outcomes = base_workflow.process_simultaneous_candidates([cand_infy, cand_tcs])

    # Winner must be TCS (P=0.62 > 0.55)
    assert outcomes[0].symbol == "TCS"
    assert outcomes[0].is_risk_approved is True
    assert outcomes[1].symbol == "INFY"
    assert outcomes[1].is_risk_approved is False
