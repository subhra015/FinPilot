"""NIST SP 800-63B-4 password policy and Argon2id security tests (SEC-05, Layer 12).

Governed by:
- NIST SP 800-63B §5.1.1.2 (Memorized Secret Authenticator Requirements)
- SECURITY_CHECKLIST.md SEC-05, SEC-06
- Layer 12 Gate: Password policy, Argon2id hashing, no arbitrary rules.
"""

from __future__ import annotations

import pytest

from finpilot.auth.passwords import (
    constant_time_dummy_verify,
    hash_password,
    needs_rehash,
    validate_password_policy,
    verify_password,
)
from finpilot.schemas.errors import DomainValidationError


def test_nist_password_length_single_factor():
    """NIST SP 800-63B requires at least 15 characters for single-factor passwords."""
    # Under 15 chars must fail for single-factor
    with pytest.raises(DomainValidationError, match="at least 15 characters"):
        validate_password_policy("shortpass1234", is_mfa_user=False)

    with pytest.raises(DomainValidationError, match="at least 15 characters"):
        validate_password_policy("14characters!!", is_mfa_user=False)

    # Exactly 15 chars valid
    validate_password_policy("correct horse b", is_mfa_user=False)
    # > 15 chars valid
    validate_password_policy("correct-horse-battery-staple-2026", is_mfa_user=False)


def test_nist_password_length_mfa_user():
    """NIST SP 800-63B allows at least 8 characters if passwords are used with MFA."""
    # Under 8 chars must fail even for MFA users
    with pytest.raises(DomainValidationError, match="at least 8 characters"):
        validate_password_policy("short12", is_mfa_user=True)

    # 8 chars valid for MFA user
    validate_password_policy("mfa-pass", is_mfa_user=True)
    validate_password_policy("valid8ch", is_mfa_user=True)


def test_nist_no_arbitrary_composition_rules():
    """NIST SP 800-63B prohibits arbitrary composition rules (no mandatory special chars)."""
    # Pure lowercase passphrase with spaces/dashes is accepted
    validate_password_policy("correct horse battery staple", is_mfa_user=False)
    # Pure numbers (if not repeated) is accepted if long enough
    validate_password_policy("83920194857201847", is_mfa_user=False)


def test_nist_max_length_at_least_64():
    """NIST SP 800-63B requires permitting passwords up to at least 64 characters."""
    # 64 chars must be accepted
    pwd_64 = "abcdefg" * 9 + "h"
    validate_password_policy(pwd_64, is_mfa_user=False)

    # 128 chars accepted
    pwd_128 = "abcdefghijklmnop" * 8
    validate_password_policy(pwd_128, is_mfa_user=False)

    # Over 128 chars rejected to prevent DoS
    with pytest.raises(DomainValidationError, match="cannot exceed 128 characters"):
        validate_password_policy("z" * 129, is_mfa_user=False)


def test_blocklist_common_passwords():
    """Common breached/guessable passwords must be blocked."""
    with pytest.raises(DomainValidationError, match="too common"):
        validate_password_policy("password12345678", is_mfa_user=False)

    with pytest.raises(DomainValidationError, match="too common"):
        validate_password_policy("PASSWORD12345678", is_mfa_user=False)

    with pytest.raises(DomainValidationError, match="too common"):
        validate_password_policy("123456789012345", is_mfa_user=False)


def test_single_character_repetition_rejected():
    """Trivial passwords like 'aaaaaaaaaaaaaaa' must be rejected."""
    with pytest.raises(DomainValidationError, match="repeated single characters"):
        validate_password_policy("aaaaaaaaaaaaaaaa", is_mfa_user=False)

    with pytest.raises(DomainValidationError, match="repeated single characters"):
        validate_password_policy("abababababababab", is_mfa_user=False)


def test_argon2id_hashing_and_verification():
    """Verify Argon2id produces valid hashes and verifies correctly."""
    password = "correct-horse-battery-staple-2026"
    pw_hash = hash_password(password)

    # Check hash structure: standard Argon2id prefix
    assert pw_hash.startswith("$argon2id$v=19$m=65536,t=3,p=4$")

    # Correct password verifies
    assert verify_password(password, pw_hash) is True

    # Incorrect password fails
    assert verify_password("wrong-horse-battery-staple-2026", pw_hash) is False
    assert verify_password("", pw_hash) is False

    # Check needs_rehash is False for standard parameters
    assert needs_rehash(pw_hash) is False


def test_constant_time_dummy_verify():
    """Verify dummy verification executes without raising exceptions."""
    # Should complete cleanly without error
    constant_time_dummy_verify()
