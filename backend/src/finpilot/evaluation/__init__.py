"""Locked historical evaluation, model validation, and user trust engine (Layer 15).

Governed by:
- ACCEPTANCE_GATES.md Layer 15
- DATA_AND_PERFORMANCE_POLICY.md §2, §5, §7, §8
- PROJECT_SPEC.md §4, §5, §7, §9, §11
- SECURITY_CHECKLIST.md SEC-01 through SEC-27
"""

from __future__ import annotations

from .models import (
    ArmPerformanceMetrics,
    CapitalScenarioEvaluation,
    EconomicVerdict,
    EconomicVerdictEnum,
    EvaluationManifest,
    LockedHistoricalEvaluationReport,
    SlippageSensitivityResult,
    TradeValidationRecord,
    UncertaintyInterval,
)
from .runner import LockedHistoricalEvaluationRunner

__all__ = [
    "ArmPerformanceMetrics",
    "CapitalScenarioEvaluation",
    "EconomicVerdict",
    "EconomicVerdictEnum",
    "EvaluationManifest",
    "LockedHistoricalEvaluationReport",
    "LockedHistoricalEvaluationRunner",
    "SlippageSensitivityResult",
    "TradeValidationRecord",
    "UncertaintyInterval",
]
