"""Administrative Risk Configuration Service with RBAC and immutable audit logging (Layer 11).

Governed by:
- SECURITY_CHECKLIST.md SEC-01, SEC-06, SEC-09
- Layer 11 Gate: Strict RBAC for risk parameters, audit trail, server-side enforcement.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from finpilot.schemas.errors import DomainValidationError, ErrorCode, PermissionDeniedError
from finpilot.schemas.scoping import UserScope

from .models import RiskConfig, RiskConfigAuditEvent


class RiskConfigService:
    """Manages the lifecycle, administrative authorization, and audit logging of RiskConfig.

    Guarantees:
    1. RBAC Protection (SEC-01, SEC-09): Only UserScope with is_admin=True can mutate configuration.
       Requests from normal users, strategies, or frontends raise PermissionDeniedError.
    2. Input Validation (SEC-06): Rejects invalid bounds, negative limits, or excessive exposure.
    3. Tamper-Evident Audit Trail: Every modification produces an immutable RiskConfigAuditEvent
       storing admin ID, timestamps, diffs, and cryptographic hash chains.
    4. Kill Switch & Pause: Dedicated administrative controls to instantly suspend trading.
    """

    def __init__(self, initial_config: RiskConfig | None = None) -> None:
        self._config: RiskConfig = initial_config or RiskConfig()
        self._audit_log: list[RiskConfigAuditEvent] = []

    @property
    def config(self) -> RiskConfig:
        """Return the current active RiskConfig."""
        return self._config

    def get_config(self) -> RiskConfig:
        """Public read-only accessor for current configuration."""
        return self._config

    def get_audit_log(self) -> list[RiskConfigAuditEvent]:
        """Return a copy of the administrative audit trail."""
        return list(self._audit_log)

    def update_config(
        self,
        updates: dict[str, Any],
        user_scope: UserScope,
    ) -> RiskConfig:
        """Update risk limits. Requires admin role; raises PermissionDeniedError otherwise."""
        if not user_scope.is_admin:
            raise PermissionDeniedError(
                "Access denied: only authorized administrative roles may modify risk settings."
            )

        # Validate that updates do not contain unapproved fields
        allowed_fields = set(RiskConfig.model_fields.keys()) - {"config_version", "updated_at"}
        unknown = [k for k in updates if k not in allowed_fields]
        if unknown:
            raise DomainValidationError(
                f"Cannot update unapproved risk configuration fields: {unknown}",
                field="updates",
                code=ErrorCode.VALIDATION_ERROR,
            )

        # Validate specific numeric constraints
        if "max_exposure_per_instrument_pct" in updates:
            val = Decimal(str(updates["max_exposure_per_instrument_pct"]))
            if val <= Decimal("0.00") or val > Decimal("1.00"):
                raise DomainValidationError(
                    "max_exposure_per_instrument_pct must be between 0.01 and 1.00",
                    field="max_exposure_per_instrument_pct",
                )

        if "max_total_exposure_pct" in updates:
            val = Decimal(str(updates["max_total_exposure_pct"]))
            if val <= Decimal("0.00") or val > Decimal("1.00"):
                raise DomainValidationError(
                    "max_total_exposure_pct must be between 0.01 and 1.00",
                    field="max_total_exposure_pct",
                )

        if "max_concurrent_positions" in updates:
            pos_val = int(updates["max_concurrent_positions"])
            if pos_val < 1:
                raise DomainValidationError(
                    "max_concurrent_positions must be at least 1",
                    field="max_concurrent_positions",
                )

        if "max_daily_loss" in updates:
            loss_val = Decimal(str(updates["max_daily_loss"]))
            if loss_val <= Decimal("0.00"):
                raise DomainValidationError(
                    "max_daily_loss must be positive",
                    field="max_daily_loss",
                )

        prev_hash = self._config.calculate_config_hash()

        # Build updated config
        new_data = self._config.model_dump()
        new_data.update(updates)
        new_data["updated_by_role"] = "admin"
        new_data["updated_at"] = datetime.now(UTC)

        new_config = RiskConfig(**new_data)
        new_hash = new_config.calculate_config_hash()

        # Record audit event
        audit_event = RiskConfigAuditEvent.create(
            audit_id=f"AUDIT-{uuid.uuid4().hex[:12]}",
            user_id=user_scope.user_id,
            user_role="admin",
            action="UPDATE_RISK_LIMITS",
            previous_config_hash=prev_hash,
            new_config_hash=new_hash,
            changed_fields={k: str(v) for k, v in updates.items()},
        )
        self._audit_log.append(audit_event)
        self._config = new_config
        return self._config

    def set_kill_switch(
        self,
        active: bool,
        user_scope: UserScope,
        reason: str = "Administrative kill switch toggled",
    ) -> RiskConfig:
        """Activate or deactivate emergency kill switch. Admin only."""
        if not user_scope.is_admin:
            raise PermissionDeniedError(
                "Access denied: only administrators may toggle the kill switch."
            )

        prev_hash = self._config.calculate_config_hash()
        new_config = self._config.model_copy(
            update={
                "kill_switch_active": active,
                "updated_by_role": "admin",
                "updated_at": datetime.now(UTC),
            }
        )
        new_hash = new_config.calculate_config_hash()

        action = "ACTIVATE_KILL_SWITCH" if active else "DEACTIVATE_KILL_SWITCH"
        audit_event = RiskConfigAuditEvent.create(
            audit_id=f"AUDIT-{uuid.uuid4().hex[:12]}",
            user_id=user_scope.user_id,
            user_role="admin",
            action=action,
            previous_config_hash=prev_hash,
            new_config_hash=new_hash,
            changed_fields={"kill_switch_active": active, "reason": reason},
        )
        self._audit_log.append(audit_event)
        self._config = new_config
        return self._config

    def set_manual_pause(
        self,
        paused: bool,
        user_scope: UserScope,
        reason: str = "Manual trading pause toggled",
    ) -> RiskConfig:
        """Pause or resume trading manually. Admin only."""
        if not user_scope.is_admin:
            raise PermissionDeniedError(
                "Access denied: only administrators may pause trading."
            )

        prev_hash = self._config.calculate_config_hash()
        new_config = self._config.model_copy(
            update={
                "manual_trading_paused": paused,
                "updated_by_role": "admin",
                "updated_at": datetime.now(UTC),
            }
        )
        new_hash = new_config.calculate_config_hash()

        action = "PAUSE_TRADING" if paused else "RESUME_TRADING"
        audit_event = RiskConfigAuditEvent.create(
            audit_id=f"AUDIT-{uuid.uuid4().hex[:12]}",
            user_id=user_scope.user_id,
            user_role="admin",
            action=action,
            previous_config_hash=prev_hash,
            new_config_hash=new_hash,
            changed_fields={"manual_trading_paused": paused, "reason": reason},
        )
        self._audit_log.append(audit_event)
        self._config = new_config
        return self._config
