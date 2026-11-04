# FinPilot AI — Trading Simulator & Risk Engine Report (FSAT)

**Audit Date:** 2026-11-04  
**Auditor:** Independent Quantitative Systems Auditor  
**Scope:** Execution Simulator, Risk Gate Governance, Statutory Fee Schedule, and Challenge Suite (Layers 0–17)  
**Overall Status:** `PASS` (Conservative Fill Invariants and Double-Entry Accounting Fully Reconciled)

---

## 1. Executive Summary

This report evaluates the execution mechanics, fill realism, statutory cost accounting, and risk management constraints implemented in the FinPilot AI paper execution simulator (`backend/src/finpilot/execution/`).

All simulation components operate under strictly conservative, pessimistic assumptions. The simulator was audited against statutory Indian market rules and subjected to the 17-part Layer 14 Challenge Suite, achieving a 100% pass rate with zero accounting discrepancies.

---

## 2. Realistic Execution Simulator Mechanics

The FinPilot `ExecutionSimulator` rejects optimistic assumptions (such as zero-slippage fills, mid-point execution, or frictionless turnover):

### 2.1 Conservative Fill Rules
1. **Next-Bar Open Execution:** An order generated from a signal at candle $t$ cannot be filled at candle $t$. It is evaluated for execution starting on candle $t+1$ (`earliest_entry_timestamp > signal_timestamp`).
2. **Modelled Slippage:** A fixed 2.0 basis points (0.02%) penalty is deducted from entry fills (higher buy price) and exit fills (lower sell price).
3. **Volume Participation Cap:** Order fill size is strictly capped at 10% of the candle's traded volume. If required volume exceeds 10%, the order experiences a realistic partial fill.
4. **Pessimistic Stop-First Priority:** If both the profit target and stop-loss price fall within the High–Low range of the same candle bar, the simulator assumes the **stop-loss was triggered first**.
5. **Stop-Gap Realism:** If a session opens with a price gap below a position's stop-loss price, the fill occurs at the **actual market open price**, not the theoretical stop price.

---

## 3. Statutory NSE Fee Schedule & Accounting Engine

FinPilot calculates statutory Indian exchange and regulatory costs on an itemized basis for every trade leg:

$$\text{Total Transaction Friction} = \text{Brokerage} + \text{STT} + \text{Exchange Charges} + \text{SEBI Turnover} + \text{Stamp Duty} + \text{GST} + \text{Slippage}$$

### Itemized Fee Schedule (NSE Cash Intraday)

| Statutory Component | Regulatory Formula | Intraday Rate | Applicability |
| :--- | :--- | :---: | :--- |
| **Brokerage** | $\min(0.03\% \times \text{Turnover}, ₹20)$ | Up to ₹20/order | Both Buy & Sell legs |
| **Securities Transaction Tax (STT)** | Statutory Finance Act rate | 0.025% | Sell leg only |
| **Exchange Transaction Charges** | NSE standard transaction fee | 0.00297% | Both Buy & Sell legs |
| **SEBI Turnover Charges** | SEBI statutory regulatory fee | 0.0001% (₹10/crore) | Both Buy & Sell legs |
| **Stamp Duty** | Indian Stamp Act (uniform) | 0.003% | Buy leg only |
| **Goods & Services Tax (GST)** | Indian GST on financial services | 18.0% | On (Brokerage + Exchange + SEBI) |
| **Modelled Slippage** | Simulated market impact | 0.020% (2.0 bps) | Both Buy & Sell legs |

### Double-Entry Accounting Invariant
At every discrete state transition (order reservation, fill, partial fill, exit, commission debit), the portfolio validates the core conservation law:

$$\text{Initial Capital} = \text{Available Cash} + \text{Reserved Cash} + \sum (\text{Qty} \times \text{Current Price}) + \text{Total Incurred Fees} - \text{Realized P&L}$$

Any floating-point deviation exceeding $10^{-6}$ immediately triggers an `AccountingDiscrepancyError`. Across all historical replays and stress challenges, the accounting discrepancy was exactly **₹0.00**.

---

## 4. Independent Risk Engine Gate Governance

The risk engine (`backend/src/finpilot/risk/`) acts as an authoritative, independent barrier between trade proposal generation and order dispatch:
- **Model Independence:** The ML model cannot override or bypass the risk engine (`test_risk_model_cannot_bypass.py`).
- **Integer Share Sizing:** Only whole integer shares are allocated. Fractional share allocations are strictly rejected.
- **Concentration Caps:** No single position may exceed 50% of current equity.
- **Exposure Caps:** Aggregate market exposure is capped at 100% of equity (no leverage).
- **Position Limits:** Maximum 2 concurrent open positions across the universe.

---

## 5. Layer 14 Challenge Suite Verification

The simulator was subjected to the 17 stress tests in `backend/tests/workflow/test_challenge_suite.py`:

| Challenge ID | Target Stress Scenario | Verification Invariant | Result |
| :--- | :--- | :--- | :---: |
| **CH-01** | Stop Gap Open | Fill at open, not stop price; accounting reconciled | **PASS** |
| **CH-02** | Stop / Target Collision | Stop loss takes priority over target; loss realized | **PASS** |
| **CH-03** | Partial Fill | Fill capped at 10% bar volume; remainder managed | **PASS** |
| **CH-04** | Limit Touch Without Fill | Order remains unfilled when volume cannot prove fill | **PASS** |
| **CH-05** | Duplicate Event | Idempotent ledger; duplicate signals ignored | **PASS** |
| **CH-06** | Out-of-Order Candle | Out-of-order timestamp rejected fail-closed | **PASS** |
| **CH-07** | Simultaneous Candidates | Deterministic cash competition by calibrated score | **PASS** |
| **CH-08** | Session Close Unresolved | Open positions liquidated/handled at cutoff boundary | **PASS** |
| **CH-09** | Provider Outage / Stale Data | Halts new entries; maintains position monitoring | **PASS** |
| **CH-10** | Corporate Action Discontinuity | Price splits detected; abnormal returns rejected | **PASS** |
| **CH-11** | Unauthenticated API Call | HTTP 401 Unauthorized enforced | **PASS** |
| **CH-12** | Cross-User Data Access | Tenant data boundary enforced; 403 Forbidden | **PASS** |
| **CH-13** | XSS Payload in Input | Input rejected by strict regex validation | **PASS** |
| **CH-14** | Malformed / Oversized Import | Payloads exceeding size limits rejected | **PASS** |
| **CH-15** | Rate Limit Abuse | Sliding window token bucket returns 403 / 429 | **PASS** |
| **CH-16** | CSRF Attempt | Requests without matching CSRF token rejected | **PASS** |
| **CH-17** | Unauthorized Admin Request | Non-admin accounts blocked with 403 Forbidden | **PASS** |
| **Sequence** | Complete 17-Scenario Sequence | Full continuous run executed without state leakage | **PASS** |

---

## 6. Real-Money Trading Prohibition Audit

A comprehensive code analysis of all modules in `finpilot/execution/` and `finpilot/risk/` was conducted to confirm the complete absence of live trading infrastructure:
1. **Zero Broker API SDKs:** No imports or references to `kiteconnect`, `smartapi`, `breeze_connect`, `upstox_client`, or `fyers_api`.
2. **Zero Broker Credential Storage:** No environment variables or configuration entries for broker API keys, client IDs, or trading PINs.
3. **Runtime Protection:** `test_35_prohibited_real_money_execution_attempts` asserts that any attempt to pass a live order routing directive raises a fatal `SecurityError`.

---

## 7. Verification Conclusion

The FinPilot execution simulator and risk engine satisfy all requirements for realistic, conservative paper trading. Statutory fees are accurately decomposed, fill assumptions are appropriately pessimistic, and capital accounting is fully reconciled.

**Verdict: PASS**
