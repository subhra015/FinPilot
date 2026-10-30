# FinPilot AI — Architecture

Status: **Layer 0 contract (ratified)**. No components are implemented in Layer
0. This document defines intended boundaries and the trust model at a
component level; concretisation happens in later layers under their gates.

Related: `PROJECT_SPEC.md`, `ACCEPTANCE_GATES.md`, `SECURITY.md`,
`docs/threat-model.md`.

---

## 1. Design principles

1. **Server is authoritative.** Prices, costs, sizing, stops, targets, risk
   approval, P&L and balances are computed/validated server-side. The frontend
   is never trusted for any of these.
2. **Completed-candle decisions.** The only decision input granularity is a
   completed 5-minute candle.
3. **Independent risk authority.** The risk service is the only component that
   can authorize a simulated entry.
4. **Append-only audit.** Predictions and resulting events are persisted to an
   immutable ledger.
5. **Mode separation.** `HISTORICAL_REPLAY`, `FORWARD_PAPER` and
   `SYNTHETIC_DEMO` are structurally distinct in the API and data model.
6. **Typed boundaries.** Components communicate via typed interfaces; databases
   change only via migrations.
7. **Determinism where claimed.** Historical replay and evaluations must be
   reproducible.

## 2. Component map (logical)

| Component | Responsibility | Trust level |
|---|---|---|
| Market Data Adapter | Fetch/ingest provider data; normalise; attach provenance | Untrusted input boundary |
| Data Validator | Validate symbol, exchange, timestamp, session, freshness, OHLCV consistency, adjustment status, provenance | Trusted, gating |
| Candle Store | Persist validated completed candles + provenance | Trusted |
| Feature Pipeline | Leakage-safe features from completed candles only | Trusted |
| Trade Policy Engine | Apply versioned contract (`TP-V1`) to produce authorized *candidates* | Trusted |
| ML Selection Layer | Score/select among candidates; produces predictions | Trusted for selection only |
| Risk Authorization Service | Independent veto/approval, sizing, exposure, session rules | **Sole authority** |
| Execution & Cost Simulator | Deterministic fills, partial fills, fees, slippage | Trusted |
| Prediction/Event Ledger | Append-only record of predictions and events | Trusted, audit-critical |
| Evaluation Harness | Leakage-resistant historical evaluation + metrics | Trusted |
| API Service | Auth, validation, orchestration, persistence access | Trusted, public surface |
| Frontend | Research UI; non-authoritative | Untrusted client |
| Observability | Structured logs, metrics, alerts (no secrets) | Trusted |

## 3. Decision-to-ledger data flow (paper)

```
provider data ─► Data Adapter ─► Data Validator ─► Candle Store
                                                      │ (completed 5-min candles)
                                                      ▼
                                             Feature Pipeline
                                                      ▼
                                    Trade Policy Engine (TP-V1) ──► candidates
                                                      ▼
                                             ML Selection Layer ──► prediction
                                                      ▼
                                    Risk Authorization Service ──► approve / reject
                                                      ▼
                                    Execution & Cost Simulator ──► events
                                                      ▼
                                        Prediction/Event Ledger (append-only)
```

Model output alone never creates an accepted trade: the path passes through the
risk service by construction. In `FORWARD_PAPER`, execution uses the same
simulator with the same cost assumptions as historical evaluation.

## 4. Modes

- **HISTORICAL_REPLAY**: reads only the Candle Store; deterministic; never
  injected with live data.
- **FORWARD_PAPER**: consumes newly arriving provider data; still simulated; no
  real orders.
- **SYNTHETIC_DEMO**: reads only clearly labelled `SYNTHETIC DEMO` data.

Every persisted record carries its mode. Cross-mode aggregation is prohibited in
evidence-producing outputs.

## 5. Data model (intended, high level)

- `instruments` — symbol, exchange, series, tick/lot constraints.
- `candles` — instrument, interval (5m), start/end ts, OHLCV, adjustment flag,
  provenance/source id, validation status.
- `trade_policy_versions` — immutable contract snapshots (e.g. `TP-V1`).
- `predictions` — model version, policy version, decision candle ref, score,
  mode.
- `risk_decisions` — prediction ref, approve/reject, reason codes.
- `simulated_events` — entry/exit/expiry/partial-fill with prices and the fee
  schedule version.
- `ledger` — append-only union/audit of the above with hashes for integrity.
- `fee_schedules` — named versioned cost tables.
- `users`/`sessions`/`roles` — introduced in the API/auth layer.

Schema is created via **migrations**; no silent drops/resets.

## 6. Trust boundaries (summary)

1. Internet ↔ API (public surface): authentication, validation, rate limits.
2. API ↔ Database: least-privilege roles, private network, TLS when hosted.
3. API ↔ Data Provider: provider data treated as untrusted; validated.
4. API ↔ Hosted Notebook: high-risk boundary; see `docs/threat-model.md`.
5. API ↔ Frontend: frontend untrusted; server recomputes.
6. File import ↔ Data Validator: strict format/size/content checks (future layer).
7. Secrets store ↔ services: injected at runtime; never in source/frontend.

Full detail: `docs/threat-model.md`.

## 7. Tech stack decisions

| Concern | Choice | Status |
|---|---|---|
| Language/runtime (backend) | Python 3.11+ (CI 3.13), FastAPI + Uvicorn | `RESOLVED` (L1) |
| Configuration | pydantic-settings, `FINPILOT_*`, fail-closed production | `RESOLVED` (L1) |
| Database engine | SQLite dev/test; PostgreSQL (TLS required) for hosted | `RESOLVED` (L1; deployment L16) |
| Frontend framework | React + Vite + TypeScript | `RESOLVED` (L1) |
| Migration tool | Alembic | `RESOLVED` (L1) |
| Hosting/deployment target | to be chosen | `OPEN` (L16) |
| Auth/session mechanism | to be chosen | `OPEN` (L12) |

Layer 1 selects the foundation stack above (see `docs/layers/layer-01/README.md`).
Hosting and authentication remain deliberately `OPEN` until their owning layers.
Local HTTP development is not production-ready; production requires HTTPS (L16).

## 8. Repository layout (intended)

```
/                 root docs + config
/docs             governance, threat model, data rights, registers
/docs/layers      per-layer reports + index
/scripts          maintenance/check tooling (non-application)
/ (app code)      introduced only in later layers, per their gates
```

Layer 0 creates only documentation and a documentation consistency-check script.
