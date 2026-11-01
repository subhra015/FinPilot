# Layer 2 — Database and Persistence Foundation

Status: **PASS**  
Date: 2026-11-01  
Commit: _pending human approval; no commit made by this layer_  
Approver: _pending human approval_  

---

## 1. Scope and Objective

Establish the database and persistence foundation for FinPilot AI:

- **PostgreSQL for Operational State**: Configure and model operational state in PostgreSQL (or SQLite for isolated local dev/test), including instruments, symbol history, dataset manifests, operational accounts (₹30,000 initial scenario), portfolios, long-only positions, simulated orders, and append-only ledger events.
- **Analytical Storage Boundary**: Explicitly separate operational data from large historical analytical data (e.g. 5-minute candles, features), which reside in partitioned Parquet/Arrow files tracked via `dataset_manifests` with schema versions and SHA-256 checksums.
- **Stable Instrument Identity**: Model instruments with globally stable ISIN identifiers (`instruments`) alongside a historical symbol tracking table (`instrument_symbol_history`).
- **Strict Database Integrity**: Implement database constraints, check constraints (positive lot size, positive tick size, non-negative long-only position quantities, positive order quantities, valid timestamp ordering), foreign keys with strict referential actions, and transaction atomicity.
- **Alembic Reversible Migrations**: Safe, versioned migration chain (`0001_baseline` -> `0002_persistence_foundation`) supporting forward upgrades and complete rollbacks without data corruption.
- **Least-Privilege Roles (SEC-03)**: Formalize separate migration/admin role (`finpilot_admin`) and runtime application role (`finpilot_app` restricted to DML, no DDL/DROP/ALTER, no superuser/owner).
- **Private Network Deployment & TLS (SEC-03, SEC-11)**: Enforce private network binding (no public 0.0.0.0 exposure), TLS requirement (`sslmode=require`) in hosted PostgreSQL environments, and credential redaction in logs (SEC-08).
- **Backup & Restore Procedure**: Documented production PostgreSQL runbook and operational retention policy, verified by automated tests exercising backup/restore in a disposable test environment.

---

## 2. Initial Repository Findings

- Layer 0 (Governance) and Layer 1 (Foundation) were present and passed all tests.
- Commit `c402a17bc5c189ba6f6c848b6dbab1edb6a4ead1` was committed to `master` containing Layer 1 foundation files.
- Layer 1 provided a reversible baseline migration (`0001_baseline`) with a `schema_meta` table and no business tables.
- **Documented Conflict & Resolution**: `ACCEPTANCE_GATES.md` §2 originally planned Layer 2 as "Market data ingestion & validation". However, the user instruction explicitly directed:
  > "Execute FINPILOT LAYER 2 ONLY: DATABASE AND PERSISTENCE FOUNDATION.
  > Implement the approved database (PostgreSQL for operational state, dataset manifests, users, portfolio state, ledger; Parquet/Arrow for analytical data)."
  Per `PROJECT_RULES.md` §2 precedence and human instruction, Layer 2 is executed as the Database and Persistence Foundation. Layer roadmap and index documents are aligned accordingly.
- Security scan (gitleaks) across all reachable Git commits and uncommitted files showed 0 leaks.

---

## 3. Design and Implementation

### 3.1 Persistence Tiering & Schema Architecture
The persistence architecture establishes a strict separation between analytical data and operational state:
1. **Analytical Data**: Large historical analytical data (high-frequency completed candles, feature matrices) lives in partitioned Parquet/Arrow files. Tracked in database via `dataset_manifests` storing dataset name, version, file URI, row count, start/end timestamps, schema version, and SHA-256 checksums.
2. **Operational Database**: Managed with SQLAlchemy 2.0 ORM and Alembic migrations:
   - `instruments`: Stable ISIN identity (12 chars unique), current trading symbol, market ("EQUITY"), exchange ("NSE"), currency ("INR"), lot size (>0), tick size (>0), status.
   - `instrument_symbol_history`: Tracks ticker renames over time (`valid_from`, `valid_to`), maintaining foreign key linkage to the stable instrument.
   - `dataset_manifests`: Versioned manifests for analytical Parquet files with cryptographic checksums.
   - `accounts`: Simulation accounts with ₹30,000 initial scenario capital, current cash, currency (INR), and execution mode.
   - `portfolios`: Account portfolios grouping positions and orders.
   - `positions`: Long-only equity positions with non-negative quantity constraint (`quantity >= 0`), average entry price, current price, and P&L.
   - `orders`: Simulated order lifecycle with positive quantity constraint (`quantity > 0`), filled quantity bounds (`0 <= filled_quantity <= quantity`), and risk authorization reference.
   - `ledger_events`: Append-only audit ledger with sequential numbering, mode isolation, SHA-256 integrity hashes, and `prev_hash` chaining.

### 3.2 Alembic Migration (`0002_persistence_foundation`)
- Upgrades from `0001_baseline` to create all 8 operational tables with check constraints, foreign keys, and indexes.
- Downgrades cleanly in reverse dependency order back to `0001_baseline` and down to `base`.
- Automated regression tests prove reversible upgrade/downgrade round-trips.

### 3.3 Least-Privilege Role Model (SEC-03)
- Implemented `backend/src/finpilot/db/roles.py`:
  - `finpilot_admin`: Migration role. Owns public schema, has `CREATE` on schema, runs DDL.
  - `finpilot_app`: Runtime application role. Granted `SELECT, INSERT, UPDATE, DELETE` on operational tables; `USAGE, SELECT` on sequences. Specifically revoked from `CREATE` on schema, cannot perform DDL (no `CREATE TABLE`, `DROP TABLE`, `ALTER TABLE`), cannot modify migration tables (`alembic_version`, `schema_meta`), and is `NOSUPERUSER NOCREATEDB NOCREATEROLE`.
- Functional test in `backend/tests/test_db_roles.py` simulates unprivileged runtime role and verifies that DML succeeds while DDL attempts raise authorization errors.

### 3.4 Connection Security, TLS, and Redaction (SEC-03, SEC-08, SEC-10, SEC-11)
- Private network deployment documented: PostgreSQL is never exposed to public internet (no 0.0.0.0 binding).
- `Settings` in `config.py` enforces that production database URLs require TLS (`sslmode=require` / `sslmode=verify-full`).
- Parameterized ORM / bound SQL prevents SQL injection (SEC-10). Negative tests in `test_db_queries_security.py` execute malicious payloads (`'; DROP TABLE ...`, `UNION SELECT`) and verify that bound parameters neutralize injection attempts.
- `RedactingFormatter` in `logging_config.py` updated to automatically redact database connection string passwords (`://user:password@host` -> `://user:[REDACTED]@host`).

### 3.5 Backup, Restore & Retention Policy
- Created `docs/database-backup-restore.md` detailing PostgreSQL production backup (`pg_dump` with SHA-256 checksumming) and disaster recovery (`pg_restore`).
- Created `backend/src/finpilot/db/backup.py` providing SQLite online backup and restore with checksum verification.
- Automated tests in `backend/tests/test_backup_restore.py` exercise backup creation, database teardown, restore into a clean disposable target, schema/content verification, and tamper detection.

---

## 4. Files Added / Modified

### Added
- `backend/src/finpilot/db/enums.py`: Domain enums (`MarketType`, `ExchangeCode`, `CurrencyCode`, `InstrumentStatus`, `DataMode`, `OrderType`, `OrderSide`, `OrderStatus`, `LedgerEventType`).
- `backend/src/finpilot/db/models.py`: SQLAlchemy ORM models (`Instrument`, `InstrumentSymbolHistory`, `DatasetManifest`, `Account`, `Portfolio`, `Position`, `Order`, `LedgerEvent`).
- `backend/src/finpilot/db/roles.py`: PostgreSQL least-privilege role configuration and DDL generator.
- `backend/src/finpilot/db/backup.py`: Database backup, restore, and schema inspection utilities.
- `backend/migrations/versions/0002_persistence_foundation.py`: Migration creating operational persistence foundation.
- `backend/tests/test_db_models.py`: Model, constraint, foreign key, and timezone contract test suite.
- `backend/tests/test_db_roles.py`: Least-privilege role script and functional permission boundary test suite.
- `backend/tests/test_backup_restore.py`: Backup/restore lifecycle test suite in disposable test environments.
- `backend/tests/test_db_queries_security.py`: Parameterized queries, SQL injection, and secret redaction security test suite.
- `docs/database-backup-restore.md`: Production backup/restore runbook and retention policy specification.
- `docs/layers/layer-02/README.md`: This layer report.

### Modified
- `backend/src/finpilot/db/base.py`: Added SQLite `PRAGMA foreign_keys = ON` connect listener for strict FK parity.
- `backend/src/finpilot/db/__init__.py`: Exported all models, enums, base, and role utilities.
- `backend/src/finpilot/logging_config.py`: Added URL credential pattern to redact passwords in connection strings.
- `backend/migrations/env.py`: Registered `Base.metadata` and imported all persistence models.
- `backend/tests/test_migrations.py`: Updated to verify empty-to-head, stepwise upgrade, and full rollback.
- `ARCHITECTURE.md`: Updated §5 (Data model) and §7 (Tech stack decisions) for Layer 2 persistence foundation.
- `SECURITY_CHECKLIST.md`: Updated SEC-03, SEC-08, SEC-10, SEC-11, SEC-23 status and test evidence.
- `docs/layers/README.md`: Marked Layer 2 as PASS.
- `README.md`: Updated overall project status and verification commands.
- `scripts/check_docs.ps1`: Added Layer 2 documentation and backup runbook to required checks.

---

## 5. Verification Commands and Actual Results

| Step | Command | Result / Exit Code | Evidence Summary |
|---|---|---|---|
| Backend Test Suite | `python -m pytest backend` | Exit 0 | 51 passed in 3.79s |
| ML Test Suite | `python -m pytest ml` | Exit 0 | 1 passed in 0.02s |
| Frontend Test Suite | `npm --prefix frontend test` | Exit 0 | 5 passed in 2.34s |
| Frontend Production Build | `npm --prefix frontend run build` | Exit 0 | Built cleanly (`dist/` generated) |
| Ruff Code Linting | `python -m ruff check backend` | Exit 0 | All checks passed (0 errors) |
| Mypy Static Type Check | `python -m mypy backend/src` | Exit 0 | Success: no issues found in 11 source files |
| Secret Scanning (Git Commits) | `gitleaks detect -v` | Exit 0 | 2 commits scanned, 0 leaks found |
| Secret Scanning (Working Tree) | `gitleaks detect --no-git -v` | Exit 0 | Scanned 230 KB, 0 leaks found |
| Documentation Consistency | `powershell -File scripts/check_docs.ps1` | Exit 0 | 19 required docs present, all 27 SEC controls covered, 0 broken links |

---

## 6. Security Controls Checked (SEC IDs)

- **SEC-03 (Database Security)**:
  - SQLite uses file/memory binding with `PRAGMA foreign_keys = ON`.
  - Hosted PostgreSQL requires TLS (`sslmode=require` / `sslmode=verify-full`), private network host (`db.internal`), and prohibits public 0.0.0.0 binding.
  - Separate roles: `finpilot_admin` for migrations and `finpilot_app` restricted to DML.
  - Reversible Alembic migrations tested for empty-to-head, stepwise upgrade, and full downgrade.
  - Backup/restore procedure documented and tested in a disposable environment with SHA-256 verification.
  - **Status: IMPLEMENTED / VERIFIED for Layer 2 operational persistence.**
- **SEC-08 (Security Logging & Redaction)**:
  - Logging redaction extended to sanitize database connection URLs (`://user:password@host` -> `://user:[REDACTED]@host`).
  - Tested in `test_db_queries_security.py::test_database_url_credentials_redacted_in_logging`.
  - **Status: IMPLEMENTED / VERIFIED.**
- **SEC-10 (SQL Injection Safety & Parameterized Queries)**:
  - All database interactions use SQLAlchemy ORM or bound SQL expressions.
  - Prohibits string concatenation. Tested against malicious injection payloads (`'; DROP TABLE ...`, `UNION SELECT`) in `test_db_queries_security.py`.
  - **Status: IMPLEMENTED / VERIFIED.**
- **SEC-11 (Environment Validation & Fail-Closed Production)**:
  - Settings validated at startup; production rejects SQLite and non-TLS database URLs.
  - Tested in `test_config.py` and `test_db_queries_security.py`.
  - **Status: IMPLEMENTED / VERIFIED.**
- **SEC-23 (No Exposed Credentials/Files)**:
  - Database credentials never committed; injected via environment variables.
  - `.gitignore` prevents tracking database files (`*.db`, `*.sqlite3`).
  - Gitleaks clean across all commits and uncommitted files.
  - **Status: IMPLEMENTED / VERIFIED.**

---

## 7. Data, Model, and Trading Limitations

- **Simulation Only**: Operational accounts default to ₹30,000 initial scenario capital; no live order placement, payment processing, or broker connections are implemented.
- **Long-Only Equity Cash**: Position quantities are constrained to non-negative integers (`quantity >= 0`); short selling and margin borrowing are strictly prohibited.
- **Analytical Data Boundary**: Relational database is reserved for operational state, metadata, and the append-only ledger; high-frequency completed candles and features belong in partitioned Parquet/Arrow stores.

---

## 8. Acceptance Status

**PASS**

All Layer 2 acceptance criteria, database constraints, least-privilege role boundaries, backup/restore procedures, migration tests, security negative tests, and static checks are fully green and verified.
