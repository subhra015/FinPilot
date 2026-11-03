# FinPilot AI — Threat Model

Status: **Layer 0 initial; Layer 1 and Layer 12 controls implemented & verified** (full review in
Layer 17, per SEC-26).
Related: `SECURITY.md`, `SECURITY_CHECKLIST.md`, `ARCHITECTURE.md`,
`docs/data-rights-matrix.md`, `docs/api-auth-specification.md`.

---

## 1. Method

We enumerate **assets**, **actors/roles**, **trust boundaries** and the
**attack surface**, then map each threat to `SEC-01`…`SEC-27` controls, an
implementation layer and test evidence. STRIDE-style categories are used
(spoofing, tampering, repudiation, information disclosure, denial of service,
elevation of privilege).

## 2. Assets

| Asset | Why it matters |
|---|---|
| Account/portfolio & simulated balances | Integrity of P&L and the ₹30,000 scenario |
| Prediction/event ledger | Audit trail; tampering invalidates evidence |
| Trade policy versions (`TP-V1`) | Reproducibility and fairness of evaluation |
| Model artifacts | Confidentiality + integrity; selection decisions derive from them |
| Market data & provenance | Integrity of decisions; licensing constraints |
| Credentials/secrets (DB, providers, signing) | Broad compromise potential |
| User credentials & sessions | Account takeover |
| Evaluation results & verdicts | Must be trustworthy and non-fabricated |
| Hosted notebooks | Often hold credentials/data; high leak risk |
| DB contents (all tables) | Confidential + integrity-critical |

## 3. Actors / roles

- **Anonymous visitor** — untrusted; may reach only explicitly public surfaces.
- **Registered researcher/user** — authenticated; may access own portfolio,
  ledger and account data only.
- **Admin** — elevated; server-side role-checked; deny by default.
- **Operator/DevOps** — manages deployment/secrets; must not use prod creds
  casually.
- **Data provider** — untrusted source of market data.
- **Hosted notebook runtime** — untrusted execution context relative to secrets.

## 4. Trust boundaries

1. Internet ↔ API (public)
2. API ↔ Database
3. API ↔ Data provider
4. API ↔ Hosted notebook
5. API ↔ Frontend (frontend untrusted)
6. File-import path ↔ Data validator (future)
7. Secret store ↔ services

## 5. Attack surface inventory

| Surface | Threats (STRIDE) | Controls | Layer |
|---|---|---|---|
| Auth endpoints (login/reset/register) | Spoofing, brute force, DoS | SEC-01,05,12,15,16,17 | L12 (Verified) |
| Private APIs (portfolio/ledger/account/model) | Info disclosure, IDOR, EoP | SEC-01,06,09,10 | L12 (Verified) |
| Admin endpoints | EoP, Info disclosure | SEC-09,15 | L12 (Verified) |
| Frontend/SDK build | Info disclosure (secrets), XSS | SEC-02,07,13,14 | L13/L14 |
| API input handling | Tampering, injection | SEC-06,10 | L12 (Verified) |
| Database | Tampering, Info disclosure | SEC-03,10 | L1 |
| Data provider feed | Tampering (bad data), Info disclosure, provenance loss | SEC-06,19 + `DATA_AND_PERFORMANCE_POLICY.md` §1 | L2 |
| Price/cost/size inputs | Tampering (client-forged) | SEC-19 (server authoritative) | L2/L4/L5/L6 |
| Hosted notebooks | Info disclosure (secrets), EoP, supply chain | SEC-02,23,24; `docs/data-rights-matrix.md` | L1/L13/L17 |
| File imports (future) | RCE, traversal, DoS, parser exploits | SEC-18 | future |
| Secrets/env | Info disclosure | SEC-02,11 | L1/L16 |
| Logs | Info disclosure (secrets/PII) | SEC-08 | L1/L12/L15 |
| Model artifacts | Tampering, Info disclosure | SEC-08,23,24 | L8/L15/L17 |
| Deployment artefacts | Exposed files, source maps | SEC-20,23 | L16/L17 |
| Git history | Info disclosure (committed secrets) | SEC-24,25 | L17 |

## 6. Key threat scenarios and mitigations

1. **Forged client price/size** — attacker submits a favourable simulated price.
   Mitigation: backend sources and validates all price/cost/size/P&L; client
   values ignored (SEC-19). Test: submit tampered price, assert server ignores.
2. **Model-only trade acceptance** — bypass risk service. Mitigation: risk
   service is the sole authority in the code path (ARCHITECTURE §3); test that a
   model "approve" without risk approval creates no trade (SEC-06/SEC-19).
3. **Poisoned market data** — malformed/adjusted-mixed candles cause bad
   decisions. Mitigation: validator quarantines non-conforming rows; provenance
   recorded (SEC-06 + data policy). Test: inject bad OHLC/timestamp rows.
4. **IDOR on portfolio/ledger** — user reads another's data. Mitigation:
   ownership checks server-side (SEC-01/SEC-06). Test: cross-user access 403.
5. **Ledger tampering** — history rewritten. Mitigation: append-only + integrity
   hashes (SEC-10; ARCHITECTURE §5).
6. **Secret leakage via frontend/notebook/commit** — Mitigation: SEC-02,24;
   notebooks treated as untrusted; no secrets in client bundles.
7. **Brute force / DoS on auth or expensive APIs** — Mitigation: SEC-12 shared-
   store rate limits.
8. **CSRF on cookie-auth state changes** — Mitigation: SEC-16 tokens + origin.
9. **Mode confusion** — synthetic data reported as market evidence. Mitigation:
   mode tags enforced (SEC-06/19 + data policy).
10. **Data-rights violation** — unlicensed redistribution/public display.
    Mitigation: data-rights matrix gating; no approval until verified.

## 7. SEC-01 … SEC-27 coverage

Every control with owner/layer and test plan is maintained in
`SECURITY_CHECKLIST.md`. The mapping of surfaces above ↔ controls, plus the
checklist, satisfies the Layer 0 requirement that all 27 controls have an
owner/layer/test plan.

## 8. Assumptions and exclusions

- No live trading, no payments, no derivatives/shorting/leverage in V1.
- Foreign markets excluded until Indian pipeline validated.
- Hosted-notebook policy (`OD-06`) is `OPEN`; until resolved, notebooks must not
  receive production secrets or licensed data beyond permitted use.
- **Layer 1 controls present:** fail-closed production config validation,
  log redaction, explicit-origin CORS, security headers, HSTS (production only),
  reversible migration baseline, dependency audits and secret scanning of the
  current tree and full Git history. See `docs/layers/layer-01/README.md`.
- **Layer 12 controls present:** Argon2id password hashing, NIST SP 800-63B-4 policy,
  opaque server sessions, CSRF protection, sliding window rate limiting, IDOR ownership
  enforcement, RFC 6238 TOTP MFA, and append-only cryptographic ledger with sequential
  SHA-256 hash chaining. See `docs/layers/layer-12/README.md`.

## 9. Refresh

This model is refreshed and re-issued with negative-test evidence in Layer 17
(SEC-26/SEC-27). Material architecture changes require a re-review earlier.
