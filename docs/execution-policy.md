# FinPilot AI — Execution & Portfolio Simulation Policy

Status: **Ratified (Layer 6)**  
Related: `PROJECT_SPEC.md` §2, `docs/trade-policy-contract-v1.md`, `ARCHITECTURE.md` §1, §3.  

---

## 1. Core Principles and Causal Invariants

FinPilot AI simulates realistic execution and portfolio state tracking for **NSE cash equity intraday trading**. The execution engine adheres strictly to the following binding invariants:

1. **Server Authority (SEC-19)**: All prices, fills, costs, stops, targets, P&L, and cash reservations are calculated server-side. Client-submitted prices or quantities are never authoritative.
2. **Causal Separation of Signal vs Fill**: A completed 5-minute candle at timestamp $t_{\text{signal}}$ emits a proposal only after its close is available. The earliest executable fill event occurs at the **open of the subsequent candle** ($t_{\text{fill}} \ge t_{\text{signal}} + 5\text{m}$). **Retroactive fills at the decision candle's close are prohibited.**
3. **Integer Share Quantities**: Fractional shares are rejected ($Q \in \mathbb{Z}^+$).
4. **No Shorting & No Leverage**: Long-only cash equity; short selling and borrowing are prohibited.
5. **Shared Capital & Reservation**: All candidates share a single cash pool (initial scenario capital: ₹30,000.00). BUY orders lock estimated total capital in pending cash reservations to prevent double-spending across concurrent signals.
6. **No Real Money / No Real Broker Placement**: All orders, fills, positions, and fees are simulated within research and paper environments (`HISTORICAL_REPLAY`, `FORWARD_PAPER`, `SYNTHETIC_DEMO`). No live broker orders are placed.

---

## 2. Order Execution & Matching Rules

### 2.1 Market Orders
- Market orders execute at the next 5-minute candle's `open` adjusted for modelled slippage:
  - BUY fill price: $\text{round\_paisa}(\text{open} \times (1 + \frac{\text{slippage\_bps}}{10000}))$
  - SELL fill price: $\text{round\_paisa}(\text{open} \times (1 - \frac{\text{slippage\_bps}}{10000}))$
- Default modelled slippage: **2.0 basis points (0.02%)**.

### 2.2 Limit Orders (Touch Without Fill Rule)
- **Binding Rule**: *A limit price touch does NOT constitute a fill.*
- For BUY limit orders at limit price $P_{\text{limit}}$:
  - If $\text{bar.low} < P_{\text{limit}}$: Price penetrated below the limit $\implies$ fills at $\min(P_{\text{limit}}, \text{bar.open})$.
  - If $\text{bar.low} == P_{\text{limit}}$: Price only touched the limit without penetration $\implies$ **UNFILLED** (remains pending).
  - If $\text{bar.low} > P_{\text{limit}}$: Price never reached the limit $\implies$ **UNFILLED**.

### 2.3 Volume Participation Cap and Partial Fills
- To prevent unrealistic instant execution of large orders against illiquid bars, the engine enforces a **Maximum Volume Participation Cap**:
  $$\text{Max Fillable Quantity} = \max\left(1, \lfloor \text{bar.volume} \times 0.10 \rfloor\right)$$
- If the remaining order quantity exceeds the participation cap, the order is **partially filled** up to the cap. The unfilled remainder remains pending until subsequent candles or order expiry.
- If $\text{bar.volume} == 0$ (e.g. trading halt, circuit breaker, or missing liquidity), **zero fills occur**.

### 2.4 Gap-Through-Stop Execution
- If a stock gaps down past the protective stop loss (i.e. $\text{bar.open} < P_{\text{stop}}$), the execution simulator fills the exit at the **actual bar opening price** ($\text{bar.open}$), NOT the theoretical stop price.
- The trade is flagged with `is_gap_fill = True` and exit reason `GAP_STOP`.

### 2.5 Same-Bar Stop / Target Collision (Ambiguity Disclosure)
- In historical 5-minute OHLCV data without intra-bar tick sequences, if a bar exhibits:
  $$\text{bar.low} \le P_{\text{stop}} \quad \text{AND} \quad \text{bar.high} \ge P_{\text{target}}$$
  the execution sequence is fundamentally ambiguous.
- **Protocol**:
  1. Set `is_ambiguous_exit = True`.
  2. **Standard Conservative Policy (`CONSERVATIVE_STOP_FIRST`)**: The simulator assumes the protective stop loss was triggered first to avoid false optimism. Exit price is set to $P_{\text{stop}}$ (or $\text{bar.open}$ if gap down).
  3. **Sensitivity Reporting (`OPTIMISTIC_TARGET_FIRST`)**: Comparative evaluation runs report counterfactual outcomes assuming the profit target was hit first, explicitly disclosing the strategy's sensitivity to intra-bar ambiguity.

### 2.6 Session Cutoff & Feed Interruption
- **Entry Cutoff**: 15:00:00 IST. No new order entries are permitted after 15:00 IST. Unfilled entry orders expire immediately.
- **Compulsory Square-Off**: 15:15:00 IST. Any open position reaching 15:15 IST triggers an automatic market exit, guaranteeing flat positions prior to the 15:30 IST market close.
- **Feed Interruption / Missing Close**: If market data terminates prematurely without normal session square-off, positions are marked `PositionStatus.UNRESOLVED` at the last available mark price and flagged in the audit ledger.

---

## 3. Versioned Fee Schedule (`NSE_EQUITY_INTRADAY_V1`)

All costs are calculated deterministically and rounded to the nearest paisa (₹0.01) using `ROUND_HALF_UP`:

| Fee / Tax Component | Rate / Formula | Applied On |
|---|---|---|
| **Brokerage** | $\min(0.03\% \text{ of turnover}, ₹20.00)$ per executed order | BUY and SELL |
| **Securities Transaction Tax (STT)** | 0.025% of turnover | SELL only (Equity Intraday) |
| **Exchange Turnover Charges** | 0.00297% of turnover | BUY and SELL |
| **SEBI Turnover Charges** | 0.0001% (₹10 per crore) | BUY and SELL |
| **Stamp Duty** | 0.003% of turnover | BUY only |
| **GST** | 18% on (Brokerage + Exchange Charges + SEBI Charges) | BUY and SELL |
| **Modelled Slippage** | 2.0 basis points (0.02%) on turnover | BUY and SELL (Market Orders) |

---

## 4. Portfolio Accounting & Cash Reconciliation

### 4.1 Pending Cash Reservation
When a BUY order is placed:
$$\text{Reserved Amount} = \text{round\_paisa}\left(\text{Price} \times \text{Quantity} + \text{Estimated Costs}\right)$$
- `Available Cash` decreases by `Reserved Amount`.
- If `Available Cash < Reserved Amount`, the order is rejected with `OrderRejectionReason.INSUFFICIENT_CASH`.
- Upon fill execution, the reserved cash is cleared, actual cash is debited, and any excess reservation is refunded back to available cash.
- Upon cancellation or expiry, the entire reserved amount returns to available cash.

### 4.2 Simultaneous Signal Ordering
When multiple candidate proposals arrive at identical timestamps, they are prioritized deterministically:
1. **Model Score / Rank**: Highest score first.
2. **Reward-to-Risk Ratio**: $\frac{P_{\text{target}} - P_{\text{entry}}}{P_{\text{entry}} - P_{\text{stop}}}$ (descending).
3. **Symbol Alphabetical**: Deterministic tie-breaker.
Candidates that exceed remaining cash are rejected with explicit reason `INSUFFICIENT_CASH`.

### 4.3 Exact Accounting Identity
At all times and across all trade lifecycles, the portfolio enforces the exact accounting reconciliation identity:
$$\text{Available Cash} + \text{Reserved Cash} + \sum_{\text{open}} (\text{Avg Entry Price} \times \text{Qty}) + \text{Total Costs Paid} - \text{Gross Realized P\&L} = \text{Initial Capital}$$
This identity reconciles strictly to the paisa (maximum allowed tolerance $\le ₹0.01$).
