"""FastAPI Router for locked historical evaluation and user trust audit (Layer 15).

Governed by:
- ACCEPTANCE_GATES.md §2 (Layer 15 Gate)
- SECURITY_CHECKLIST.md SEC-01, SEC-06, SEC-18, SEC-19
- PROJECT_SPEC.md §4, §5, §7, §9, §11
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, Query

from finpilot.db.models import User
from finpilot.evaluation.models import (
    CapitalScenarioEvaluation,
    EvaluationManifest,
    LockedHistoricalEvaluationReport,
    TradeValidationRecord,
)
from finpilot.evaluation.runner import LockedHistoricalEvaluationRunner

from .dependencies import get_current_user

router = APIRouter(prefix="/evaluation", tags=["evaluation"])

REPORT_PATH = Path("artifacts/evaluation/locked_historical_evaluation_report.json")
MANIFEST_PATH = Path("artifacts/evaluation/EVALUATION_MANIFEST_LOCKED_TEST.json")


def _get_or_run_report(model_id: str = "MODEL-LOGREG-V1") -> LockedHistoricalEvaluationReport:
    """Load existing locked evaluation report or run evaluation if missing."""
    if REPORT_PATH.exists():
        with open(REPORT_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return LockedHistoricalEvaluationReport.model_validate(data)

    runner = LockedHistoricalEvaluationRunner()
    return runner.run_locked_evaluation(model_id=model_id)


@router.get("/locked-test", response_model=LockedHistoricalEvaluationReport)
def get_locked_evaluation_report(
    model_id: str = Query(default="MODEL-LOGREG-V1"),
    current_user: User = Depends(get_current_user),
) -> LockedHistoricalEvaluationReport:
    """Retrieve the complete, tamper-evident locked historical evaluation report."""
    return _get_or_run_report(model_id=model_id)


@router.get("/manifest", response_model=EvaluationManifest)
def get_evaluation_manifest(
    model_id: str = Query(default="MODEL-LOGREG-V1"),
    current_user: User = Depends(get_current_user),
) -> EvaluationManifest:
    """Retrieve the cryptographically frozen evaluation manifest."""
    if MANIFEST_PATH.exists():
        with open(MANIFEST_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return EvaluationManifest.model_validate(data)

    rep = _get_or_run_report(model_id=model_id)
    return rep.manifest


@router.get("/user-validation-log", response_model=list[TradeValidationRecord])
def get_trade_validation_log(
    model_id: str = Query(default="MODEL-LOGREG-V1"),
    limit: int = Query(default=50, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
) -> list[TradeValidationRecord]:
    """Retrieve transparent trade validation and decision logs for candidate opportunities."""
    rep = _get_or_run_report(model_id=model_id)
    return rep.user_validation_sample[:limit]


@router.get("/capital-scenarios", response_model=list[CapitalScenarioEvaluation])
def get_capital_scenarios(
    model_id: str = Query(default="MODEL-LOGREG-V1"),
    current_user: User = Depends(get_current_user),
) -> list[CapitalScenarioEvaluation]:
    """Retrieve simulated performance across user-configurable virtual capital scenarios."""
    rep = _get_or_run_report(model_id=model_id)
    return rep.capital_scenarios
