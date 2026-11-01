"""OHLCV completed candle schema and market session contract tests (Layer 3)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from finpilot.schemas import (
    CandleBar,
    CandleBatch,
    DomainValidationError,
)

IST = timezone(timedelta(hours=5, minutes=30))


def _valid_ts() -> datetime:
    # A regular trading day: Friday 2026-10-30 at 09:15 IST
    return datetime(2026, 10, 30, 9, 15, 0, tzinfo=IST)


def test_valid_5m_completed_candle_creation() -> None:
    candle = CandleBar(
        symbol="RELIANCE",
        timestamp=_valid_ts(),
        open=Decimal("2500.0000"),
        high=Decimal("2515.5000"),
        low=Decimal("2498.0000"),
        close=Decimal("2510.0000"),
        volume=15000,
        interval="5m",
        is_completed=True,
    )
    assert candle.symbol == "RELIANCE"
    assert candle.high >= candle.open
    assert candle.high >= candle.close
    assert candle.low <= candle.open
    assert candle.low <= candle.close
    # Timestamp normalized to UTC internally
    assert candle.timestamp.tzinfo == UTC


def test_ohlc_inconsistency_rejected() -> None:
    # High < Open rejected
    with pytest.raises((DomainValidationError, ValidationError)) as exc_high_open:
        CandleBar(
            symbol="RELIANCE",
            timestamp=_valid_ts(),
            open=Decimal("2520.0000"),
            high=Decimal("2510.0000"),  # < Open
            low=Decimal("2498.0000"),
            close=Decimal("2505.0000"),
            volume=1000,
        )
    assert "high" in str(exc_high_open.value).lower()

    # Low > Close rejected
    with pytest.raises((DomainValidationError, ValidationError)) as exc_low_close:
        CandleBar(
            symbol="RELIANCE",
            timestamp=_valid_ts(),
            open=Decimal("2500.0000"),
            high=Decimal("2515.0000"),
            low=Decimal("2510.0000"),  # > Close
            close=Decimal("2505.0000"),
            volume=1000,
        )
    assert "low" in str(exc_low_close.value).lower()


@pytest.mark.parametrize(
    "bad_price",
    [
        Decimal("0.0000"),
        Decimal("-10.0000"),
        float("nan"),
        float("inf"),
        float("-inf"),
    ],
)
def test_non_positive_or_infinite_prices_rejected(bad_price: object) -> None:
    with pytest.raises((DomainValidationError, ValidationError)):
        CandleBar(
            symbol="RELIANCE",
            timestamp=_valid_ts(),
            open=bad_price,  # type: ignore[arg-type]
            high=Decimal("2510.0000"),
            low=Decimal("2498.0000"),
            close=Decimal("2505.0000"),
            volume=1000,
        )


def test_negative_volume_rejected() -> None:
    with pytest.raises((DomainValidationError, ValidationError)) as exc:
        CandleBar(
            symbol="RELIANCE",
            timestamp=_valid_ts(),
            open=Decimal("2500.0000"),
            high=Decimal("2510.0000"),
            low=Decimal("2498.0000"),
            close=Decimal("2505.0000"),
            volume=-1,
        )
    assert "volume" in str(exc.value).lower()


def test_incomplete_candle_rejected_for_decision_use() -> None:
    with pytest.raises((DomainValidationError, ValidationError)) as exc:
        CandleBar(
            symbol="RELIANCE",
            timestamp=_valid_ts(),
            open=Decimal("2500.0000"),
            high=Decimal("2510.0000"),
            low=Decimal("2498.0000"),
            close=Decimal("2505.0000"),
            volume=1000,
            is_completed=False,  # Incomplete bar
        )
    assert "incomplete candle rejected" in str(exc.value).lower()


def test_unaligned_timestamps_rejected() -> None:
    # 09:17 IST (not divisible by 5)
    unaligned_minute = datetime(2026, 10, 30, 9, 17, 0, tzinfo=IST)
    with pytest.raises((DomainValidationError, ValidationError)) as exc_min:
        CandleBar(
            symbol="RELIANCE",
            timestamp=unaligned_minute,
            open=Decimal("2500.0000"),
            high=Decimal("2510.0000"),
            low=Decimal("2498.0000"),
            close=Decimal("2505.0000"),
            volume=1000,
        )
    assert "5-minute boundary" in str(exc_min.value).lower()

    # 09:15:30 IST (non-zero second)
    unaligned_sec = datetime(2026, 10, 30, 9, 15, 30, tzinfo=IST)
    with pytest.raises((DomainValidationError, ValidationError)) as exc_sec:
        CandleBar(
            symbol="RELIANCE",
            timestamp=unaligned_sec,
            open=Decimal("2500.0000"),
            high=Decimal("2510.0000"),
            low=Decimal("2498.0000"),
            close=Decimal("2505.0000"),
            volume=1000,
        )
    assert "5-minute boundary" in str(exc_sec.value).lower()


def test_out_of_session_and_weekend_timestamps_rejected() -> None:
    # Pre-market (08:30 IST)
    pre_market = datetime(2026, 10, 30, 8, 30, 0, tzinfo=IST)
    with pytest.raises((DomainValidationError, ValidationError)) as exc_pre:
        CandleBar(
            symbol="RELIANCE",
            timestamp=pre_market,
            open=Decimal("2500.0000"),
            high=Decimal("2510.0000"),
            low=Decimal("2498.0000"),
            close=Decimal("2505.0000"),
            volume=1000,
        )
    assert "outside regular nse session" in str(exc_pre.value).lower()

    # Post-market (15:30 IST candle open - session closes at 15:30)
    post_market = datetime(2026, 10, 30, 15, 30, 0, tzinfo=IST)
    with pytest.raises((DomainValidationError, ValidationError)) as exc_post:
        CandleBar(
            symbol="RELIANCE",
            timestamp=post_market,
            open=Decimal("2500.0000"),
            high=Decimal("2510.0000"),
            low=Decimal("2498.0000"),
            close=Decimal("2505.0000"),
            volume=1000,
        )
    assert "outside regular nse session" in str(exc_post.value).lower()

    # Weekend: Saturday 2026-10-31 09:15 IST
    saturday = datetime(2026, 10, 31, 9, 15, 0, tzinfo=IST)
    with pytest.raises((DomainValidationError, ValidationError)) as exc_wknd:
        CandleBar(
            symbol="RELIANCE",
            timestamp=saturday,
            open=Decimal("2500.0000"),
            high=Decimal("2510.0000"),
            low=Decimal("2498.0000"),
            close=Decimal("2505.0000"),
            volume=1000,
        )
    assert "outside regular nse trading days (saturday)" in str(exc_wknd.value).lower()


def test_candle_batch_bounds() -> None:
    candle = CandleBar(
        symbol="RELIANCE",
        timestamp=_valid_ts(),
        open=Decimal("2500.0000"),
        high=Decimal("2510.0000"),
        low=Decimal("2498.0000"),
        close=Decimal("2505.0000"),
        volume=1000,
    )
    batch = CandleBatch(candles=[candle])
    assert len(batch.candles) == 1

    # Empty batch rejected
    with pytest.raises(ValidationError):
        CandleBatch(candles=[])
