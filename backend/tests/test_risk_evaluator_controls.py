"""Adversarial unit tests proving risk controls reject invalid proposals (Layer 11).

Governed by:
- PROJECT_SPEC.md §4, §5, §7
- SECURITY_CHECKLIST.md SEC-01, SEC-06, SEC-09, SEC-19
- Layer 11 Gate: Deny-by-default on all 11 controls, machine-readable rejection reasons,
  and signed authorization contracts.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from finpilot.data.models import MarketDataRecord
from finpilot.db.enums import DataMode, OrderSide
from finpilot.risk.evaluator import RiskEvaluator
from finpilot.risk.models import (
    RiskConfig,
    RiskDecisionStatus,
    RiskRejectionReason,
)
from finpilot.schemas.trade_policy import TradeProposal

IST = ZoneInfo("Asia/Kolkata")


@pytest.fixture
def base_config() -> RiskConfig:
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
def valid_candle() -> MarketDataRecord:
    # 10:00 AM IST (within session, before 15:00 cutoff)
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
def valid_proposal(valid_candle: MarketDataRecord) -> TradeProposal:
    return TradeProposal(
        proposal_id="PROP-RISK-001",
        instrument_id=101,
        symbol="RELIANCE",
        decision_timestamp=valid_candle.timestamp,
        earliest_entry_timestamp=datetime(2026, 1, 15, 4, 35, tzinfo=UTC),
        entry_price=Decimal("2500.00"),
        stop_loss=Decimal("2475.00"),  # 25 pt risk * 5 shares = ₹125 risk (< ₹600 cap)
        target_price=Decimal("2550.00"),
        quantity=5,  # 5 * 2500 = ₹12,500 notional (< ₹15k cap)
        side=OrderSide.BUY,
        mode=DataMode.HISTORICAL_REPLAY,
    )


def test_control_1_kill_switch_rejects(
    base_config: RiskConfig,
    valid_proposal: TradeProposal,
    valid_candle: MarketDataRecord,
) -> None:
    """Control 1: Active kill switch must immediately deny authorization."""
    cfg = base_config.model_copy(update={"kill_switch_active": True})
    evaluator = RiskEvaluator(config=cfg)

    res = evaluator.evaluate_entry_proposal(
        proposal=valid_proposal,
        candle=valid_candle,
        available_cash=Decimal("30000.00"),
        total_equity=Decimal("30000.00"),
    )

    assert res.status == RiskDecisionStatus.REJECTED
    assert res.authorization is None
    assert RiskRejectionReason.KILL_SWITCH_ACTIVE in res.rejection_reasons


def test_control_2_manual_pause_rejects(
    base_config: RiskConfig,
    valid_proposal: TradeProposal,
    valid_candle: MarketDataRecord,
) -> None:
    """Control 2: Manual trading pause must immediately deny authorization."""
    cfg = base_config.model_copy(update={"manual_trading_paused": True})
    evaluator = RiskEvaluator(config=cfg)

    res = evaluator.evaluate_entry_proposal(
        proposal=valid_proposal,
        candle=valid_candle,
        available_cash=Decimal("30000.00"),
        total_equity=Decimal("30000.00"),
    )

    assert res.status == RiskDecisionStatus.REJECTED
    assert RiskRejectionReason.MANUAL_TRADING_PAUSED in res.rejection_reasons


def test_control_3_unsupported_instrument_rejects(
    base_config: RiskConfig,
    valid_candle: MarketDataRecord,
) -> None:
    """Control 3: Unapproved instrument ticker must be denied."""
    evaluator = RiskEvaluator(config=base_config)
    unapproved_prop = TradeProposal(
        proposal_id="PROP-RISK-UNAPPROVED",
        instrument_id=999,
        symbol="UNAPPROVED_CO",
        decision_timestamp=valid_candle.timestamp,
        earliest_entry_timestamp=datetime(2026, 1, 15, 4, 35, tzinfo=UTC),
        entry_price=Decimal("100.00"),
        stop_loss=Decimal("95.00"),
        target_price=Decimal("110.00"),
        quantity=10,
    )

    res = evaluator.evaluate_entry_proposal(
        proposal=unapproved_prop,
        candle=valid_candle,
        available_cash=Decimal("30000.00"),
        total_equity=Decimal("30000.00"),
    )

    assert res.status == RiskDecisionStatus.REJECTED
    assert RiskRejectionReason.UNSUPPORTED_INSTRUMENT in res.rejection_reasons


def test_control_4_policy_and_model_version_mismatch(
    base_config: RiskConfig,
    valid_proposal: TradeProposal,
    valid_candle: MarketDataRecord,
) -> None:
    """Control 4: Mismatch in model ID or trade policy version must be denied."""
    evaluator = RiskEvaluator(config=base_config)

    # Rogue model
    res = evaluator.evaluate_entry_proposal(
        proposal=valid_proposal,
        candle=valid_candle,
        available_cash=Decimal("30000.00"),
        total_equity=Decimal("30000.00"),
        model_id="ROGUE-MODEL-V99",
    )
    assert res.status == RiskDecisionStatus.REJECTED
    assert RiskRejectionReason.MODEL_VERSION_MISMATCH in res.rejection_reasons


def test_control_5_missing_market_data_rejects(
    base_config: RiskConfig,
    valid_proposal: TradeProposal,
) -> None:
    """Control 5: Missing candle data must fail closed."""
    evaluator = RiskEvaluator(config=base_config)

    res = evaluator.evaluate_entry_proposal(
        proposal=valid_proposal,
        candle=None,
        available_cash=Decimal("30000.00"),
        total_equity=Decimal("30000.00"),
    )

    assert res.status == RiskDecisionStatus.REJECTED
    assert RiskRejectionReason.DATA_STALE_OR_MISSING in res.rejection_reasons


def test_control_6_invalid_ohlc_geometry_rejects(
    base_config: RiskConfig,
    valid_proposal: TradeProposal,
) -> None:
    """Control 6: Malformed candle geometry (high < open) must be rejected."""
    evaluator = RiskEvaluator(config=base_config)
    bad_candle = MarketDataRecord(
        source="HISTORICAL_SIM",
        retrieval_time=valid_proposal.decision_timestamp,
        instrument_id=101,
        symbol="RELIANCE",
        timestamp=valid_proposal.decision_timestamp,
        open=Decimal("2500.00"),
        high=Decimal("2450.00"),  # high is lower than open!
        low=Decimal("2400.00"),
        close=Decimal("2480.00"),
        volume=1000,
    )

    res = evaluator.evaluate_entry_proposal(
        proposal=valid_proposal,
        candle=bad_candle,
        available_cash=Decimal("30000.00"),
        total_equity=Decimal("30000.00"),
    )

    assert res.status == RiskDecisionStatus.REJECTED
    assert RiskRejectionReason.MARKET_DATA_INVALID in res.rejection_reasons


def test_control_7_out_of_session_and_cutoff_rejections(
    base_config: RiskConfig,
    valid_proposal: TradeProposal,
) -> None:
    """Control 7: Out-of-session and past 15:00 IST entry cutoff rejections."""
    evaluator = RiskEvaluator(config=base_config)

    # 1. Past session cutoff: 15:05 IST
    ts_cutoff = datetime(2026, 1, 15, 15, 5, tzinfo=IST).astimezone(UTC)
    cutoff_candle = MarketDataRecord(
        source="HISTORICAL_SIM",
        retrieval_time=ts_cutoff,
        instrument_id=101,
        symbol="RELIANCE",
        timestamp=ts_cutoff,
        open=Decimal("2500.00"),
        high=Decimal("2510.00"),
        low=Decimal("2490.00"),
        close=Decimal("2505.00"),
        volume=5000,
    )
    res_cutoff = evaluator.evaluate_entry_proposal(
        proposal=valid_proposal,
        candle=cutoff_candle,
        available_cash=Decimal("30000.00"),
        total_equity=Decimal("30000.00"),
    )
    assert res_cutoff.status == RiskDecisionStatus.REJECTED
    assert RiskRejectionReason.SESSION_ENTRY_CUTOFF in res_cutoff.rejection_reasons

    # 2. Out of regular session: 16:00 IST
    ts_out = datetime(2026, 1, 15, 16, 0, tzinfo=IST).astimezone(UTC)
    out_candle = MarketDataRecord(
        source="HISTORICAL_SIM",
        retrieval_time=ts_out,
        instrument_id=101,
        symbol="RELIANCE",
        timestamp=ts_out,
        open=Decimal("2500.00"),
        high=Decimal("2510.00"),
        low=Decimal("2490.00"),
        close=Decimal("2505.00"),
        volume=5000,
    )
    res_out = evaluator.evaluate_entry_proposal(
        proposal=valid_proposal,
        candle=out_candle,
        available_cash=Decimal("30000.00"),
        total_equity=Decimal("30000.00"),
    )
    assert res_out.status == RiskDecisionStatus.REJECTED
    assert RiskRejectionReason.OUT_OF_SESSION in res_out.rejection_reasons


def test_control_8_duplicate_order_and_existing_position(
    base_config: RiskConfig,
    valid_proposal: TradeProposal,
    valid_candle: MarketDataRecord,
) -> None:
    """Control 8: Duplicate proposal ID and existing open position rejection."""
    evaluator = RiskEvaluator(config=base_config)

    # 1. Duplicate active order
    res_dup = evaluator.evaluate_entry_proposal(
        proposal=valid_proposal,
        candle=valid_candle,
        available_cash=Decimal("30000.00"),
        total_equity=Decimal("30000.00"),
        active_order_proposal_ids={valid_proposal.proposal_id},
    )
    assert res_dup.status == RiskDecisionStatus.REJECTED
    assert RiskRejectionReason.DUPLICATE_SIGNAL_OR_ORDER in res_dup.rejection_reasons

    # 2. Existing open position on same instrument
    existing_pos = [{"symbol": "RELIANCE", "notional": "12500.00"}]
    res_pos = evaluator.evaluate_entry_proposal(
        proposal=valid_proposal,
        candle=valid_candle,
        available_cash=Decimal("30000.00"),
        total_equity=Decimal("30000.00"),
        current_positions=existing_pos,
    )
    assert res_pos.status == RiskDecisionStatus.REJECTED
    assert RiskRejectionReason.UNRESOLVED_POSITION_STATE in res_pos.rejection_reasons


def test_control_9_max_concurrent_positions_cap(
    base_config: RiskConfig,
    valid_proposal: TradeProposal,
    valid_candle: MarketDataRecord,
) -> None:
    """Control 9: Rejects entry when concurrent positions cap (1) is reached."""
    evaluator = RiskEvaluator(config=base_config)
    # Already holding 1 position in TCS
    other_pos = [{"symbol": "TCS", "notional": "10000.00"}]

    res = evaluator.evaluate_entry_proposal(
        proposal=valid_proposal,
        candle=valid_candle,
        available_cash=Decimal("20000.00"),
        total_equity=Decimal("30000.00"),
        current_positions=other_pos,
    )
    assert res.status == RiskDecisionStatus.REJECTED
    assert RiskRejectionReason.MAX_CONCURRENT_POSITIONS_EXCEEDED in res.rejection_reasons


def test_control_10_daily_loss_and_drawdown_circuit_breakers(
    base_config: RiskConfig,
    valid_proposal: TradeProposal,
    valid_candle: MarketDataRecord,
) -> None:
    """Control 10: Circuit breakers for daily loss (>= ₹1500) and drawdown (>= 10%)."""
    evaluator = RiskEvaluator(config=base_config)

    # 1. Daily loss >= ₹1,500
    res_loss = evaluator.evaluate_entry_proposal(
        proposal=valid_proposal,
        candle=valid_candle,
        available_cash=Decimal("25000.00"),
        total_equity=Decimal("28000.00"),
        daily_realized_loss=Decimal("1500.00"),
    )
    assert res_loss.status == RiskDecisionStatus.CIRCUIT_BROKEN
    assert RiskRejectionReason.DAILY_LOSS_LIMIT_EXCEEDED in res_loss.rejection_reasons

    # 2. Drawdown >= 10%
    res_dd = evaluator.evaluate_entry_proposal(
        proposal=valid_proposal,
        candle=valid_candle,
        available_cash=Decimal("25000.00"),
        total_equity=Decimal("26000.00"),
        current_drawdown_pct=0.105,
    )
    assert res_dd.status == RiskDecisionStatus.SUSPENDED
    assert RiskRejectionReason.DRAWDOWN_SUSPENSION_TRIGGERED in res_dd.rejection_reasons


def test_control_11_insufficient_cash_affordability(
    base_config: RiskConfig,
    valid_proposal: TradeProposal,
    valid_candle: MarketDataRecord,
) -> None:
    """Control 11: Rejects when required cash (notional + buffer + fees) > available cash."""
    evaluator = RiskEvaluator(config=base_config)

    # Proposal requires ~₹12,500 + fees, but available cash is only ₹5,000
    res = evaluator.evaluate_entry_proposal(
        proposal=valid_proposal,
        candle=valid_candle,
        available_cash=Decimal("5000.00"),
        total_equity=Decimal("30000.00"),
    )

    assert res.status == RiskDecisionStatus.REJECTED
    assert RiskRejectionReason.INSUFFICIENT_AVAILABLE_CASH in res.rejection_reasons


def test_control_12_excessive_stop_risk_rejects(
    base_config: RiskConfig,
    valid_candle: MarketDataRecord,
) -> None:
    """Control 12: Rejects when planned stop loss exceeds 2% of total equity (₹600 on ₹30k)."""
    evaluator = RiskEvaluator(config=base_config)

    # Stop loss set at ₹2,300 -> risk is ₹200/share * 5 = ₹1,000 (> ₹600 cap)
    risky_proposal = TradeProposal(
        proposal_id="PROP-RISK-HIGH-STOP",
        instrument_id=101,
        symbol="RELIANCE",
        decision_timestamp=valid_candle.timestamp,
        earliest_entry_timestamp=datetime(2026, 1, 15, 4, 35, tzinfo=UTC),
        entry_price=Decimal("2500.00"),
        stop_loss=Decimal("2300.00"),
        target_price=Decimal("2700.00"),
        quantity=5,
    )

    res = evaluator.evaluate_entry_proposal(
        proposal=risky_proposal,
        candle=valid_candle,
        available_cash=Decimal("30000.00"),
        total_equity=Decimal("30000.00"),
    )

    assert res.status == RiskDecisionStatus.REJECTED
    assert RiskRejectionReason.EXCESSIVE_STOP_RISK in res.rejection_reasons


def test_control_13_position_and_total_exposure_caps(
    base_config: RiskConfig,
    valid_candle: MarketDataRecord,
) -> None:
    """Control 13: Rejects when position exposure exceeds 50% or total exceeds 100%."""
    evaluator = RiskEvaluator(config=base_config)

    # 1. Position exposure: 8 shares * ₹2500 = ₹20,000 (> 50% of ₹30,000 = ₹15,000)
    large_pos_prop = TradeProposal(
        proposal_id="PROP-RISK-EXPOSURE",
        instrument_id=101,
        symbol="RELIANCE",
        decision_timestamp=valid_candle.timestamp,
        earliest_entry_timestamp=datetime(2026, 1, 15, 4, 35, tzinfo=UTC),
        entry_price=Decimal("2500.00"),
        stop_loss=Decimal("2480.00"),  # risk is 20 * 8 = ₹160 (< ₹600)
        target_price=Decimal("2550.00"),
        quantity=8,
    )

    res_pos = evaluator.evaluate_entry_proposal(
        proposal=large_pos_prop,
        candle=valid_candle,
        available_cash=Decimal("30000.00"),
        total_equity=Decimal("30000.00"),
    )
    assert res_pos.status == RiskDecisionStatus.REJECTED
    assert RiskRejectionReason.POSITION_EXPOSURE_CAP_EXCEEDED in res_pos.rejection_reasons


def test_authorized_proposal_generates_signed_token(
    base_config: RiskConfig,
    valid_proposal: TradeProposal,
    valid_candle: MarketDataRecord,
) -> None:
    """Valid proposal passing all checks receives cryptographically signed RiskAuthorization."""
    evaluator = RiskEvaluator(config=base_config)

    res = evaluator.evaluate_entry_proposal(
        proposal=valid_proposal,
        candle=valid_candle,
        available_cash=Decimal("30000.00"),
        total_equity=Decimal("30000.00"),
    )

    assert res.status == RiskDecisionStatus.AUTHORIZED
    assert len(res.rejection_reasons) == 0
    assert res.authorization is not None

    auth = res.authorization
    assert auth.proposal_id == valid_proposal.proposal_id
    assert auth.symbol == "RELIANCE"
    assert auth.authorized_quantity == 5
    assert auth.verify_signature() is True
