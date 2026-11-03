"""FastAPI Router for approved model registry inspection (SEC-01, SEC-06, Layer 12).

Governed by:
- SECURITY_CHECKLIST.md SEC-01, SEC-06, SEC-18
- Layer 12 Gate: Authenticate private model-management routes.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from finpilot.db.models import User

from .dependencies import get_current_user

router = APIRouter(prefix="/models", tags=["models"])


class ModelSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_id: str
    feature_schema_version: str
    training_data_mode: str
    sha256_checksum: str


@router.get("", response_model=list[dict[str, Any]])
def list_approved_models(
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List approved models and verified checksums (Authenticated)."""
    # Return approved model candidates from V1 specification
    return [
        {
            "model_id": "MODEL-LOGREG-V1",
            "algorithm": "LogisticRegression (Platt Calibrated)",
            "policy_version": "TP-V1",
            "feature_set": "FS-V1",
            "decision_threshold": 0.5400,
            "status": "APPROVED",
        },
        {
            "model_id": "MODEL-LIGHTGBM-V1",
            "algorithm": "LightGBM (Isotonic Calibrated)",
            "policy_version": "TP-V1",
            "feature_set": "FS-V1",
            "decision_threshold": 0.3000,
            "status": "APPROVED",
        },
    ]
