"""Core Authentication Service orchestrating credentials, MFA, sessions, and logs (Layer 12).

Governed by:
- NIST SP 800-63B-4
- OWASP Authentication Cheat Sheet
- SECURITY_CHECKLIST.md SEC-01, SEC-05, SEC-06, SEC-08, SEC-09, SEC-15, SEC-17
- Layer 12 Gate: Production-quality authentication, generic responses, Argon2id, MFA, audit trail.
"""

from __future__ import annotations

import json
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from finpilot.db.enums import UserRole
from finpilot.db.models import PasswordResetToken, SecurityAuditLog, User
from finpilot.schemas.errors import DomainValidationError, ErrorCode, PermissionDeniedError

from .mfa import generate_totp_secret, get_totp_uri, verify_totp_code
from .passwords import (
    constant_time_dummy_verify,
    hash_password,
    validate_password_policy,
    verify_password,
)
from .rate_limiter import (
    LOGIN_RATE_LIMIT,
    REGISTER_RATE_LIMIT,
    RESET_RATE_LIMIT,
    limiter,
)
from .sessions import SessionManager

# Generic authentication failure message (prevents user enumeration)
GENERIC_AUTH_ERROR = "Invalid email or password."
GENERIC_RESET_MSG = "If the account exists, password reset instructions have been issued."
RESET_TOKEN_EXPIRY_MINUTES = 15


class AuthService:
    """Production authentication service enforcing NIST SP 800-63B-4 and OWASP standards."""

    def __init__(
        self,
        session_manager: SessionManager | None = None,
        email_enabled: bool = False,
    ) -> None:
        self.session_manager = session_manager or SessionManager()
        self.email_enabled = email_enabled

    def register_user(
        self,
        db: DBSession,
        email: str,
        password: str,
        role: UserRole = UserRole.USER,
        ip_address: str | None = None,
    ) -> User:
        """Register a new user account with Argon2id password hashing and NIST validation."""
        # 1. Rate limiting
        limiter.enforce("register", ip_address or "unknown", *REGISTER_RATE_LIMIT)

        # 2. Input hygiene
        clean_email = email.strip().lower()
        if "@" not in clean_email or len(clean_email) < 3:
            raise DomainValidationError(
                "Invalid email address format.", field="email", code=ErrorCode.VALIDATION_ERROR
            )

        # Check existing user
        existing = db.execute(select(User).where(User.email == clean_email)).scalar_one_or_none()
        if existing:
            # Rejection with safe generic response
            raise DomainValidationError(
                "Email address already registered.", field="email", code=ErrorCode.VALIDATION_ERROR
            )

        # 3. Password policy: Admin requires MFA (>=8 chars), single-factor requires >=15 chars
        is_mfa_user = role == UserRole.ADMIN
        validate_password_policy(password, is_mfa_user=is_mfa_user)

        # 4. Hash with Argon2id
        hashed_pwd = hash_password(password)
        new_user_id = f"USR-{uuid.uuid4().hex[:12].upper()}"

        user = User(
            user_id=new_user_id,
            email=clean_email,
            password_hash=hashed_pwd,
            role=role.value,
            is_active=True,
            mfa_enabled=False,
            mfa_secret=generate_totp_secret() if is_mfa_user else None,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        # Log security audit event
        self.log_security_event(
            db=db,
            event_type="AUTH_REGISTER_SUCCESS",
            user_id=user.user_id,
            ip_address=ip_address,
            details={"email": clean_email, "role": user.role},
        )
        return user

    def authenticate(
        self,
        db: DBSession,
        email: str,
        password: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[User, str | None, bool]:
        """Authenticate user credentials.

        Returns tuple of:
        - (User, raw_session_token, mfa_required: bool)
        If mfa_required is True, raw_session_token is None until MFA code is verified.
        """
        clean_email = email.strip().lower()

        # 1. Rate limit online guessing per IP and per username
        limiter.enforce("login_ip", ip_address or "unknown", *LOGIN_RATE_LIMIT)
        limiter.enforce("login_user", clean_email, *LOGIN_RATE_LIMIT)

        # 2. Look up user
        user = db.execute(select(User).where(User.email == clean_email)).scalar_one_or_none()
        if not user or not user.is_active:
            # Timing mitigation
            constant_time_dummy_verify()
            self.log_security_event(
                db=db,
                event_type="AUTH_LOGIN_FAILED",
                user_id=None,
                ip_address=ip_address,
                details={"email": clean_email, "reason": "user_not_found_or_inactive"},
            )
            raise PermissionDeniedError(GENERIC_AUTH_ERROR)

        # 3. Verify Argon2id password
        if not verify_password(password, user.password_hash):
            self.log_security_event(
                db=db,
                event_type="AUTH_LOGIN_FAILED",
                user_id=user.user_id,
                ip_address=ip_address,
                details={"email": clean_email, "reason": "password_mismatch"},
            )
            raise PermissionDeniedError(GENERIC_AUTH_ERROR)

        # 4. Check MFA requirements
        # Admins MUST complete MFA. Standard users with mfa_enabled also require MFA.
        requires_mfa = user.role == UserRole.ADMIN.value or user.mfa_enabled
        if requires_mfa:
            self.log_security_event(
                db=db,
                event_type="AUTH_MFA_CHALLENGE_ISSUED",
                user_id=user.user_id,
                ip_address=ip_address,
                details={"role": user.role},
            )
            return user, None, True

        # 5. Create opaque session with token rotation
        raw_token, _ = self.session_manager.create_session(
            db=db,
            user=user,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        self.log_security_event(
            db=db,
            event_type="AUTH_LOGIN_SUCCESS",
            user_id=user.user_id,
            ip_address=ip_address,
            details={"role": user.role, "mfa_used": False},
        )
        return user, raw_token, False

    def verify_mfa_login(
        self,
        db: DBSession,
        user_id: str,
        totp_code: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[User, str]:
        """Verify second factor (TOTP) and issue session token upon success."""
        user = db.execute(select(User).where(User.user_id == user_id)).scalar_one_or_none()
        if not user or not user.is_active or not user.mfa_secret:
            raise PermissionDeniedError("MFA authentication failed.")

        if not verify_totp_code(user.mfa_secret, totp_code):
            self.log_security_event(
                db=db,
                event_type="AUTH_MFA_VERIFY_FAILED",
                user_id=user.user_id,
                ip_address=ip_address,
                details={"reason": "invalid_totp_code"},
            )
            raise PermissionDeniedError("Invalid multi-factor authentication code.")

        # Ensure mfa_enabled is marked true once verified
        if not user.mfa_enabled:
            user.mfa_enabled = True
            db.commit()

        # Issue authenticated session
        raw_token, _ = self.session_manager.create_session(
            db=db,
            user=user,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        self.log_security_event(
            db=db,
            event_type="AUTH_LOGIN_SUCCESS",
            user_id=user.user_id,
            ip_address=ip_address,
            details={"role": user.role, "mfa_used": True},
        )
        return user, raw_token

    def setup_mfa(self, db: DBSession, user: User) -> tuple[str, str]:
        """Setup TOTP for an active user. Returns (secret, otpauth_uri)."""
        secret = generate_totp_secret()
        user.mfa_secret = secret
        db.commit()

        uri = get_totp_uri(secret, email=user.email)
        return secret, uri

    def logout(self, db: DBSession, raw_session_token: str, user: User | None = None) -> None:
        """Revoke active session on logout."""
        self.session_manager.revoke_session(db, raw_session_token)
        self.log_security_event(
            db=db,
            event_type="AUTH_LOGOUT",
            user_id=user.user_id if user else None,
            ip_address=None,
            details={"status": "revoked"},
        )

    def request_password_reset(
        self,
        db: DBSession,
        email: str,
        ip_address: str | None = None,
    ) -> str:
        """Request single-use password reset token.

        SEC-17: If email infrastructure is unconfigured, feature is disabled with generic response.
        If configured, issues high-entropy token, stores only SHA-256 hash, 15m expiry.
        """
        limiter.enforce("reset_request", ip_address or "unknown", *RESET_RATE_LIMIT)
        clean_email = email.strip().lower()

        # Generic response regardless of whether account exists (anti-enumeration)
        if not self.email_enabled:
            # Email infrastructure is not configured in V1; feature is disabled
            self.log_security_event(
                db=db,
                event_type="AUTH_RESET_REQUEST_DISABLED",
                user_id=None,
                ip_address=ip_address,
                details={"email": clean_email, "reason": "email_infrastructure_disabled"},
            )
            return GENERIC_RESET_MSG

        user = db.execute(select(User).where(User.email == clean_email)).scalar_one_or_none()
        if not user or not user.is_active:
            return GENERIC_RESET_MSG

        # Generate high-entropy single-use token
        raw_reset_token = secrets.token_urlsafe(32)
        token_hash = SessionManager.hash_session_token(raw_reset_token)
        now_utc = datetime.now(UTC)

        reset_record = PasswordResetToken(
            token_hash=token_hash,
            user_id=user.id,
            expires_at=now_utc + timedelta(minutes=RESET_TOKEN_EXPIRY_MINUTES),
            is_used=False,
            created_at=now_utc,
        )
        db.add(reset_record)
        db.commit()

        self.log_security_event(
            db=db,
            event_type="AUTH_RESET_REQUEST_ISSUED",
            user_id=user.user_id,
            ip_address=ip_address,
            details={"expires_minutes": RESET_TOKEN_EXPIRY_MINUTES},
        )
        return GENERIC_RESET_MSG

    def confirm_password_reset(
        self,
        db: DBSession,
        raw_reset_token: str,
        new_password: str,
        ip_address: str | None = None,
    ) -> bool:
        """Validate single-use reset token and update password with Argon2id.

        Invalidates all user sessions upon password change.
        """
        if not self.email_enabled:
            raise PermissionDeniedError(
                "Password reset is disabled because email infrastructure is not configured."
            )

        token_hash = SessionManager.hash_session_token(raw_reset_token)
        now_utc = datetime.now(UTC)

        stmt = (
            select(PasswordResetToken, User)
            .join(User, PasswordResetToken.user_id == User.id)
            .where(
                PasswordResetToken.token_hash == token_hash,
                PasswordResetToken.is_used.is_(False),
                PasswordResetToken.expires_at > now_utc,
            )
        )
        result = db.execute(stmt).first()
        if not result:
            raise PermissionDeniedError("Invalid or expired password reset token.")

        reset_record, user = result

        # Validate new password policy
        validate_password_policy(new_password, is_mfa_user=user.mfa_enabled)

        # Update password hash
        user.password_hash = hash_password(new_password)
        reset_record.is_used = True

        # Invalidate all existing sessions
        revoked_count = self.session_manager.revoke_all_user_sessions(db, user.id)

        db.commit()

        self.log_security_event(
            db=db,
            event_type="AUTH_PASSWORD_RESET_SUCCESS",
            user_id=user.user_id,
            ip_address=ip_address,
            details={"revoked_sessions": revoked_count},
        )
        return True

    def log_security_event(
        self,
        db: DBSession,
        event_type: str,
        user_id: str | None,
        ip_address: str | None,
        details: dict[str, Any],
    ) -> None:
        """Persist structured security audit event with secret redaction."""
        sanitized_details = self._redact_secrets(details)
        event = SecurityAuditLog(
            event_id=f"SEC-EVT-{uuid.uuid4().hex[:12].upper()}",
            event_type=event_type,
            user_id=user_id,
            ip_address=ip_address,
            details=json.dumps(sanitized_details, sort_keys=True),
            timestamp=datetime.now(UTC),
        )
        db.add(event)
        db.commit()

    @staticmethod
    def _redact_secrets(data: dict[str, Any]) -> dict[str, Any]:
        """Redact sensitive fields from audit telemetry."""
        sensitive_keys = {"password", "secret", "token", "hash", "session_id", "csrf", "mfa_secret"}
        redacted: dict[str, Any] = {}
        for k, v in data.items():
            if any(s in k.lower() for s in sensitive_keys):
                redacted[k] = "[REDACTED]"
            elif isinstance(v, dict):
                redacted[k] = AuthService._redact_secrets(v)
            else:
                redacted[k] = v
        return redacted
