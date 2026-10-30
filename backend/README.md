# FinPilot AI — Backend (Layer 1 foundation)

FastAPI backend foundation. **No trading, data or authentication features are
implemented in Layer 1.** This package provides validated configuration,
redacting logging, a secure app skeleton, and a reversible migration baseline.

## Prerequisites

- Python 3.11+ (CI uses 3.13)

## Local setup (Windows PowerShell)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
copy ..\.env.example .env   # optional for local dev; edit placeholders
```

## Commands

```powershell
ruff check src tests          # lint
ruff format --check src tests # format check
mypy src                      # type check
pytest                        # unit tests
pip-audit --strict            # dependency audit
alembic upgrade head          # apply migrations
alembic downgrade base        # revert migrations (reversibility check)
python -m finpilot            # run the API on the configured host/port
```

## Configuration

Settings are read from `FINPILOT_*` environment variables (or a local `.env`
that is git-ignored). See `../.env.example`.

- `development`: localhost binding, debug and docs allowed, SQLite file.
- `test`: isolated in-memory SQLite only.
- `production`: **fails closed** unless a ≥32-char secret, explicit HTTPS CORS
  origins, `debug=false`, docs disabled and a TLS database URL are supplied.

## Security notes (Layer 1)

- SEC-02: no secrets in source; frontend receives no secrets.
- SEC-08: logging redacts passwords, tokens, API keys and session ids.
- SEC-11: startup validation; production fails closed.
- SEC-13/14: explicit CORS origins; CSP, HSTS (prod), XCTO, Referrer-Policy,
  frame-ancestors, Permissions-Policy.
- SEC-20: no production debug and no interactive docs in production.
- SEC-03/10: migrations only; parameterised SQL via SQLAlchemy (no schema reset).
