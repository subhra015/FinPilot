"""Feature definitions, metadata catalog, and proxy disclosures (Layer 5).

Governed by:
- DATA_AND_PERFORMANCE_POLICY.md §2 (Decision Granularity & Point-in-Time Correctness)
- ARCHITECTURE.md §2, §3 (Feature Pipeline)
- Layer 5 Gate & Research Specification (FS-V1)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

FS_V1_VERSION: Final[str] = "FS-V1"

# Documented proxy disclosures required by policy
VWAP_PROXY_DISCLOSURE: Final[str] = (
    "OHLCV typical-price cumulative session approximation ((H+L+C)/3 * V). "
    "NOT an observed trade-level execution VWAP from tick data."
)

VOLUME_PROXY_DISCLOSURE: Final[str] = (
    "Rolling prior-period relative volume ratio. "
    "Does NOT represent observed order-book depth or queue position."
)

TURNOVER_PROXY_DISCLOSURE: Final[str] = (
    "Bar turnover proxy derived from close * volume in INR. "
    "Does NOT reflect tick-level trade value distribution, bid-ask spread, or queue position."
)


class FeatureCategory(StrEnum):
    """Semantic category of features."""

    MOMENTUM = "MOMENTUM"
    TREND = "TREND"
    VOLATILITY = "VOLATILITY"
    VOLUME = "VOLUME"
    LIQUIDITY = "LIQUIDITY"
    PRICE_LOCATION = "PRICE_LOCATION"


@dataclass(frozen=True)
class FeatureDefinition:
    """Catalog definition and causal specification for an individual feature."""

    name: str
    category: FeatureCategory
    description: str
    warmup_bars: int
    cross_session_allowed: bool
    is_proxy: bool
    proxy_disclosure: str | None
    min_value: float | None
    max_value: float | None
    units: str


# Catalog of all approved features in Feature Set V1 (FS-V1)
FEATURE_CATALOG_V1: Final[dict[str, FeatureDefinition]] = {
    "ret_1": FeatureDefinition(
        name="ret_1",
        category=FeatureCategory.MOMENTUM,
        description="1-bar (5-minute) percentage price return",
        warmup_bars=1,
        cross_session_allowed=False,
        is_proxy=False,
        proxy_disclosure=None,
        min_value=-1.0,
        max_value=10.0,
        units="ratio",
    ),
    "ret_3": FeatureDefinition(
        name="ret_3",
        category=FeatureCategory.MOMENTUM,
        description="3-bar (15-minute) percentage price return",
        warmup_bars=3,
        cross_session_allowed=False,
        is_proxy=False,
        proxy_disclosure=None,
        min_value=-1.0,
        max_value=10.0,
        units="ratio",
    ),
    "ret_6": FeatureDefinition(
        name="ret_6",
        category=FeatureCategory.MOMENTUM,
        description="6-bar (30-minute) percentage price return",
        warmup_bars=6,
        cross_session_allowed=False,
        is_proxy=False,
        proxy_disclosure=None,
        min_value=-1.0,
        max_value=10.0,
        units="ratio",
    ),
    "sma_9": FeatureDefinition(
        name="sma_9",
        category=FeatureCategory.TREND,
        description="9-period (45-minute) Simple Moving Average of close price",
        warmup_bars=9,
        cross_session_allowed=True,
        is_proxy=False,
        proxy_disclosure=None,
        min_value=0.01,
        max_value=1000000.0,
        units="INR",
    ),
    "sma_21": FeatureDefinition(
        name="sma_21",
        category=FeatureCategory.TREND,
        description="21-period (105-minute) Simple Moving Average of close price",
        warmup_bars=21,
        cross_session_allowed=True,
        is_proxy=False,
        proxy_disclosure=None,
        min_value=0.01,
        max_value=1000000.0,
        units="INR",
    ),
    "sma_ratio_9_21": FeatureDefinition(
        name="sma_ratio_9_21",
        category=FeatureCategory.TREND,
        description="Moving average trend ratio (SMA_9 / SMA_21 - 1.0)",
        warmup_bars=21,
        cross_session_allowed=True,
        is_proxy=False,
        proxy_disclosure=None,
        min_value=-1.0,
        max_value=5.0,
        units="ratio",
    ),
    "rsi_14": FeatureDefinition(
        name="rsi_14",
        category=FeatureCategory.MOMENTUM,
        description="14-period Wilder's Relative Strength Index",
        warmup_bars=14,
        cross_session_allowed=True,
        is_proxy=False,
        proxy_disclosure=None,
        min_value=0.0,
        max_value=100.0,
        units="index",
    ),
    "atr_14": FeatureDefinition(
        name="atr_14",
        category=FeatureCategory.VOLATILITY,
        description="14-period Average True Range in price units",
        warmup_bars=14,
        cross_session_allowed=True,
        is_proxy=False,
        proxy_disclosure=None,
        min_value=0.0,
        max_value=100000.0,
        units="INR",
    ),
    "natr_14": FeatureDefinition(
        name="natr_14",
        category=FeatureCategory.VOLATILITY,
        description="14-period Normalized ATR (ATR_14 / Close)",
        warmup_bars=14,
        cross_session_allowed=True,
        is_proxy=False,
        proxy_disclosure=None,
        min_value=0.0,
        max_value=2.0,
        units="ratio",
    ),
    "vwap_approx_distance": FeatureDefinition(
        name="vwap_approx_distance",
        category=FeatureCategory.PRICE_LOCATION,
        description=(
            "Normalized distance of close price from intraday OHLCV-derived session VWAP "
            "approximation: (Close - VWAP) / VWAP"
        ),
        warmup_bars=1,
        cross_session_allowed=False,  # Strictly intraday session-bound; resets at session open
        is_proxy=True,
        proxy_disclosure=VWAP_PROXY_DISCLOSURE,
        min_value=-1.0,
        max_value=5.0,
        units="ratio",
    ),
    "causal_rel_vol": FeatureDefinition(
        name="causal_rel_vol",
        category=FeatureCategory.VOLUME,
        description=(
            "Causal relative volume: current bar volume divided by the rolling mean of prior 10 "
            "completed bars. Never uses eventual full-day volume."
        ),
        warmup_bars=10,
        cross_session_allowed=True,
        is_proxy=True,
        proxy_disclosure=VOLUME_PROXY_DISCLOSURE,
        min_value=0.0,
        max_value=1000.0,
        units="ratio",
    ),
    "turnover_proxy_5m": FeatureDefinition(
        name="turnover_proxy_5m",
        category=FeatureCategory.LIQUIDITY,
        description="5-minute bar traded value proxy (Close * Volume in INR)",
        warmup_bars=0,
        cross_session_allowed=False,
        is_proxy=True,
        proxy_disclosure=TURNOVER_PROXY_DISCLOSURE,
        min_value=0.0,
        max_value=1e12,
        units="INR",
    ),
}
