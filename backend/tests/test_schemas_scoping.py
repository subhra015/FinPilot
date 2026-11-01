"""User/owner scoping and cross-user isolation tests (SEC-01, SEC-06, SEC-09, Layer 3)."""

from __future__ import annotations

import pytest

from finpilot.schemas import (
    ErrorCode,
    PermissionDeniedError,
    UserScope,
    enforce_account_access,
    enforce_resource_owner,
)


def test_matching_resource_owner_passes() -> None:
    scope = UserScope(user_id="user_123")
    # Resource owned by user_123 succeeds
    enforce_resource_owner(resource_owner_id="user_123", user_scope=scope)


def test_cross_user_resource_access_denied_without_leakage() -> None:
    scope = UserScope(user_id="user_attacker")
    # Attempt to access resource owned by user_victim rejected
    with pytest.raises(PermissionDeniedError) as exc:
        enforce_resource_owner(
            resource_owner_id="user_victim",
            user_scope=scope,
            resource_name="Portfolio",
        )
    assert exc.value.code == ErrorCode.PERMISSION_DENIED
    # Error message does NOT leak the victim's user ID
    assert "user_victim" not in str(exc.value)
    assert "Access denied: unauthorized Portfolio scope." in str(exc.value)


def test_admin_bypasses_resource_owner_restriction() -> None:
    admin_scope = UserScope(user_id="admin_001", is_admin=True)
    # Admin can access any resource owner without raising
    enforce_resource_owner(resource_owner_id="user_victim", user_scope=admin_scope)


def test_allowed_account_access_passes() -> None:
    scope = UserScope(
        user_id="user_123",
        allowed_accounts=frozenset({"ACC_DEMO_001", "ACC_SIM_002"}),
    )
    enforce_account_access(account_number="ACC_DEMO_001", user_scope=scope)


def test_unauthorized_account_access_denied_without_leakage() -> None:
    scope = UserScope(
        user_id="user_123",
        allowed_accounts=frozenset({"ACC_DEMO_001"}),
    )
    # Attempt to access another user's account rejected
    with pytest.raises(PermissionDeniedError) as exc:
        enforce_account_access(account_number="ACC_FOREIGN_999", user_scope=scope)
    assert exc.value.code == ErrorCode.PERMISSION_DENIED
    # Error message does NOT leak the foreign account number
    assert "ACC_FOREIGN_999" not in str(exc.value)
    assert "Access denied: unauthorized account scope." in str(exc.value)


def test_admin_bypasses_account_access_restriction() -> None:
    admin_scope = UserScope(
        user_id="admin_001",
        is_admin=True,
        allowed_accounts=frozenset(),
    )
    enforce_account_access(account_number="ACC_FOREIGN_999", user_scope=admin_scope)
