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

There is still **no live trading logic, no ML model and no authentication flow**. Layer 6 established the event-driven execution simulator, the single versioned trade policy contract (`TP-V1`), realistic statutory fee calculations (`NSE_EQUITY_INTRADAY_V1`), causal next-bar fills, volume participation limits, gap-through-stop executions, collision ambiguity protocols, pre-fill cash reservation, and ₹0.01-precision accounting reconciliation. Implementation of subsequent features begins in later layers, each requiring explicit human approval.

## Repository contents

| Path | Purpose |
|---|---|
| `PROJECT_RULES.md` | Governing rules, precedence, layer discipline, decision vocabulary |
| `PROJECT_SPEC.md` | V1 scope, research question, verdicts, metrics, open decisions |
| `ARCHITECTURE.md` | Component boundaries, trust model, resolved persistence stack (L2) |
| `ACCEPTANCE_GATES.md` | Global + per-layer gates (Layer 0–19 roadmap) |
| `DATA_AND_PERFORMANCE_POLICY.md` | Data validation, modes, metrics, uncertainty |
| `docs/trade-policy-contract-v1.md` | The single versioned trade-policy contract (`TP-V1`) |
| `docs/execution-policy.md` | Execution policy, fill rules, participation caps, fee schedule & accounting |
| `docs/database-backup-restore.md` | Database backup/restore procedures & retention policy |
| `SECURITY.md` | Security policy and V1 security boundaries |
| `SECURITY_CHECKLIST.md` | `SEC-01`…`SEC-27` status/owner/layer/evidence |
| `docs/threat-model.md` | Assets, trust boundaries, attack surface |
| `docs/data-rights-matrix.md` | Audited data candidate rights across 7 use cases |
| `docs/data-health-guide.md` | Data health, session geometry, 8 audit checks & quarantine |
| `docs/feature-dictionary.md` | FS-V1 feature definitions, formulas, proxies & disclosures |
| `docs/security-decisions.md`, `docs/exception-register.md` | Security governance |
| `docs/layers/README.md` | Layer index |
| `docs/layers/layer-00/README.md` … `layer-06/README.md` | Layer reports |
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
  gap-through-stop handling, collision ambiguity flags, statutory fee breakdown, and
  ₹0.01-precision portfolio accounting reconciliation.
- **What is planned:** an independent risk authorization service (L7), persistent
  ledger events (L8), ML selection models (L9), and backtesting/forward simulation harnesses.
- **What is never claimed:** guaranteed returns, the ₹300–₹1,500 band as a
  promise, live-trading capability, or production-ready HTTPS (that is a later
  deployment layer; local HTTP is development-only).
