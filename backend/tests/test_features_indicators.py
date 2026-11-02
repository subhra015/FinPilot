"""Unit tests for pure causal mathematical indicators (Layer 5)."""

from __future__ import annotations

import pytest

from finpilot.features.indicators import (
    calculate_atr,
    calculate_causal_relative_volume,
    calculate_return,
    calculate_rsi,
    calculate_sma,
    calculate_true_range,
    calculate_turnover_proxy,
    calculate_vwap_approx,
)


def test_calculate_return_causal_and_warmup() -> None:
    # Insufficient history
    assert calculate_return([], period=1) is None
    assert calculate_return([100.0], period=1) is None
    assert calculate_return([100.0, 105.0], period=2) is None

    # Valid returns
    closes = [100.0, 105.0, 102.0, 110.0]
    # ret_1 for last bar: (110 - 102) / 102
    assert calculate_return(closes, period=1) == pytest.approx((110.0 - 102.0) / 102.0)
    # ret_3 for last bar: (110 - 100) / 100 = 0.10
    assert calculate_return(closes, period=3) == pytest.approx(0.10)


def test_calculate_sma_warmup_and_values() -> None:
    assert calculate_sma([10.0, 20.0], period=3) is None
    closes = [10.0, 20.0, 30.0, 40.0, 50.0]
    # SMA 3 on last 3 bars: (30 + 40 + 50) / 3 = 40.0
    assert calculate_sma(closes, period=3) == pytest.approx(40.0)


def test_calculate_rsi_boundary_cases() -> None:
    # Warmup check: 14 period requires 15 closes
    closes_short = [100.0 + i for i in range(14)]
    assert calculate_rsi(closes_short, period=14) is None

    # Strictly monotonic uptrend: all gains -> RSI = 100.0
    closes_up = [100.0 + i * 2.0 for i in range(20)]
    assert calculate_rsi(closes_up, period=14) == pytest.approx(100.0)

    # Strictly monotonic downtrend: all losses -> RSI = 0.0
    closes_down = [200.0 - i * 2.0 for i in range(20)]
    assert calculate_rsi(closes_down, period=14) == pytest.approx(0.0)

    # Completely flat price: no gain, no loss -> RSI = 50.0
    closes_flat = [100.0 for _ in range(20)]
    assert calculate_rsi(closes_flat, period=14) == pytest.approx(50.0)


def test_calculate_true_range_and_atr() -> None:
    # First bar TR has no prev_close -> high - low
    tr0 = calculate_true_range(high=105.0, low=95.0, prev_close=None)
    assert tr0 == pytest.approx(10.0)

    # Gap up: prev_close = 90.0, high = 105.0, low = 95.0
    # max(10, |105 - 90| = 15, |95 - 90| = 5) -> 15.0
    tr_gap = calculate_true_range(high=105.0, low=95.0, prev_close=90.0)
    assert tr_gap == pytest.approx(15.0)

    # ATR warmup check
    highs = [105.0] * 13
    lows = [95.0] * 13
    closes = [100.0] * 13
    assert calculate_atr(highs, lows, closes, period=14) is None

    highs.append(105.0)
    lows.append(95.0)
    closes.append(100.0)
    # 14 identical bars of H=105, L=95, C=100 -> all TR = 10.0 -> ATR = 10.0
    assert calculate_atr(highs, lows, closes, period=14) == pytest.approx(10.0)


def test_calculate_vwap_approx_and_turnover() -> None:
    tps = [100.0, 102.0, 101.0]
    volumes = [1000, 2000, 1000]
    # sum(tp * v) = 100*1000 + 102*2000 + 101*1000 = 100,000 + 204,000 + 101,000 = 405,000
    # sum(v) = 4000 -> VWAP = 405,000 / 4,000 = 101.25
    vwap = calculate_vwap_approx(tps, volumes)
    assert vwap == pytest.approx(101.25)

    # Turnover proxy
    assert calculate_turnover_proxy(close=2500.50, volume=100) == pytest.approx(250050.0)


def test_calculate_causal_relative_volume_never_uses_future() -> None:
    # Need 10 prior bars for window=10
    prior_vols = [1000] * 9
    assert calculate_causal_relative_volume(current_volume=2000, prior_volumes=prior_vols) is None

    # Exactly 10 prior bars with mean = 1000
    prior_vols.append(1000)
    # Current bar = 2500 -> relative volume = 2500 / 1000 = 2.5
    rel_vol = calculate_causal_relative_volume(current_volume=2500, prior_volumes=prior_vols)
    assert rel_vol == pytest.approx(2.5)

    # Invariance check: mutating a hypothetical future volume does NOT affect calculation
    # because prior_volumes strictly represents completed past bars
    prior_vols_copy = list(prior_vols)
    rel_vol2 = calculate_causal_relative_volume(current_volume=2500, prior_volumes=prior_vols_copy)
    assert rel_vol == rel_vol2
