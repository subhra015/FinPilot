"""Causal feature pipeline computing FS-V1 features from completed bars (Layer 5).

Governed by:
- DATA_AND_PERFORMANCE_POLICY.md §2 (Decision Granularity & Point-in-Time Correctness)
- ARCHITECTURE.md §2 (Feature Pipeline)
- Layer 5 Gate & Security Controls (SEC-06, SEC-19)
"""

from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo

from finpilot.data.models import MarketDataRecord
from finpilot.db.enums import DataMode
from finpilot.schemas.candles import CandleBar
from finpilot.schemas.common import normalize_to_utc
from finpilot.schemas.errors import DomainValidationError, ErrorCode

from .definitions import (
    FEATURE_CATALOG_V1,
    FS_V1_VERSION,
    TURNOVER_PROXY_DISCLOSURE,
    VOLUME_PROXY_DISCLOSURE,
    VWAP_PROXY_DISCLOSURE,
)
from .indicators import (
    calculate_atr,
    calculate_causal_relative_volume,
    calculate_return,
    calculate_rsi,
    calculate_sma,
    calculate_turnover_proxy,
    calculate_vwap_approx,
)
from .models import FeatureVector

IST = ZoneInfo("Asia/Kolkata")


class CausalFeaturePipeline:
    """Computes strictly causal, point-in-time features for completed 5-minute bars.

    Invariants:
    - Pure causal calculations: bar `t` uses only bars `<= t`.
    - Future bar modification does not alter past bar features.
    - Session isolation: intraday metrics (VWAP approximation, session bar index) reset at
      the start of each NSE session (09:15 IST).
    - Insufficient history / warm-up values are represented as `None`.
    - Mandatory proxy disclosures attached to metadata.
    """

    def __init__(
        self,
        feature_set_version: str = FS_V1_VERSION,
        require_sorted_input: bool = False,
    ) -> None:
        if feature_set_version != FS_V1_VERSION:
            raise DomainValidationError(
                f"Unsupported feature set version: {feature_set_version!r}. "
                f"Must be {FS_V1_VERSION}",
                field="feature_set_version",
                code=ErrorCode.VALIDATION_ERROR,
            )
        self.feature_set_version = feature_set_version
        self.require_sorted_input = require_sorted_input

    def compute_features(
        self,
        bars: list[CandleBar] | list[MarketDataRecord],
        instrument_id: int | None = None,
    ) -> list[FeatureVector]:
        """Compute chronological feature vectors from completed 5-minute bars."""
        if not bars:
            return []

        # Validate input sorting or sort deterministically
        normalized_bars = self._normalize_and_sort_bars(bars)

        # Determine stable instrument identity
        resolved_instrument_id = self._resolve_instrument_id(normalized_bars[0], instrument_id)
        symbol = normalized_bars[0].symbol

        feature_vectors: list[FeatureVector] = []

        # Historical rolling queues across sessions
        history_closes: list[float] = []
        history_highs: list[float] = []
        history_lows: list[float] = []
        history_volumes: list[int] = []

        # Session-specific state
        current_session_date: date | None = None
        session_bar_index = 0
        session_typical_prices: list[float] = []
        session_volumes: list[int] = []

        for bar in normalized_bars:
            is_completed = getattr(bar, "is_completed", True)
            if not is_completed:
                raise DomainValidationError(
                    f"Bar at {bar.timestamp.isoformat()} is not completed. "
                    "Features require completed bars only.",
                    field="is_completed",
                    code=ErrorCode.INVALID_CANDLE,
                )

            # Convert prices and volume
            c_val = float(bar.close)
            h_val = float(bar.high)
            l_val = float(bar.low)
            v_val = int(bar.volume)
            tp_val = (h_val + l_val + c_val) / 3.0

            # Session boundary tracking (IST date)
            bar_ist = bar.timestamp.astimezone(IST)
            bar_date = bar_ist.date()

            if current_session_date is None or bar_date != current_session_date:
                # New session: reset intraday session-bound accumulators
                current_session_date = bar_date
                session_bar_index = 0
                session_typical_prices = [tp_val]
                session_volumes = [v_val]
            else:
                session_bar_index += 1
                session_typical_prices.append(tp_val)
                session_volumes.append(v_val)

            # Update rolling queues (including current completed bar)
            history_closes.append(c_val)
            history_highs.append(h_val)
            history_lows.append(l_val)
            # For causal relative volume, we pass prior volumes strictly before current bar
            prior_volumes = list(history_volumes)
            history_volumes.append(v_val)

            # 1. Momentum / Returns
            ret_1 = calculate_return(history_closes, period=1)
            ret_3 = calculate_return(history_closes, period=3)
            ret_6 = calculate_return(history_closes, period=6)

            # 2. Moving Average Trend
            sma_9 = calculate_sma(history_closes, period=9)
            sma_21 = calculate_sma(history_closes, period=21)
            sma_ratio_9_21: float | None = None
            if sma_9 is not None and sma_21 is not None and sma_21 > 0.0:
                sma_ratio_9_21 = (sma_9 / sma_21) - 1.0

            # 3. RSI
            rsi_14 = calculate_rsi(history_closes, period=14)

            # 4. Volatility (ATR, NATR)
            atr_14 = calculate_atr(history_highs, history_lows, history_closes, period=14)
            natr_14: float | None = None
            if atr_14 is not None and c_val > 0.0:
                natr_14 = atr_14 / c_val

            # 5. Price Location: Intraday VWAP Approximation Distance
            # Strictly within current session!
            session_vwap = calculate_vwap_approx(session_typical_prices, session_volumes)
            vwap_approx_distance: float | None = None
            if session_vwap is not None and session_vwap > 0.0:
                vwap_approx_distance = (c_val - session_vwap) / session_vwap

            # 6. Causal Relative Volume
            causal_rel_vol = calculate_causal_relative_volume(
                current_volume=v_val,
                prior_volumes=prior_volumes,
                window=10,
            )

            # 7. Liquidity: Turnover Proxy
            turnover_proxy_5m = calculate_turnover_proxy(c_val, v_val)

            # Assemble features dictionary
            features_dict: dict[str, float | None] = {
                "ret_1": ret_1,
                "ret_3": ret_3,
                "ret_6": ret_6,
                "sma_9": sma_9,
                "sma_21": sma_21,
                "sma_ratio_9_21": sma_ratio_9_21,
                "rsi_14": rsi_14,
                "atr_14": atr_14,
                "natr_14": natr_14,
                "vwap_approx_distance": vwap_approx_distance,
                "causal_rel_vol": causal_rel_vol,
                "turnover_proxy_5m": turnover_proxy_5m,
            }

            # Check full warm-up (all 12 approved features present and not None)
            is_fully_warmed_up = all(
                features_dict.get(fname) is not None for fname in FEATURE_CATALOG_V1
            )

            # Determine mode
            mode = getattr(bar, "mode", DataMode.HISTORICAL_REPLAY)

            # Assemble vector
            vector = FeatureVector(
                instrument_id=resolved_instrument_id,
                symbol=symbol,
                timestamp=bar.timestamp,
                feature_set_version=self.feature_set_version,
                features=features_dict,
                is_fully_warmed_up=is_fully_warmed_up,
                mode=mode,
                bar_count_in_session=session_bar_index,
                metadata={
                    "vwap_disclosure": VWAP_PROXY_DISCLOSURE,
                    "volume_disclosure": VOLUME_PROXY_DISCLOSURE,
                    "turnover_disclosure": TURNOVER_PROXY_DISCLOSURE,
                },
            )
            feature_vectors.append(vector)

        return feature_vectors

    def _normalize_and_sort_bars(
        self,
        bars: list[CandleBar] | list[MarketDataRecord],
    ) -> list[CandleBar | MarketDataRecord]:
        """Normalize bar timestamps to UTC and check/enforce chronological ordering."""
        # Check ordering
        if self.require_sorted_input:
            for i in range(1, len(bars)):
                if bars[i].timestamp < bars[i - 1].timestamp:
                    raise DomainValidationError(
                        f"Unsorted bar stream at index {i}: {bars[i].timestamp.isoformat()} < "
                        f"{bars[i - 1].timestamp.isoformat()}",
                        field="timestamp",
                        code=ErrorCode.INVALID_CANDLE,
                    )
            return list(bars)

        # Sort deterministically by timestamp
        return sorted(bars, key=lambda b: normalize_to_utc(b.timestamp))

    def _resolve_instrument_id(
        self,
        first_bar: CandleBar | MarketDataRecord,
        override_id: int | None,
    ) -> int:
        if override_id is not None:
            return override_id
        if hasattr(first_bar, "instrument_id") and first_bar.instrument_id is not None:
            return int(first_bar.instrument_id)
        # Default placeholder if not supplied (must be positive int per schema)
        return 1
