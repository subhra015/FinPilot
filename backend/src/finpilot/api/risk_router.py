"""FastAPI Router for administrative risk configuration and kill switch (SEC-01, SEC-09, Layer 12).

Governed by:
- SECURITY_CHECKLIST.md SEC-01, SEC-09
- Layer 12 Gate: Admin routes require explicit admin permission server-side; signed audit trail.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from finpilot.db.models import User
from finpilot.risk.config_service import RiskConfigService
from finpilot.risk.models import RiskConfig, RiskConfigAuditEvent
from finpilot.schemas.scoping import UserScope

from .dependencies import require_admin, require_csrf

router = APIRouter(prefix="/risk", tags=["risk"])
risk_config_service = RiskConfigService()


class RiskUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    updates: dict[str, Any]


class KillSwitchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    active: bool


@router.get("/config", response_model=RiskConfig)
def get_risk_config(
    current_user: User = Depends(require_admin),
) -> RiskConfig:
    """Retrieve active risk configuration (Admin only)."""
    return risk_config_service.config


@router.patch("/config", response_model=RiskConfig, dependencies=[Depends(require_csrf)])
def update_risk_config(
    payload: RiskUpdateRequest,
    current_user: User = Depends(require_admin),
) -> RiskConfig:
    """Update risk limits with signed administrative audit event (Admin only)."""
    admin_scope = UserScope(user_id=current_user.user_id, is_admin=True)
    return risk_config_service.update_config(
        updates=payload.updates,
        user_scope=admin_scope,
    )


@router.post("/kill-switch", response_model=RiskConfig, dependencies=[Depends(require_csrf)])
def set_kill_switch(
    payload: KillSwitchRequest,
    current_user: User = Depends(require_admin),
) -> RiskConfig:
    """Engage or disengage emergency kill switch with signed audit event (Admin only)."""
    admin_scope = UserScope(user_id=current_user.user_id, is_admin=True)
    return risk_config_service.set_kill_switch(
        active=payload.active,
        user_scope=admin_scope,
    )


@router.get("/audit-log", response_model=list[RiskConfigAuditEvent])
def get_risk_audit_log(
    current_user: User = Depends(require_admin),
) -> list[RiskConfigAuditEvent]:
    """Retrieve immutable administrative risk audit trail (Admin only)."""
    return risk_config_service.get_audit_log()
