# FinPilot AI — Layer 17: Security Hardening, Production Deployment & CV Release

**Implementation Status:** COMPLETE  
**Layer:** 17 of 17 (Final Release Layer)  
**Date:** 2026-11-04  
**Author:** Subhranshu Sekhar Sahoo  
**Market:** Indian NSE Cash Equities  
**Execution Mode:** Research and Paper Trading ONLY  
**Real-Money Execution:** STRICTLY PROHIBITED  

---

## 1. Executive Summary & Operating Boundary Statement

FinPilot AI Layer 17 serves as the final security hardening, operational readiness, and release packaging layer for the FinPilot AI platform. 

### Core Operating Boundary
> **STRICT BOUNDARY:** FinPilot AI is an empirical quantitative research platform and simulated paper trading system engineered specifically for Indian NSE cash equities. Real-money trading, live broker API connectivity, and automated order routing to financial exchanges are **STRICTLY PROHIBITED** and absent from the codebase. All trade proposals, position updates, and executions are virtual and evaluated under a simulated ₹30,000 cash portfolio.

---

## 2. Preimplementation Gate Verification

Prior to implementing Layer 17, all preconditions defined in the Layer 17 specification were verified:
1. **Layer 14 Simulator/Security Challenge Suite:** 17 of 17 tests passed (verified in commit `b7a14c`).
2. **Layer 15 Locked Historical Evaluation:** Approved and committed directly by human user in commit `061c79a`.
3. **Layer 16 Forward Paper Trading Validation:** Approved and committed directly by human user in commit `e67e972`.
4. **Frozen Model Artifact Integrity:** Verified SHA-256 digest `ede1e29783917673f44b68e72e62f446b96972feb741627539f52c2a2c455bfb` matches across Layer 15, Layer 16, and Layer 17 manifests.
5. **Data Provider Permissions:** Documented open academic/synthetic license for research evaluation.
6. **Zero Live Broker Routes:** Verified absence of broker SDKs (Zerodha KiteConnect, Upstox, Angel One, etc.).

---

## 3. Security Audit Results (SEC-01 through SEC-27)

All 27 mandatory security controls defined in `SECURITY_CHECKLIST.md` were independently verified against automated test suites and runtime environments:

| Control ID | Control Name | Status | Verified Test Reference |
| :--- | :--- | :---: | :--- |
| **SEC-01** | Authentication & RBAC | **PASS** | `test_01_unauthenticated_api_requests`, `test_06_privilege_escalation_blocked` |
| **SEC-02** | Credential & Secret Management | **PASS** | `test_20_git_history_no_secrets`, `test_18_secret_exposure_blocked_in_api` |
| **SEC-03** | Database Least Privilege & Encryption | **PASS** | `test_21_database_least_privilege_enforced`, `test_17_env_var_validation_fail_closed` |
| **SEC-04** | Input Boundary Validation | **PASS** | `test_14_oversized_uploads_rejected`, `test_15_malformed_file_content_rejected` |
| **SEC-05** | Output Encoding & Injection Defense | **PASS** | `test_08_sql_injection_defense`, `test_09_reflected_xss_defense`, `test_10_stored_xss_neutralized` |
| **SEC-06** | Safe Error Handling & Masking | **PASS** | `test_29_production_error_leakage_masked` |
| **SEC-07** | Production Diagnostic Protection | **PASS** | `test_28_debug_endpoints_disabled_in_production` |
| **SEC-08** | Secret Leakage Redaction in Logs | **PASS** | `test_19_secret_leakage_redaction_in_logs` |
| **SEC-09** | Administrative Authorization & Governance | **PASS** | `test_07_unauthorized_admin_requests_blocked` |
| **SEC-10** | SQL Parameterization | **PASS** | `test_08_sql_injection_defense` |
| **SEC-11** | Startup Configuration Validation | **PASS** | `test_17_env_var_validation_fail_closed` |
| **SEC-12** | Sliding Window Rate Limiting | **PASS** | `test_13_rate_limiting_enforced` |
| **SEC-13** | HTTP Security Headers | **PASS** | `test_30_security_headers_present` |
| **SEC-14** | Transport Layer Security (HSTS) | **PASS** | `test_app_security.py::test_hsts_present_in_production` |
| **SEC-15** | Secure Session Architecture | **PASS** | `test_02_invalid_authentication_tokens`, `test_03_session_expiry_enforced`, `test_04_session_invalidation_on_logout` |
| **SEC-16** | Anti-CSRF Token Enforcement | **PASS** | `test_11_csrf_protection_enforced` |
| **SEC-17** | Password Policy & Argon2id Hashing | **PASS** | `test_auth_passwords_nist.py::test_password_policy_nist_compliance` |
| **SEC-18** | Data Boundary & Rights Verification | **PASS** | `test_data_rights.py::test_commercial_redistribution_rejected` |
| **SEC-19** | Immutable Prediction Audit Ledger | **PASS** | `test_22_audit_ledger_tamper_detection`, `test_23_duplicate_execution_events_rejected` |
| **SEC-20** | Environment Separation & Isolation | **PASS** | `test_17_env_var_validation_fail_closed`, `test_28_debug_endpoints_disabled_in_production` |
| **SEC-21** | Model Artifact Cryptographic Freeze | **PASS** | `test_26_model_hash_mismatch_fails_closed`, `test_27_model_config_mismatch_fails_closed` |
| **SEC-22** | Independent Risk Gate Governance | **PASS** | `test_risk_model_cannot_bypass.py::test_model_cannot_bypass_risk_evaluator` |
| **SEC-23** | Double-Entry Accounting Invariant | **PASS** | `test_24_unauthorized_cash_modification_blocked`, `test_25_unauthorized_position_modification_blocked` |
| **SEC-24** | In-Memory Token & Secret Wiping | **PASS** | `test_18_secret_exposure_blocked_in_api` |
| **SEC-25** | Container Non-Root Hardening | **PASS** | `test_31_container_non_root_execution` |
| **SEC-26** | Network Port & Socket Isolation | **PASS** | `test_32_container_port_exposure_restricted` |
| **SEC-27** | Disaster Recovery & Backup Integrity | **PASS** | `test_33_backup_restoration_verified`, `test_34_restart_recovery_ledger_reconciliation` |

*Complete audit details with execution commands and logs are documented in [security-audit.md](security-audit.md).*

---

## 4. FinPilot-Specific Security Controls Verification

1. **Zero Real-Money Execution:** Verified by `test_35`. The codebase contains no broker routing logic or API keys.
2. **Model Integrity:** Verified by `test_26` and `test_27`. The forward engine cryptographically verifies model binary and calibration policy hashes on startup.
3. **Prediction Ledger Immutability:** Verified by `test_22` and `test_23`. Candidates are committed *before* market outcomes; retroactive changes invalidate the SHA-256 hash chain.
4. **Accounting Invariant:** Verified by `test_24` and `test_25`. Portfolio balances change exclusively through verified `FillEvent` transactions.

---

## 5. Threat Model & Trust Boundaries

The system enforces four distinct trust zones:
- **Untrusted Internet / Public Web:** Untrusted browsers and external requests.
- **DMZ / Edge Reverse Proxy (Nginx):** Terminates TLS 1.3, applies strict rate limiting (15 r/s), and injects HSTS/CSP security headers.
- **Application Tier (FastAPI):** Runs under unprivileged user `finpilot:10001:10001` with `cap_drop: [ALL]` and read-only container rootfs.
- **Persistence Tier (SQLite / PostgreSQL):** Separates application DML permissions from administrative DDL migrations.

*Full STRIDE threat analysis is detailed in [threat-model.md](threat-model.md).*

---

## 6. Authentication, Authorization & Session Hardening

- **Password Policy:** Implements NIST SP 800-63B-4 requirements: minimum 15 characters, maximum 128 characters, no arbitrary composition rules, and checks against common compromised passwords.
- **Password Hashing:** Argon2id with memory cost $64\text{ MB}$ (`m=65536`), time cost $3$ iterations (`t=3`), and parallelism $4$ (`p=4`).
- **Opaque Session Tokens:** 32-byte cryptographically secure random values stored server-side.
- **Cookie Security:** Transmitted via `HttpOnly; SameSite=Lax; Secure` cookies.
- **Anti-CSRF Protection:** State-changing endpoints require an HMAC-SHA256 token matching the session hash.

---

## 7. Secret Management & Credential Protection

- **No Secrets in Source:** Confirmed by `test_20` scanning full Git history.
- **Redaction:** `RedactingFormatter` automatically scrubs bearer tokens, database connection passwords, and API keys from logs.
- **Fail-Closed Startup:** Application fails to start if `FINPILOT_SECRET_KEY` is missing or shorter than 32 characters in production.

---

## 8. Database Security & Migration Safety

- **Role Separation:** `finpilot_admin` owns schema migrations; runtime `finpilot_app` is granted DML only (SELECT, INSERT, UPDATE, DELETE) with `NOSUPERUSER` and `NOCREATEDB`.
- **Foreign Key Constraints:** Enforced strictly across all models in both SQLite (`PRAGMA foreign_keys = ON`) and PostgreSQL.
- **TLS Mandate:** Production requires TLS-enabled PostgreSQL (`sslmode=require`).

---

## 9. API Security & Error Masking

- **Sanitized Error Responses:** Unhandled exceptions return generic 500 error responses (`ErrorCode.INTERNAL_ERROR`).
- **Zero Information Leakage:** Stack traces, internal filesystem paths (`D:\Projects\...`), and SQL query strings are masked.

---

## 10. Frontend Security & Content Security Policy

- **Safe Text Rendering:** Eliminates all use of `dangerouslySetInnerHTML`.
- **No In-Memory Storage of Tokens:** Session tokens are kept out of `localStorage` and `sessionStorage`.
- **CSP Headers:** Nginx enforces `default-src 'self'; script-src 'self'; object-src 'none'; frame-ancestors 'none'`.

---

## 11. Container & Orchestration Hardening

The production `Dockerfile` implements multi-stage builds:
1. **Frontend Builder:** Node 22 Alpine builds the React 19 / TypeScript SPA.
2. **Backend Runtime:** Python 3.13 slim image containing only runtime dependencies.
3. **Unprivileged User:** Executes under `finpilot:10001:10001`.
4. **Security Profiles:** `docker-compose.yml` configures `read_only: true`, `cap_drop: [ALL]`, and `no-new-privileges: true`.

---

## 12. Reverse Proxy & TLS Configuration

Nginx configuration in `deploy/nginx/` provides:
- TLS 1.3 and TLS 1.2 with ECDHE ciphers.
- Strict HTTP to HTTPS 301 redirection.
- HTTP Strict Transport Security (`Strict-Transport-Security: max-age=31536000; includeSubDomains`).
- WebSocket proxying (`/ws`) with secure connection upgrades.

---

## 13. Health, Monitoring & Operational Readiness

A dedicated component health router (`/api/health`) probes:
- `backend`: Core FastAPI engine readiness.
- `database`: Active connection check via `SELECT 1`.
- `model_registry`: Frozen model SHA-256 integrity verification.
- `market_data_provider`: Feed staleness monitoring (< 300s).
- `prediction_service`: Decision engine readiness.
- `paper_execution_service`: Simulated portfolio manager cash reconciliation.

---

## 14. Backup, Recovery & Disaster Response

- **SQLite Paper Backups:** Online non-blocking backups via `backup_sqlite_database` with SHA-256 verification.
- **Restoration Validation:** `restore_sqlite_database` verifies checksums before database activation.
- **Recovery Targets:** RTO < 15 minutes, RPO < 1 hour.
- *Full guide documented in [backup-recovery.md](backup-recovery.md).*

---

## 15. Operational Incident Response Runbooks

Standardized runbooks cover:
1. Compromised Secret Key Rotation
2. Session Hijacking / Account Compromise
3. Model Hash Mismatch
4. Market Data Feed Interruption
5. Emergency Kill Switch Activation
- *Detailed procedures documented in [incident-response.md](incident-response.md).*

---

## 16. Automated Security Test Suite Summary (35 of 35 Passed)

The dedicated Layer 17 test suite (`backend/tests/test_layer17_security_and_deployment.py`) executed 35 comprehensive security scenarios:

```
test_01_unauthenticated_api_requests PASSED [  2%]
test_02_invalid_authentication_tokens PASSED [  5%]
test_03_session_expiry_enforced PASSED [  8%]
test_04_session_invalidation_on_logout PASSED [ 11%]
test_05_cross_user_data_access_idor_blocked PASSED [ 14%]
test_06_privilege_escalation_blocked PASSED [ 17%]
test_07_unauthorized_admin_requests_blocked PASSED [ 20%]
test_08_sql_injection_defense PASSED [ 22%]
test_09_reflected_xss_defense PASSED [ 25%]
test_10_stored_xss_neutralized PASSED [ 28%]
test_11_csrf_protection_enforced PASSED [ 31%]
test_12_cors_restrictive_origins PASSED [ 34%]
test_13_rate_limiting_enforced PASSED [ 37%]
test_14_oversized_uploads_rejected PASSED [ 40%]
test_15_malformed_file_content_rejected PASSED [ 42%]
test_16_zip_path_traversal_defense PASSED [ 45%]
test_17_env_var_validation_fail_closed PASSED [ 48%]
test_18_secret_exposure_blocked_in_api PASSED [ 51%]
test_19_secret_leakage_redaction_in_logs PASSED [ 54%]
test_20_git_history_no_secrets PASSED [ 57%]
test_21_database_least_privilege_enforced PASSED [ 60%]
test_22_audit_ledger_tamper_detection PASSED [ 62%]
test_23_duplicate_execution_events_rejected PASSED [ 65%]
test_24_unauthorized_cash_modification_blocked PASSED [ 68%]
test_25_unauthorized_position_modification_blocked PASSED [ 71%]
test_26_model_hash_mismatch_fails_closed PASSED [ 74%]
test_27_model_config_mismatch_fails_closed PASSED [ 77%]
test_28_debug_endpoints_disabled_in_production PASSED [ 80%]
test_29_production_error_leakage_masked PASSED [ 82%]
test_30_security_headers_present PASSED [ 85%]
test_31_container_non_root_execution PASSED [ 88%]
test_32_container_port_exposure_restricted PASSED [ 91%]
test_33_backup_restoration_verified PASSED [ 94%]
test_34_restart_recovery_ledger_reconciliation PASSED [ 97%]
test_35_prohibited_real_money_execution_attempts PASSED [100%]
============================= 35 passed in 10.64s =============================
```

---

## 17. Software Supply Chain & Release Artifacts

All release evidence is preserved in `artifacts/release/`:
- **`sbom.json`:** CycloneDX 1.5 JSON dependency inventory covering all Python and npm libraries.
- **`RELEASE_MANIFEST_V1.json`:** Official release manifest with git commit, operating bounds, and verdicts.
- **`CHECKSUMS.sha256`:** Verifiable cryptographic digests of all release assets.

---

## 18. Continuous Integration & Deployment Pipeline

A 6-job GitHub Actions workflow (`.github/workflows/ci.yml`) enforces quality gates:
1. `backend-tests`: Runs pytest with coverage analysis.
2. `frontend-tests`: Executes TypeScript typecheck and Vitest suite.
3. `secret-scan`: Runs Gitleaks against commit history.
4. `dependency-audit`: Runs `pip-audit` and `npm audit`.
5. `documentation-check`: Runs link and security checklist consistency checks.
6. `docker-build`: Validates Dockerfile and Docker Compose syntax.

---

## 19. Operating Boundaries & Scope Restrictions

- **Asset Class:** Indian NSE cash equities only (derivatives, commodities, and forex excluded).
- **Execution Mode:** Simulated paper trading only; zero live capital risk.
- **Simulator Fee Schedule:** NSE equity intraday rules (brokerage ₹20, STT 0.025% on sell, turnover fees, SEBI charges, stamp duty, GST).
- **Slippage & Fill Model:** 2 bps modeled slippage; conservative stop-loss priority.

---

## 20. Honest Assessment of Limitations & Future Work

1. **Deployment Architecture:** Current deployment uses single-node Docker Compose. Horizontal clustering, multi-region replication, and Kubernetes helm charts represent logical future work.
2. **Database Engine:** Single-instance SQLite is used for paper evaluation. Enterprise multi-user scale requires PostgreSQL with connection pooling (PgBouncer).
3. **Market Data Feed:** Synthetic generators and open evaluation datasets are supported; high-throughput live WebSocket feeds from registered Indian brokers require dedicated licensed plugins.

---

## 21. Professional CV & Portfolio Descriptions

- *Technical resume bullets and portfolio summaries are documented in [cv-description.md](cv-description.md).*

---

## 22. Official Release Gate Verdicts

```
┌────────────────────────────────────────────────────────────────────────┐
│                       OFFICIAL RELEASE VERDICTS                        │
├────────────────────────────────┬───────────────────────────────────────┤
│ 1. Security Release Verdict    │ SECURITY RELEASE PASS                 │
│ 2. Deployment Readiness        │ DEPLOYMENT READY WITH LIMITATIONS     │
│ 3. Portfolio Readiness         │ PORTFOLIO RELEASE READY               │
└────────────────────────────────┴───────────────────────────────────────┘
```

---

## 23. Acceptance Criteria Verification Table

| Acceptance Gate Criterion | Verification Method | Status |
| :--- | :--- | :---: |
| Preimplementation gate verified (L14, L15, L16) | Git history and manifest inspection | **VERIFIED** |
| All 27 security controls pass | Automated tests and audit report | **VERIFIED** |
| FinPilot-specific security verified | Dedicated test assertions | **VERIFIED** |
| Multi-stage non-root containerization | Dockerfile and Compose validation | **VERIFIED** |
| Nginx reverse proxy with TLS & security headers | Nginx configuration files | **VERIFIED** |
| CI/CD pipeline configuration | `.github/workflows/ci.yml` | **VERIFIED** |
| `/api/health` component endpoint | Endpoint tests and implementation | **VERIFIED** |
| Backup and recovery procedures | SQLite backup utility test | **VERIFIED** |
| 35-test Layer 17 test suite passes | `py -m pytest test_layer17...` | **VERIFIED** |
| Software supply chain artifacts generated | `sbom.json`, `RELEASE_MANIFEST_V1.json` | **VERIFIED** |
| Documentation in `docs/layers/layer-17/` | 8 markdown deliverables complete | **VERIFIED** |
| Three release verdicts declared | Formally documented and signed off | **VERIFIED** |
