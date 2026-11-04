# FinPilot AI — Production Deployment Guide

**Document Version:** 1.0.0  
**Layer:** 17 of 17  
**Status:** PRODUCTION HARDENED  
**Operating Environment:** Linux (Ubuntu 22.04 LTS / Debian 12 / RHEL 9) or Windows Server

---

## 1. System Prerequisites

- **Compute:** Minimum 2 vCPU, 2 GB RAM (4 GB recommended).
- **Storage:** 20 GB SSD storage with persistent volume support.
- **Runtimes:**
  - Docker Engine 24.0+
  - Docker Compose v2.20+
- **Network:**
  - Public Ports: `80/tcp` (HTTP to HTTPS redirect), `443/tcp` (HTTPS / TLS 1.3).
  - Internal Ports: `8000/tcp` (FastAPI backend - strictly isolated inside Docker network).
- **TLS Certificates:** Valid X.509 certificate and private key (Let's Encrypt or corporate CA).

---

## 2. Step-by-Step Deployment Procedure

### Step 1: Clone Repository and Checkout Release
```bash
git clone https://github.com/subhra015/FinPilot.git
cd FinPilot
git checkout v1.0.0
```

### Step 2: Verify Release Artifact Integrity
Verify all frozen models, evaluation manifests, and deployment configuration files:
```bash
sha256sum -c artifacts/release/CHECKSUMS.sha256
```
*Expected output: All 12 files must report `OK`.*

### Step 3: Configure Production Environment Variables
Copy the production environment template:
```bash
cp .env.production.example .env.production
chmod 600 .env.production
```
Generate a cryptographically secure 64-character secret key and edit `.env.production`:
```bash
# Generate key using Python CSPRNG
python3 -c "import secrets; print(secrets.token_hex(32))"
```
Populate `.env.production`:
```env
FINPILOT_APP_ENV=production
FINPILOT_DEBUG=false
FINPILOT_SECRET_KEY=<PASTE_GENERATED_64_CHAR_HEX_KEY>
FINPILOT_DATABASE_URL=postgresql+psycopg://finpilot_app:db_strong_password@db.internal:5432/finpilot?sslmode=require
FINPILOT_CORS_ALLOWED_ORIGINS=https://finpilot.yourdomain.com
FINPILOT_DOCS_ENABLED=false
FINPILOT_LOG_LEVEL=INFO
```

### Step 4: Install TLS Certificates
Place your TLS certificates into the Nginx configuration directory:
```bash
mkdir -p deploy/nginx/certs
cp /path/to/fullchain.pem deploy/nginx/certs/finpilot.crt
cp /path/to/privkey.pem deploy/nginx/certs/finpilot.key
chmod 600 deploy/nginx/certs/finpilot.key
```

### Step 5: Launch Containers via Docker Compose
Build and start the application in detached mode:
```bash
docker compose up -d --build
```

### Step 6: Verify Deployment Health
Query the comprehensive component health endpoint:
```bash
curl -k https://localhost/api/health
```
*Expected response:*
```json
{
  "status": "healthy",
  "components": {
    "backend": {"status": "UP"},
    "database": {"status": "UP"},
    "model_registry": {"status": "UP", "details": {"model_hash_verified": true}},
    "market_data_provider": {"status": "UP"},
    "prediction_service": {"status": "UP"},
    "paper_execution_service": {"status": "UP"}
  }
}
```

---

## 3. Production Environment Reference

| Environment Variable | Required | Default | Description |
| :--- | :---: | :---: | :--- |
| `FINPILOT_APP_ENV` | Yes | `production` | Runtime mode. Must be `production` (enforces HSTS, disables docs). |
| `FINPILOT_DEBUG` | Yes | `false` | Must be `false` in production. Fails closed if `true`. |
| `FINPILOT_SECRET_KEY` | Yes | None | Minimum 32 chars (64 hex recommended). Used for CSRF HMAC and cookie encryption. |
| `FINPILOT_DATABASE_URL` | Yes | None | Production PostgreSQL URL requiring TLS (`sslmode=require`). |
| `FINPILOT_CORS_ALLOWED_ORIGINS` | Yes | None | Comma-separated HTTPS origins. Wildcard `*` is strictly rejected. |
| `FINPILOT_DOCS_ENABLED` | No | `false` | Disables `/docs`, `/redoc`, and `/openapi.json`. |
| `FINPILOT_LOG_LEVEL` | No | `INFO` | Application log verbosity (`INFO`, `WARNING`, `ERROR`). |

---

## 4. Container Hardening Verification

Inspect the running containers to confirm non-root execution and security profiles:
```bash
docker inspect finpilot-api --format '{{.Config.User}}'
# Returns: 10001:10001 (unprivileged user)

docker inspect finpilot-api --format '{{.HostConfig.ReadonlyRootfs}}'
# Returns: true (immutable root filesystem)
```
