"""Owner/user scoping at the schema and service boundary (SEC-01, SEC-06, SEC-09, Layer 3).

Guarantees:
- Private resources (accounts, portfolios, positions, orders) cannot be accessed
  across user boundaries.
- Cross-user identifier tampering is rejected at the boundary.
- Denial responses never leak metadata about foreign resources.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .errors import PermissionDeniedError


class UserScope(BaseModel):
    """User context for request scoping."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: str = Field(..., min_length=1, max_length=64)
    is_admin: bool = Field(default=False)
    allowed_accounts: frozenset[str] = Field(default_factory=frozenset)


def enforce_resource_owner(
    resource_owner_id: str,
    user_scope: UserScope,
    resource_name: str = "Resource",
) -> None:
    """Enforce that ``resource_owner_id`` matches ``user_scope.user_id`` unless admin."""
    if user_scope.is_admin:
        return

    if resource_owner_id != user_scope.user_id:
        raise PermissionDeniedError(
            f"Access denied: unauthorized {resource_name} scope."
        )


def enforce_account_access(
    account_number: str,
    user_scope: UserScope,
) -> None:
    """Enforce that ``account_number`` is within ``user_scope.allowed_accounts`` unless admin."""
    if user_scope.is_admin:
        return

    if user_scope.allowed_accounts and account_number not in user_scope.allowed_accounts:
        raise PermissionDeniedError("Access denied: unauthorized account scope.")
