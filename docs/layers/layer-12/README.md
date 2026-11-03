# FinPilot AI — Layer 12 Report: Secure API, Authentication, Authorization & Audit Ledger

Status: **PASS**  
Completed: 2026-11-03  
Gate: `ACCEPTANCE_GATES.md` Layer 12 Gate  
Owning Packages: `backend/src/finpilot/auth/`, `backend/src/finpilot/ledger/`, `backend/src/finpilot/api/`  
Primary Security Controls: `SEC-01`, `SEC-02`, `SEC-05`, `SEC-06`, `SEC-08`, `SEC-09`, `SEC-10`, `SEC-11`, `SEC-12`, `SEC-13`, `SEC-15`, `SEC-16`, `SEC-17`, `SEC-24`  

---

## 1. Executive Summary & Scope Boundary

Layer 12 establishes the mandatory **Security Gate** before any user-facing or private API endpoints are exposed.

In accordance with strict project governance, security, and research contracts:
- **Production-Quality Authentication (`SEC-05`)**: Uses maintained and well-reviewed libraries (`argon2-cffi`). Implements Argon2id password hashing with recommended OWASP/RFC 9106 parameters (`time_cost=3`, `memory_cost=65536`, `parallelism=4`).
- **NIST SP 800-63B-4 Password Policy (`SEC-05`)**: Requires $\ge 15$ characters for password-only single-factor accounts; allows $\ge 8$ characters for MFA-enrolled accounts. Permits passphrases up to 128 characters. Prohibits arbitrary composition rules (no mandatory special characters or uppercase rules). Blocks common breached/guessable passwords and trivial single-character repetitions.
- **Opaque Server-Side Sessions (`SEC-15`)**: Issues high-entropy opaque tokens stored only as SHA-256 hashes (`session_id_hash`) in the database; raw tokens are NEVER stored in plaintext or database columns. Delivered to clients via `HttpOnly`, `Secure` (production), `SameSite=Lax` cookies. Enforces idle (30m) and absolute (12h) expiration with instant revocation on logout and password change.
- **Anti-Enumeration Generic Responses (`SEC-02`, `SEC-17`)**: Registration, login, and password reset endpoints return standardized responses and constant-time dummy verifications on nonexistent accounts to prevent timing attacks and account enumeration.
- **CSRF Protection & Origin Validation (`SEC-15`, `SEC-16`)**: Enforces session-bound HMAC-SHA256 CSRF tokens (`x-csrf-token` header) and strict `Origin`/`Referer` validation against the CORS allowlist on all state-changing endpoints (`POST`, `PUT`, `PATCH`, `DELETE`).
- **Sliding Window Rate Limiting (`SEC-12`)**: Thread-safe in-memory sliding window limiter protecting sensitive endpoints: login (5/min), registration (3/min), password reset (3/min), data import (10/min), and model inference (30/min).
- **Role-Based Access Control & IDOR Defense (`SEC-01`, `SEC-06`, `SEC-09`)**: Deny-by-default RBAC (`USER`, `ADMIN`, `SERVICE`). Explicit object ownership enforcement on all account and portfolio resources; prevents Insecure Direct Object References (IDOR).
- **Append-Only Cryptographic Audit Ledger (`SEC-08`, `SEC-19`)**: Append-only decision/outcome ledger recording all states (`ACCEPTED`, `NO_TRADE`, `INSUFFICIENT_DATA`, `RISK_REJECTED`, `ENTRY_UNFILLED`, `EXECUTION_UNRESOLVED`, `CORRECTION`, `OPPORTUNITY_OMITTED`, `PORTFOLIO_OUTCOME`, `HYPOTHETICAL_OUTCOME`). Sequential SHA-256 hash chaining ($H_n = \text{SHA256}(H_{n-1} \parallel \dots)$). Explicit `CORRECTION` records (never silent mutation in-place), full separation of hypothetical from paper portfolio accounting, and deterministic replay verification.

> [!NOTE]
> **Strict Layer Boundary**: Layer 12 implements the Secure API, Authentication, Authorization, and Audit Ledger ONLY. It does not scaffold frontend user interfaces (Layer 13) or live broker execution integrations.

---

## 2. Implementation Architecture & Module Overview

```
backend/
├── migrations/versions/
│   └── 0003_auth_and_audit_ledger.py # Alembic migration for users, sessions, resets, logs
├── src/finpilot/
│   ├── auth/                         # Core Authentication Package
│   │   ├── __init__.py               # Clean exports
│   │   ├── passwords.py              # Argon2id hashing, NIST SP 800-63B-4 policy, dummy verify
│   │   ├── mfa.py                    # RFC 6238 TOTP engine & WebAuthn contract schemas
│   │   ├── sessions.py               # Opaque session tokens, SHA-256 storage, idle/absolute expiry
│   │   ├── csrf.py                   # HMAC-SHA256 CSRF tokens & Origin allowlist enforcement
│   │   ├── rate_limiter.py           # Thread-safe sliding window rate limiter & error types
│   │   └── service.py                # High-level AuthService coordinating auth lifecycle
│   ├── ledger/                       # Append-Only Audit Ledger Package
│   │   ├── __init__.py               # Clean exports
│   │   ├── models.py                 # Pydantic V2 schemas (LedgerEventPayload, ReplayResult)
│   │   └── service.py                # AuditLedgerService with SHA-256 chaining & deterministic replay
│   └── api/                          # Secure API Routers & Dependencies
│       ├── __init__.py               # Clean router exports
│       ├── dependencies.py           # get_db, get_current_user, require_admin, require_csrf, IDOR checks
│       ├── auth_router.py            # /api/auth (register, login, mfa, logout, me, reset)
│       ├── account_router.py         # /api/accounts (scoped to authenticated user)
│       ├── portfolio_router.py       # /api/portfolios (scoped to authenticated user)
│       ├── ledger_router.py          # /api/ledger (events and replay)
│       ├── risk_router.py            # /api/risk (config, kill switch, audit logs; admin only)
│       └── model_router.py           # /api/models (approved models registry)
```

---

## 3. Database Schema & Migration (`0003_auth_and_audit_ledger.py`)

The persistence tier was extended with complete Alembic forward and backward migrations:

1. **`users` Table**:
   - `id`: Primary key (autoincrement).
   - `user_id`: Stable alphanumeric identifier (`USR-...`, unique, indexed).
   - `email`: Normalized lowercase email (unique, indexed).
   - `password_hash`: Argon2id PHC format string (`$argon2id$...`, $\ge 64$ bytes).
   - `role`: Authorization role (`USER`, `ADMIN`, `SERVICE`).
   - `is_active`: Boolean kill-switch flag.
   - `mfa_enabled`: Mandatory `True` for admins before session issuance; optional for users.
   - `mfa_secret`: RFC 4648 Base32 encrypted/masked secret for TOTP.
   - `created_at`, `updated_at`: Timezone-aware UTC timestamps.
2. **`user_sessions` Table**:
   - `id`: Primary key.
   - `session_id_hash`: SHA-256 digest of the opaque token (64 hex characters, unique, indexed).
   - `user_id`: Foreign key to `users.id` (cascade delete on account removal).
   - `created_at`, `expires_at`, `last_active_at`: Timezone-aware timestamps for absolute and idle timeout enforcement.
   - `is_revoked`: Instant invalidation flag.
   - `ip_address`, `user_agent`: Security audit metadata.
3. **`password_reset_tokens` Table**:
   - `id`: Primary key.
   - `token_hash`: SHA-256 digest of single-use high-entropy token (64 hex characters, unique).
   - `user_id`: Foreign key to `users.id`.
   - `expires_at`: 15-minute absolute lifetime.
   - `is_used`: Replay prevention flag.
4. **`security_audit_logs` Table**:
   - `id`: Primary key.
   - `event_id`: Unique identifier (`SEC-EVT-...`).
   - `event_type`: Security classification (`AUTH_LOGIN_SUCCESS`, `AUTH_LOGIN_FAILED`, `ACCESS_DENIED_IDOR`, etc.).
   - `user_id`: Optional user ID.
   - `ip_address`, `user_agent`: Request metadata.
   - `details`: Sanitized JSON metadata with all secrets redacted.
5. **`accounts` Table Enhancement**:
   - Added `user_id`: Foreign key to `users.id` with `RESTRICT` on delete, establishing strict resource ownership (`SEC-06`).

---

## 4. Authentication Architecture & NIST SP 800-63B-4 Compliance

### Argon2id Password Hashing
- Library: `argon2-cffi` (maintained CFFI bindings to reference Argon2 library).
- Parameters: `time_cost=3`, `memory_cost=65536` (64 MiB), `parallelism=4`, `hash_len=32`, `salt_len=16`.
- Mitigates GPU-accelerated and ASIC offline brute-force attacks.

### NIST SP 800-63B-4 Memorized Secret Policy
1. **Length Boundaries**:
   - Single-factor (password only): $\ge 15$ characters.
   - Multi-factor (password + MFA): $\ge 8$ characters.
   - Maximum permitted length: At least 64 characters (FinPilot permits up to 128 characters).
2. **No Arbitrary Composition Rules**:
   - No requirements for mandatory uppercase, lowercase, digits, or symbols (e.g. `correct horse battery staple` is accepted).
3. **Blocklist Comparison**:
   - Checked against common breached, sequential, and trivial passphrases (`COMMON_PASSWORDS_BLOCKLIST`).
   - Rejects single-character repetitions across length (e.g. `aaaaaaaaaaaaaaaa`).
4. **Anti-Enumeration & Timing Attack Mitigation**:
   - Generic login failure responses (`"Invalid email or password."`).
   - Constant-time dummy Argon2id verification (`constant_time_dummy_verify()`) when account does not exist to prevent timing side-channel account enumeration.

---

## 5. Session Management & CSRF Defense

1. **Opaque Server-Side Sessions (`SEC-15`)**:
   - High-entropy cryptographic random token generation: `secrets.token_urlsafe(32)`.
   - Token is hashed with SHA-256 before storage (`session_id_hash`). The raw token is **never** written to database disk or logs.
   - Cookie Flags: `HttpOnly`, `SameSite=Lax`, `Secure` in production, `Path=/`.
   - Storage in browser: Never accessible to JavaScript; completely immune to `localStorage`/`sessionStorage` token exfiltration via XSS.
2. **Session Rotation**:
   - `rotate_session()` issues a new session ID and revokes the previous session upon login and privilege elevation, preventing session fixation attacks.
3. **Dual Timeout Enforcement**:
   - **Idle Timeout**: 1,800 seconds (30 minutes). Session is rejected if `now - last_active_at > 1800s`.
   - **Absolute Timeout**: 43,200 seconds (12 hours). Session is permanently expired regardless of activity.
4. **Instant Revocation**:
   - `logout()` sets `is_revoked = True` in the database and overwrites cookies with empty values.
   - Password reset immediately invokes `revoke_all_user_sessions()` across all active devices.
5. **Anti-CSRF Defense (`SEC-16`)**:
   - Session-bound HMAC-SHA256 CSRF tokens: $\text{HMAC-SHA256}(\text{session\_id\_hash}, \text{secret\_key})$.
   - Delivered in `finpilot_csrf` cookie (readable by JS) and required in `X-CSRF-Token` header on all mutating requests (`POST`, `PUT`, `PATCH`, `DELETE`).
   - Strict `Origin` and `Referer` validation against the configured `cors_allowed_origins` allowlist.

---

## 6. Authorization Model & Object-Level Access Control (SEC-06)

FinPilot implements a deny-by-default Role-Based Access Control (RBAC) model:

| Role | Permitted Actions |
|---|---|
| `USER` | View own accounts, own portfolios, execute self-scoped simulation queries, update own profile. |
| `ADMIN` | All `USER` permissions plus emergency kill-switch activation, risk configuration updates, system audit logs, and replay verification. Requires mandatory MFA. |
| `SERVICE` | Internal automated services executing within local process boundaries. |

### Insecure Direct Object Reference (IDOR) Defense
- `enforce_resource_ownership(db, user, resource_type, resource_id)` checks that the resource's `user_id` matches the authenticated `current_user.id`.
- If User A attempts to request `/api/accounts/{account_b_id}` or `/api/portfolios/{portfolio_b_id}`, the request is rejected with `403 Forbidden` (`PermissionDeniedError`) and logged to `security_audit_logs` (`ACCESS_DENIED_IDOR`).

---

## 7. Append-Only Audit Ledger & Deterministic Replay

The append-only audit ledger (`AuditLedgerService`) records every decision, simulation step, and outcome:

```
[Genesis: 000...000]
        │
        ▼
[Event 1: Seq 1] ── integrity_hash = SHA256(prev_hash | seq | type | ts | payload)
        │
        ▼
[Event 2: Seq 2] ── prev_hash = Event 1 integrity_hash
        │
        ▼
[Event 3: Seq 3] ── prev_hash = Event 2 integrity_hash
```

### Governance Rules:
1. **Append-Only Immutability**: Existing rows are never updated or deleted.
2. **Explicit Corrections (`CORRECTION`)**: Errors or reconciliations are appended as new audit records with `prior_event_id` and `correction_reason`. Silent mutation is structurally impossible.
3. **Hypothetical Isolation (`is_hypothetical=True`)**: Counterfactual model predictions and unselected baseline outcomes are recorded with `is_hypothetical=True`. During replay, these do not touch paper cash or portfolio positions.
4. **Idempotency**: Duplicate submissions of identical `event_id` and payload return the existing record cleanly. Submitting a conflicting payload for an existing `event_id` raises `DomainValidationError(CONFLICT)`.
5. **Deterministic Replay**: `replay_ledger()` iterates through all recorded events, recalculates SHA-256 hashes, verifies sequential linkage, and reconstructs exact portfolio balances. Flags `tamper_detected=True` if any bit in the database was modified.

---

## 8. Verification & Test Evidence

All security controls and API endpoints were verified through 6 dedicated test suites:

| Test Suite | Focus Area | Tests | Status |
|---|---|---|---|
| `test_auth_passwords_nist.py` | NIST SP 800-63B-4 policy, Argon2id, timing defense | 8 | **PASS** |
| `test_auth_sessions_security.py` | Opaque sessions, SHA-256 storage, idle/absolute timeouts, rotation, revocation | 7 | **PASS** |
| `test_auth_mfa_totp.py` | RFC 6238 TOTP, Base32 secrets, time drift $\pm 1$ step, otpauth URI | 6 | **PASS** |
| `test_auth_csrf_and_rate_limiting.py` | HMAC CSRF tokens, Origin allowlist, sliding window rate limiter | 5 | **PASS** |
| `test_audit_ledger_security.py` | Append-only ledger, SHA-256 chaining, tamper detection, corrections, replay | 6 | **PASS** |
| `test_api_auth_acceptance.py` | Unauthenticated 401, registration/login, cross-user IDOR 403, CSRF 403, SQLi safety | 6 | **PASS** |
| `test_app_security.py` | Security headers, CSP frame-ancestors, nosniff, production HSTS, CORS | 5 | **PASS** |

### Test Execution Summary:
- **Unit & Security Domain Tests**: 335 passed in 30.73s (clean sandbox execution).
- **API & HTTP Acceptance Tests**: 11 passed (5 in `test_app_security.py` + 6 in `test_api_auth_acceptance.py`).
- **Total Passing Tests**: **346 tests passed, 0 failures**.
- **Static Typing & Linting**: `ruff check backend` (0 errors), `mypy backend/src` (0 errors across 91 source files).

---

## 9. Security Checklist & Acceptance Gate Status

| Security Control | Description | Status in Layer 12 |
|---|---|---|
| `SEC-01` | Strong MFA (RFC 6238 TOTP mandatory for admins; WebAuthn contract) | **VERIFIED** |
| `SEC-02` | Anti-enumeration generic login/reset responses | **VERIFIED** |
| `SEC-05` | NIST SP 800-63B-4 password policy & Argon2id hashing | **VERIFIED** |
| `SEC-06` | Parameterized queries & object ownership (IDOR defense) | **VERIFIED** |
| `SEC-08` | Append-only audit logging & sequential SHA-256 hash chaining | **VERIFIED** |
| `SEC-09` | Role-based access control (deny-by-default `USER`, `ADMIN`, `SERVICE`) | **VERIFIED** |
| `SEC-10` | Request body validation & schema constraints | **VERIFIED** |
| `SEC-11` | Secret redaction in logs & security audit events | **VERIFIED** |
| `SEC-12` | Sliding window rate limiting on sensitive endpoints | **VERIFIED** |
| `SEC-13` | Security headers (CSP, nosniff, deny frame-ancestors) | **VERIFIED** |
| `SEC-15` | Opaque server-side sessions in `HttpOnly, Secure, SameSite` cookies | **VERIFIED** |
| `SEC-16` | Anti-CSRF tokens & Origin header validation | **VERIFIED** |
| `SEC-17` | Single-use password reset tokens with SHA-256 hashed storage | **VERIFIED** |
| `SEC-24` | Comprehensive automated security test suites | **VERIFIED** |

Layer 12 Gate Status: **PASS**  
Next Gate: **Layer 13 (User Interface & Interactive Workflows)** — Mandatory human approval required before proceeding.
