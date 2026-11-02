"""Adversarial and future-leakage verification tests for the feature pipeline (Layer 5).

Governed by:
- DATA_AND_PERFORMANCE_POLICY.md §2 (Point-in-Time Correctness)
- ARCHITECTURE.md §2 (Feature Pipeline)
- Layer 5 Acceptance Gate: Future-leakage tests and determinism.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from finpilot.features.definitions import FS_V1_VERSION
from finpilot.features.pipeline import CausalFeaturePipeline
from finpilot.schemas.candles import CandleBar
from finpilot.schemas.errors import DomainValidationError

IST = ZoneInfo("Asia/Kolkata")


def generate_session_bars(
    symbol: str,
    day_offset: int = 0,
    base_price: float = 2500.0,
    seed: int = 42,
) -> list[CandleBar]:
    """Generate a full regular NSE session of 75 5-minute bars (09:15 to 15:25 IST opening)."""
    rng = random.Random(seed)  # noqa: S311
    bars: list[CandleBar] = []
    # 2026-11-02 is a Monday
    start_time = datetime(2026, 11, 2 + day_offset, 9, 15, tzinfo=IST)
    current_price = base_price

    for i in range(75):
        bar_time = start_time + timedelta(minutes=5 * i)
        step = rng.uniform(-5.0, 5.0)
        open_p = current_price
        close_p = max(10.0, open_p + step)
        high_p = max(open_p, close_p) + rng.uniform(0.5, 3.0)
        low_p = min(open_p, close_p) - rng.uniform(0.5, 3.0)
        vol = rng.randint(500, 5000)
        current_price = close_p

        bars.append(
            CandleBar(
                symbol=symbol,
                timestamp=bar_time,
                open=Decimal(f"{open_p:.2f}"),
                high=Decimal(f"{high_p:.2f}"),
                low=Decimal(f"{low_p:.2f}"),
                close=Decimal(f"{close_p:.2f}"),
                volume=vol,
                interval="5m",
                is_completed=True,
            )
        )
    return bars


def test_future_candle_mutation_does_not_affect_earlier_features() -> None:
    """CRITICAL CAUSAL TEST: Mutating future bars must NEVER change prior features."""
    pipeline = CausalFeaturePipeline(feature_set_version=FS_V1_VERSION)
    bars = generate_session_bars("RELIANCE", day_offset=0, seed=101)

    # 1. Compute features for the first 35 bars
    cutoff = 35
    early_vectors = pipeline.compute_features(bars[:cutoff], instrument_id=1)
    assert len(early_vectors) == cutoff

    # 2. Mutate bars from index 35 onwards with extreme price spikes and volume
    mutated_bars = list(bars)
    for i in range(cutoff, len(mutated_bars)):
        orig = mutated_bars[i]
        mutated_bars[i] = CandleBar(
            symbol=orig.symbol,
            timestamp=orig.timestamp,
            open=orig.open * Decimal("3.0"),
            high=orig.high * Decimal("5.0"),
            low=orig.low * Decimal("2.0"),
            close=orig.close * Decimal("4.0"),
            volume=orig.volume * 50,
            interval="5m",
            is_completed=True,
        )

    # 3. Compute features for the full mutated stream
    full_vectors = pipeline.compute_features(mutated_bars, instrument_id=1)
    assert len(full_vectors) == len(mutated_bars)

    # 4. Assert that vectors 0..cutoff-1 match bit-for-bit
    for idx in range(cutoff):
        v_early = early_vectors[idx]
        v_full = full_vectors[idx]
        assert v_early.timestamp == v_full.timestamp
        assert v_early.bar_count_in_session == v_full.bar_count_in_session
        assert v_early.is_fully_warmed_up == v_full.is_fully_warmed_up

        for fname, early_val in v_early.features.items():
            full_val = v_full.features[fname]
            if early_val is None:
                assert full_val is None, f"Feature {fname} at idx {idx} expected None"
            else:
                assert full_val == pytest.approx(early_val, rel=1e-9), (
                    f"Leakage detected! Feature {fname} at bar {idx} changed after "
                    f"mutating future bars. Original: {early_val}, After mutation: {full_val}"
                )


def test_future_candle_addition_does_not_affect_prior_features() -> None:
    """Appending future sessions or bars must not alter features computed on earlier bars."""
    pipeline = CausalFeaturePipeline()
    day1_bars = generate_session_bars("TCS", day_offset=0, seed=201)
    day2_bars = generate_session_bars("TCS", day_offset=1, seed=202)

    # Compute on Day 1 only
    day1_only_vectors = pipeline.compute_features(day1_bars, instrument_id=2)

    # Compute on Day 1 + Day 2 combined
    combined_vectors = pipeline.compute_features(day1_bars + day2_bars, instrument_id=2)

    # Verify Day 1 features in combined run match day1_only_vectors exactly
    assert len(combined_vectors) == 150
    for idx in range(len(day1_bars)):
        v_orig = day1_only_vectors[idx]
        v_comb = combined_vectors[idx]
        for fname, val in v_orig.features.items():
            if val is None:
                assert v_comb.features[fname] is None
            else:
                assert v_comb.features[fname] == pytest.approx(val, rel=1e-9)


def test_session_boundary_intraday_vwap_reset() -> None:
    """Intraday session VWAP must strictly reset to session start at 09:15 IST."""
    pipeline = CausalFeaturePipeline()
    day1_bars = generate_session_bars("INFY", day_offset=0, base_price=1500.0, seed=301)
    day2_bars = generate_session_bars("INFY", day_offset=1, base_price=1600.0, seed=302)

    vectors = pipeline.compute_features(day1_bars + day2_bars, instrument_id=3)

    # Day 1 final bar index is 74
    v_day1_last = vectors[74]
    assert v_day1_last.bar_count_in_session == 74

    # Day 2 first bar index resets to 0
    v_day2_first = vectors[75]
    assert v_day2_first.bar_count_in_session == 0

    # At bar index 0 of Day 2, session VWAP approximation is based ONLY on Day 2 bar 0 typical price
    bar_d2_0 = day2_bars[0]
    tp_d2_0 = float(bar_d2_0.high + bar_d2_0.low + bar_d2_0.close) / 3.0
    c_d2_0 = float(bar_d2_0.close)
    expected_dist = (c_d2_0 - tp_d2_0) / tp_d2_0

    actual_dist = v_day2_first.features["vwap_approx_distance"]
    assert actual_dist is not None
    assert actual_dist == pytest.approx(expected_dist, rel=1e-6)


def test_causal_relative_volume_never_uses_full_day_volume() -> None:
    """Morning relative volume must NOT depend on afternoon volume of the same day."""
    pipeline = CausalFeaturePipeline()
    bars = generate_session_bars("SBIN", day_offset=0, seed=401)

    # Baseline features
    vectors_baseline = pipeline.compute_features(bars, instrument_id=4)
    morning_rel_vol = vectors_baseline[15].features["causal_rel_vol"]  # ~10:30 AM bar

    # Mutate the afternoon bar at 14:00 (index 57) with 1,000,000x volume
    bars_mutated = list(bars)
    orig_afternoon = bars_mutated[57]
    bars_mutated[57] = CandleBar(
        symbol=orig_afternoon.symbol,
        timestamp=orig_afternoon.timestamp,
        open=orig_afternoon.open,
        high=orig_afternoon.high,
        low=orig_afternoon.low,
        close=orig_afternoon.close,
        volume=orig_afternoon.volume * 1000000,
        interval="5m",
        is_completed=True,
    )

    vectors_mutated = pipeline.compute_features(bars_mutated, instrument_id=4)
    morning_rel_vol_after_leak_attempt = vectors_mutated[15].features["causal_rel_vol"]

    assert morning_rel_vol is not None
    assert morning_rel_vol == morning_rel_vol_after_leak_attempt


def test_shuffling_input_order_handled_deterministically_or_rejected() -> None:
    bars = generate_session_bars("WIPRO", day_offset=0, seed=501)
    shuffled_bars = list(bars)
    random.Random(999).shuffle(shuffled_bars)  # noqa: S311

    # 1. Deterministic sorting when require_sorted_input=False (default)
    pipeline_sort = CausalFeaturePipeline(require_sorted_input=False)
    v_sorted = pipeline_sort.compute_features(bars, instrument_id=5)
    v_shuffled = pipeline_sort.compute_features(shuffled_bars, instrument_id=5)

    assert len(v_sorted) == len(v_shuffled)
    for vs, vsh in zip(v_sorted, v_shuffled, strict=True):
        assert vs.timestamp == vsh.timestamp
        assert vs.features == vsh.features

    # 2. Strict rejection when require_sorted_input=True
    pipeline_strict = CausalFeaturePipeline(require_sorted_input=True)
    with pytest.raises(DomainValidationError) as exc:
        pipeline_strict.compute_features(shuffled_bars, instrument_id=5)
    assert "Unsorted bar stream" in str(exc.value)


def test_uncompleted_bar_rejected() -> None:
    # 1. CandleBar schema rejects uncompleted bars
    with pytest.raises(Exception) as exc_candle:
        CandleBar(
            symbol="HCLTECH",
            timestamp=datetime(2026, 11, 2, 9, 15, tzinfo=IST),
            open=Decimal("1500.0"),
            high=Decimal("1510.0"),
            low=Decimal("1495.0"),
            close=Decimal("1505.0"),
            volume=1000,
            is_completed=False,
        )
    assert "Incomplete candle rejected" in str(exc_candle.value)

    # 2. Pipeline directly guards against uncompleted bars
    class IncompleteBarStub:
        symbol = "HCLTECH"
        timestamp = datetime(2026, 11, 2, 9, 15, tzinfo=IST)
        open = Decimal("1500.0")
        high = Decimal("1510.0")
        low = Decimal("1495.0")
        close = Decimal("1505.0")
        volume = 1000
        is_completed = False

    pipeline = CausalFeaturePipeline()
    with pytest.raises(DomainValidationError) as exc_pipe:
        pipeline.compute_features([IncompleteBarStub()], instrument_id=6)  # type: ignore[list-item]
    assert "not completed" in str(exc_pipe.value)


def test_warmup_insufficient_history_behavior() -> None:
    pipeline = CausalFeaturePipeline()
    bars = generate_session_bars("TATAMOTORS", day_offset=0, seed=701)
    vectors = pipeline.compute_features(bars, instrument_id=7)

    # Bar 0: zero history -> multi-period indicators are None
    v0 = vectors[0]
    assert v0.features["ret_1"] is None
    assert v0.features["ret_3"] is None
    assert v0.features["sma_9"] is None
    assert v0.features["sma_21"] is None
    assert v0.features["rsi_14"] is None
    assert v0.features["atr_14"] is None
    assert v0.features["causal_rel_vol"] is None
    assert v0.features["turnover_proxy_5m"] is not None
    assert v0.is_fully_warmed_up is False

    # Bar 20 (21st bar): 21 SMA and all 12 indicators are warmed up
    v20 = vectors[20]
    assert v20.features["sma_21"] is not None
    assert v20.features["sma_ratio_9_21"] is not None
    assert v20.features["rsi_14"] is not None
    assert v20.features["atr_14"] is not None
    assert v20.features["causal_rel_vol"] is not None
    assert v20.is_fully_warmed_up is True
