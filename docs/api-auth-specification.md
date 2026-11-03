# FinPilot AI — API & Authentication Technical Specification

Version: 1.0.0  
Last Updated: 2026-11-03  
Governed by: `SECURITY_CHECKLIST.md` (SEC-01, SEC-02, SEC-05, SEC-06, SEC-08, SEC-09, SEC-10, SEC-11, SEC-12, SEC-15, SEC-16, SEC-17), NIST SP 800-63B-4, RFC 6238, RFC 9106.

---

## 1. Overview & Security Architecture

FinPilot exposes a RESTful JSON API designed under a zero-trust, defense-in-depth architecture:
- **Authentication**: Opaque, server-side sessions stored exclusively as SHA-256 hashes in the persistence tier. Raw tokens are delivered in `HttpOnly, Secure, SameSite=Lax` cookies. Tokens are NEVER stored in browser `localStorage`, `sessionStorage`, or client-accessible caches.
- **Authorization**: Deny-by-default Role-Based Access Control (`USER`, `ADMIN`, `SERVICE`) with strict object-level ownership checks (IDOR mitigation).
- **Password Security**: Argon2id password hashing (`time_cost=3`, `memory_cost=65536`, `parallelism=4`) adhering strictly to NIST SP 800-63B-4 guidelines.
- **Multi-Factor Authentication (MFA)**: Mandatory for administrative accounts; RFC 6238 TOTP (6-digit numeric, 30s epoch step, $\pm 1$ step drift allowance) and phishing-resistant WebAuthn passkey contracts.
- **CSRF Defense**: Session-bound HMAC-SHA256 tokens (`X-CSRF-Token` header) coupled with strict `Origin` and `Referer` allowlist matching for all state-changing HTTP methods.
- **Rate Limiting**: Sliding window rate limiter enforcing per-IP thresholds on authentication, data import, and machine learning inference endpoints.
- **Append-Only Audit Ledger**: Sequential SHA-256 cryptographic hash chaining guaranteeing tamper-evidence and reproducible deterministic replay.

---

## 2. Cookie & Header Contracts

### Cookies

| Cookie Name | Scope | HttpOnly | Secure | SameSite | Lifetime | Description |
|---|---|---|---|---|---|---|
| `finpilot_session` | `/` | **Yes** | **Yes** (Prod) | `Lax` | 12 hours (Absolute), 30 min (Idle) | Opaque cryptographic bearer token. Contains high-entropy random bits (`secrets.token_urlsafe(32)`). |
| `finpilot_csrf` | `/` | **No** | **Yes** (Prod) | `Lax` | 12 hours | Session-bound HMAC-SHA256 anti-CSRF token read by JavaScript to include in request headers. |

### Request Headers

| Header | Required For | Format | Description |
|---|---|---|---|
| `X-CSRF-Token` | State-changing requests (`POST`, `PUT`, `PATCH`, `DELETE`) with session cookie | 64-char Hex | Must match $\text{HMAC-SHA256}(\text{session\_id\_hash}, \text{secret\_key})$. |
| `Origin` | State-changing requests | `http(s)://domain[:port]` | Must match an entry in `cors_allowed_origins`. |
| `Content-Type` | Requests with JSON payload | `application/json` | Required for body parsing. |

### Response Security Headers
Every API response includes the mandatory security headers:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: no-referrer`
- `Content-Security-Policy: default-src 'none'; frame-ancestors 'none';`
- `Permissions-Policy: payment=()`
- `Strict-Transport-Security: max-age=31536000; includeSubDomains` (Production only)

---

## 3. NIST SP 800-63B-4 Password Policy

FinPilot aligns directly with NIST Special Publication 800-63B §5.1.1.2:

1. **Length Requirements**:
   - Single-Factor Accounts (password-only): Minimum **15 characters**.
   - Multi-Factor Accounts (password + MFA): Minimum **8 characters**.
   - Maximum Permitted Length: At least 64 characters; FinPilot accepts up to **128 characters**.
2. **Prohibition of Arbitrary Composition Rules**:
   - The system does **not** mandate combinations of uppercase letters, lowercase letters, digits, or special characters. Long natural-language passphrases (e.g. `correct horse battery staple`) are fully valid and encouraged.
3. **Blocklist Enforcement**:
   - Passwords are checked against a blocklist of compromised and commonly guessable passwords (`COMMON_PASSWORDS_BLOCKLIST`).
   - Trivial single-character repetitions across the entire password (e.g. `aaaaaaaaaaaaaaaa`) are rejected.
4. **Offline Cracking Resistance (Argon2id)**:
   - Algorithm: Argon2id (`argon2.Type.ID`, version 19).
   - Time Cost ($t$): 3 iterations.
   - Memory Cost ($m$): 65,536 KiB (64 MiB).
   - Parallelism ($p$): 4 threads.
   - Salt Length: 16 bytes cryptographically secure random.
   - Hash Output Length: 32 bytes.
5. **Anti-Enumeration Protections**:
   - Responses for nonexistent accounts return generic authentication failure messages.
   - `constant_time_dummy_verify()` is executed on failed account lookups to eliminate timing differentials between existent and nonexistent accounts.

---

## 4. Multi-Factor Authentication (RFC 6238 TOTP & WebAuthn)

### TOTP Implementation
- Algorithm: HMAC-SHA1 per RFC 6238.
- Secret: 32-character RFC 4648 Base32 string (160-bit high-entropy secret).
- Code Length: 6 decimal digits.
- Time Step: 30 seconds.
- Drift Window: $\pm 1$ step (permits verification at $T-1$, $T$, and $T+1$ to tolerate 30-second clock drift).
- URI Format: `otpauth://totp/FinPilot%20AI:<email>?secret=<secret>&issuer=FinPilot%20AI&algorithm=SHA1&digits=6&period=30`.

### WebAuthn Passkey Contract (FIDO2)
FinPilot supports phishing-resistant passkeys using the standard W3C WebAuthn Level 3 specification:
- RP ID: Configured domain (default `localhost`).
- User Verification: `preferred` / `required`.
- Supported Algorithms: ES256 (-7) and RS256 (-257).
- Attestation: Direct or none.

---

## 5. Rate Limiting Specification

Thread-safe sliding window rate limiting is enforced per client IP address:

| Endpoint Group | Max Requests | Window | Key Identifier | Action on Breach |
|---|---|---|---|---|
| `POST /api/auth/login` | 5 | 60 sec | `login:<ip>` | 403 Forbidden with `Retry-After` |
| `POST /api/auth/register` | 3 | 60 sec | `register:<ip>` | 403 Forbidden with `Retry-After` |
| `POST /api/auth/reset-password-request` | 3 | 60 sec | `reset_request:<ip>` | 403 Forbidden with `Retry-After` |
| Data Import Endpoints | 10 | 60 sec | `import:<ip>` | 429 Too Many Requests |
| ML Inference & Replay Endpoints | 30 | 60 sec | `inference:<user_id>` | 429 Too Many Requests |

---

## 6. Endpoints Reference

### Authentication Endpoints (`/api/auth`)

#### `POST /api/auth/register`
- **Access**: Public (Rate-limited: 3/min).
- **Request Body**:
  ```json
  {
    "email": "user@finpilot.test",
    "password": "correct-horse-battery-staple-2026",
    "role": "USER"
  }
  ```
- **Response (201 Created)**:
  ```json
  {
    "user_id": "USR-ABC123XYZ789",
    "email": "user@finpilot.test",
    "role": "USER",
    "mfa_enabled": false,
    "created_at": "2026-11-03T22:00:00Z"
  }
  ```

#### `POST /api/auth/login`
- **Access**: Public (Rate-limited: 5/min).
- **Request Body**:
  ```json
  {
    "email": "user@finpilot.test",
    "password": "correct-horse-battery-staple-2026"
  }
  ```
- **Response (200 OK — Direct Login)**:
  Sets `finpilot_session` and `finpilot_csrf` cookies.
  ```json
  {
    "user": {
      "user_id": "USR-ABC123XYZ789",
      "email": "user@finpilot.test",
      "role": "USER",
      "mfa_enabled": false,
      "created_at": "2026-11-03T22:00:00Z"
    },
    "mfa_required": false,
    "csrf_token": "a1b2c3..."
  }
  ```
- **Response (200 OK — MFA Required)**:
  ```json
  {
    "user": {
      "user_id": "USR-ADMIN01",
      "email": "admin@finpilot.test",
      "role": "ADMIN",
      "mfa_enabled": true,
      "created_at": "2026-11-03T22:00:00Z"
    },
    "mfa_required": true,
    "csrf_token": null
  }
  ```

#### `POST /api/auth/mfa/verify-login`
- **Access**: Public (Rate-limited: 5/min).
- **Request Body**:
  ```json
  {
    "user_id": "USR-ADMIN01",
    "totp_code": "123456"
  }
  ```
- **Response (200 OK)**:
  Validates 6-digit TOTP code, establishes session, sets `finpilot_session` and `finpilot_csrf` cookies.

#### `POST /api/auth/mfa/setup`
- **Access**: Authenticated User.
- **Response (200 OK)**:
  ```json
  {
    "secret": "JBSWY3DPEHPK3PXP...",
    "otpauth_uri": "otpauth://totp/FinPilot%20AI:user@finpilot.test?..."
  }
  ```

#### `POST /api/auth/mfa/verify`
- **Access**: Authenticated User.
- **Request Body**: `{"totp_code": "123456"}`
- **Response (200 OK)**: Enables MFA on the account.

#### `POST /api/auth/logout`
- **Access**: Authenticated User (Requires CSRF).
- **Response (200 OK)**:
  Revokes session in database, clears session and CSRF cookies.

#### `GET /api/auth/me`
- **Access**: Authenticated User.
- **Response (200 OK)**: Returns authenticated user profile.

---

### Account & Portfolio Endpoints (`/api/accounts`, `/api/portfolios`)

All account and portfolio routes enforce object ownership (`SEC-06`):
- `GET /api/accounts`: Returns accounts owned by the authenticated user.
- `GET /api/accounts/{account_id}`: Returns account details if owned by caller; otherwise returns `403 Forbidden`.
- `GET /api/portfolios`: Returns portfolios belonging to caller's accounts.
- `GET /api/portfolios/{portfolio_id}`: Returns portfolio details if owned by caller; otherwise returns `403 Forbidden`.
- `GET /api/portfolios/{portfolio_id}/positions`: Returns active positions for the portfolio.

---

### Append-Only Ledger Endpoints (`/api/ledger`)

#### `POST /api/ledger/events`
- **Access**: Authenticated User (Requires CSRF).
- **Request Body**: `LedgerEventPayload`.
- **Response (201 Created / 200 OK)**:
  Idempotent recording with SHA-256 sequential hash chaining.

#### `POST /api/ledger/replay`
- **Access**: Authenticated User / Admin.
- **Query Parameters**: `mode=HISTORICAL_REPLAY`, `verify_hash_chain=true`.
- **Response (200 OK)**:
  ```json
  {
    "is_valid": true,
    "events_replayed": 1420,
    "corrections_applied": 2,
    "chain_verified": true,
    "reconstructed_cash": "31450.80",
    "reconstructed_positions": {"RELIANCE": 10},
    "reconstructed_realized_pnl": "1450.80",
    "hypothetical_realized_pnl": "0.00",
    "tamper_detected": false,
    "tamper_details": []
  }
  ```

---

### Risk Administration Endpoints (`/api/risk`)

All risk endpoints strictly require role `ADMIN` (`SEC-09`):
- `GET /api/risk/config`: Retrieves active `RiskConfig` parameters.
- `POST /api/risk/kill-switch`: Engages or disengages global emergency kill switch.
- `GET /api/risk/audit-log`: Returns signed configuration mutation audit events.

---

## 7. Append-Only Ledger Cryptographic Specification

Every event record links sequentially to its predecessor:

$$\text{prev\_hash}_1 = \text{"0"} \times 64$$

$$\text{integrity\_hash}_n = \text{SHA-256}\left(\text{prev\_hash}_n \parallel \text{seq}_n \parallel \text{type}_n \parallel \text{ts}_n \parallel \text{canonical\_payload}_n\right)$$

$$\text{prev\_hash}_{n+1} = \text{integrity\_hash}_n$$

Where:
- $\text{canonical\_payload}_n$ is the deterministic JSON serialization (keys sorted alphabetically, whitespace stripped: `json.dumps(obj, sort_keys=True, separators=(',', ':'))`).
- Replay verification recalculates $\text{integrity\_hash}_n$ over stored payloads and compares sequentially. Any database bit flip or deletion breaks the chain and triggers `tamper_detected = True`.
