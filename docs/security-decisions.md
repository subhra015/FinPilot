# FinPilot AI — Security Decisions

Status: **Layer 0 initial**. Record of security-relevant decisions with rationale
(SEC-26). Refreshed in Layer 17.

Related: `SECURITY.md`, `SECURITY_CHECKLIST.md`, `docs/threat-model.md`,
`docs/exception-register.md`.

| ID | Decision | Status | Rationale | Layer |
|---|---|---|---|---|
| SD-01 | V1 is research/paper only; no live orders, no payments | RESOLVED | Scope boundary; removes whole classes of financial/regulatory risk | L0 |
| SD-02 | Risk service is the sole entry authority | RESOLVED | Prevents model-only accepted trades; defence in depth | L0/L6 |
| SD-03 | Frontend never authoritative for prices/costs/P&L | RESOLVED | Prevents client forgery (SEC-19) | L0/L12 |
| SD-04 | Market data treated as untrusted input | RESOLVED | Prevents poisoned-data decisions | L0/L2 |
| SD-05 | Modes separated structurally | RESOLVED | Prevents synthetic/market evidence confusion | L0/L2–L11 |
| SD-06 | Password hashing = Argon2id (or justified equivalent) | PLANNED | Current best practice (SEC-05) | L12 |
| SD-07 | Hosted notebooks untrusted; no prod secrets | OPEN | OD-06 pending; conservative default | L1/L17 |
| SD-08 | Deny-by-default for admin and unknown inputs | RESOLVED | Safe default | all |
| SD-09 | No data approved until license verified | RESOLVED | Legal/rights safety; off data-rights matrix | L0/L2 |
| SD-10 | Backend stack/DB/hosting choices | PARTIAL | L1 resolved backend=Python/FastAPI, config=pydantic-settings, DB=SQLite dev/test + PostgreSQL (TLS) hosted, frontend=React/Vite/TS, migrations=Alembic. Hosting (L16) and auth (L12) remain OPEN | L1/L16 |

Status values: `RESOLVED` · `PLANNED` · `OPEN` · `SUPERSEDED`.
