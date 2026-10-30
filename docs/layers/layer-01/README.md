# Layer 1 — Repository and Development Foundation

Status: **PASS**
Date: 2026-10-31
Commit: _pending human approval; no commit made by this layer_
Approver: _pending human approval_

---

## 1. Scope and objective

Establish the repository and development foundation for FinPilot AI:

- Monorepo structure for **frontend / backend / ML** with independent tooling.
- Local development commands, formatting, linting, type checking, unit-test
  runners, configuration loading and CI.
- Secure configuration foundations: placeholder-only `.env.example`,
  comprehensive `.gitignore`, environment-aware validation with **fail-closed
  production**, redacting logging, lockfiles and dependency-audit commands.
- Secret scanning of current files and the **full reachable Git history**.
- Pre-commit/CI checks for formatting, tests, dependency and secret scanning.
- Safe development defaults: localhost binding, no wildcard CORS, no production
  debug, no public database binding.
- Documentation, layer index, root README and security checklist updates.

**Explicitly out of scope:** authentication flows, trading/data/model features,
broker integration, payments and any future-layer business logic.

## 2. Initial repository findings

- Layer 0 was present and **PASS** (documentation only); git had one commit
  (`b79b372`, "Initial commit") and a remote `github.com/subhra015/FinPilot`.
- `ARCHITECTURE.md §7` and `docs/security-decisions.md` `SD-10` left the backend
  language, database, frontend framework and migration tool `OPEN`, owned by
  Layer 1. This layer resolves them (§3).
- **Documented conflict (resolved safely):** `ACCEPTANCE_GATES.md` Layer 1 gate
  requires "DB + migrations" and "migrations reversible", but the Layer 1 prompt
  omits any database requirement. Safest interpretation: include a **minimal,
  reversible migration baseline** with **no business tables**. This satisfies the
  gate without implementing any future layer. Recorded here per
  `PROJECT_RULES.md §2`.
- Pre-change secret scan (current tree + full history): **no leaks found**.

## 3. Stack decisions (resolving L1 ownership)

| Concern | Choice | Rationale |
|---|---|---|
| Backend language/runtime | Python 3.11+ (CI 3.13) | Typed, mature ecosystem; matches validation/security requirements |
| Backend framework | FastAPI + Uvicorn | Typed ASGI, explicit middleware for headers/CORS |
| Config | pydantic-settings | Typed env loading with validators and fail-closed rules |
| Database (dev/test) | SQLite (file / in-memory) | Zero-setup local development; tests fully isolated |
| Database (hosted, intended) | PostgreSQL with TLS required | Enforced by settings validation; not deployed in L1 |
| Migrations | Alembic | Reversible, versioned schema changes |
| Frontend | React + Vite + TypeScript | Vite build + `VITE_*` env handling referenced by the contract |
| Frontend test | Vitest + Testing Library | Fast unit/component testing |
| ML | Python package scaffold only | Home for later layers; no models in L1 |
| Hosting/deployment target | `OPEN` (Layer 16) | Deliberately deferred |
| Auth/session mechanism | `OPEN` (Layer 12) | Deliberately deferred |

## 4. Files added / modified / deleted

Added (root):
- `.editorconfig`, `.env.example`, `.gitignore`, `.gitleaks.toml`,
  `.pre-commit-config.yaml`, `.github/workflows/ci.yml`

Added (backend):
- `backend/pyproject.toml`, `backend/README.md`, `backend/alembic.ini`,
  `backend/requirements.lock`
- `backend/src/finpilot/{__init__,__main__,app,config,logging_config}.py`
- `backend/src/finpilot/db/{__init__,base}.py`
- `backend/migrations/{env.py,script.py.mako}`
- `backend/migrations/versions/0001_baseline.py`
- `backend/tests/{conftest,test_config,test_logging_redaction,test_app_security,test_migrations,test_db}.py`

Added (ML):
- `ml/pyproject.toml`, `ml/README.md`, `ml/requirements.lock`
- `ml/src/finpilot_ml/__init__.py`, `ml/tests/test_smoke.py`

Added (frontend):
- `frontend/package.json`, `frontend/package-lock.json`, `frontend/tsconfig.json`,
  `frontend/vite.config.ts`, `frontend/eslint.config.js`, `frontend/.prettierrc.json`,
  `frontend/.prettierignore`, `frontend/index.html`, `frontend/README.md`
- `frontend/src/{main.tsx,App.tsx,App.test.tsx,vite-env.d.ts}`
- `frontend/src/config/{env.ts,env.test.ts}`, `frontend/src/test/setup.ts`

Modified:
- `ARCHITECTURE.md` (§7 stack decisions resolved for L1)
- `docs/security-decisions.md` (SD-10 updated)
- `docs/threat-model.md` (Layer 1 controls note)
- `SECURITY_CHECKLIST.md` (SEC-02/03/08/11/13/14/20/21/22/23)
- `docs/layers/README.md` (Layer 1 row)
- `README.md` (status + setup/verification)
- `scripts/check_docs.ps1` (Layer 1 report added to required documents)

Deleted: none.

## 5. Design and implementation

### 5.1 Configuration (SEC-11, SEC-20)

`backend/src/finpilot/config.py` loads `FINPILOT_*` settings with three distinct
environments and **non-shared defaults**:

- `development`: `host=127.0.0.1`, debug/docs allowed, SQLite file, localhost CORS.
- `test`: isolated in-memory SQLite only; CORS empty; docs disabled.
- `production`: **fail-closed**. Startup raises `ConfigError` unless a ≥32-char
  `SECRET_KEY`, explicit `https://` CORS origins (no wildcard), `debug=false`,
  docs disabled, and a non-SQLite database URL (PostgreSQL with `sslmode`) are
  present. `load_settings()` wraps validation errors as `ConfigError`.

### 5.2 Logging (SEC-08)

`backend/src/finpilot/logging_config.py` provides a redacting formatter (text in
development, JSON in production) that redacts bearer tokens and
`password|secret|token|api_key|session_id|...` key/value pairs in both the
message and structured extra fields.

### 5.3 HTTP defaults (SEC-13, SEC-14, SEC-20)

`backend/src/finpilot/app.py` builds the app with explicit CORS origins only,
`X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options`, a restrictive
`Content-Security-Policy` with `frame-ancestors 'none'`, a `Permissions-Policy`,
and HSTS **only** in production. Interactive docs are enabled only where
configured (development default), disabled in test/production.

### 5.4 DB/migration baseline (SEC-03, SEC-10)

SQLAlchemy 2.x engine/session helpers plus an Alembic baseline that creates only
`schema_meta`. `upgrade`/`downgrade` are exercised by a reversibility test. No
business tables, no auto `create_all`, no silent resets.

### 5.5 Frontend secret guard (SEC-02)

`frontend/src/config/env.ts` enforces an allow-list (`VITE_API_BASE_URL` only)
and throws on any secret-like `VITE_*` name. CI also greps the built bundle for
secret-like values.

## 6. Commands executed and actual results (exit codes)

### 6.1 Backend

```
PS> backend\.venv\Scripts\ruff.exe check src tests
All checks passed!                                   (exit 0)
PS> backend\.venv\Scripts\ruff.exe format --check src tests
13 files already formatted                           (exit 0)
PS> backend\.venv\Scripts\mypy.exe src
Success: no issues found in 7 source files           (exit 0)
PS> backend\.venv\Scripts\python.exe -m pytest --cov=finpilot --cov-report=term-missing
27 passed, 1 warning in 3.18s; TOTAL coverage 93%    (exit 0)
PS> backend\.venv\Scripts\pip-audit.exe -r requirements.lock --strict --progress-spinner off
No known vulnerabilities found                       (exit 0)
```

(One non-fatal warning: Starlette deprecation notice about `httpx` vs `httpx2`
in `TestClient`. Recorded, not suppressed.)

### 6.2 ML

```
PS> ml\.venv\Scripts\ruff.exe check src tests          -> All checks passed!        (exit 0)
PS> ml\.venv\Scripts\ruff.exe format --check src tests -> 2 files already formatted (exit 0)
PS> ml\.venv\Scripts\mypy.exe src                      -> Success: no issues found (exit 0)
PS> ml\.venv\Scripts\python.exe -m pytest              -> 1 passed                   (exit 0)
PS> ml\.venv\Scripts\pip-audit.exe -r requirements.lock --strict --progress-spinner off
No known vulnerabilities found                         (exit 0)
```

### 6.3 Frontend

```
PS> npm run lint          -> eslint .                 (exit 0)
PS> npm run format:check  -> All matched files use Prettier code style! (exit 0)
PS> npm run typecheck     -> tsc --noEmit             (exit 0)
PS> npm test              -> 2 files, 5 tests passed  (exit 0)
PS> npm run build         -> built dist (vite 6.4.5)  (exit 0)
PS> npm audit --audit-level=high -> found 0 vulnerabilities (exit 0)
```

During development the audit initially flagged 3 dev-toolchain vulnerabilities
(`tinypool`, `@vitest/mocker` via vitest 2). Per SEC-21 the toolchain was upgraded
to `vitest 5.0.5`; all tests/build re-ran green and the audit then reported
**0 vulnerabilities**.

### 6.4 Secret scan (current files + full Git history)

```
PS> gitleaks detect --source . --no-git --config .gitleaks.toml --redact --exit-code 1
scanned ~153301 bytes; no leaks found                 (exit 0)
PS> gitleaks detect --source . --config .gitleaks.toml --redact --exit-code 1 --log-opts="--all"
1 commits scanned; no leaks found                     (exit 0)
```

Vendored/ignored directories (`node_modules`, `.venv`, `dist`, `coverage`) are
excluded from the local filesystem scan because they are not committed and
contain third-party fixtures; documentation files are **not** allowlisted.
No credential was found in current files or reachable history; therefore no
compromise/rotation action is required. (Values are never printed.)

### 6.5 Documentation consistency

```
PS> powershell -ExecutionPolicy Bypass -File .\scripts\check_docs.ps1
  ... 17 required documents OK (incl. docs/layers/layer-01/README.md)
  checked 2 relative link(s); 0 broken
  OK   all 27 controls present
RESULT: PASS                                          (exit 0)
```

`check_docs.ps1` now excludes vendored/ignored directories (`.git`,
`node_modules`, `.venv`, `dist`, `coverage`, caches) and skips link targets with
path-illegal characters, so it is no longer confused by third-party files.

## 7. Tests: passed / failed / skipped / not run

- Backend: **27 passed**, 0 failed, 0 skipped (coverage 93%).
- ML: **1 passed**, 0 failed, 0 skipped.
- Frontend: **5 passed** (2 files), 0 failed, 0 skipped.
- Migrations: upgrade→downgrade reversibility **passed**.
- Security negative tests: production fail-closed matrix, wildcard/http CORS
  rejection, SQLite-in-prod rejection, test-env shared-DB rejection, log
  redaction, missing-docs/hidden-docs, HSTS presence only in production — all
  **passed**.

## 8. Security controls checked (SEC IDs)

| ID | Status in L1 | Evidence |
|---|---|---|
| SEC-02 | IMPLEMENTED | `.env.example` placeholders only; `env.ts` allow-list + secret-name rejection; bundle grep in CI; gitleaks clean |
| SEC-03 | IMPLEMENTED (foundation) | SQLAlchemy/Alembic only; reversible migration test; prod rejects SQLite; no public DB binding |
| SEC-08 | IMPLEMENTED | Redaction unit tests (text + JSON extra fields) |
| SEC-11 | IMPLEMENTED | Prod fail-closed matrix (secret/debug/docs/CORS/DB) tests |
| SEC-13 | IMPLEMENTED | Explicit-origin CORS test; production rejects wildcard |
| SEC-14 | IMPLEMENTED | Header assertions incl. CSP frame-ancestors, XCTO, Referrer, Permissions-Policy; HSTS prod-only |
| SEC-20 | IMPLEMENTED | Docs disabled in test/prod; prod requires `debug=false` |
| SEC-21 | IMPLEMENTED | pip-audit (backend, ML) + npm audit; vitest toolchain upgraded with regression re-run |
| SEC-22 | REVIEWED | Dependencies are minimal and each used; no confirmed-unused package removed |
| SEC-23 | PARTIAL (L1 scope) | `.gitignore` excludes `.env`, DB, logs, build outputs; deployment artefact inspection is Layer 16/17 |

## 9. Known limitations and assumptions

- Interactive docs are enabled by default in development only; production
  requires docs disabled.
- Hosted PostgreSQL/TLS is **intended and validated at config level only**; no
  hosted database is deployed or verified in Layer 1.
- HTTPS/HSTS production behaviour is asserted at config/middleware level; actual
  TLS termination is a Layer 16 concern. Local HTTP is **not** production-ready.
- `mypy` checks `src` (not tests); tests are linted by ruff. This is the configured
  CI contract for Layer 1.
- Frontend bundle is a static scaffold; no backend calls/auth exist yet.
- The DB baseline intentionally contains no business tables.

## 10. Acceptance result

**PASS** — meets the Layer 1 prompt and `ACCEPTANCE_GATES.md` Layer 1 gate:

- Clean setup documented per package (`backend/`, `frontend/`, `ml/` READMEs).
- Lint, format, typecheck, tests and CI workflow present and green locally.
- No committed secret; current-tree and full-history scans clean.
- Environment-validation tests pass, including fail-closed production.
- Development/test/production configurations use distinct defaults and cannot
  silently share insecure defaults (asserted by `test_environments_do_not_share_insecure_defaults`).
- Reversible migration baseline verified.
- Documentation, layer index, root README and SECURITY_CHECKLIST updated.

Known non-blocking items: Starlette `httpx` deprecation warning; SEC-23 full
artefact inspection deferred to Layers 16/17; hosted TLS/deploy deferred to
Layer 16.
