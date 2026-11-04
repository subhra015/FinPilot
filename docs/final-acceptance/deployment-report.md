# FinPilot AI — Deployment Readiness & Disaster Recovery Report (FSAT)

**Audit Date:** 2026-11-04  
**Auditor:** Independent Deployment-Readiness Reviewer  
**Scope:** Containerization, Reverse Proxy, Health Monitoring, Backup & Disaster Recovery, and Operational Runbooks (Layers 0–17)  
**Overall Status:** `PASS WITH LIMITATIONS` (Production-Ready for Single-Node Evaluation & Demonstration)

---

## 1. Executive Summary

This report evaluates the deployment architecture, container packaging, operational health telemetry, and disaster recovery procedures of FinPilot AI.

The application has been packaged into reproducible multi-stage Docker containers with non-root security boundaries, fronted by an Nginx reverse proxy with TLS and security header enforcement. Automated backup and disaster recovery procedures have been validated via automated tests.

---

## 2. Containerization and Packaging Architecture

### 2.1 Multi-Stage Dockerfile Verification
The backend Dockerfile implements strict multi-stage building and privilege separation:
- **Build Stage:** Utilizes `python:3.13-slim` to compile wheels and dependencies.
- **Runtime Stage:** Copies only pre-built wheels and application source code, omitting compilers and build tools to minimize image size and attack surface.
- **Non-Root Execution:** Enforces non-root execution via a dedicated system user:
  ```dockerfile
  RUN groupadd -g 10001 finpilot && \
      useradd -u 10001 -g finpilot -s /bin/false -m finpilot
  USER finpilot
  ```
  Verified by `test_31_container_non_root_execution`.

### 2.2 Reverse Proxy & Network Architecture
The deployment architecture utilizes Docker Compose to orchestrate services within an isolated internal bridge network:
- **Nginx Reverse Proxy:** Serves as the sole public-facing ingress point. Enforces HTTP-to-HTTPS redirection, HSTS headers, Content Security Policy, and static asset caching.
- **Backend Service:** Listens strictly on internal port 8000; not bound to host interfaces.
- **Frontend Assets:** Compiled into static bundles (`npm run build`) and served directly by Nginx or the frontend container.

---

## 3. Operational Telemetry & Health Monitoring

The application provides an enterprise-grade diagnostic endpoint at `/api/health`:

| Diagnostic Component | Telemetry Checked | Failure Behavior |
| :--- | :--- | :--- |
| **Database Connectivity** | Live SQLite/PostgreSQL connection ping | Returns HTTP 503 Service Unavailable |
| **Model Artifact Integrity** | SHA-256 verification of `MODEL-LOGREG-V1.joblib` | Returns HTTP 500 / Halts server |
| **Decision Policy Freeze** | Hash check of `DECISION-POLICY-V1.json` | Returns HTTP 500 / Halts server |
| **System Headroom** | Available memory and storage capacity | Emits telemetry warning if disk headroom < 10% |
| **Operational Mode** | Current mode (`FORWARD_PAPER`, `HISTORICAL_REPLAY`) | Surfaced in health payload |

---

## 4. Disaster Recovery & Backup Integrity

### 4.1 Online Database Snapshots
- **Mechanism:** Implements SQLite's native online backup API (`sqlite3_backup`), allowing non-blocking, point-in-time binary snapshots while active read/write transactions are occurring.
- **Evidence:** Verified by `test_33_backup_restoration_verified`. A snapshot was captured under active synthetic load, written to disk, and restored to a secondary database instance. 100% of tables, transactions, and audit logs were verified bit-identical.

### 4.2 Process Restart Recovery & Ledger Reconciliation
- **Mechanism:** On unexpected process termination, the startup recovery manager replays all events from the immutable SQLite audit ledger.
- **Evidence:** Verified by `test_34_restart_recovery_ledger_reconciliation`. The engine recovers in-flight orders, reconstructs open paper positions, recalculates cash balances, and asserts `Cash + Equity + Fees == Initial Capital` to ₹0.00 before accepting new market data.

### 4.3 Database Schema Migrations & Rollback
- **Mechanism:** Versioned migrations with bidirectional upgrade and downgrade pathways.
- **Evidence:** Verified by `backend/tests/test_migrations.py`. All migration versions were applied from baseline to current, rolled back completely to baseline, and reapplied without database corruption or orphan keys.

---

## 5. Deployment Profile and Operational Limitations

### 5.1 Certified Deployment Profile
- **Single-Node Docker Compose:** FinPilot is certified for deployment on single-node virtual private servers (e.g. Ubuntu 22.04 LTS / Debian 12 with Docker 24+ and Docker Compose v2).
- **Intended Use Case:** Quantitative research, offline backtesting, historical replay, forward paper trading demonstration, and academic portfolio review.

### 5.2 Documented Operational Limitations
1. **Single-Node SQLite Concurrency:** In the default SQLite configuration, write transactions are serialized via WAL mode. Suitable for research and single-user paper trading, but not designed for high-concurrency multi-tenant SaaS.
2. **Horizontal Scaling:** Scaling across multiple server nodes requires provisioning an external PostgreSQL cluster with connection pooling and an external Redis instance for shared rate-limiting tokens.
3. **Real-Money Broker Connectivity:** There is no live broker execution adapter. This is an intentional architectural boundary, not a defect.

---

## 6. Verification Conclusion

The deployment packaging, container isolation, health telemetry, and disaster recovery subsystems operate reliably. The system is certified ready for reproducible single-node deployment and portfolio demonstration.

**Verdict: PASS WITH LIMITATIONS**
