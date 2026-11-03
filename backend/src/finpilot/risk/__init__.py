"""FinPilot AI — Independent Risk Engine and Authorization Authority (Layer 11).

Governed by:
- PROJECT_SPEC.md §4, §5, §7
- DATA_AND_PERFORMANCE_POLICY.md §2, §7
- SECURITY_CHECKLIST.md SEC-01, SEC-06, SEC-09, SEC-19
- Layer 11 Gate: Complete independent risk service, replayable decision store,
  audit tracking, and simulator integration.
"""

from __future__ import annotations

from .config_service import RiskConfigService
from .evaluator import RiskEvaluator
from .models import (
    PositionCloseIntent,
    RiskAuthorization,
    RiskConfig,
    RiskConfigAuditEvent,
    RiskDecisionStatus,
    RiskEvaluationResult,
    RiskMetricsSnapshot,
    RiskRejectionReason,
)
from .service import RiskService

__all__ = [
    "PositionCloseIntent",
    "RiskAuthorization",
    "RiskConfig",
    "RiskConfigAuditEvent",
    "RiskConfigService",
    "RiskDecisionStatus",
    "RiskEvaluationResult",
    "RiskEvaluator",
    "RiskMetricsSnapshot",
    "RiskRejectionReason",
    "RiskService",
]
