# FinPilot AI — Acceptance Gates & Layer Roadmap

Status: **Layer 0 contract (ratified)**
Related: `PROJECT_RULES.md`, `PROJECT_SPEC.md`, `SECURITY_CHECKLIST.md`.

A layer may start only after the previous layer is **PASS** and the human
approver has authorized it. A gate is the set of checks that must all pass for a
layer to be marked PASS.

---

## 1. Global gate (applies to every layer)

A layer cannot pass unless, in addition to its specific gate:

- **G-1 Scope**: only the requested layer was implemented; no future layer
  scaffolded.
- **G-2 Focused tests**: tests for this layer pass.
- **G-3 Regression**: all prior layers' tests pass.
- **G-4 Security**: relevant `SEC-*` controls implemented and tested; no
  un-approved exception.
- **G-5 Scans**: relevant static/security/dependency/secret scans run and
  honestly reported.
- **G-6 Diff hygiene**: no secrets, debug code, generated files or unrelated
  changes in the diff.
- **G-7 Docs**: `docs/layers/layer-XX/README.md`, `docs/layers/README.md`, root
  `README.md` and `SECURITY_CHECKLIST.md` updated with exact commands + real
  outputs.
- **G-8 No fabrication**: no invented data, results, scans or status.

Outcome labels: **PASS**, **FAIL** (check ran and failed), **BLOCKED**
(could not run / dependency `OPEN`). `OPEN` decisions block dependent layers.

## 2. Layer roadmap and per-layer gates

| Layer | Title | Gate summary | Primary SEC |
|---|---|---|---|
| 0 | Project contract & research governance | All governance docs consistent; unresolved decisions explicit; SEC-01..27 have owner/layer/test plan; no code | SEC-26 |
| 1 | Foundation: repo/tooling, env config, DB + migrations, CI, logging skeleton | Build/lint/type/test tooling green; env validation (fail-closed in prod); migrations reversible; structured logging with secret redaction | SEC-08,11,20,21,22,23 |
| 2 | Database & persistence foundation | SQLAlchemy models & reversible migrations; stable instrument identity & symbol history; dataset manifests with checksums; operational account/portfolio/position/order/ledger schema; least-privilege roles; backup/restore procedure; parameterized ORM (no string-concatenated SQL) | SEC-03,08,10,11,23 |
| 3 | Market data ingestion & validation | Provider adapter + validator enforcing symbol/exchange/ts/session/freshness/OHLCV/adjustment/provenance; untrusted-input negative tests; Candle Store via migration | SEC-06,10,18,*SEC-19 (data)* |
| 4 | Feature pipeline (leakage-safe) | Features derived from completed candles only; point-in-time correctness; leakage tests | SEC-06 |
| 5 | Trade policy engine (`TP-V1`) | Contract fields schema-enforced; OPEN numerics resolved with evidence or layer blocked; no model influence | SEC-06,19 |
| 6 | Execution & cost simulator | Deterministic fills/partial fills/unfilled; fee schedule versioning; reproducibility hash | SEC-19 |
| 7 | Risk authorization service | Sole authority; independent tests; rejects bypass attempts; integer sizing/exposure/session enforced | SEC-06,09,19 |
| 8 | Prediction/event ledger | Append-only; integrity hashes; every decision+event recorded with mode/versions | SEC-08,10 |
| 9 | ML selection layer | Selection-only; reproducible training; versioned artifacts; cannot authorize trades | SEC-06,21,23 |
| 10 | Historical evaluation harness | No leakage; predeclared comparators; pre-selected uncertainty method; unseen data; mode-safe | SEC-06,19 |
| 11 | Forward paper simulation | Same cost/model path as history; no live orders; mode isolation | SEC-19 |
| 12 | Synthetic demo mode | Clearly labelled `SYNTHETIC DEMO`; cannot be reported as market evidence | SEC-06,19 |
| 13 | Backend API & authentication | Authn on all private endpoints; server-side validation; least-privilege DB; sessions/cookies | SEC-01,05,06,08,10,12,15,16,17 |
| 14 | Frontend research UI | No secrets in frontend; CSP; context-safe output; frontend non-authoritative | SEC-02,07,13,14 |
| 15 | Security hardening & abuse controls | Rate limits, CSRF, CORS allow-list, headers, admin checks | SEC-09,12,13,14,16 |
| 16 | Observability, logging & monitoring | Security-event logging without secrets/PII; alerting | SEC-08 |
| 17 | Deployment, HTTPS & production env | HTTPS+redirect+HSTS; prod debug off; secret injection; no exposed files | SEC-03,04,11,20,23 |
| 18 | Full security review & verification | Threat model + attack-surface refreshed; negative tests; PASS/FAIL/BLOCKED/N-A report; exception register; dependency + git-history scans | SEC-21,24,25,26,27 |
| 19 | Final evaluation & verdicts | Uncertainty method applied on unseen data; software/research/economic verdicts issued; band used as evaluation only | SEC-19,27 |

> Layer numbering is a plan; the human approver may re-order. Gates for later
> layers are defined here to satisfy Layer 0's requirement that **each later
> layer has a clear gate**; defining a gate does not implement the layer.

## 3. Layer 0 gate (this layer)

Layer 0 passes if and only if:

- **L0-1** All twelve required documents exist and are internally consistent.
- **L0-2** V1 scope is stated consistently across docs (NSE cash, long-only,
  5-min completed candles, no leverage/derivatives/shorting, no real orders, no
  payments, ₹30,000 scenario, foreign markets deferred).
- **L0-3** Exactly one versioned trade-policy contract exists with all required
  fields, `OPEN` numerics explicitly blocking dependent layers.
- **L0-4** Research question and the three verdicts are defined; ₹300–₹1,500
  framed as an evaluation band, not a target/promise; uncertainty method marked
  `OPEN`; no invented proof thresholds.
- **L0-5** Threat model covers all named surfaces.
- **L0-6** All `SEC-01`..`SEC-27` have owner/layer/test plan in
  `SECURITY_CHECKLIST.md`; payment processing is `NOT APPLICABLE (V1)` with a
  rationale and a future billing gate.
- **L0-7** Data-rights matrix covers all required use cases; no dataset claimed
  approved.
- **L0-8** Documentation link/consistency checks run and recorded.
- **L0-9** No application/trading/model code exists.
- **L0-10** `docs/layers/layer-00/README.md`, `docs/layers/README.md`, root
  `README.md` updated.

## 4. Result recording

Each layer report states: focused test results, regression results, scans,
security controls touched, known limitations, `OPEN`/`BLOCKED` items and the
final PASS/FAIL/BLOCKED status with reasons.
