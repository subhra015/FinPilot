# FinPilot AI — Database Backup and Disaster Recovery Guide

**Document Version:** 1.0.0  
**Layer:** 17 of 17  
**Status:** PRODUCTION OPERATIONAL  
**RTO Target:** < 15 Minutes | **RPO Target:** < 1 Hour

---

## 1. Backup Architecture Overview

FinPilot AI relies on a two-tier persistence architecture:
1. **Relational Database Tier (SQLite / PostgreSQL):** Stores accounts, portfolios, positions, users, sessions, and security audit logs.
2. **Immutable Event Ledger Tier (JSON / SQLite):** Stores append-only forward prediction records and sequential execution outcomes.

### Recovery Objectives
- **Recovery Point Objective (RPO):** Maximum allowable data loss is 1 hour of paper trades.
- **Recovery Time Objective (RTO):** Complete service restoration within 15 minutes of failure detection.

---

## 2. Automated SQLite Backup & Restoration (Paper Mode)

FinPilot provides native, non-blocking online backup utilities in `finpilot.db.backup` utilizing the SQLite Online Backup API. This ensures consistent snapshots without database locking.

### 2.1 Generating an Online Backup
```python
from pathlib import Path
from finpilot.db.backup import backup_sqlite_database

src_db = Path("data/finpilot_paper.db")
backup_dest = Path("backups/finpilot_paper_snapshot.db")

# Creates atomic copy and returns SHA-256 checksum
checksum = backup_sqlite_database(src_db, backup_dest)
print(f"Backup created successfully. Checksum: {checksum}")
```

### 2.2 Restoring from Backup with Integrity Check
```python
from pathlib import Path
from finpilot.db.backup import restore_sqlite_database

backup_file = Path("backups/finpilot_paper_snapshot.db")
target_db = Path("data/finpilot_paper.db")

# Restores database and validates SHA-256 checksum before activating
restore_sqlite_database(backup_file, target_db, expected_sha256=checksum)
print("Database restoration verified and completed.")
```

---

## 3. Production PostgreSQL Backup & Restoration

For hosted PostgreSQL deployments, automated dump and point-in-time recovery (PITR) procedures are enforced.

### 3.1 Daily Automated Backup Script (`cron.daily`)
```bash
#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="/var/backups/finpilot"
TIMESTAMP=$(date -u +"%Y%m%d_%H%M%SZ")
BACKUP_FILE="${BACKUP_DIR}/finpilot_db_${TIMESTAMP}.dump"

mkdir -p "${BACKUP_DIR}"

# Execute custom-format compressed dump via secure socket/TLS
pg_dump -Fc -v \
  --dbname="${FINPILOT_DATABASE_URL}" \
  -f "${BACKUP_FILE}"

# Generate SHA-256 digest
sha256sum "${BACKUP_FILE}" > "${BACKUP_FILE}.sha256"

# Retain backups for 30 days
find "${BACKUP_DIR}" -type f -mtime +30 -delete
```

### 3.2 Restoration Procedure
```bash
#!/usr/bin/env bash
set -euo pipefail

RESTORE_FILE="$1"

# Verify backup file digest before restoration
sha256sum -c "${RESTORE_FILE}.sha256"

# Terminate active application connections
docker compose stop api

# Execute restore into clean database
pg_restore -v --clean --if-exists --no-owner \
  --dbname="${FINPILOT_DATABASE_URL}" \
  "${RESTORE_FILE}"

# Re-run migrations to ensure schema alignment
docker compose run --rm api alembic upgrade head

# Restart application
docker compose start api
```

---

## 4. Disaster Recovery Validation Testing

Disaster recovery is continuously tested as part of the automated test suite:
- **Test:** `backend/tests/test_layer17_security_and_deployment.py::test_33_backup_restoration_verified`
- **Verification:** Creates test database, inserts records, performs online backup with checksum generation, restores to fresh path, and confirms table rows and schemas are 100% identical.
- **Status:** **PASS**.
