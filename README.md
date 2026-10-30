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

- **Layer 0 — Project contract & research governance — PASS** (documentation only).
- **Layer 1 — Repository & development foundation — PASS** (tooling/config only;
  pending human approval).

There is still **no trading logic, no market-data ingestion, no ML model and no
authentication flow**. Layer 1 established the monorepo structure, tooling,
secure configuration validation, redacting logging, a reversible migration
baseline and CI. Implementation of product features begins in later layers, each
requiring explicit human approval.

## Repository contents

| Path | Purpose |
|---|---|
| `PROJECT_RULES.md` | Governing rules, precedence, layer discipline, decision vocabulary |
| `PROJECT_SPEC.md` | V1 scope, research question, verdicts, metrics, open decisions |
| `ARCHITECTURE.md` | Component boundaries, trust model, resolved stack (L1) |
| `ACCEPTANCE_GATES.md` | Global + per-layer gates (Layer 0–18 roadmap) |
| `DATA_AND_PERFORMANCE_POLICY.md` | Data validation, modes, metrics, uncertainty |
| `docs/trade-policy-contract-v1.md` | The single versioned trade-policy contract (`TP-V1`) |
| `SECURITY.md` | Security policy and V1 security boundaries |
| `SECURITY_CHECKLIST.md` | `SEC-01`…`SEC-27` status/owner/layer/evidence |
| `docs/threat-model.md` | Assets, trust boundaries, attack surface |
| `docs/data-rights-matrix.md` | Data use-case rights (nothing approved yet) |
| `docs/security-decisions.md`, `docs/exception-register.md` | Security governance |
| `docs/layers/README.md` | Layer index |
| `docs/layers/layer-00/README.md`, `docs/layers/layer-01/README.md` | Layer reports |
| `backend/` | Python 3.11+ / FastAPI foundation (config, logging, app skeleton, migrations) |
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
pip-audit -r requirements.lock --strict --progress-spinner off
alembic upgrade head; alembic downgrade base

# Frontend
cd frontend
npm run lint
npm run format:check
npm run typecheck
npm test
npm run build
npm audit --audit-level=high

# ML
cd ml
ruff check src tests
mypy src
pytest

# Secrets + docs (from repository root)
gitleaks detect --source . --no-git --config .gitleaks.toml --redact
gitleaks detect --source . --config .gitleaks.toml --redact --log-opts="--all"
powershell -ExecutionPolicy Bypass -File .\scripts\check_docs.ps1
```

## Roadmap

See `docs/layers/README.md` and `ACCEPTANCE_GATES.md` for the 18-layer roadmap
and each layer's gate.

## Honest capability claims

- **What works today:** typed configuration with fail-closed production
  validation, redacting logging, a minimal secure API skeleton, a reversible
  migration baseline, and green lint/type/test/CI tooling across backend,
  frontend and ML.
- **What is planned:** a leakage-resistant research pipeline with an independent
  risk service, a versioned trade policy, realistic simulated costs and an
  append-only ledger.
- **What is never claimed:** guaranteed returns, the ₹300–₹1,500 band as a
  promise, live-trading capability, or production-ready HTTPS (that is a later
  deployment layer; local HTTP is development-only).
