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
| 5 | Causal features & point-in-time universe | Strictly causal FS-V1 features; completed 5m bars; session reset at 09:15 IST; no leakage; PIT universe | SEC-06,19 |
| 6 | Execution & portfolio simulator | Event-driven matching engine; next-bar fill timing; limit penetration; volume cap; fee schedule; ledger reconciliation | SEC-06,19 |
| 7 | Baseline strategies | Predeclared simple strategy (`STRAT-SIMPLE-V1`) & No-trade reference; identical execution parity; uncurated multi-period evaluation | SEC-06,19 |
| 8 | Labeling and temporal validation design | Trade-policy labeling (Approach A); globally chronological multi-symbol splits; boundary purging; horizon-justified embargo; locked final test | SEC-06,19 |
| 9 | Baseline ML model training | Train approved candidates (LogReg + LightGBM); training-only fit; calibration on CALIBRATION; threshold tuning on validation; locked final-test isolation; safe model loading; selection layer evaluation against baselines | SEC-06,18,23 |
| 10 | Calibration and selective decision logic | Probability calibration on designated splits; reliability diagrams; Murphy Brier decomposition; 5-state selective decision engine; sample-support & OOD abstention; no double cost subtraction; frozen decision policy; no final-test access | SEC-06,19,23 |
| 11 | Independent risk engine | Complete independent authority; ML model cannot authorize or bypass; 11 deny-by-default controls; signed RiskAuthorization; admin RBAC & tamper-evident audit; entry vs exit distinction | SEC-01,06,08,09,19 |
| 12 | Forward paper simulation | Same cost/model path as history; no live orders; mode isolation | SEC-19 |
| 13 | Synthetic demo mode | Clearly labelled `SYNTHETIC DEMO`; cannot be reported as market evidence | SEC-06,19 |
| 14 | Backend API & authentication | Authn on all private endpoints; server-side validation; least-privilege DB; sessions/cookies | SEC-01,05,06,08,10,12,15,16,17 |
| 15 | Frontend research UI | No secrets in frontend; CSP; context-safe output; frontend non-authoritative | SEC-02,07,13,14 |
| 16 | Security hardening & abuse controls | Rate limits, CSRF, CORS allow-list, headers, admin checks | SEC-09,12,13,14,16 |
| 17 | Observability, logging & monitoring | Security-event logging without secrets/PII; alerting | SEC-08 |
| 18 | Deployment, HTTPS & production env | HTTPS+redirect+HSTS; prod debug off; secret injection; no exposed files | SEC-03,04,11,20,23 |
| 19 | Full security review & verification | Threat model + attack-surface refreshed; negative tests; PASS/FAIL/BLOCKED/N-A report; exception register; dependency + git-history scans | SEC-21,24,25,26,27 |
| 20 | Final evaluation & verdicts | Uncertainty method applied on unseen data; software/research/economic verdicts issued; band used as evaluation only | SEC-19,27 |

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
