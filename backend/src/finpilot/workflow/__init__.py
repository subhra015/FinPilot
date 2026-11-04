"""FinPilot Workflow Package (Layer 14).

Provides:
- EndToEndPaperWorkflow orchestrator
- SecurityAuditLogger and audit logging helpers
- SimulatorSecurityChallengeSuite running all 17 challenges
"""

from .audit_logger import (
    SecurityAuditLogger,
    SuspiciousActivityRecord,
    SuspiciousActivityType,
    audit_logger,
)
from .challenge_suite import ChallengeResult, SimulatorSecurityChallengeSuite
from .orchestrator import (
    CandidateSignal,
    EndToEndPaperWorkflow,
    WorkflowExecutionOutcome,
)

__all__ = [
    "audit_logger",
    "SecurityAuditLogger",
    "SuspiciousActivityRecord",
    "SuspiciousActivityType",
    "CandidateSignal",
    "EndToEndPaperWorkflow",
    "WorkflowExecutionOutcome",
    "ChallengeResult",
    "SimulatorSecurityChallengeSuite",
]
