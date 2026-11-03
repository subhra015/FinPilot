"""Tests verifying entry vs exit asymmetry and deterministic replay in RiskEvaluator (Layer 11).

Governed by:
- PROJECT_SPEC.md §4, §5, §7
- SECURITY_CHECKLIST.md SEC-01, SEC-06, SEC-09, SEC-19
- Layer 11 Gate: Distinguish blocking new entries from attempting to close an existing
  position (never assume a close can fill if market/candle is unavailable).
- Deterministic replay verification: bit-identical decisions and audit signatures.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from finpilot.data.models import MarketDataRecord
from finpilot.db.enums import OrderSide
from finpilot.risk.evaluator import RiskEvaluator
from finpilot.risk.models import (
    PositionCloseIntent,
    RiskConfig,
    RiskDecisionStatus,
    RiskRejectionReason,
)
from finpilot.schemas.trade_policy import TradeProposal

IST = ZoneInfo("Asia/Kolkata")


@pytest.fixture
def risk_config() -> RiskConfig:
    return RiskConfig(
        max_account_equity=Decimal("30000.00"),
        max_exposure_per_instrument_pct=Decimal("0.50"),
        max_total_exposure_pct=Decimal("1.00"),
        max_concurrent_positions=1,
        max_planned_stop_risk_pct=Decimal("0.02"),
        max_slippage_buffer_bps=Decimal("10.0"),
        max_daily_loss=Decimal("1500.00"),
        max_drawdown_pct=0.10,
        approved_instruments=["RELIANCE", "TCS", "INFY"],
        approved_policy_version="TP-V1",
        approved_model_ids=["MODEL-LOGREG-V1", "MODEL-LIGHTGBM-V1", "STRAT-SIMPLE-V1"],
    )


@pytest.fixture
def evaluator(risk_config: RiskConfig) -> RiskEvaluator:
    return RiskEvaluator(config=risk_config)


@pytest.fixture
def post_cutoff_candle() -> MarketDataRecord:
    # 15:15 IST (Forced square-off time; after 15:00 entry cutoff)
    ts = datetime(2026, 1, 15, 15, 15, tzinfo=IST).astimezone(UTC)
    return MarketDataRecord(
        source="HISTORICAL_SIM",
        retrieval_time=ts,
        instrument_id=101,
        symbol="RELIANCE",
        timestamp=ts,
        open=Decimal("2520.00"),
        high=Decimal("2525.00"),
        low=Decimal("2515.00"),
        close=Decimal("2520.00"),
        volume=5000,
    )


@pytest.fixture
def valid_entry_proposal(post_cutoff_candle: MarketDataRecord) -> TradeProposal:
    return TradeProposal(
        proposal_id="PROP-POST-CUTOFF-001",
        instrument_id=101,
        symbol="RELIANCE",
        decision_timestamp=post_cutoff_candle.timestamp,
        earliest_entry_timestamp=datetime(2026, 1, 15, 9, 50, tzinfo=UTC),
        entry_price=Decimal("2520.00"),
        stop_loss=Decimal("2500.00"),
        target_price=Decimal("2560.00"),
        quantity=5,
        side=OrderSide.BUY,
    )


@pytest.fixture
def exit_intent(post_cutoff_candle: MarketDataRecord) -> PositionCloseIntent:
    return PositionCloseIntent(
        close_id="EXIT-RELIANCE-001",
        symbol="RELIANCE",
        instrument_id=101,
        quantity_to_close=5,
        reason="FORCED_EOD_SQUARE_OFF",
        timestamp=post_cutoff_candle.timestamp,
    )


def test_exit_allowed_after_entry_cutoff_while_entry_is_blocked(
    evaluator: RiskEvaluator,
    valid_entry_proposal: TradeProposal,
    exit_intent: PositionCloseIntent,
    post_cutoff_candle: MarketDataRecord,
) -> None:
    """At 15:15 IST, new entries must be REJECTED, but forced exits must be AUTHORIZED."""
    # 1. New entry at 15:15 IST -> DENIED
    entry_res = evaluator.evaluate_entry_proposal(
        proposal=valid_entry_proposal,
        candle=post_cutoff_candle,
        available_cash=Decimal("30000.00"),
        total_equity=Decimal("30000.00"),
    )
    assert entry_res.status == RiskDecisionStatus.REJECTED
    assert RiskRejectionReason.SESSION_ENTRY_CUTOFF in entry_res.rejection_reasons
    assert entry_res.authorization is None

    # 2. Position exit at 15:15 IST -> AUTHORIZED
    exit_res = evaluator.evaluate_close_intent(
        close_intent=exit_intent,
        candle=post_cutoff_candle,
        current_timestamp=post_cutoff_candle.timestamp,
    )
    assert exit_res.status == RiskDecisionStatus.AUTHORIZED
    assert len(exit_res.rejection_reasons) == 0
    assert exit_res.authorization is not None
    assert exit_res.authorization.proposal_id == exit_intent.close_id
    assert exit_res.authorization.authorized_quantity == 5
    assert exit_res.authorization.side == OrderSide.SELL
    assert exit_res.authorization.verify_signature() is True


def test_exit_allowed_with_zero_available_cash(
    evaluator: RiskEvaluator,
    exit_intent: PositionCloseIntent,
    post_cutoff_candle: MarketDataRecord,
) -> None:
    """Closing a position releases capital and must not be blocked by zero available cash."""
    exit_res = evaluator.evaluate_close_intent(
        close_intent=exit_intent,
        candle=post_cutoff_candle,
        current_timestamp=post_cutoff_candle.timestamp,
    )
    assert exit_res.status == RiskDecisionStatus.AUTHORIZED
    assert exit_res.authorization is not None


def test_exit_allowed_when_max_concurrent_positions_is_reached(
    evaluator: RiskEvaluator,
    valid_entry_proposal: TradeProposal,
    exit_intent: PositionCloseIntent,
    post_cutoff_candle: MarketDataRecord,
) -> None:
    """When at capacity (1 position held), entry is blocked but exit is allowed."""
    # Entry blocked by capacity
    midday_ts = datetime(2026, 1, 15, 11, 0, tzinfo=IST).astimezone(UTC)
    midday_candle = post_cutoff_candle.model_copy(
        update={"timestamp": midday_ts, "retrieval_time": midday_ts}
    )
    midday_proposal = valid_entry_proposal.model_copy(update={"decision_timestamp": midday_ts})

    entry_res = evaluator.evaluate_entry_proposal(
        proposal=midday_proposal,
        candle=midday_candle,
        available_cash=Decimal("20000.00"),
        total_equity=Decimal("30000.00"),
        current_positions=[{"symbol": "RELIANCE", "notional": "12500.00"}],
    )
    assert entry_res.status == RiskDecisionStatus.REJECTED
    assert RiskRejectionReason.MAX_CONCURRENT_POSITIONS_EXCEEDED in entry_res.rejection_reasons

    # Exit allowed
    exit_res = evaluator.evaluate_close_intent(
        close_intent=exit_intent,
        candle=midday_candle,
        current_timestamp=midday_ts,
    )
    assert exit_res.status == RiskDecisionStatus.AUTHORIZED


def test_exit_rejected_if_market_candle_is_missing(
    evaluator: RiskEvaluator,
    exit_intent: PositionCloseIntent,
) -> None:
    """Fail-closed: Never assume an exit can fill if market data is absent."""
    exit_res = evaluator.evaluate_close_intent(
        close_intent=exit_intent,
        candle=None,
    )
    assert exit_res.status == RiskDecisionStatus.REJECTED
    assert RiskRejectionReason.DATA_STALE_OR_MISSING in exit_res.rejection_reasons
    assert exit_res.authorization is None


def test_exit_rejected_if_market_bar_has_zero_volume_or_halt(
    evaluator: RiskEvaluator,
    exit_intent: PositionCloseIntent,
    post_cutoff_candle: MarketDataRecord,
) -> None:
    """Fail-closed: If the market bar volume is 0 (halt / illiquid), do not authorize exit fill."""
    zero_vol_candle = post_cutoff_candle.model_copy(update={"volume": 0})
    exit_res = evaluator.evaluate_close_intent(
        close_intent=exit_intent,
        candle=zero_vol_candle,
    )
    assert exit_res.status == RiskDecisionStatus.REJECTED
    assert RiskRejectionReason.MARKET_DATA_INVALID in exit_res.rejection_reasons
    assert exit_res.authorization is None


def test_exit_rejected_if_market_close_price_is_invalid(
    evaluator: RiskEvaluator,
    exit_intent: PositionCloseIntent,
    post_cutoff_candle: MarketDataRecord,
) -> None:
    """Fail-closed: Non-positive or corrupted price must reject exit authorization."""
    bad_price_candle = post_cutoff_candle.model_copy(update={"close": Decimal("-10.00")})
    exit_res = evaluator.evaluate_close_intent(
        close_intent=exit_intent,
        candle=bad_price_candle,
    )
    assert exit_res.status == RiskDecisionStatus.REJECTED
    assert RiskRejectionReason.MARKET_DATA_INVALID in exit_res.rejection_reasons


def test_deterministic_replay_produces_identical_decisions_and_signatures(
    risk_config: RiskConfig,
    valid_entry_proposal: TradeProposal,
    exit_intent: PositionCloseIntent,
    post_cutoff_candle: MarketDataRecord,
) -> None:
    """Replay of identical evaluation sequence produces bit-identical signatures and decisions."""
    evaluator_1 = RiskEvaluator(config=risk_config)
    evaluator_2 = RiskEvaluator(config=risk_config)

    ts = post_cutoff_candle.timestamp

    # Run 1
    entry_1 = evaluator_1.evaluate_entry_proposal(
        proposal=valid_entry_proposal,
        candle=post_cutoff_candle,
        available_cash=Decimal("30000.00"),
        total_equity=Decimal("30000.00"),
        current_timestamp=ts,
    )
    exit_1 = evaluator_1.evaluate_close_intent(
        close_intent=exit_intent,
        candle=post_cutoff_candle,
        current_timestamp=ts,
    )

    # Run 2
    entry_2 = evaluator_2.evaluate_entry_proposal(
        proposal=valid_entry_proposal,
        candle=post_cutoff_candle,
        available_cash=Decimal("30000.00"),
        total_equity=Decimal("30000.00"),
        current_timestamp=ts,
    )
    exit_2 = evaluator_2.evaluate_close_intent(
        close_intent=exit_intent,
        candle=post_cutoff_candle,
        current_timestamp=ts,
    )

    # Statuses and reasons must match exactly
    assert entry_1.status == entry_2.status
    assert entry_1.rejection_reasons == entry_2.rejection_reasons

    assert exit_1.status == exit_2.status
    assert exit_1.rejection_reasons == exit_2.rejection_reasons

    assert exit_1.authorization is not None
    assert exit_2.authorization is not None
    # Authorization signature verifies internal cryptographic seal determinism
    assert exit_1.authorization.verify_signature() is True
    assert exit_2.authorization.verify_signature() is True
    assert exit_1.authorization.auth_signature == exit_2.authorization.auth_signature
    assert exit_1.authorization.authorization_id == exit_2.authorization.authorization_id
    assert exit_1.decision_id == exit_2.decision_id
    assert entry_1.decision_id == entry_2.decision_id
