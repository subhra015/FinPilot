# FinPilot AI — Architecture

Status: **Layer 2 Contract (Ratified)**.
Related: `PROJECT_SPEC.md`, `ACCEPTANCE_GATES.md`, `SECURITY.md`,
`docs/threat-model.md`, `docs/database-backup-restore.md`.

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
| Persistence / DB | Operational state, instruments, accounts, orders, ledger events | Trusted (ACID store) |
| Analytical Store | Immutable partitioned Parquet/Arrow historical files + manifests | Trusted (analytical store) |
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
provider data ─► Data Adapter ─► Data Validator ─► Analytical Store (Parquet)
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
                                            Operational Ledger Events (append-only)
```

Model output alone never creates an accepted trade: the path passes through the
risk service by construction. In `FORWARD_PAPER`, execution uses the same
simulator with the same cost assumptions as historical evaluation.

## 4. Modes

- **HISTORICAL_REPLAY**: reads only stored historical data; deterministic; never
  injected with live data.
- **FORWARD_PAPER**: consumes newly arriving provider data; still simulated; no
  real orders.
- **SYNTHETIC_DEMO**: reads only clearly labelled `SYNTHETIC DEMO` data.

Every persisted record carries its mode. Cross-mode aggregation is prohibited in
evidence-producing outputs.

## 5. Data model (operational & analytical tiering)

FinPilot enforces a two-tier persistence architecture (Layer 2):

### 5.1 Analytical Tier (Large Historical Data)
- Stored in **partitioned Apache Parquet / Arrow files** to optimize analytical
  throughput and prevent operational database bloat.
- Tracked in `dataset_manifests` with dataset name, version, file path/URI,
  SHA-256 checksum, row count, start/end timestamps, and schema version.

### 5.2 Operational Tier (Relational State & Ledger)
Managed via SQLAlchemy models and Alembic migrations:
- `instruments` — stable instrument identity (ISIN unique), active symbol,
  market ("EQUITY"), exchange ("NSE"), currency ("INR"), lot size (>0), tick size (>0).
- `instrument_symbol_history` — tracks historical ticker renames preserving stable
  instrument identity (`valid_from`, `valid_to`).
- `dataset_manifests` — analytical file manifests with integrity checksums.
- `accounts` — simulation accounts (default ₹30,000 initial scenario capital,
  currency INR, execution mode).
- `portfolios` — portfolio grouping positions and orders for an account.
- `positions` — long-only equity cash positions (`quantity >= 0`, entry price,
  current price, P&L).
- `orders` — simulated order lifecycle (`quantity > 0`, filled quantity, risk
  authorization reference).
- `ledger_events` — append-only prediction and event ledger with sequential
  numbering, mode isolation, SHA-256 integrity hashes, and previous-hash chaining.

Schema is created strictly via **migrations**; no silent drops or resets.

## 6. Trust boundaries (summary)

1. Internet ↔ API (public surface): authentication, validation, rate limits.
2. API ↔ Database: least-privilege roles, private network (`db.internal`), TLS when hosted.
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
| Database engine | SQLite dev/test; PostgreSQL (TLS required) for hosted | `RESOLVED` (L1, L2; deployment L16) |
| Persistence / ORM | SQLAlchemy 2.0 (typed Mapped models, bound parameters) | `RESOLVED` (L2) |
| Migration tool | Alembic (reversible migrations) | `RESOLVED` (L1, L2) |
| Analytical storage format | Partitioned Apache Parquet / Arrow files + manifests | `RESOLVED` (L2) |
| Database roles | `finpilot_admin` (DDL) vs `finpilot_app` (DML only) | `RESOLVED` (L2) |
| Frontend framework | React + Vite + TypeScript | `RESOLVED` (L1) |
| Hosting/deployment target | to be chosen | `OPEN` (L16) |
| Auth/session mechanism | to be chosen | `OPEN` (L12) |

## 8. Repository layout

```
/                 root docs + config
/docs             governance, threat model, data rights, registers, backup runbook
/docs/layers      per-layer reports + index
/backend          FastAPI app, SQLAlchemy models, Alembic migrations, test suites
/frontend         React + TypeScript + Vite UI
/ml               ML package scaffold
/scripts          maintenance/check tooling (non-application)
```
