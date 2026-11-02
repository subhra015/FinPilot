"""Feature engineering and point-in-time universe package (Layer 5).

Governed by:
- DATA_AND_PERFORMANCE_POLICY.md §2 (Decision Granularity & Point-in-Time Correctness)
- ARCHITECTURE.md §2 (Feature Pipeline)
- Layer 5 Gate: Causal features and point-in-time universe.
"""

from __future__ import annotations

from .aggregator import SessionAwareBarAggregator, SourceBar
from .definitions import (
    FEATURE_CATALOG_V1,
    FS_V1_VERSION,
    TURNOVER_PROXY_DISCLOSURE,
    VOLUME_PROXY_DISCLOSURE,
    VWAP_PROXY_DISCLOSURE,
    FeatureCategory,
    FeatureDefinition,
)
from .indicators import (
    calculate_atr,
    calculate_causal_relative_volume,
    calculate_return,
    calculate_rsi,
    calculate_sma,
    calculate_true_range,
    calculate_turnover_proxy,
    calculate_vwap_approx,
)
from .models import (
    FeatureBatch,
    FeatureVector,
    PointInTimeUniverseSnapshot,
    UniverseMember,
    WarmupStatus,
)
from .pipeline import CausalFeaturePipeline
from .transforms import DeterministicFeatureScaler, ScalerFeatureStats
from .universe import PointInTimeUniverseManager

__all__ = [
    "CausalFeaturePipeline",
    "DeterministicFeatureScaler",
    "FEATURE_CATALOG_V1",
    "FS_V1_VERSION",
    "FeatureBatch",
    "FeatureCategory",
    "FeatureDefinition",
    "FeatureVector",
    "PointInTimeUniverseManager",
    "PointInTimeUniverseSnapshot",
    "ScalerFeatureStats",
    "SessionAwareBarAggregator",
    "SourceBar",
    "TURNOVER_PROXY_DISCLOSURE",
    "UniverseMember",
    "VOLUME_PROXY_DISCLOSURE",
    "VWAP_PROXY_DISCLOSURE",
    "WarmupStatus",
    "calculate_atr",
    "calculate_causal_relative_volume",
    "calculate_return",
    "calculate_rsi",
    "calculate_sma",
    "calculate_true_range",
    "calculate_turnover_proxy",
    "calculate_vwap_approx",
]
