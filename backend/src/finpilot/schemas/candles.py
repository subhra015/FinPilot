"""OHLCV completed candle schemas and validation contracts (Layer 3).

Enforces:
- 5-minute interval completion.
- Timezone awareness (normalized internally to UTC).
- Regular NSE session hours (09:15 to 15:30 IST) and trading days (Mon-Fri).
- Positive finite prices; High >= max(Open, Close, Low); Low <= min(Open, Close, High).
- Nonnegative volume; rejection of NaN/Infinity.
"""

from __future__ import annotations

import math
from datetime import datetime, time
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from finpilot.db.enums import DataMode, ExchangeCode

from .common import normalize_to_utc
from .errors import DomainValidationError, ErrorCode

IST = ZoneInfo("Asia/Kolkata")
NSE_OPEN = time(9, 15)
NSE_CLOSE = time(15, 30)
NSE_LAST_5M_OPEN = time(15, 25)  # The final 5m bar in the regular session opens at 15:25


class CandleBar(BaseModel):
    """A validated 5-minute OHLCV candle bar for NSE cash equity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str = Field(..., min_length=1, max_length=20, description="NSE Trading symbol")
    timestamp: datetime = Field(
        ...,
        description="Bar opening timestamp, normalized to UTC internally",
    )
    open: Decimal = Field(..., description="Opening price (> 0, finite)")
    high: Decimal = Field(..., description="Highest price (>= max(open, close, low))")
    low: Decimal = Field(..., description="Lowest price (<= min(open, close, high))")
    close: Decimal = Field(..., description="Closing price (> 0, finite)")
    volume: int = Field(..., ge=0, description="Traded volume (>= 0)")
    interval: str = Field(default="5m", description="Bar interval (fixed to 5m for V1)")
    exchange: ExchangeCode = Field(default=ExchangeCode.NSE)
    mode: DataMode = Field(default=DataMode.HISTORICAL_REPLAY)
    is_completed: bool = Field(
        default=True,
        description="Completed-bar flag; trade policy only acts on completed bars",
    )

    @field_validator("timestamp", mode="before")
    @classmethod
    def validate_and_normalize_timestamp(cls, v: Any) -> datetime:
        utc_dt = normalize_to_utc(v)
        ist_dt = utc_dt.astimezone(IST)

        # 1. Check 5-minute boundary alignment (00, 05, ..., 55 minutes, 00 seconds)
        if ist_dt.second != 0 or ist_dt.microsecond != 0 or ist_dt.minute % 5 != 0:
            raise DomainValidationError(
                f"Candle timestamp {ist_dt.isoformat()} is not aligned to a 5-minute boundary.",
                field="timestamp",
                code=ErrorCode.INVALID_CANDLE,
            )

        # 2. Check market trading days (Mon-Fri)
        if ist_dt.weekday() >= 5:
            day_name = "Saturday" if ist_dt.weekday() == 5 else "Sunday"
            raise DomainValidationError(
                f"Candle timestamp falls outside regular NSE trading days ({day_name}): "
                f"{ist_dt.date()}.",
                field="timestamp",
                code=ErrorCode.INVALID_CANDLE,
            )

        # 3. Check market trading session hours (09:15 to 15:30 IST)
        t = ist_dt.time()
        if t < NSE_OPEN or t > NSE_LAST_5M_OPEN:
            raise DomainValidationError(
                f"Candle time {t.isoformat()} is outside regular NSE session "
                "(09:15-15:30 IST; last 5m bar starts at 15:25).",
                field="timestamp",
                code=ErrorCode.INVALID_CANDLE,
            )

        return utc_dt

    @field_validator("open", "high", "low", "close", mode="before")
    @classmethod
    def check_finite_positive_price(cls, v: Any) -> Decimal:
        if v is None:
            raise DomainValidationError("Price cannot be None.", code=ErrorCode.INVALID_CANDLE)
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            raise DomainValidationError(
                "Price cannot be NaN or Infinite.", code=ErrorCode.INVALID_CANDLE
            )
        try:
            d = Decimal(str(v))
        except Exception as exc:
            raise DomainValidationError(
                f"Cannot parse price as decimal: {v!r}", code=ErrorCode.INVALID_CANDLE
            ) from exc

        if d.is_nan() or d.is_infinite():
            raise DomainValidationError(
                "Price cannot be NaN or Infinite.", code=ErrorCode.INVALID_CANDLE
            )
        if d <= Decimal("0"):
            raise DomainValidationError(
                f"Price must be strictly positive (> 0); got {d}.", code=ErrorCode.INVALID_CANDLE
            )
        return d

    @field_validator("volume", mode="before")
    @classmethod
    def check_nonnegative_volume(cls, v: Any) -> int:
        if v is None:
            raise DomainValidationError("Volume cannot be None.", code=ErrorCode.INVALID_CANDLE)
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            raise DomainValidationError(
                "Volume cannot be NaN or Infinite.", code=ErrorCode.INVALID_CANDLE
            )
        try:
            vol = int(v)
        except Exception as exc:
            raise DomainValidationError(
                f"Cannot parse volume as integer: {v!r}", code=ErrorCode.INVALID_CANDLE
            ) from exc

        if vol < 0:
            raise DomainValidationError(
                f"Volume must be non-negative (>= 0); got {vol}.", code=ErrorCode.INVALID_CANDLE
            )
        return vol

    @model_validator(mode="after")
    def validate_ohlc_relationships_and_completion(self) -> CandleBar:
        # High must be >= max(open, close, low)
        if self.high < self.open or self.high < self.close or self.high < self.low:
            raise DomainValidationError(
                f"OHLC inconsistency: High ({self.high}) must be >= "
                f"max(Open={self.open}, Close={self.close}, Low={self.low}).",
                field="high",
                code=ErrorCode.INVALID_CANDLE,
            )

        # Low must be <= min(open, close, high)
        if self.low > self.open or self.low > self.close or self.low > self.high:
            raise DomainValidationError(
                f"OHLC inconsistency: Low ({self.low}) must be <= "
                f"min(Open={self.open}, Close={self.close}, High={self.high}).",
                field="low",
                code=ErrorCode.INVALID_CANDLE,
            )

        # Completed bar status: decisions require completed bars
        if not self.is_completed:
            raise DomainValidationError(
                "Incomplete candle rejected: research decisions use completed 5-minute bars only.",
                field="is_completed",
                code=ErrorCode.INVALID_CANDLE,
            )

        return self


class CandleBatch(BaseModel):
    """Bounded batch of candles for ingestion or replay."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candles: list[CandleBar] = Field(..., min_length=1, max_length=1000)
