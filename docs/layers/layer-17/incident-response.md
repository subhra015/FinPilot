# FinPilot AI — Operational Incident Response Runbook

**Document Version:** 1.0.0  
**Layer:** 17 of 17  
**Status:** ACTIVE / PRODUCTION  
**Scope:** Security Breaches, Operational Outages, and Execution Anomalies

---

## 1. Incident Classification Matrix

| Severity | Definition | Target Response | Target Resolution | Examples |
| :---: | :--- | :---: | :---: | :--- |
| **P1 — Critical** | Immediate security breach, secret leak, or accounting compromise | < 15 minutes | < 2 hours | Production secret key leaked, ledger tamper detected, unauthorized model modification. |
| **P2 — High** | Subsystem outage, data feed interruption, or session hijacking | < 30 minutes | < 4 hours | Stale market data feed (> 300s), database failover, persistent rate-limit breaches. |
| **P3 — Medium** | Degraded functionality or minor configuration anomaly | < 2 hours | < 24 hours | Non-critical background task delay, frontend rendering warning, individual test timeout. |
| **P4 — Low** | Informational event, minor bug, or documentation defect | < 8 hours | < 72 hours | Typo in log message, minor telemetry gap, non-breaking dependency alert. |

---

## 2. Emergency Operational Runbooks

### Runbook 1: Exposed Secret Key / Credential Leakage (P1)
1. **Immediate Revocation & Rotation:**
   - Generate a fresh 64-character secret key:
     ```bash
     python3 -c "import secrets; print(secrets.token_hex(32))"
     ```
   - Update `FINPILOT_SECRET_KEY` in `.env.production`.
   - Restart the application container: `docker compose restart api`.
2. **Session Invalidation:**
   - Rotating `FINPILOT_SECRET_KEY` automatically invalidates all existing CSRF tokens and forces all users to re-authenticate.
   - Revoke all active user sessions in the database:
     ```sql
     UPDATE user_sessions SET is_revoked = true, revoked_at = NOW();
     ```
3. **Repository Cleanse (if leaked to Git):**
   - Execute `git-filter-repo` or BFG to remove compromised commits.
   - Force push cleaned branch and notify all repository collaborators.

### Runbook 2: Model Hash Mismatch / Unauthorized Model Change (P1)
1. **Symptom:** Application reports `CRITICAL INTEGRITY FAILURE: Frozen model checksum mismatch` and refuses to process predictions.
2. **Containment:**
   - Do NOT restart with forced bypass. Engine fail-closed behavior is working as intended.
3. **Verification:**
   - Compute hash of active model file:
     ```bash
     sha256sum artifacts/models/MODEL-LOGREG-V1/MODEL-LOGREG-V1.joblib
     ```
   - Compare against frozen manifest hash (`ede1e29783917673f44b68e72e62f446b96972feb741627539f52c2a2c455bfb`).
4. **Remediation:**
   - Restore canonical model binary from verified release artifacts:
     ```bash
     git checkout v1.0.0 -- artifacts/models/MODEL-LOGREG-V1/MODEL-LOGREG-V1.joblib
     ```
   - Review audit logs for unauthorized file modifications.

### Runbook 3: Market Data Provider Outage / Stale Data (P2)
1. **Symptom:** `/api/health` reports `market_data_provider` as `DEGRADED` or `DOWN`.
2. **Automatic Policy:**
   - The engine automatically triggers the **Fail-Closed Stale Data Policy**:
     - All new candidate trade proposals are rejected (`DATA_STALE`).
     - Existing open positions continue to be monitored for protective exits (stop-loss / target / 15:15 IST forced cut).
3. **Operational Action:**
   - Verify provider endpoint connectivity and API quota.
   - If feed cannot be restored by 15:00 IST, trigger manual forced session liquidation of open paper positions.

### Runbook 4: Paper Portfolio Accounting Discrepancy (P1)
1. **Symptom:** Portfolio manager raises `DomainValidationError: Accounting invariant breach`.
2. **Investigation:**
   - Execute double-entry reconciliation query:
     $$\text{Cash} + \text{Position Market Value} + \text{Incurred Fees} - \text{Gross Realized P\&L} = \text{Initial Capital}$$
   - Inspect `ledger_events` table for duplicate fill events or sequence gaps.
3. **Remediation:**
   - Reconstruct portfolio state by replaying verified ledger events from sequence 1.
   - Record an auditable `CORRECTION` event with detailed administrative justification.

---

## 3. Emergency Kill Switch Activation

If unexpected market behavior or catastrophic data corruption occurs:

### Option A: Via Authenticated Admin API
```bash
curl -X PATCH https://finpilot.yourdomain.com/api/risk/config \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: $CSRF_TOKEN" \
  --cookie "finpilot_session=$SESSION_TOKEN" \
  -d '{"updates": {"kill_switch_active": true}}'
```

### Option B: Via Container Shell / Direct Command Line
```bash
docker exec -it finpilot-api python3 -c "
from finpilot.risk.config_service import RiskConfigService
svc = RiskConfigService()
svc.activate_kill_switch('Emergency containment initiated by ops')
print('Kill switch successfully activated')
"
```
*Effect: All new proposal authorizations are instantly denied until administrative deactivation.*
