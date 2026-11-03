"""Tests for trade-policy labeling engine under TP-V1 (Layer 8).

Governed by:
- docs/trade-policy-contract-v1.md
- docs/execution-policy.md
- Layer 8 Gate: Labeling under executable trade policy, next-bar entry,
  stop/target resolution, statutory costs, and integer share sizing (Approach A).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from finpilot.data.models import MarketDataRecord
from finpilot.db.enums import DataMode
from finpilot.execution.fee_schedule import round_paisa
from finpilot.features.models import FeatureVector
from finpilot.labeling.generator import TradePolicyLabelGenerator
from finpilot.labeling.models import TradeOutcomeReason

IST = ZoneInfo("Asia/Kolkata")


def make_bar(
    symbol: str,
    ts_ist: datetime,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: int = 10000,
    instrument_id: int = 1,
) -> MarketDataRecord:
    """Helper creating a valid completed 5-minute MarketDataRecord."""
    utc_ts = ts_ist.astimezone(ZoneInfo("UTC"))
    return MarketDataRecord(
        source="TEST_FEED",
        retrieval_time=utc_ts,
        instrument_id=instrument_id,
        symbol=symbol,
        exchange="NSE",
        timestamp=utc_ts,
        open=Decimal(str(open_)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        volume=volume,
        mode=DataMode.HISTORICAL_REPLAY,
    )


def make_feature_vector(
    symbol: str,
    ts_ist: datetime,
    instrument_id: int = 1,
    is_warmed_up: bool = True,
) -> FeatureVector:
    """Helper creating a point-in-time FeatureVector."""
    utc_ts = ts_ist.astimezone(ZoneInfo("UTC"))
    return FeatureVector(
        instrument_id=instrument_id,
        symbol=symbol,
        timestamp=utc_ts,
        feature_set_version="FS-V1",
        features={
            "ret_1": 0.002,
            "sma_ratio_9_21": 0.005,
            "rsi_14": 58.5,
            "causal_rel_vol": 1.25,
        },
        is_fully_warmed_up=is_warmed_up,
        bar_count_in_session=25,
        mode=DataMode.HISTORICAL_REPLAY,
    )


def test_next_bar_executable_entry_delay() -> None:
    """Verify entry fill occurs at next-candle open, not retroactively at decision candle close."""
    generator = TradePolicyLabelGenerator(
        stop_loss_pct=Decimal("0.015"),
        take_profit_pct=Decimal("0.030"),
        modelled_slippage_bps=Decimal("2.0"),
    )

    base_time = datetime(2026, 1, 15, 10, 0, tzinfo=IST)
    # Decision candle at 10:00 (Close 1000.0)
    # Next candle at 10:05 (Open 1005.0)
    # Target candle at 10:10 (High 1040.0, hits 3% target)
    bars = [
        make_bar("RELIANCE", base_time, 995.0, 1002.0, 995.0, 1000.0),
        make_bar("RELIANCE", base_time + timedelta(minutes=5), 1005.0, 1010.0, 1004.0, 1008.0),
        make_bar("RELIANCE", base_time + timedelta(minutes=10), 1010.0, 1040.0, 1009.0, 1038.0),
    ]
    feat = {bars[0].timestamp: make_feature_vector("RELIANCE", base_time)}

    labels, excluded = generator.generate_labels_for_series(1, "RELIANCE", bars, feat)
    assert len(labels) == 1
    lbl = labels[0]

    # Decision time must match candle 0
    assert lbl.decision_time == bars[0].timestamp
    # Entry time must be open of candle 1 (10:05 IST)
    assert lbl.entry_time == bars[1].timestamp
    # Entry price must be 1005.0 * (1 + 0.0002) = 1005.20, NOT 1000.00 close
    expected_entry_price = round_paisa(Decimal("1005.0") * Decimal("1.0002"))
    assert lbl.entry_price == expected_entry_price
    assert lbl.outcome_reason == TradeOutcomeReason.TARGET_HIT


def test_net_positive_pnl_labeling_under_fees() -> None:
    """Verify trade with small gross profit losing money after fees is labeled 0.

    Anti-leakage / true economic alignment:
    Generic price-rise models label this 1 because exit > entry.
    FinPilot's trade-policy labeler under Approach A marks it 0 because net P&L <= 0.
    """
    generator = TradePolicyLabelGenerator(
        stop_loss_pct=Decimal("0.015"),
        take_profit_pct=Decimal("0.030"),
        modelled_slippage_bps=Decimal("2.0"),
        scenario_equity=Decimal("30000.00"),
    )

    base_time = datetime(2026, 1, 15, 10, 0, tzinfo=IST)
    # Candle 0: Decision at 10:00
    # Candle 1: Entry at 10:05 (Open 100.0) -> Entry fill 100.02
    # Candle 2-6: Choppy, exits on max holding bars (6 bars) with tiny gross gain (Exit open 100.05)
    bars = [
        make_bar("TCS", base_time, 99.8, 100.2, 99.7, 100.0),
        make_bar("TCS", base_time + timedelta(minutes=5), 100.0, 100.2, 99.5, 100.1),
        make_bar("TCS", base_time + timedelta(minutes=10), 100.1, 100.2, 99.5, 100.0),
        make_bar("TCS", base_time + timedelta(minutes=15), 100.0, 100.2, 99.5, 100.0),
        make_bar("TCS", base_time + timedelta(minutes=20), 100.0, 100.2, 99.5, 100.0),
        make_bar("TCS", base_time + timedelta(minutes=25), 100.0, 100.2, 99.5, 100.0),
        # Bar 7: Exits at max holding bars, open 100.05
        make_bar("TCS", base_time + timedelta(minutes=30), 100.05, 100.1, 99.8, 100.0),
    ]
    feat = {bars[0].timestamp: make_feature_vector("TCS", base_time)}

    labels, _ = generator.generate_labels_for_series(2, "TCS", bars, feat)
    assert len(labels) == 1
    lbl = labels[0]

    # Gross P&L is slightly positive or near flat
    # But fees exceed gross P&L, making net P&L negative
    assert lbl.fees > Decimal("0.00")
    assert lbl.net_pnl < Decimal("0.00")
    assert lbl.binary_label == 0  # CRUCIAL: Not 1!
    assert lbl.outcome_reason == TradeOutcomeReason.MAX_HOLDING_EXPIRY


def test_stop_loss_and_gap_through_stop() -> None:
    """Verify stop loss triggers and market gaps down past stop are filled at open."""
    generator = TradePolicyLabelGenerator(
        stop_loss_pct=Decimal("0.015"),  # 1.5% stop
        take_profit_pct=Decimal("0.030"),
    )

    base_time = datetime(2026, 1, 15, 10, 0, tzinfo=IST)
    # Entry at 100.02. Stop loss = 100.02 * (1 - 0.015) = 98.52
    # Next bar gaps down at Open = 97.00 (< 98.52)
    bars = [
        make_bar("INFY", base_time, 99.8, 100.2, 99.7, 100.0),
        make_bar("INFY", base_time + timedelta(minutes=5), 100.0, 100.2, 99.5, 100.1),
        make_bar("INFY", base_time + timedelta(minutes=10), 97.0, 97.5, 96.5, 97.0),
    ]
    feat = {bars[0].timestamp: make_feature_vector("INFY", base_time)}

    labels, _ = generator.generate_labels_for_series(3, "INFY", bars, feat)
    assert len(labels) == 1
    lbl = labels[0]

    assert lbl.outcome_reason == TradeOutcomeReason.GAP_STOP_HIT
    assert lbl.is_gap_fill is True
    # Fill price must be the gapped bar open (97.00), not the theoretical stop price (98.52)
    assert lbl.exit_price == Decimal("97.00")
    assert lbl.net_pnl < Decimal("0.00")
    assert lbl.binary_label == 0


def test_same_bar_collision_ambiguity() -> None:
    """Verify same-bar stop & target breaches apply conservative stop loss first."""
    generator = TradePolicyLabelGenerator(
        stop_loss_pct=Decimal("0.015"),  # Stop: 98.52
        take_profit_pct=Decimal("0.030"),  # Target: 103.02
    )

    base_time = datetime(2026, 1, 15, 10, 0, tzinfo=IST)
    # Bar 2 has Low 98.00 (breaches stop) AND High 104.00 (breaches target)
    bars = [
        make_bar("HDFCBANK", base_time, 99.8, 100.2, 99.7, 100.0),
        make_bar("HDFCBANK", base_time + timedelta(minutes=5), 100.0, 100.2, 99.5, 100.1),
        make_bar("HDFCBANK", base_time + timedelta(minutes=10), 100.0, 104.0, 98.0, 101.0),
    ]
    feat = {bars[0].timestamp: make_feature_vector("HDFCBANK", base_time)}

    labels, _ = generator.generate_labels_for_series(4, "HDFCBANK", bars, feat)
    assert len(labels) == 1
    lbl = labels[0]

    assert lbl.is_ambiguous_exit is True
    assert lbl.outcome_reason == TradeOutcomeReason.SAME_BAR_AMBIGUOUS_STOP
    # Stop price applied
    assert lbl.exit_price == Decimal("98.52")
    assert lbl.binary_label == 0


def test_compulsory_session_square_off() -> None:
    """Verify positions still open at 15:15 IST are closed at session cutoff."""
    generator = TradePolicyLabelGenerator(
        max_holding_bars=20,  # Long max hold, but hits 15:15 IST cutoff first
    )

    # Signal candle at 14:50 IST
    base_time = datetime(2026, 1, 15, 14, 50, tzinfo=IST)
    bars = [
        make_bar("SBIN", base_time, 500.0, 501.0, 499.0, 500.5),  # 14:50 dec
        make_bar(
            "SBIN", base_time + timedelta(minutes=5), 500.5, 501.0, 500.0, 500.2
        ),  # 14:55 entry
        make_bar("SBIN", base_time + timedelta(minutes=10), 500.2, 500.8, 500.0, 500.3),
        make_bar("SBIN", base_time + timedelta(minutes=15), 500.3, 500.9, 500.1, 500.5),
        make_bar("SBIN", base_time + timedelta(minutes=20), 500.5, 501.0, 500.2, 500.4),
        make_bar(
            "SBIN", base_time + timedelta(minutes=25), 500.4, 500.8, 500.0, 500.2
        ),  # 15:15 cutoff
    ]
    feat = {bars[0].timestamp: make_feature_vector("SBIN", base_time)}

    labels, _ = generator.generate_labels_for_series(5, "SBIN", bars, feat)
    assert len(labels) == 1
    lbl = labels[0]

    assert lbl.outcome_reason == TradeOutcomeReason.SESSION_SQUARE_OFF
    assert lbl.exit_time == bars[-1].timestamp
