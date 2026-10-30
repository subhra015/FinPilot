# FinPilot AI — Security Policy

Status: **Layer 0 contract (ratified)**. Controls are implemented/verified in
later layers and tracked in `SECURITY_CHECKLIST.md`.
Related: `docs/threat-model.md`, `SECURITY_CHECKLIST.md`,
`docs/security-decisions.md`, `docs/exception-register.md`.

---

## 1. Security is cross-layer

Security is applied in **every** layer, with secure defaults and deny-by-default.
No feature ships with an un-reviewed security impact. The mandatory controls are
`SEC-01` … `SEC-27` (see `SECURITY_CHECKLIST.md`). Each control has an
owner/layer and a test plan; status must be evidenced, never asserted.

## 2. V1 security scope

V1 is a research/paper simulator. The following are security-boundary rules:

- **No live broker orders** and **no payment processing** are implemented.
- Market data is untrusted input and is validated (`DATA_AND_PERFORMANCE_POLICY.md`).
- The frontend is never authoritative for prices, brokerage, charges, quantity,
  stop, target, risk approval, P&L or balance; the backend recomputes/validates.
- The **risk service is the only** component allowed to authorize a simulated
  entry; model output alone never creates an accepted trade.
- Execution modes (`HISTORICAL_REPLAY`, `FORWARD_PAPER`, `SYNTHETIC_DEMO`) are
  separated visibly and in the API/data model.
- Market data and derived outputs are not published/redistributed/exposed unless
  source terms permit the intended use.

## 3. Payment processing — NOT APPLICABLE (V1)

Rationale: V1 has no paid tiers, no billing, no checkout and no stored payment
instrument. `SEC-19`'s payment clauses are therefore `NOT APPLICABLE (V1)`; the
price/trade-integrity clauses remain **applicable** for simulated prices.

**Future billing gate** (must all hold before any billing code is merged):
server-side product/price verification; signed webhook verification with
idempotency keys; no storage of card data (use a compliant processor); explicit
per-payment integrity tests; re-run of SEC-19 and SEC-27 for the new attack
surface.

## 4. Secrets management

- Secrets live only in server-side environment injection / a secret manager.
- Never in frontend code, `VITE_*`/`NEXT_PUBLIC_*` client variables, source,
  notebooks, logs, screenshots, README files or committed config.
- Required environment variables are validated at startup; production fails
  closed if any are missing.
- On exposure, treat as compromised: identify provider/owner, provide rotation/
  revocation steps, verify replacement; never claim revocation without provider
  confirmation; never auto-revoke production credentials without authorization.

## 5. Authentication, sessions and access

- All private user-specific APIs/pages require authentication.
- Passwords hashed with Argon2id (or a justified current equivalent).
- Session cookies: `Secure`, `HttpOnly`, appropriate `SameSite`; rotate on auth/
  privilege change; inactivity + absolute expiry.
- CSRF protection for cookie-authenticated state-changing requests.
- Admin endpoints require server-side role checks; deny by default.
- Password reset is disabled unless implemented properly (hashed single-use,
  short expiry, generic responses, rate limited); otherwise `NOT APPLICABLE (V1)`.

## 6. Input, output and injection safety

- Validate every request server-side (types, lengths, ranges, enums, ownership,
  business rules); frontend validation is UX only.
- Use ORM/bound parameters; never concatenate untrusted values into SQL.
- Context-safe output; no unsafe HTML injection; CSP set; sanitize only where
  rich text is genuinely required.
- File imports (if enabled later): allow-list formats, byte/row/decompression
  limits, content/signature checks, parser-error handling, path-traversal
  rejection, storage outside web root, no executables.

## 7. Transport, headers and abuse controls

- Production uses HTTPS; HTTP redirects to HTTPS; HSTS only when HTTPS is
  correctly configured.
- Security headers: CSP, HSTS (HTTPS prod), `X-Content-Type-Options`,
  `Referrer-Policy`, frame protection via CSP `frame-ancestors`, restrictive
  `Permissions-Policy`.
- CORS: explicit trusted origins only; no wildcard origin with credentials.
- Rate limits on login, reset, registration, data import and expensive APIs;
  shared store when multiple workers/instances run.
- Production: debug mode, verbose errors and dev CORS disabled; interactive docs
  disabled unless intentionally public.

## 8. Logging, monitoring and privacy

- Log security-relevant events; never log passwords, tokens, API keys, session
  ids, reset tokens or sensitive personal data.
- Model artifacts, notebooks and exports are access-controlled and screened for
  secrets before storage/sharing.

## 9. Dependency, secret and git hygiene

- Run dependency vulnerability checks; update vulnerable packages with
  regression tests; do not blindly upgrade everything.
- Remove only confirmed-unused packages, then regression test.
- Inspect routes/deployment artifacts for `.env`, backups, dumps, logs,
  credential-bearing notebooks, source maps and private exports.
- Scan the entire reachable **Git history** for secrets; never print detected
  values.

## 10. Governance artefacts

Maintained (and refreshed in Layer 17):

- `docs/threat-model.md` — assets, trust boundaries, surfaces, threats.
- `docs/security-decisions.md` — decisions and rationale.
- `docs/exception-register.md` — approved exceptions with expiry/owner.
- `SECURITY_CHECKLIST.md` — control status/evidence/owner/layer.
- Security verification report (Layer 17) with PASS/FAIL/BLOCKED/N-A and
  remediation, backed by negative tests (SEC-27).
