"""FinPilot AI — Probability Calibration and Selective Decision Logic (Layer 10).

Governed by:
- PROJECT_SPEC.md §4, §5, §7, §9
- DATA_AND_PERFORMANCE_POLICY.md §2, §7, §8
- Layer 10 Gate: Calibration on designated partitions, reliability diagrams, proper scoring
  rule decomposition, explicit 5-state selective decisions, sample support & OOD abstention,
  expectancy estimation without double cost deduction, and frozen decision policy.
"""

from __future__ import annotations

from .engine import SelectiveDecisionEngine
from .models import (
    BrierDecomposition,
    CalibrationBin,
    DecisionDiagnostics,
    DecisionState,
    FrozenDecisionPolicy,
    ReliabilityDiagramData,
    SelectiveDecision,
)
from .ood import OODDetector
from .reliability import ReliabilityEvaluator

__all__ = [
    "BrierDecomposition",
    "CalibrationBin",
    "DecisionDiagnostics",
    "DecisionState",
    "FrozenDecisionPolicy",
    "OODDetector",
    "ReliabilityDiagramData",
    "ReliabilityEvaluator",
    "SelectiveDecision",
    "SelectiveDecisionEngine",
]
