"""FinPilot AI — Labeling and Temporal Validation Design (Layer 8).

Governed by:
- docs/trade-policy-contract-v1.md
- docs/execution-policy.md
- DATA_AND_PERFORMANCE_POLICY.md §2, §7, §8
- Layer 8 Gate: Labeling under executable trade policy, globally chronological partitions,
  boundary overlap purging, embargo from information horizon, and locked final-test lockbox.
"""

from __future__ import annotations

from .generator import TradePolicyLabelGenerator
from .lockbox import FinalTestLockbox
from .models import (
    LabelingApproach,
    PartitionManifest,
    PartitionType,
    SplitManifest,
    TradeOutcomeReason,
    TradePolicyLabel,
)
from .split_manager import (
    DEFAULT_EMBARGO_JUSTIFICATION,
    DEFAULT_SURVIVORSHIP_LIMITATION,
    FinalTestLockedError,
    TemporalSplitManager,
)

__all__ = [
    "DEFAULT_EMBARGO_JUSTIFICATION",
    "DEFAULT_SURVIVORSHIP_LIMITATION",
    "FinalTestLockedError",
    "FinalTestLockbox",
    "LabelingApproach",
    "PartitionManifest",
    "PartitionType",
    "SplitManifest",
    "TemporalSplitManager",
    "TradeOutcomeReason",
    "TradePolicyLabel",
    "TradePolicyLabelGenerator",
]
