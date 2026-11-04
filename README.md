# FinPilot AI

An **India-first, long-only NSE cash-equity intraday research and paper-trading
platform**. FinPilot evaluates whether an ML *selection* layer improves **net
portfolio outcomes** over a no-trade reference and one predeclared simple
strategy, on unseen data, under identical execution and cost assumptions.

> **V1 boundary:** research/paper simulation only. No live-money orders, no
> derivatives, no short selling, no leverage, no personalized financial advice,
> no payment processing. Foreign markets are deferred until the Indian pipeline
> is validated. The ₹300–₹1,500 monthly result on ₹30,000 is an **evaluation
> band** — not a target and not a promise.

## Current status

- **Layer 0 — Project contract & research governance — PASS** (documentation only; `b79b372`).
- **Layer 1 — Repository & development foundation — PASS** (foundation & tooling; `c402a17`).
- **Layer 2 — Database & persistence foundation — PASS** (persistence, models, roles, backup/restore).
- **Layer 3 — Domain schemas & validation contracts — PASS** (typed schemas, candles, trade policy, scoping, sanitized errors).
- **Layer 4 — Data rights, data audit, import & provider adapters — PASS** (rights audit, adapters, 8-point audit, quarantine, safe tabular import).
- **Layer 5 — Causal features & point-in-time universe — PASS** (FS-V1 catalog, session-aware 5m aggregator, causal indicators, deterministic learned scaling, point-in-time universe).
- **Layer 6 — Execution & portfolio simulator (`TP-V1`) — PASS** (event-driven matching, fee schedule, causal next-bar fills, gap-through-stops, collision ambiguity, portfolio cash reservation, exact accounting reconciliation).
- **Layer 7 — Baseline strategies (`REF-NOTRADE-V1`, `STRAT-SIMPLE-V1`) — PASS** (no-trade reference, predeclared simple trend-VWAP-momentum strategy, uncurated multi-month simulation, exact ledger reconciliation to ₹0.00).
- **Layer 8 — Labeling and temporal validation design — PASS** (trade-policy labeling under Approach A, globally chronological multi-symbol partitions, boundary overlap purging, horizon-justified embargo, sealed final-test lockbox).
- **Layer 9 — Baseline ML model training — PASS** (approved candidates LogReg + LightGBM, training-only preprocessing fit, Platt & Isotonic calibration on CALIBRATION split, threshold tuning on THRESHOLD_SELECTION, sealed final-test lockbox, trusted model registry with SHA-256 integrity verification, economic selection layer evaluation).
- **Layer 10 — Calibration & selective decision logic — PASS** (probability calibration on CALIBRATION split, reliability diagrams, Murphy 1973 Brier score decomposition, ECE, hierarchical 5-state selective decision engine, epistemic sample support & OOD abstention, non-double-deducted net expectancy, frozen decision policy contracts `DECISION-POLICY-V1`, zero access to sealed final test).
- **Layer 11 — Independent risk engine — PASS** (complete independent authority, 11 deny-by-default controls, cryptographically sealed RiskAuthorization, simulator enforcement, entry vs exit asymmetry, admin RBAC & signed audit trail with hash chaining).
- **Layer 12 — Secure API, authentication, authorization & audit ledger — PASS** (NIST SP 800-63B-4 password policy, Argon2id, opaque server sessions in HttpOnly/Secure cookies, anti-CSRF tokens, sliding window rate limits, object-level IDOR protection, RFC 6238 TOTP MFA, append-only cryptographic ledger with sequential SHA-256 hash chaining).
- **Layer 13 — Frontend user interface & client-side security — PASS** (React/TypeScript dashboard with 8 authenticated views: research status, stock scanner, trade proposal, risk console, paper portfolio, prediction ledger, evaluation report, and data health; distinct HISTORICAL REPLAY, FORWARD PAPER, and SYNTHETIC DEMO visual indicators; CSRF token synchronization; safe DOM rendering; zero secrets in browser bundles).
- **Layer 14 — End-to-end paper workflow & challenge suite — PASS** (event-driven orchestrator integrating Data -> Features -> Proposal -> Selection -> Risk Engine -> Simulator -> Ledger -> Dashboard; idempotent event processing; bounded retries; fail-closed stale data policy and deterministic clock abstraction; 17/17 simulator & security stress challenges passed; exact cryptographic hash-chained crash recovery reconciliation).
- **Layer 15 — Locked historical evaluation, model validation & user trust — PASS** (pre-evaluation cryptographic manifest `EVAL-MANIFEST-LOCKED-MODEL-LOGREG-V1`, final-test lockbox unsealed with verified token, 3-arm comparison under identical ₹30,000 capital, statutory fees and slippage, Murphy 1973 Brier score decomposition, date-clustered session block bootstrap B=1,000 CIs, slippage sensitivity grid, virtual capital tiers with integer-share cash constraints, transparent trade validation log, predeclared economic verdict `SUGGESTIVE BUT INCONCLUSIVE` with +₹166.00 incremental net P&L over non-ML baseline).
- **Layer 16 — Forward paper trading, live-data validation & user confidence — PASS** (server-authoritative forward paper trading engine `ForwardPaperTradingEngine`; frozen Layer 15 model SHA-256 and policy hash integrity verification; user-controlled virtual portfolios ₹2,000, ₹10,000, ₹30,000, ₹50,000, custom with integer-share cash constraints; fail-closed stale data handling > 300s wall clock lag with exit monitoring; append-only prediction ledger recording predictions strictly before market outcomes; real-time drift, latency, and data health monitoring with safe `NO_NEW_ENTRIES` mode without silent retraining; double-entry accounting reconciled to ₹0.00; authenticated FastAPI endpoints under `/api/forward-paper/`; CLI runner `scripts/run_forward_paper.py`; 9/9 forward paper tests passed).

There is still **no live trading logic, no live broker execution, no derivatives, and no payment processing**. Forward paper trading operates strictly in `DataMode.FORWARD_PAPER` with simulated order execution. Predictions are recorded in an append-only ledger prior to market outcomes, and outcomes are appended separately. All market data lag exceeding 300s blocks new entries fail-closed while continuously monitoring open position exits. Implementation of subsequent features begins in later layers, each requiring explicit human approval.

## Repository contents

| Path | Purpose |
|---|---|
| `PROJECT_RULES.md` | Governing rules, precedence, layer discipline, decision vocabulary |
| `PROJECT_SPEC.md` | V1 scope, research question, verdicts, metrics, open decisions |
| `ARCHITECTURE.md` | Component boundaries, trust model, resolved persistence stack (L2) |
| `ACCEPTANCE_GATES.md` | Global + per-layer gates (Layer 0–20 roadmap) |
| `DATA_AND_PERFORMANCE_POLICY.md` | Data validation, modes, metrics, uncertainty |
| `docs/trade-policy-contract-v1.md` | The single versioned trade-policy contract (`TP-V1`) |
| `docs/execution-policy.md` | Execution policy, fill rules, participation caps, fee schedule & accounting |
| `docs/validation-protocol.md` | Validation protocol, trade-policy labeling, temporal splits, purging & lockbox |
| `docs/model-registry.md` | Model registry governance, model cards (`LOGREG`, `LIGHTGBM`), and evaluation evidence |
| `docs/calibration-methodology.md` | Calibration methodology, Murphy (1973) Brier decomposition, 5-state decision logic & abstention |
| `docs/risk-engine-policy.md` | Risk engine policy, 11 deny-by-default controls, authorization contract & RBAC |
| `docs/api-auth-specification.md` | API & authentication technical specification, NIST policy, TOTP MFA & ledger chaining |
| `docs/user-flow.md` | User journeys, session management, CSRF handshake, and navigation architecture |
| `docs/operational-runbook.md` | Standard operating procedures, trading sessions, fail-closed policy, and crash recovery |
| `docs/database-backup-restore.md` | Database backup/restore procedures & retention policy |
| `SECURITY.md` | Security policy and V1 security boundaries |
| `SECURITY_CHECKLIST.md` | `SEC-01`…`SEC-27` status/owner/layer/evidence |
| `docs/threat-model.md` | Assets, trust boundaries, attack surface |
| `docs/data-rights-matrix.md` | Audited data candidate rights across 7 use cases |
| `docs/data-health-guide.md` | Data health, session geometry, 8 audit checks & quarantine |
| `docs/feature-dictionary.md` | FS-V1 feature definitions, formulas, proxies & disclosures |
| `docs/experiment-register.md` | Experiment register and immutable baseline run artifacts |
| `docs/security-decisions.md`, `docs/exception-register.md` | Security governance |
| `docs/layers/README.md` | Layer index |
| `docs/layers/layer-00/README.md` … `layer-15/README.md` | Layer reports |
| `backend/` | Python 3.11+ / FastAPI, SQLAlchemy models, Alembic migrations, test suites |
| `frontend/` | React + Vite + TypeScript foundation (ESLint/Prettier/Vitest) |
| `ml/` | Python ML package scaffold (no models yet) |
| `.github/workflows/ci.yml` | CI: lint, format, types, tests, build, audits, secret scan |
| `.env.example` | Placeholder-only environment template (no secrets) |
| `.gitleaks.toml`, `.pre-commit-config.yaml` | Secret scanning and pre-commit hooks |
| `scripts/check_docs.ps1` | Documentation consistency/link checker |

## Setup

### Backend (Python 3.11+)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

### Frontend (Node 20+)

```powershell
cd frontend
npm ci
```

### ML (Python 3.11+)

```powershell
cd ml
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

### Environment

Copy `.env.example` to `.env` (git-ignored) and replace placeholders. Never put
secrets in `VITE_*` variables or commit them. Production fails closed unless
validated security settings are supplied.

## Verification

```powershell
# Backend
cd backend
ruff check src tests
ruff format --check src tests
mypy src
pytest
alembic upgrade head; alembic downgrade base

# Frontend
cd frontend
npm run lint
npm run format:check
npm run typecheck
npm test
npm run build

# ML
cd ml
ruff check src tests
mypy src
pytest

# Secrets + docs (from repository root)
gitleaks detect -v
powershell -ExecutionPolicy Bypass -File .\scripts\check_docs.ps1
```

## Roadmap

See `docs/layers/README.md` and `ACCEPTANCE_GATES.md` for the layer roadmap
and each layer's gate.

## Honest capability claims

- **What works today:** typed configuration with fail-closed production
  validation, redacting logging (extended to connection strings), a minimal secure
  API skeleton, operational persistence models (instruments, symbol history, dataset
  manifests, accounts, portfolios, positions, orders, ledger events), reversible
  migrations, least-privilege role scripts with tested privilege boundaries, a
  verified backup/restore runbook, causal feature pipeline & point-in-time universe,
  the single versioned trade policy contract (`TP-V1`), an event-driven execution simulator
  with next-bar fill timing, limit penetration rules, volume participation caps,
  gap-through-stop handling, collision ambiguity flags, statutory fee breakdown,
  ₹0.00-precision portfolio accounting reconciliation, and fully reproducible baseline
  strategy evaluation (`REF-NOTRADE-V1` cash reference and `STRAT-SIMPLE-V1` predeclared
  simple strategy).
- **What is planned:** an independent risk authorization service (L8), persistent
  ledger events (L9), ML selection models (L10), and backtesting/forward simulation harnesses.
- **What is never claimed:** guaranteed returns, the ₹300–₹1,500 band as a
  promise, live-trading capability, or production-ready HTTPS (that is a later
  deployment layer; local HTTP is development-only).
