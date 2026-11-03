"""Security and RBAC audit trail unit tests for the Risk Configuration Service (Layer 11).

Governed by:
- SECURITY_CHECKLIST.md SEC-01, SEC-06, SEC-08, SEC-09
- Layer 11 Gate: Only authorized admin roles can modify risk settings; immutable audit events.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from finpilot.risk.config_service import RiskConfigService
from finpilot.schemas.errors import DomainValidationError, PermissionDeniedError
from finpilot.schemas.scoping import UserScope


@pytest.fixture
def risk_service() -> RiskConfigService:
    return RiskConfigService()


@pytest.fixture
def normal_user_scope() -> UserScope:
    return UserScope(user_id="trader_john", is_admin=False)


@pytest.fixture
def admin_user_scope() -> UserScope:
    return UserScope(user_id="sec_admin_root", is_admin=True)


def test_normal_user_cannot_update_risk_limits(
    risk_service: RiskConfigService,
    normal_user_scope: UserScope,
) -> None:
    """SEC-01 & SEC-09: Normal user attempting to weaken risk limits is denied."""
    with pytest.raises(PermissionDeniedError, match="only authorized administrative roles"):
        risk_service.update_config(
            updates={"max_planned_stop_risk_pct": Decimal("0.05")},
            user_scope=normal_user_scope,
        )


def test_normal_user_cannot_toggle_kill_switch(
    risk_service: RiskConfigService,
    normal_user_scope: UserScope,
) -> None:
    """SEC-09: Normal user attempting to toggle emergency kill switch is denied."""
    with pytest.raises(PermissionDeniedError, match="only administrators may toggle"):
        risk_service.set_kill_switch(active=True, user_scope=normal_user_scope)


def test_normal_user_cannot_pause_trading(
    risk_service: RiskConfigService,
    normal_user_scope: UserScope,
) -> None:
    """SEC-09: Normal user attempting to pause manual trading is denied."""
    with pytest.raises(PermissionDeniedError, match="only administrators may pause"):
        risk_service.set_manual_pause(paused=True, user_scope=normal_user_scope)


def test_admin_updates_risk_limits_generates_signed_audit_event(
    risk_service: RiskConfigService,
    admin_user_scope: UserScope,
) -> None:
    """SEC-08 & SEC-09: Admin can update limits, generating an immutable signed audit event."""
    initial_config = risk_service.config
    initial_hash = initial_config.calculate_config_hash()

    updates = {
        "max_exposure_per_instrument_pct": Decimal("0.40"),
        "max_concurrent_positions": 2,
    }

    new_config = risk_service.update_config(updates=updates, user_scope=admin_user_scope)

    assert new_config.max_exposure_per_instrument_pct == Decimal("0.40")
    assert new_config.max_concurrent_positions == 2
    assert new_config.calculate_config_hash() != initial_hash

    # Verify audit event
    audit_events = risk_service.get_audit_log()
    assert len(audit_events) == 1
    event = audit_events[0]
    assert event.user_id == "sec_admin_root"
    assert event.action == "UPDATE_RISK_LIMITS"
    assert event.previous_config_hash == initial_hash
    assert event.new_config_hash == new_config.calculate_config_hash()
    assert event.changed_fields == {
        "max_exposure_per_instrument_pct": "0.40",
        "max_concurrent_positions": "2",
    }
    assert len(event.audit_signature) == 64


def test_admin_kill_switch_generates_audit_event(
    risk_service: RiskConfigService,
    admin_user_scope: UserScope,
) -> None:
    """Admin toggling kill switch updates active state and emits an audit event."""
    risk_service.set_kill_switch(
        active=True,
        user_scope=admin_user_scope,
        reason="High market volatility event",
    )
    assert risk_service.config.kill_switch_active is True

    audit_events = risk_service.get_audit_log()
    assert len(audit_events) == 1
    assert audit_events[0].action == "ACTIVATE_KILL_SWITCH"
    assert audit_events[0].changed_fields["kill_switch_active"] is True

    # Deactivate
    risk_service.set_kill_switch(
        active=False,
        user_scope=admin_user_scope,
        reason="Market stabilized",
    )
    assert risk_service.config.kill_switch_active is False
    assert len(risk_service.get_audit_log()) == 2
    assert risk_service.get_audit_log()[1].action == "DEACTIVATE_KILL_SWITCH"


def test_reject_unapproved_fields_and_invalid_bounds(
    risk_service: RiskConfigService,
    admin_user_scope: UserScope,
) -> None:
    """SEC-06: Server-side validation rejects unapproved fields and invalid parameter ranges."""
    # Unknown field injection
    with pytest.raises(DomainValidationError, match="unapproved risk configuration fields"):
        risk_service.update_config(
            updates={"arbitrary_injected_setting": "malicious"},
            user_scope=admin_user_scope,
        )

    # Invalid exposure bounds (> 1.00)
    with pytest.raises(DomainValidationError, match="max_exposure_per_instrument_pct"):
        risk_service.update_config(
            updates={"max_exposure_per_instrument_pct": Decimal("1.50")},
            user_scope=admin_user_scope,
        )

    # Negative daily loss
    with pytest.raises(DomainValidationError, match="max_daily_loss must be positive"):
        risk_service.update_config(
            updates={"max_daily_loss": Decimal("-500.00")},
            user_scope=admin_user_scope,
        )

    # Zero positions cap
    with pytest.raises(DomainValidationError, match="max_concurrent_positions must be at least 1"):
        risk_service.update_config(
            updates={"max_concurrent_positions": 0},
            user_scope=admin_user_scope,
        )
