# FinPilot AI User Flow & Operator Guide

Governed by:
- [PROJECT_SPEC.md](../PROJECT_SPEC.md)
- [ARCHITECTURE.md](../ARCHITECTURE.md)
- [SECURITY_CHECKLIST.md](../SECURITY_CHECKLIST.md) (SEC-01, SEC-02, SEC-06, SEC-07, SEC-09, SEC-15, SEC-16, SEC-19)

---

## 1. Overview & Navigation Architecture

FinPilot AI provides an intuitive, high-density, accessible dark-mode quantitative terminal built in React 19 and TypeScript. The application cleanly isolates three execution modes (`HISTORICAL REPLAY`, `FORWARD PAPER`, `SYNTHETIC DEMO`) and provides eight primary navigation views:

1. **Research Status** (`/research`): Specification parameters, hypothesis, V1 temporal partitions, 1-session embargo, active models, and the ₹300–₹1,500 evaluation hurdle band.
2. **Stock Scanner** (`/scanner`): Point-in-time universe explorer with causal relative volume, RSI, ATR, VWAP approximation distance, and session geometry.
3. **Trade Proposal** (`/proposal`): Next-bar execution inspector ($t_{\text{fill}} \ge t_{\text{signal}} + 5\text{m}$), integer share sizing ($Q \ge 1$), round-trip statutory fee breakdown, and selective decision states.
4. **Risk Console** (`/risk`): 11 deny-by-default safety gate rules, emergency kill switch, manual trading pause, and cryptographically signed audit stream.
5. **Paper Portfolio** (`/portfolio`): Server-authoritative ₹30,000 capital accounting, available cash, reserved margin, active positions, orderly square-off, and emergency exit actions.
6. **Prediction Ledger** (`/ledger`): Append-only SHA-256 hash-chained event stream, immutable records, explicit `CORRECTION` events, and deterministic replay verification.
7. **Evaluation Report** (`/evaluation`): Multi-baseline comparison (`REF-NOTRADE-V1`, `STRAT-SIMPLE-V1` vs ML models), economics breakdown, and Murphy Brier score decomposition (Reliability, Resolution, Uncertainty).
8. **Data Health** (`/data-health`): 8-point data integrity audit checklist, licensing governance contracts, and quarantine log inspection.

---

## 2. Authentication & Session Lifecycles (NIST SP 800-63B-4)

### 2.1 Sign In & Registration
- **Password Policy**: Adheres strictly to NIST SP 800-63B-4. Standard user passphrases must contain at least 15 characters without arbitrary composition rules. MFA-enabled admin accounts require at least 8 characters.
- **Session Security (SEC-15)**: Authentication sets an opaque, cryptographically random `finpilot_session` cookie marked `HttpOnly`, `Secure`, and `SameSite=Lax`. Zero session tokens or credentials exist in `window.localStorage` or `window.sessionStorage`.
- **Anti-CSRF Protection (SEC-16)**: Mutating requests (`POST`, `PUT`, `PATCH`, `DELETE`) automatically extract the anti-CSRF token from the `finpilot_csrf` cookie and inject it into the `X-CSRF-Token` HTTP header.
- **Session Expiration**: Automatic 30-minute inactivity sliding expiration and 12-hour absolute timeout. An unauthorized (401) response immediately triggers the `SessionExpiredModal` requesting safe re-authentication without data loss.

---

## 3. Execution Mode Selection & Visual Isolation

The dashboard features a persistent mode switcher in the top navigation header paired with a full-width warning banner:
- **`HISTORICAL REPLAY` (Cyan Banner)**: Point-in-time backtesting using historical completed NSE 5-minute candles.
- **`FORWARD PAPER` (Amber Banner)**: Forward-looking paper simulation under strict ₹30,000 capital limits. Disconnected from live broker execution.
- **`SYNTHETIC DEMO` (Purple Banner)**: Isolated synthetic fixtures for component demonstration. Disclaimed as artificial fixtures prohibited from market evidence reporting.

---

## 4. Operational Flows Across Views

### 4.1 Stock Scanner to Proposal Generation
1. In the **Stock Scanner**, view liquid Nifty 50 stocks with causal relative volume (calculated strictly against historical comparable intraday intervals).
2. Click **Propose Trade** on any symbol (e.g. `TCS`).
3. The dashboard transitions to the **Trade Proposal** view, pre-populating symbol, entry price, stop loss, and profit target.
4. Modify parameters and observe real-time client-side validation (enforcing integer $Q \ge 1$, entry $> 0$, stop loss $<$ entry, target $>$ entry, and capital $\le$ ₹30,000).
5. Review the Indian intraday statutory transaction fee breakdown (Brokerage, STT, Exchange turnover, SEBI turnover, Stamp duty, GST).
6. Click **Generate Verified Proposal** to review calibrated probability, bin sample support, and next-bar executable fill timing ($t_{\text{fill}} \ge t_{\text{signal}} + 5\text{m}$).

### 4.2 Risk Engine & Emergency Interventions (SEC-09)
1. In the **Risk Console**, inspect the live status of all 11 deny-by-default rules.
2. If logged in as `USER` (read-only monitor), emergency controls are disabled with clear tooltips indicating administrative authority is required.
3. If logged in as `ADMIN`, operators can click **ACTIVATE KILL SWITCH** to instantly halt all order routing across the entire platform, or **Pause Trading** to prevent new entries while preserving orderly exits.
4. All administrative actions create immutable, signed audit events displayed in the audit trail table.

### 4.3 Paper Portfolio Management (SEC-19)
1. View server-authoritative balances: Initial Capital (₹30,000.00), Available Cash, Reserved Margin, and Total Equity.
2. For open positions, trigger:
   - **Orderly Square-off**: Dispatches intent to exit position cleanly at the next 5-minute bar open.
   - **Emergency Exit**: Cancels outstanding bracket orders and dispatches an immediate market exit.

### 4.4 Deterministic Replay & Ledger Audit
1. In the **Prediction Ledger**, inspect the continuous SHA-256 hash chain ($H_n = \text{SHA256}(H_{n-1} \parallel \dots)$).
2. Review explicit `CORRECTION` events which reference prior event IDs without mutating prior historical records.
3. Click **Run Replay Verification** to trigger a full from-genesis deterministic ledger replay. Verify reconstructed cash, positions, realized P&L, and zero-tampering guarantees.
