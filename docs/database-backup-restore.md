# FinPilot AI — Database Backup, Restore & Retention Policy

Status: **Layer 2 Specification (Ratified)**  
Related: `ARCHITECTURE.md` §5, `SECURITY.md` (SEC-03, SEC-10, SEC-11, SEC-23), `docs/threat-model.md`.

---

## 1. Persistence Architecture Overview

FinPilot AI distinguishes between two persistence tiers to guarantee both high-performance analytics and ACID operational safety:

1. **Analytical Tier (Large Historical Data)**:
   - Historical completed candles, high-frequency time series, and derived feature vectors are stored in **immutable, partitioned Apache Parquet / Arrow files**.
   - Tracked in the operational database via `dataset_manifests` with schema versions, row counts, start/end timestamps, and SHA-256 integrity checksums.
   - Retained permanently in cold/warm object storage; no heavy analytical candle bloat in the operational relational database.

2. **Operational Tier (Relational State & Audit Ledger)**:
   - Managed in **PostgreSQL** (with TLS enforced via `sslmode=require` / `sslmode=verify-full`).
   - Stores operational state: instruments, symbol history, accounts (₹30,000 initial scenario), portfolios, positions (long-only equity), orders, and the append-only `ledger_events`.
   - Local development and automated testing utilize SQLite with `PRAGMA foreign_keys = ON` and in-memory or file isolation.

---

## 2. Private Network Deployment & Connection Security (SEC-03)

- **No Public Database Binding**:
  - The PostgreSQL database is bound exclusively to a private VPC subnet or internal network (e.g. `db.internal:5432`).
  - It is **never** bound to `0.0.0.0` or assigned a public IP address.
  - Access is restricted to application server containers/hosts via strict security group rules / firewall allow-lists.
- **TLS Requirement**:
  - Production configurations enforce TLS by validating that `database_url` includes `sslmode=require` or `sslmode=verify-full`. Non-TLS configurations fail closed at startup (`ConfigError`).
- **Connection Secret Hygiene (SEC-02, SEC-08, SEC-11)**:
  - Database credentials are injected via `FINPILOT_DATABASE_URL` environment variable at runtime.
  - Plaintext credentials must never appear in repository files, logs, or client-facing responses. The logging formatter (`RedactingFormatter` / `JsonFormatter`) automatically redacts `://user:password@` patterns to `://user:[REDACTED]@`.

---

## 3. Least-Privilege Role Model (SEC-03)

FinPilot enforces separate database roles to isolate schema migrations from runtime operations:

| Role Name | Scope | Privileges | Prohibited Actions |
|---|---|---|---|
| `finpilot_admin` | Migration & Schema Management | Owns database schema; `CREATE`, `ALTER`, `DROP` tables and indexes; runs Alembic migrations | Not used by runtime application services |
| `finpilot_app` | Runtime Application Service | DML only: `SELECT`, `INSERT`, `UPDATE`, `DELETE` on application tables; `USAGE, SELECT` on sequences | No DDL (`CREATE`, `ALTER`, `DROP`), no superuser, no createdb, read-only on `schema_meta` and `alembic_version` |

Role setup script is generated via `finpilot.db.roles.generate_role_setup_script()`:
```sql
-- See backend/src/finpilot/db/roles.py for the full template
ALTER SCHEMA public OWNER TO finpilot_admin;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO finpilot_admin, finpilot_app;
GRANT CREATE ON SCHEMA public TO finpilot_admin;
REVOKE CREATE ON SCHEMA public FROM finpilot_app;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO finpilot_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO finpilot_app;
REVOKE INSERT, UPDATE, DELETE ON TABLE alembic_version FROM finpilot_app;
REVOKE INSERT, UPDATE, DELETE ON TABLE schema_meta FROM finpilot_app;
```

---

## 4. Production Backup & Restore Runbook (PostgreSQL)

### 4.1 Automated Daily Snapshot (Backup)
Execute via a cron job running inside the private network:

```bash
#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="/var/backups/finpilot"
TIMESTAMP=$(date -u +"%Y%m%d_%H%M%SZ")
BACKUP_FILE="${BACKUP_DIR}/finpilot_prod_${TIMESTAMP}.dump"
CHECKSUM_FILE="${BACKUP_FILE}.sha256"

mkdir -p "${BACKUP_DIR}"
chmod 700 "${BACKUP_DIR}"

# 1. Execute pg_dump using custom directory/tar format with compression
pg_dump \
  --host="db.internal" \
  --port=5432 \
  --username="finpilot_admin" \
  --format=custom \
  --compress=9 \
  --blobs \
  --file="${BACKUP_FILE}" \
  finpilot

# 2. Compute SHA-256 checksum for integrity verification
sha256sum "${BACKUP_FILE}" > "${CHECKSUM_FILE}"
chmod 600 "${BACKUP_FILE}" "${CHECKSUM_FILE}"

echo "Backup completed: ${BACKUP_FILE} (SHA-256 verified)"
```

### 4.2 Disaster Recovery Procedure (Restore)

```bash
#!/usr/bin/env bash
set -euo pipefail

BACKUP_FILE="$1"
CHECKSUM_FILE="${BACKUP_FILE}.sha256"
TARGET_DB="finpilot_recovery"

# 1. Verify SHA-256 checksum before restoration
echo "Verifying backup integrity..."
sha256sum -c "${CHECKSUM_FILE}"

# 2. Re-create clean target database with proper role ownership
dropdb --host="db.internal" --username="finpilot_admin" --if-exists "${TARGET_DB}"
createdb --host="db.internal" --username="finpilot_admin" --owner="finpilot_admin" "${TARGET_DB}"

# 3. Restore schema and data using pg_restore
pg_restore \
  --host="db.internal" \
  --port=5432 \
  --username="finpilot_admin" \
  --dbname="${TARGET_DB}" \
  --no-owner \
  --clean \
  --if-exists \
  "${BACKUP_FILE}"

# 4. Verify table counts and ledger integrity
psql --host="db.internal" --username="finpilot_admin" --dbname="${TARGET_DB}" -c "
  SELECT count(*) AS instruments_count FROM instruments;
  SELECT count(*) AS accounts_count FROM accounts;
  SELECT count(*) AS ledger_events_count FROM ledger_events;
"
```

---

## 5. Local Development & Disposable Test Procedures (SQLite)

In local development and automated testing:
- **Backup**: `backup_sqlite_database(src, dst)` invokes the SQLite Online Backup API (`src_conn.backup(dst_conn)`), producing a consistent snapshot and computing its SHA-256 checksum.
- **Restore**: `restore_sqlite_database(backup_file, target_db, expected_sha256)` validates the SHA-256 checksum to prevent loading corrupted/tampered artifacts, then restores the database into a target disposable path.
- Automated tests in `backend/tests/test_backup_restore.py` continuously exercise this procedure in CI.

---

## 6. Retention Policy

| Tier / Data Category | Backup Frequency | Retention Period | Storage Target | Disposal Method |
|---|---|---|---|---|
| **Operational DB (PostgreSQL)** | Daily full dump + WAL archiving | 30 days daily dumps; 7 days point-in-time WAL | Encrypted private bucket / isolated volume | Cryptographic shredding after retention expiry |
| **Prediction / Event Ledger** | Continuous append-only replication | Permanent (immutable audit trail) | PostgreSQL + WORM-compliant storage replication | Retained indefinitely for research and audit validity |
| **Analytical Parquet Manifests** | Per dataset ingestion / export | Permanent (versioned) | Object storage with object lock/versioning | Version deprecation only; manifests preserved |
| **Ephemeral Test Databases** | On-demand in test suites | Immediate teardown post-test | Temp directory / memory | Automatically purged by test runner |
