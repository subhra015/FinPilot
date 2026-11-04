# FinPilot AI — Production Threat Model & Attack Surface Analysis

**Document Version:** 1.0.0  
**Layer:** 17 of 17  
**Status:** ACTIVE / PRODUCTION  
**Governing Standard:** Microsoft STRIDE Threat Modeling & OWASP Top 10

---

## 1. System Trust Boundaries & Architecture

```
   [ UNTRUSTED INTERNET ]
            │
            ▼ (HTTPS:443 / TLS 1.3 only)
┌────────────────────────────────────────────────────────┐
│ Edge DMZ: Nginx Reverse Proxy (Non-Root UID 101)       │
│ - TLS Termination & Strict Cipher Negotiation          │
│ - Security Headers (HSTS, CSP, X-Frame-Options: DENY)  │
│ - Rate Limiting (15 req/sec burst limit)               │
│ - Static SPA Asset Delivery (React 19 / TypeScript)    │
└───────────────────────────┬────────────────────────────┘
                            │ (Internal Docker Network)
                            ▼ (HTTP:8000)
┌────────────────────────────────────────────────────────┐
│ Application Container: FastAPI Core (UID 10001)        │
│ - Unprivileged user 'finpilot' (Drop Capabilities ALL) │
│ - NIST SP 800-63B-4 Auth & Argon2id Password Hashing   │
│ - Opaque Server-Side Session Validation                │
│ - HMAC-SHA256 Double Submit Anti-CSRF Gate             │
│ - Independent Risk Evaluator & Capital Sizing Gate     │
│ - Execution Simulator (Zero Live Broker Routes)        │
└───────────────────────────┬────────────────────────────┘
                            │ (Loopback / Private TLS)
                            ▼
┌────────────────────────────────────────────────────────┐
│ Persistence Tier: Database & Append-Only Ledger        │
│ - SQLite WAL Mode / PostgreSQL with TLS (sslmode=req)  │
│ - Database Role Separation (App DML vs Migration DDL)  │
│ - SHA-256 Chained Immutable Audit & Prediction Ledger  │
│ - Cryptographically Verified Frozen Model Artifacts    │
└────────────────────────────────────────────────────────┘
```

---

## 2. Threat Actor Profiles

1. **External Anonymous Attacker:** Unauthenticated adversary attempting credential stuffing, brute-force guessing, SQL injection, reflected/stored XSS, or path traversal.
2. **Malicious Authenticated Tenant:** Low-privilege user attempting IDOR (viewing/manipulating other users' portfolios/orders), privilege escalation to admin risk controls, or CSRF exploitation.
3. **Compromised Operator / Rogue Process:** Attacker with limited container or host shell attempting container escape, secret extraction from environment, or ledger tampering.
4. **Adversarial / Corrupted Market Data Feed:** Malicious or failing market data provider transmitting stale prices, inverted candles, or extreme gap prices to trigger fraudulent executions.

---

## 3. STRIDE Threat Analysis & Implemented Mitigations

### 3.1 Spoofing (Identity Spoofing)
- **Threat:** Attacker impersonates an existing user or forges authentication tokens.
- **Mitigation:**
  - NIST SP 800-63B-4 compliant password policy (minimum 15 characters, no arbitrary composition requirements).
  - Argon2id password hashing (`m=65536, t=3, p=4`).
  - Opaque 32-byte CSPRNG session tokens stored in server-side DB/cache.
  - Session tokens transmitted solely via `HttpOnly; SameSite=Lax; Secure` cookies.
  - Idle timeout (15 minutes) and absolute session ceiling (8 hours) enforced server-side.

### 3.2 Tampering (Data & Logic Modification)
- **Threat:** Attacker modifies prediction records, tampers with model weights, or falsifies account cash.
- **Mitigation:**
  - Predictions recorded *before* market outcomes into an append-only ledger.
  - SHA-256 sequential hash chaining (`prev_hash + sequence + event_type + timestamp + payload`).
  - Double-entry accounting invariant: cash and positions only modify via verified `FillEvent` records.
  - Cryptographic verification of frozen model weights (`ede1e...`) and calibration policy at engine startup; fails closed if altered.

### 3.3 Repudiation (Denial of Actions)
- **Threat:** User or administrator denies executing a trade, updating risk limits, or triggering the kill switch.
- **Mitigation:**
  - Every administrative action generates an immutable `RiskConfigAuditEvent` capturing admin ID, timestamp, and field diffs.
  - All paper trading decisions, fills, and forced exits are logged with ISO 8601 UTC timestamps and persisted to the audit ledger.

### 3.4 Information Disclosure (Data Leakage)
- **Threat:** Attacker intercepts credentials, reads internal filesystem paths, or extracts database secrets from logs/errors.
- **Mitigation:**
  - Global FastAPI exception handlers sanitize all 500 error responses, suppressing tracebacks, SQL fragments, and paths.
  - `RedactingFormatter` automatically strips bearer tokens, DB connection strings, and passwords from log records.
  - Responses enforce `nosniff`, `no-referrer`, and strict `Content-Security-Policy`.
  - TLS 1.3 with forward secrecy enforced by Nginx.

### 3.5 Denial of Service (Resource Exhaustion)
- **Threat:** Attacker overwhelms authentication endpoints or uploads massive malicious files.
- **Mitigation:**
  - In-memory thread-safe `SlidingWindowRateLimiter` throttles authentication guesses (5 req/min) and data imports.
  - Nginx enforces edge request rate limiting (`15 req/sec` with burst `10`).
  - Strict 50 MB upload size limit and Parquet magic-byte (`PAR1`) header verification before memory allocation.
  - Docker container CPU and memory resource limits (`mem_limit: 1g`).

### 3.6 Elevation of Privilege (Unauthorized Access)
- **Threat:** Normal user executes administrative risk commands, or container process escapes to root host.
- **Mitigation:**
  - Server-side RBAC: admin endpoints explicitly require `require_admin` dependency; denies by default.
  - Multi-stage Dockerfile executes under dedicated unprivileged user `finpilot:10001:10001`.
  - Container drops all Linux capabilities (`cap_drop: [ALL]`), enables `no-new-privileges: true`, and mounts root filesystem read-only.
  - Absolute prohibition of real-money broker routing prevents financial liability.

---

## 4. Residual Risk Assessment

| Residual Risk | Impact | Likelihood | Compensating Operational Control |
| :--- | :---: | :---: | :--- |
| Single-Node Docker Outage | Low | Medium | Automated daily backups, rapid container restart via Docker Compose `restart: unless-stopped`. |
| SQLite File Lock Contention | Low | Low | Forward paper trading runs dedicated engine instances; production multi-user uses PostgreSQL. |
| External Market Data Outage | Low | Medium | Fail-closed stale data policy (>300s halts entries; existing protective exits remain active). |
