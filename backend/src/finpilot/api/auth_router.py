"""FastAPI Router for authentication, MFA, sessions, and password management (Layer 12).

Governed by:
- NIST SP 800-63B-4
- SECURITY_CHECKLIST.md SEC-01, SEC-05, SEC-06, SEC-09, SEC-15, SEC-16, SEC-17
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session as DBSession

from finpilot.auth import (
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    AuthService,
    generate_csrf_token,
)
from finpilot.config import Settings
from finpilot.db.enums import UserRole
from finpilot.db.models import User

from .dependencies import get_current_user, get_db, require_csrf

router = APIRouter(prefix="/auth", tags=["auth"])
auth_service = AuthService()


# Request / Response Schemas
class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(..., min_length=5, max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(..., min_length=8, max_length=128)
    role: UserRole = Field(default=UserRole.USER)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(..., min_length=5, max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(..., min_length=1, max_length=128)


class MFALoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str = Field(..., min_length=1, max_length=64)
    totp_code: str = Field(..., min_length=6, max_length=6)


class MFAVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    totp_code: str = Field(..., min_length=6, max_length=6)


class PasswordResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(..., min_length=5, max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class PasswordResetConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(..., min_length=16)
    new_password: str = Field(..., min_length=8, max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str
    email: str
    role: str
    mfa_enabled: bool
    created_at: datetime
    csrf_token: str | None = None


class LoginResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user: UserResponse | None = None
    mfa_required: bool = False
    user_id: str | None = None
    message: str = "Success"


def _set_auth_cookies(
    response: Response,
    request: Request,
    raw_session_token: str,
) -> str:
    """Set secure HttpOnly session cookie and readable anti-CSRF token cookie."""
    settings: Settings = request.app.state.settings
    is_prod = settings.is_production
    secret_key = (
        settings.secret_key.get_secret_value()
        if settings.secret_key
        else "fallback-dev-secret-key-32chars"
    )

    session_hash = auth_service.session_manager.hash_session_token(raw_session_token)
    csrf_token = generate_csrf_token(session_hash, secret_key)

    # 1. HttpOnly Opaque Session Cookie (SEC-15)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=raw_session_token,
        httponly=True,
        secure=is_prod,
        samesite="lax",
        path="/",
        max_age=auth_service.session_manager.absolute_timeout_seconds,
    )

    # 2. Client-accessible Anti-CSRF Token Cookie (SEC-16)
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        httponly=False,  # Client JS reads this to attach X-CSRF-Token header
        secure=is_prod,
        samesite="lax",
        path="/",
        max_age=auth_service.session_manager.absolute_timeout_seconds,
    )
    return csrf_token


def _clear_auth_cookies(response: Response, request: Request) -> None:
    """Clear session and CSRF cookies on logout."""
    settings: Settings = request.app.state.settings
    is_prod = settings.is_production
    response.delete_cookie(
        key=SESSION_COOKIE_NAME, path="/", httponly=True, secure=is_prod, samesite="lax"
    )
    response.delete_cookie(
        key=CSRF_COOKIE_NAME, path="/", httponly=False, secure=is_prod, samesite="lax"
    )


@router.post("/register", response_model=UserResponse, status_code=201)
def register(
    payload: RegisterRequest,
    request: Request,
    db: DBSession = Depends(get_db),
) -> UserResponse:
    """Register a new user account with Argon2id hashing and NIST password policy."""
    client_ip = request.client.host if request.client else None
    user = auth_service.register_user(
        db=db,
        email=payload.email,
        password=payload.password,
        role=payload.role,
        ip_address=client_ip,
    )
    return UserResponse(
        user_id=user.user_id,
        email=user.email,
        role=user.role,
        mfa_enabled=user.mfa_enabled,
        created_at=user.created_at,
    )


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: DBSession = Depends(get_db),
) -> LoginResponse:
    """Authenticate user credentials with rate limiting and opaque server sessions."""
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")

    user, raw_session_token, mfa_required = auth_service.authenticate(
        db=db,
        email=payload.email,
        password=payload.password,
        ip_address=client_ip,
        user_agent=user_agent,
    )

    if mfa_required:
        return LoginResponse(
            user=None,
            mfa_required=True,
            user_id=user.user_id,
            message="Multi-factor authentication code required.",
        )

    assert raw_session_token is not None
    csrf_token = _set_auth_cookies(response, request, raw_session_token)

    return LoginResponse(
        user=UserResponse(
            user_id=user.user_id,
            email=user.email,
            role=user.role,
            mfa_enabled=user.mfa_enabled,
            created_at=user.created_at,
            csrf_token=csrf_token,
        ),
        mfa_required=False,
        user_id=user.user_id,
        message="Authentication successful.",
    )


@router.post("/mfa/verify-login", response_model=LoginResponse)
def verify_mfa_login(
    payload: MFALoginRequest,
    request: Request,
    response: Response,
    db: DBSession = Depends(get_db),
) -> LoginResponse:
    """Verify second-factor TOTP code and issue authenticated session token."""
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")

    user, raw_session_token = auth_service.verify_mfa_login(
        db=db,
        user_id=payload.user_id,
        totp_code=payload.totp_code,
        ip_address=client_ip,
        user_agent=user_agent,
    )

    csrf_token = _set_auth_cookies(response, request, raw_session_token)

    return LoginResponse(
        user=UserResponse(
            user_id=user.user_id,
            email=user.email,
            role=user.role,
            mfa_enabled=user.mfa_enabled,
            created_at=user.created_at,
            csrf_token=csrf_token,
        ),
        mfa_required=False,
        user_id=user.user_id,
        message="MFA authentication successful.",
    )


@router.post("/mfa/setup")
def setup_mfa(
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> dict[str, str]:
    """Setup RFC 6238 TOTP for current user (authenticated route)."""
    secret, uri = auth_service.setup_mfa(db=db, user=current_user)
    return {"secret": secret, "otpauth_uri": uri}


@router.post("/mfa/verify", dependencies=[Depends(require_csrf)])
def verify_mfa_setup(
    payload: MFAVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> dict[str, Any]:
    """Verify and activate TOTP MFA for current user."""
    from finpilot.auth.mfa import verify_totp_code
    from finpilot.schemas.errors import PermissionDeniedError

    if not current_user.mfa_secret or not verify_totp_code(
        current_user.mfa_secret, payload.totp_code
    ):
        raise PermissionDeniedError("Invalid TOTP verification code.")

    current_user.mfa_enabled = True
    db.commit()
    return {"status": "MFA activated successfully.", "mfa_enabled": True}


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> dict[str, str]:
    """Revoke current opaque session and clear cookies."""
    raw_token = request.cookies.get(SESSION_COOKIE_NAME, "")
    auth_service.logout(db=db, raw_session_token=raw_token, user=current_user)
    _clear_auth_cookies(response, request)
    return {"status": "Logged out successfully."}


@router.get("/me", response_model=UserResponse)
def get_me(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Return authenticated user profile."""
    return UserResponse(
        user_id=current_user.user_id,
        email=current_user.email,
        role=current_user.role,
        mfa_enabled=current_user.mfa_enabled,
        created_at=current_user.created_at,
    )


@router.post("/reset-password-request")
def request_password_reset(
    payload: PasswordResetRequest,
    request: Request,
    db: DBSession = Depends(get_db),
) -> dict[str, str]:
    """Request password reset (generic response to prevent user enumeration)."""
    client_ip = request.client.host if request.client else None
    msg = auth_service.request_password_reset(db=db, email=payload.email, ip_address=client_ip)
    return {"message": msg}


@router.post("/reset-password-confirm")
def confirm_password_reset(
    payload: PasswordResetConfirmRequest,
    request: Request,
    db: DBSession = Depends(get_db),
) -> dict[str, str]:
    """Confirm password reset with high-entropy token and update Argon2id hash."""
    client_ip = request.client.host if request.client else None
    auth_service.confirm_password_reset(
        db=db,
        raw_reset_token=payload.token,
        new_password=payload.new_password,
        ip_address=client_ip,
    )
    return {"message": "Password updated successfully. All active sessions have been revoked."}
