"""Password hashing with Argon2id and NIST SP 800-63B-4 policy validation (SEC-05, Layer 12).

Governed by:
- NIST SP 800-63B §5.1.1.2 (Memorized Secret Authenticator Requirements)
- SECURITY_CHECKLIST.md SEC-05, SEC-06
- Layer 12 Gate: Argon2id password hashing, NIST SP 800-63B-4 policy, no arbitrary rules.
"""

from __future__ import annotations

import contextlib
import secrets

import argon2

from finpilot.schemas.errors import DomainValidationError, ErrorCode

# Standard OWASP / RFC 9106 Argon2id parameters
_ARGON2_TIME_COST = 3
_ARGON2_MEMORY_COST = 65536  # 64 MiB
_ARGON2_PARALLELISM = 4
_ARGON2_HASH_LEN = 32
_ARGON2_SALT_LEN = 16

_HASHER = argon2.PasswordHasher(
    time_cost=_ARGON2_TIME_COST,
    memory_cost=_ARGON2_MEMORY_COST,
    parallelism=_ARGON2_PARALLELISM,
    hash_len=_ARGON2_HASH_LEN,
    salt_len=_ARGON2_SALT_LEN,
    type=argon2.Type.ID,
)

# Common breached / trivial passwords blocklist (case-insensitive)
COMMON_PASSWORDS_BLOCKLIST: frozenset[str] = frozenset(
    {
        "password12345678",
        "passwordpassword",
        "123456789012345",
        "qwertyuiopasdfg",
        "administrator123",
        "correcthorsebatterystaple",
        "iloveyouiloveyou",
        "welcometofinpilot",
        "changeme12345678",
        "finpilot12345678",
        "adminadminadmin",
        "letmeinletmein12",
        "trustnoone123456",
        "sunshine1234567",
        "princess1234567",
        "dragon123456789",
        "football1234567",
        "monkey123456789",
        "shadow123456789",
        "master123456789",
    }
)


def hash_password(password: str) -> str:
    """Hash a plaintext password using Argon2id."""
    return _HASHER.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against an Argon2id hash in constant time."""
    try:
        return _HASHER.verify(hashed_password, plain_password)
    except (
        argon2.exceptions.VerifyMismatchError,
        argon2.exceptions.VerificationError,
        argon2.exceptions.InvalidHashError,
    ):
        return False


def check_needs_rehash(hashed_password: str) -> bool:
    """Check if the hash was created with older parameters and needs re-hashing."""
    try:
        return _HASHER.check_needs_rehash(hashed_password)
    except Exception:
        return True


needs_rehash = check_needs_rehash


def validate_password_policy(password: str, is_mfa_user: bool = False) -> None:
    """Validate password against NIST SP 800-63B-4 memorized secret requirements.

    NIST SP 800-63B-4 Requirements:
    1. Minimum Length:
       - Single-factor (password-only): At least 15 characters.
       - Multi-factor (password + MFA): At least 8 characters.
    2. Maximum Length:
       - Must permit at least 64 characters (we support up to 128 characters).
    3. No Arbitrary Composition Rules:
       - Do NOT require specific mixes of uppercase, lowercase, numbers, or symbols.
    4. Block Common / Compromised Passwords:
       - Compare against blocklist of breached and trivial passwords.
    """
    if not isinstance(password, str):
        raise DomainValidationError(
            "Password must be a string.", field="password", code=ErrorCode.VALIDATION_ERROR
        )

    min_length = 8 if is_mfa_user else 15
    max_length = 128

    if len(password) < min_length:
        msg = (
            f"Password must be at least {min_length} characters "
            f"({'MFA-enabled user' if is_mfa_user else 'single-factor password-only'})."
        )
        raise DomainValidationError(msg, field="password", code=ErrorCode.VALIDATION_ERROR)

    if len(password) > max_length:
        raise DomainValidationError(
            f"Password cannot exceed {max_length} characters.",
            field="password",
            code=ErrorCode.VALIDATION_ERROR,
        )

    # Check against breached / common passwords list (case-insensitive)
    lower_pwd = password.lower().strip()
    if lower_pwd in COMMON_PASSWORDS_BLOCKLIST:
        raise DomainValidationError(
            "This password is too common or easily guessable. Please choose a unique passphrase.",
            field="password",
            code=ErrorCode.VALIDATION_ERROR,
        )

    # Check for simple single-character repetitions across full length (e.g., "aaaaaaaaaaaaaaa")
    if len(set(password)) <= 2:
        raise DomainValidationError(
            "Password must not consist of repeated single characters.",
            field="password",
            code=ErrorCode.VALIDATION_ERROR,
        )


_DUMMY_ARGON2_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHQxMjM0NTY3OA$"
    "9Z5eS9QW4qV3r4j2X7t8Y1b2c3d4e5f6g7h8i9j0k1l"
)


def constant_time_dummy_verify() -> None:
    """Perform a dummy verification to mitigate timing attacks on nonexistent accounts."""
    with contextlib.suppress(Exception):
        _HASHER.verify(_DUMMY_ARGON2_HASH, secrets.token_hex(16))
