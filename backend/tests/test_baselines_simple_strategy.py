"""Tests for Predeclared Simple Strategy rules and sizing (Layer 7).

Governed by:
- PROJECT_SPEC.md §5 (Predeclared simple strategy: single fixed, non-ML rule set)
- docs/trade-policy-contract-v1.md (TP-V1 parameters)
- Layer 7 Gate: Frozen, transparent benchmark evaluated with exact sizing and boundary tests.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from finpilot.baselines.simple_strategy import PredeclaredSimpleStrategy
from finpilot.data.models import MarketDataRecord
from finpilot.db.enums import CurrencyCode, DataMode, ExchangeCode, OrderSide
from finpilot.features.definitions import FS_V1_VERSION
from finpilot.features.models import FeatureVector

IST = ZoneInfo("Asia/Kolkata")


def make_test_bar(
    timestamp_ist: datetime,
    close: Decimal = Decimal("2000.00"),
) -> MarketDataRecord:
    now_utc = datetime.now(UTC)
    return MarketDataRecord(
        source="TEST_SOURCE",
        retrieval_time=now_utc,
        symbol="RELIANCE",
        instrument_id=101,
        exchange=ExchangeCode.NSE,
        currency=CurrencyCode.INR,
        timestamp=timestamp_ist,
        open=close - Decimal("5.00"),
        high=close + Decimal("10.00"),
        low=close - Decimal("10.00"),
        close=close,
        volume=10000,
        mode=DataMode.SYNTHETIC_DEMO,
    )


def make_feature_vector(
    bar: MarketDataRecord,
    sma_ratio: float = 0.02,
    vwap_dist: float = 0.01,
    ret_1: float = 0.005,
    rsi_14: float = 60.0,
    rel_vol: float = 1.5,
    is_warmed_up: bool = True,
) -> FeatureVector:
    return FeatureVector(
        instrument_id=bar.instrument_id,
        symbol=bar.symbol,
        timestamp=bar.timestamp,
        feature_set_version=FS_V1_VERSION,
        features={
            "ret_1": ret_1,
            "ret_3": 0.01,
            "ret_6": 0.015,
            "sma_9": 2010.0,
            "sma_21": 1970.0,
            "sma_ratio_9_21": sma_ratio,
            "rsi_14": rsi_14,
            "atr_14": 15.0,
            "natr_14": 0.0075,
            "vwap_approx_distance": vwap_dist,
            "causal_rel_vol": rel_vol,
            "turnover_proxy_5m": 20000000.0,
        },
        is_fully_warmed_up=is_warmed_up,
        bar_count_in_session=25,
        mode=bar.mode,
    )


def test_simple_strategy_generates_valid_proposal_when_all_conditions_met() -> None:
    strategy = PredeclaredSimpleStrategy()
    ts = datetime(2026, 1, 5, 10, 30, tzinfo=IST)
    bar = make_test_bar(ts, close=Decimal("2000.0000"))
    f_vec = make_feature_vector(bar)

    proposal = strategy.evaluate_candle(bar, f_vec, current_equity=Decimal("30000.00"))
    assert proposal is not None
    assert proposal.symbol == "RELIANCE"
    assert proposal.instrument_id == 101
    assert proposal.entry_price == Decimal("2000.0000")
    # Stop loss: 2000 * 0.985 = 1970.00
    assert proposal.stop_loss == Decimal("1970.0000")
    # Target price: 2000 * 1.030 = 2060.00
    assert proposal.target_price == Decimal("2060.0000")
    assert proposal.policy_version == "TP-V1"
    assert proposal.side == OrderSide.BUY
    # 1% risk on 30k = 300. Risk per share = 30. Shares = 300 / 30 = 10.
    # 50% max exposure = 15000 / 2000 = 7.
    # Quantity = min(10, 7) = 7.
    assert proposal.quantity == 7
    assert proposal.earliest_entry_timestamp == bar.timestamp + timedelta(minutes=5)


def test_simple_strategy_rejects_incomplete_warmup() -> None:
    strategy = PredeclaredSimpleStrategy()
    ts = datetime(2026, 1, 5, 9, 30, tzinfo=IST)
    bar = make_test_bar(ts)
    f_vec = make_feature_vector(bar, is_warmed_up=False)

    proposal = strategy.evaluate_candle(bar, f_vec)
    assert proposal is None


def test_simple_strategy_rejects_at_or_after_1500_session_cutoff() -> None:
    strategy = PredeclaredSimpleStrategy()
    ts_cutoff = datetime(2026, 1, 5, 15, 0, tzinfo=IST)
    bar_cutoff = make_test_bar(ts_cutoff)
    f_vec_cutoff = make_feature_vector(bar_cutoff)

    assert strategy.evaluate_candle(bar_cutoff, f_vec_cutoff) is None

    ts_late = datetime(2026, 1, 5, 15, 15, tzinfo=IST)
    bar_late = make_test_bar(ts_late)
    f_vec_late = make_feature_vector(bar_late)

    assert strategy.evaluate_candle(bar_late, f_vec_late) is None


def test_simple_strategy_rejects_when_trend_condition_fails() -> None:
    strategy = PredeclaredSimpleStrategy()
    ts = datetime(2026, 1, 5, 11, 0, tzinfo=IST)
    bar = make_test_bar(ts)
    # Downtrend: sma_ratio <= 0
    f_vec = make_feature_vector(bar, sma_ratio=-0.01)

    assert strategy.evaluate_candle(bar, f_vec) is None


def test_simple_strategy_rejects_when_vwap_condition_fails() -> None:
    strategy = PredeclaredSimpleStrategy()
    ts = datetime(2026, 1, 5, 11, 0, tzinfo=IST)
    bar = make_test_bar(ts)
    # Below VWAP: vwap_dist <= 0
    f_vec = make_feature_vector(bar, vwap_dist=-0.005)

    assert strategy.evaluate_candle(bar, f_vec) is None


def test_simple_strategy_rejects_when_momentum_or_rsi_fails() -> None:
    strategy = PredeclaredSimpleStrategy()
    ts = datetime(2026, 1, 5, 11, 0, tzinfo=IST)
    bar = make_test_bar(ts)

    # Negative 1-bar return: ret_1 <= 0
    f_vec_neg_ret = make_feature_vector(bar, ret_1=-0.002)
    assert strategy.evaluate_candle(bar, f_vec_neg_ret) is None

    # Bearish RSI: rsi <= 50
    f_vec_low_rsi = make_feature_vector(bar, rsi_14=45.0)
    assert strategy.evaluate_candle(bar, f_vec_low_rsi) is None

    # Overbought RSI: rsi > 70
    f_vec_high_rsi = make_feature_vector(bar, rsi_14=75.0)
    assert strategy.evaluate_candle(bar, f_vec_high_rsi) is None


def test_simple_strategy_rejects_when_volume_condition_fails() -> None:
    strategy = PredeclaredSimpleStrategy()
    ts = datetime(2026, 1, 5, 11, 0, tzinfo=IST)
    bar = make_test_bar(ts)
    # Below average volume: rel_vol < 1.0
    f_vec = make_feature_vector(bar, rel_vol=0.8)

    assert strategy.evaluate_candle(bar, f_vec) is None
