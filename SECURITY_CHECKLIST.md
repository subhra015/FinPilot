# FinPilot AI — Security Checklist (SEC-01 … SEC-27)

Status legend: `NOT STARTED` · `IN PROGRESS` · `IMPLEMENTED` · `VERIFIED` ·
`NOT APPLICABLE (V1)` · `BLOCKED`.
Evidence must be a command + observed result, or a named test — never an
assertion. No control may be marked `VERIFIED` without negative-test evidence.
This checklist is initialised in Layer 0 and updated each layer. Layer 17
performs the full verification pass.

| ID | Control (summary) | Owner/Layer | Test plan / evidence | Status |
|---|---|---|---|---|
| SEC-01 | Authentication on all private APIs/pages | API/Auth — L12 | Negative tests: unauthenticated requests to portfolio/ledger/account/model endpoints return 401/403 | NOT STARTED |
| SEC-02 | No secrets in frontend/source/logs/committed config; server injection | Foundation L1; Frontend L13 | Secret scan of source + build output; assert no `VITE_*`/`NEXT_PUBLIC_*` secrets; env injection only | NOT STARTED |
| SEC-03 | DB private binding, least-privilege roles, TLS, safe migrations | Foundation L1; Deploy L16 | Migration reversibility test; role-permission assertions; hosted TLS check | NOT STARTED |
| SEC-04 | HTTPS + HTTP→HTTPS redirect + HSTS when correct | Deploy L16 | Request over HTTP asserts redirect; HSTS header present only with valid TLS | NOT STARTED |
| SEC-05 | Argon2id password hashing | API/Auth L12 | Unit test: stored hash is Argon2id; plaintext never persisted | NOT STARTED |
| SEC-06 | Server-side request validation (types/ranges/enums/ownership) | All data layers; API L12 | Negative tests for each endpoint/validator; malformed/oversized/foreign-owner inputs rejected | NOT STARTED |
| SEC-07 | XSS-safe output + CSP | Frontend L13; API L12 | CSP header test; no unsafe HTML injection test | NOT STARTED |
| SEC-08 | Security-event logging without secrets/PII | Foundation L1; Obs L15 | Log-redaction tests: tokens/passwords/session ids never appear | NOT STARTED |
| SEC-09 | Admin endpoints require server-side role checks; deny by default | API L12; Hardening L14 | Negative test: non-admin/admin-bypass attempts rejected | NOT STARTED |
| SEC-10 | Parameterised SQL / ORM only | All DB layers (L1,2,7,12) | Injection negative tests against queries | NOT STARTED |
| SEC-11 | Env-var validation at startup; fail-closed in prod | Foundation L1 | Test: missing required var in prod config aborts startup | NOT STARTED |
| SEC-12 | Rate limits on auth/import/expensive APIs; shared store | Hardening L14; API L12 | Test: repeated login/import attempts throttled; shared-store config assertion | NOT STARTED |
| SEC-13 | CORS explicit origins; no wildcard+credentials | Hardening L14; API L12 | Test: disallowed origin rejected; wildcard-with-credentials absent | NOT STARTED |
| SEC-14 | Security headers (CSP/HSTS/XCTO/Referrer/frame-ancestors/Permissions-Policy) | Hardening L14; Deploy L16 | Header assertion tests per environment | NOT STARTED |
| SEC-15 | Session cookies Secure/HttpOnly/SameSite; rotation; expiry | API/Auth L12 | Cookie attribute test; rotation on privilege change; expiry test | NOT STARTED |
| SEC-16 | CSRF protection for cookie-authenticated state changes | API/Auth L12; Hardening L14 | Missing/invalid token rejected; origin-check test | NOT STARTED |
| SEC-17 | Password reset: hashed single-use, expiry, generic, rate limited — else N/A | API/Auth L12 | If implemented: token tests. Else `NOT APPLICABLE (V1)` documented | NOT APPLICABLE (V1) — reset disabled; no fake flow |
| SEC-18 | Safe file import (future): allow-list, limits, content checks, no traversal, outside web root | Data import (future layer) | Upload negative tests; not enabled in V1 | NOT APPLICABLE (V1) — import not enabled |
| SEC-19 | Price/trade integrity server-side; **payment** N/A with future gate | Data L2; Policy L4; Execution L5; Risk L6 | Simulated price/cost/size recomputed server-side; client values ignored. Payment clauses N/A | Payment `NOT APPLICABLE (V1)`; integrity NOT STARTED |
| SEC-20 | Prod debug off; docs/verbose errors/dev CORS disabled | Deploy L16; Foundation L1 | Prod config assertions | NOT STARTED |
| SEC-21 | Dependency vulnerability checks with regression tests | Foundation L1; Review L17 | Dependency scan recorded; upgrades carry regression tests | NOT STARTED |
| SEC-22 | Remove only confirmed-unused deps + regression | Foundation L1; Review L17 | Unused-dependency report; regression green after removal | NOT STARTED |
| SEC-23 | No exposed `.env`/backups/dumps/logs/creds-notebooks/source maps | Deploy L16; Review L17 | Artefact/route inspection for exposed files | NOT STARTED |
| SEC-24 | Scan full reachable Git history for secrets (do not print values) | Review L17 | Git-history secret scan recorded (counts only) | NOT STARTED |
| SEC-25 | Compromised-key handling: rotate steps, no false revocation claims | Review L17 | Documented runbook; verification of replacement | NOT STARTED |
| SEC-26 | Maintain threat model, attack-surface inventory, decisions, exception register | Layer 0 (initial), refresh L17 | Artefacts exist and are linked; refreshed in L17 | IN PROGRESS — initial artefacts created in L0 |
| SEC-27 | Security verification with negative tests + report | Review L17 | Negative-test suite + PASS/FAIL/BLOCKED/N-A security report | NOT STARTED |

## Notes

- `NOT APPLICABLE (V1)` entries have rationale in `SECURITY.md` §3 and §5 and
  are re-opened automatically if the triggering feature is added.
- Payment processing is `NOT APPLICABLE (V1)`; the **future billing gate**
  (SEC-19) is defined in `SECURITY.md` §3.
- Every control must reach at least `IMPLEMENTED` with tests before its owning
  layer can PASS; `VERIFIED` is required by Layer 17 for applicable controls.
- Exceptions require an entry in `docs/exception-register.md` with owner,
  justification and expiry.
