"""Session-aware 5-minute bar aggregation from source bars (Layer 5).

Governed by:
- DATA_AND_PERFORMANCE_POLICY.md §1, §2 (Session Alignment & Decision Granularity)
- ARCHITECTURE.md §2 (Market Data Aggregation)
- Layer 5 Gate: Session-aware five-minute aggregation without cross-session leakage.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from finpilot.db.enums import CurrencyCode, DataMode, ExchangeCode
from finpilot.schemas.candles import CandleBar, normalize_to_utc
from finpilot.schemas.errors import DomainValidationError, ErrorCode

IST = ZoneInfo("Asia/Kolkata")
NSE_SESSION_OPEN = time(9, 15)
NSE_SESSION_CLOSE = time(15, 30)


@dataclass(frozen=True)
class SourceBar:
    """A raw sub-session source bar (e.g. 1-minute bar)."""

    symbol: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    exchange: ExchangeCode = ExchangeCode.NSE
    currency: CurrencyCode = CurrencyCode.INR
    mode: DataMode = DataMode.HISTORICAL_REPLAY


class SessionAwareBarAggregator:
    """Aggregates sub-session source bars into completed 5-minute NSE session bars.

    Enforces:
    - Rejection or chronological sorting of input bars.
    - Rejection of out-of-session (before 09:15, after 15:30 IST) or weekend bars.
    - Exact 5-minute bucket alignment: [09:15, 09:20), [09:20, 09:25), ..., [15:25, 15:30).
    - Session boundaries: Each session day produces up to 75 5-minute bars.
    """

    def __init__(
        self,
        min_bars_per_bucket: int = 1,
        expected_source_granularity_seconds: int = 60,
    ) -> None:
        self.min_bars_per_bucket = min_bars_per_bucket
        self.expected_source_granularity_seconds = expected_source_granularity_seconds

    def _get_5m_bucket_start(self, dt: datetime) -> datetime:
        """Calculate the 5-minute bucket starting boundary for a timestamp in IST."""
        ist_dt = dt.astimezone(IST)
        minute = ist_dt.minute - (ist_dt.minute % 5)
        bucket_ist = ist_dt.replace(minute=minute, second=0, microsecond=0)
        return bucket_ist.astimezone(ZoneInfo("UTC"))

    def aggregate(
        self,
        bars: list[SourceBar],
        sort_if_unsorted: bool = True,
    ) -> list[CandleBar]:
        """Aggregate a list of sub-session source bars into completed 5-minute CandleBars.

        Returns a list of validated, completed 5-minute CandleBar instances.
        """
        if not bars:
            return []

        # Validate symbol consistency
        symbol = bars[0].symbol
        for b in bars:
            if b.symbol != symbol:
                raise DomainValidationError(
                    f"Aggregator received mixed symbols: {symbol!r} and {b.symbol!r}",
                    field="symbol",
                    code=ErrorCode.INVALID_INSTRUMENT,
                )

        # Check and normalize timestamps
        processed_bars: list[SourceBar] = []
        for b in bars:
            utc_ts = normalize_to_utc(b.timestamp)
            ist_ts = utc_ts.astimezone(IST)

            # Check weekend
            if ist_ts.weekday() >= 5:
                raise DomainValidationError(
                    f"Bar timestamp falls on a weekend: {ist_ts.isoformat()}",
                    field="timestamp",
                    code=ErrorCode.INVALID_CANDLE,
                )

            # Check NSE market hours (09:15 to 15:30 IST)
            t = ist_ts.time()
            if t < NSE_SESSION_OPEN or t >= NSE_SESSION_CLOSE:
                raise DomainValidationError(
                    f"Bar timestamp is outside regular NSE session: {ist_ts.isoformat()}",
                    field="timestamp",
                    code=ErrorCode.INVALID_CANDLE,
                )

            processed_bars.append(
                SourceBar(
                    symbol=b.symbol,
                    timestamp=utc_ts,
                    open=b.open,
                    high=b.high,
                    low=b.low,
                    close=b.close,
                    volume=b.volume,
                    exchange=b.exchange,
                    currency=b.currency,
                    mode=b.mode,
                )
            )

        # Sort chronologically if requested
        if sort_if_unsorted:
            processed_bars.sort(key=lambda x: x.timestamp)
        else:
            for i in range(1, len(processed_bars)):
                if processed_bars[i].timestamp < processed_bars[i - 1].timestamp:
                    raise DomainValidationError(
                        f"Unsorted bars provided at index {i}",
                        field="timestamp",
                        code=ErrorCode.INVALID_CANDLE,
                    )

        # Group bars into 5-minute buckets
        buckets: dict[datetime, list[SourceBar]] = {}
        for b in processed_bars:
            bucket_start = self._get_5m_bucket_start(b.timestamp)
            if bucket_start not in buckets:
                buckets[bucket_start] = []
            buckets[bucket_start].append(b)

        # Aggregate buckets
        candle_bars: list[CandleBar] = []
        sorted_bucket_starts = sorted(buckets.keys())

        for b_start in sorted_bucket_starts:
            bucket_bars = buckets[b_start]
            if len(bucket_bars) < self.min_bars_per_bucket:
                continue

            open_price = bucket_bars[0].open
            high_price = max(b.high for b in bucket_bars)
            low_price = min(b.low for b in bucket_bars)
            close_price = bucket_bars[-1].close
            volume = sum(b.volume for b in bucket_bars)

            candle_bars.append(
                CandleBar(
                    symbol=symbol,
                    timestamp=b_start,
                    open=open_price,
                    high=high_price,
                    low=low_price,
                    close=close_price,
                    volume=volume,
                    interval="5m",
                    exchange=bucket_bars[0].exchange,
                    mode=bucket_bars[0].mode,
                    is_completed=True,
                )
            )

        return candle_bars
