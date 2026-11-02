"""Unit and negative tests for session-aware 5-minute bar aggregator (Layer 5)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from finpilot.features.aggregator import SessionAwareBarAggregator, SourceBar
from finpilot.schemas.errors import DomainValidationError

IST = ZoneInfo("Asia/Kolkata")


def make_1m_bar(
    symbol: str,
    hour: int,
    minute: int,
    open_p: float,
    high_p: float,
    low_p: float,
    close_p: float,
    vol: int,
    day_offset: int = 0,
) -> SourceBar:
    # 2026-11-02 is a Monday
    dt_ist = datetime(2026, 11, 2 + day_offset, hour, minute, tzinfo=IST)
    return SourceBar(
        symbol=symbol,
        timestamp=dt_ist,
        open=Decimal(str(open_p)),
        high=Decimal(str(high_p)),
        low=Decimal(str(low_p)),
        close=Decimal(str(close_p)),
        volume=vol,
    )


def test_aggregator_aggregates_5_1m_bars_into_one_5m_candle() -> None:
    aggregator = SessionAwareBarAggregator(min_bars_per_bucket=1)
    bars = [
        make_1m_bar("RELIANCE", 9, 15, 2500.0, 2510.0, 2495.0, 2505.0, 100),
        make_1m_bar("RELIANCE", 9, 16, 2505.0, 2515.0, 2502.0, 2512.0, 150),
        make_1m_bar("RELIANCE", 9, 17, 2512.0, 2520.0, 2508.0, 2510.0, 200),
        make_1m_bar("RELIANCE", 9, 18, 2510.0, 2514.0, 2505.0, 2508.0, 120),
        make_1m_bar("RELIANCE", 9, 19, 2508.0, 2511.0, 2500.0, 2502.0, 130),
    ]

    candles = aggregator.aggregate(bars)
    assert len(candles) == 1
    c = candles[0]
    assert c.symbol == "RELIANCE"
    # Open = first bar open (2500.0)
    assert c.open == Decimal("2500.0")
    # High = max high across 5 bars (2520.0)
    assert c.high == Decimal("2520.0")
    # Low = min low across 5 bars (2495.0)
    assert c.low == Decimal("2495.0")
    # Close = last bar close (2502.0)
    assert c.close == Decimal("2502.0")
    # Volume = sum(100, 150, 200, 120, 130) = 700
    assert c.volume == 700
    assert c.is_completed is True


def test_aggregator_rejects_out_of_session_bars() -> None:
    aggregator = SessionAwareBarAggregator()

    # Pre-market bar (09:10 IST)
    early_bar = make_1m_bar("TCS", 9, 10, 3500.0, 3505.0, 3495.0, 3500.0, 50)
    with pytest.raises(DomainValidationError) as exc:
        aggregator.aggregate([early_bar])
    assert "outside regular NSE session" in str(exc.value)

    # Post-market bar (15:31 IST)
    late_bar = make_1m_bar("TCS", 15, 31, 3500.0, 3505.0, 3495.0, 3500.0, 50)
    with pytest.raises(DomainValidationError) as exc2:
        aggregator.aggregate([late_bar])
    assert "outside regular NSE session" in str(exc2.value)


def test_aggregator_rejects_weekend_bars() -> None:
    aggregator = SessionAwareBarAggregator()
    # 2026-11-07 is a Saturday
    sat_dt = datetime(2026, 11, 7, 10, 0, tzinfo=IST)
    sat_bar = SourceBar(
        symbol="INFY",
        timestamp=sat_dt,
        open=Decimal("1800.0"),
        high=Decimal("1810.0"),
        low=Decimal("1790.0"),
        close=Decimal("1805.0"),
        volume=500,
    )
    with pytest.raises(DomainValidationError) as exc:
        aggregator.aggregate([sat_bar])
    assert "weekend" in str(exc.value)


def test_aggregator_sorts_shuffled_bars_deterministically() -> None:
    aggregator = SessionAwareBarAggregator()
    bars = [
        make_1m_bar("HDFCBANK", 9, 18, 1600.0, 1605.0, 1598.0, 1602.0, 100),
        make_1m_bar("HDFCBANK", 9, 15, 1590.0, 1600.0, 1585.0, 1595.0, 120),
        make_1m_bar("HDFCBANK", 9, 17, 1597.0, 1602.0, 1595.0, 1600.0, 110),
        make_1m_bar("HDFCBANK", 9, 19, 1602.0, 1608.0, 1600.0, 1607.0, 130),
        make_1m_bar("HDFCBANK", 9, 16, 1595.0, 1598.0, 1592.0, 1597.0, 90),
    ]

    # Shuffled input
    candles_shuffled = aggregator.aggregate(bars, sort_if_unsorted=True)
    # Sorted input
    bars_sorted = sorted(bars, key=lambda b: b.timestamp)
    candles_sorted = aggregator.aggregate(bars_sorted, sort_if_unsorted=True)

    assert len(candles_shuffled) == 1
    assert candles_shuffled[0].open == candles_sorted[0].open
    assert candles_shuffled[0].high == candles_sorted[0].high
    assert candles_shuffled[0].low == candles_sorted[0].low
    assert candles_shuffled[0].close == candles_sorted[0].close
    assert candles_shuffled[0].volume == candles_sorted[0].volume


def test_aggregator_rejects_mixed_symbols() -> None:
    aggregator = SessionAwareBarAggregator()
    bars = [
        make_1m_bar("INFY", 9, 15, 1800.0, 1805.0, 1795.0, 1800.0, 100),
        make_1m_bar("TCS", 9, 16, 3500.0, 3510.0, 3495.0, 3505.0, 100),
    ]
    with pytest.raises(DomainValidationError) as exc:
        aggregator.aggregate(bars)
    assert "mixed symbols" in str(exc.value)
