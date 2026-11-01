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
| SEC-02 | No secrets in frontend/source/logs/committed config; server injection | Foundation L1; Frontend L13 | L1: `.env.example` placeholders only; `env.ts` allow-list rejects secret-like `VITE_*` (unit test); CI greps built bundle; gitleaks clean. L13: end-to-end frontend build audit | IN PROGRESS — L1 foundation done; frontend L13 pending |
| SEC-03 | DB private binding, least-privilege roles, TLS, safe migrations | Foundation L1, L2; Deploy L16 | L1: baseline migration reversible. L2: reversible migration `0002_persistence_foundation`, least-privilege role script and permission authorizer tests pass (`test_db_roles.py`), backup/restore exercised in disposable env (`test_backup_restore.py`), private network & TLS enforced (`test_db_queries_security.py`). L16: hosted TLS verification | IMPLEMENTED (L2 operational persistence; L16 hosted deploy pending) |
| SEC-04 | HTTPS + HTTP→HTTPS redirect + HSTS when correct | Deploy L16 | Request over HTTP asserts redirect; HSTS header present only with valid TLS | NOT STARTED |
| SEC-05 | Argon2id password hashing | API/Auth L12 | Unit test: stored hash is Argon2id; plaintext never persisted | NOT STARTED |
| SEC-06 | Server-side request validation (types/ranges/enums/ownership) | All data layers; API L12 | L3: Typed domain schemas in `finpilot.schemas` with negative & adversarial tests (`test_schemas_*.py`). Rejection of malformed/oversized payloads, NaN/Inf prices, unaligned/naive timestamps, out-of-session hours, illegal state transitions, and cross-user tampering without leaking internal details (`test_schemas_adversarial.py`). L12: API endpoints | IMPLEMENTED (L3 domain schemas & validation contracts; API L12 pending) |
| SEC-07 | XSS-safe output + CSP | Frontend L13; API L12 | CSP header test; no unsafe HTML injection test | NOT STARTED |
| SEC-08 | Security-event logging without secrets/PII | Foundation L1, L2; Obs L15 | L1: `test_logging_redaction.py` — text + JSON redacting key/bearer. L2: extended to database connection credentials (`://user:[REDACTED]@host`), verified in `test_db_queries_security.py`. L15: security-event coverage | IMPLEMENTED (L1/L2 foundation); L15 pending |
| SEC-09 | Admin endpoints require server-side role checks; deny by default | API L12; Hardening L14 | Negative test: non-admin/admin-bypass attempts rejected | NOT STARTED |
| SEC-10 | Parameterised SQL / ORM only | All DB layers (L1,2,3,7,12) | L2: SQLAlchemy parameterised ORM only; `test_db_queries_security.py` tests malicious injection payloads with bound parameters. L3: `SortOrderSpec` enforces identifier syntax & strict allowlists (`test_schemas_common.py`); adversarial tests (`test_schemas_adversarial.py`) verify SQL injection strings are treated as data or rejected. | IMPLEMENTED (L2 persistence; L3 dynamic query & input contracts) |
| SEC-11 | Env-var validation at startup; fail-closed in prod | Foundation L1, L2 | L1: `test_config.py` production fail-closed matrix (secret length, debug, docs, CORS, HTTPS, non-SQLite, TLS) all raise `ConfigError`. L2: `test_db_queries_security.py` tests TLS enforcement | IMPLEMENTED (L1/L2) |
| SEC-12 | Rate limits on auth/import/expensive APIs; shared store | Hardening L14; API L12 | Test: repeated login/import attempts throttled; shared-store config assertion | NOT STARTED |
| SEC-13 | CORS explicit origins; no wildcard+credentials | Hardening L14; API L12 | L1: `test_app_security.py` — allowed origin returned, disallowed not echoed, production rejects wildcard/http. L14: full abuse hardening | IMPLEMENTED (L1 foundation); L14 pending |
| SEC-14 | Security headers (CSP/HSTS/XCTO/Referrer/frame-ancestors/Permissions-Policy) | Hardening L14; Deploy L16 | L1: header assertion tests; CSP `frame-ancestors 'none'`; HSTS present only in production. L16: real TLS | IMPLEMENTED (L1 foundation); L14/L16 pending |
| SEC-15 | Session cookies Secure/HttpOnly/SameSite; rotation; expiry | API/Auth L12 | Cookie attribute test; rotation on privilege change; expiry test | NOT STARTED |
| SEC-16 | CSRF protection for cookie-authenticated state changes | API/Auth L12; Hardening L14 | Missing/invalid token rejected; origin-check test | NOT STARTED |
| SEC-17 | Password reset: hashed single-use, expiry, generic, rate limited — else N/A | API/Auth L12 | If implemented: token tests. Else `NOT APPLICABLE (V1)` documented | NOT APPLICABLE (V1) — reset disabled; no fake flow |
| SEC-18 | Safe file import (future): allow-list, limits, content checks, no traversal, outside web root | Data import (future layer) | Upload negative tests; not enabled in V1 | NOT APPLICABLE (V1) — import not enabled |
| SEC-19 | Price/trade integrity server-side; **payment** N/A with future gate | Data L3; Policy L5; Execution L6; Risk L7 | L3: `TradePolicyV1Contract` and `TradeProposal` enforce long-only invariants (stop_loss < entry_price < target_price), whole integer share quantities, finite positive prices, completed-bar timing (`earliest_entry > decision_ts`), and statutory Indian cost breakdown computed server-side (`test_schemas_trade_policy.py`, `test_schemas_adversarial.py`). Payment clauses N/A. L5-L7: engine integration | IMPLEMENTED (L3 validation contracts; L5-L7 engine pending) |
| SEC-20 | Prod debug off; docs/verbose errors/dev CORS disabled | Deploy L16; Foundation L1 | L1: production rejects `debug=true` and docs-enabled; test env docs default off; `/docs` and `/openapi.json` return 404 when disabled | IMPLEMENTED (L1 foundation); L16 pending |
| SEC-21 | Dependency vulnerability checks with regression tests | Foundation L1; Review L17 | L1: pip-audit (backend/ML lockfiles) = no known vulns; npm audit initially flagged 3 dev-toolchain vulns, upgraded vitest→5.0.5, re-ran tests/build green, audit now 0 | IMPLEMENTED (L1); L17 re-check |
| SEC-22 | Remove only confirmed-unused deps + regression | Foundation L1; Review L17 | L1: dependency set is minimal and each package is used; no package removed. Re-checked in L17 | REVIEWED (L1); no removal needed |
| SEC-23 | No exposed `.env`/backups/dumps/logs/creds-notebooks/source maps | Deploy L16; Review L17 | L1: `.gitignore` excludes `.env`, DBs, logs, build outputs. L2: backup/restore test verifies disposable DB cleanup; gitleaks clean on commits and working tree | IMPLEMENTED (L1/L2; L16/L17 pending) |
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
