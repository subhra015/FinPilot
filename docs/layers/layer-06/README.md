# Layer 6 — Execution and Portfolio Simulator

Status: **PASS**  
Date: 2026-11-03  
Commit: _pending human approval; no commit made by this layer_  
Approver: _pending human approval_  

---

## 1. Scope and Objective

Layer 6 implements the event-driven execution and portfolio simulator, incorporating the single versioned trade policy contract (`TP-V1`), realistic statutory fee calculations, causal fill mechanics, and exact portfolio ledger reconciliation for FinPilot AI:

- **Single Versioned Trade Policy (`TP-V1`)**: Implements strictly fixed parameters (1.5% stop loss, 3.0% take profit, 6-bar / 30-minute max hold duration, long-only cash equity). No multi-parameter grid search or parameter optimization.
- **Strict Causal Fill Invariant**: Clearly separates signal generation timestamp ($t_{\text{signal}}$, available only upon completion of a 5-minute candle) from executable fill timestamp ($t_{\text{fill}} \ge t_{\text{signal}} + 5\text{m}$, next bar open). Retroactive fills at the signal candle's close are strictly prohibited.
- **Explicit Order Types & Cancellation**: Implements `MARKET`, `LIMIT`, and `STOP_LOSS` order models with state transitions (`PENDING_SUBMISSION`, `SUBMITTED`, `PARTIALLY_FILLED`, `FILLED`, `CANCELLED`, `EXPIRED`, `REJECTED`).
- **Limit Order Penetration Requirement**: Touch without penetration ($\text{low} = \text{limit}$) does not fill; market price must penetrate the limit level ($\text{low} < \text{limit}$ for BUY) to guarantee execution without order-book depth.
- **Partial Fills & Participation Cap**: Orders are subject to a maximum participation cap of 10% of bar volume. Zero-volume bars produce zero fills. Residual quantity remains active across subsequent bars.
- **Gap-Through-Stop Execution**: If market prices open or jump below a stop-loss level, the order is filled at the actual open/gap price, never at the theoretical stop price.
- **Same-Bar Collision Ambiguity**: When an intraday candle breaches both stop-loss and profit-target price bands, the simulator flags `is_ambiguous_exit = True`. The primary accounting defaults to conservative stop-first execution, while sensitivity reporting calculates the optimistic target-first variance.
- **Session Cutoffs**: New entries are strictly rejected at or after 15:00 IST. Open intraday positions undergo mandatory square-off at 15:15 IST (last possible bar opens at 15:10 IST), guaranteeing a flat portfolio before market close (15:30 IST).
- **Feed Interruption & Unresolved Positions**: Market sessions terminating prematurely or lacking closing candles transition open positions into `PositionStatus.UNRESOLVED`, halting trade booking and preventing spurious P&L creation.
- **Statutory Fee Schedule (`NSE_EQUITY_INTRADAY_V1`)**: Exact breakdown of brokerage (0.03% or ₹20/order max), STT (0.025% on sell), exchange turnover fee (0.00297%), SEBI turnover charge (₹10 per crore), stamp duty (0.003% on buy), 18% GST on brokerage+turnover+SEBI, and modelled slippage (2 bps). Paisa rounding enforces exact `ROUND_HALF_UP` to ₹0.01.
- **Integer Shares & Long-Only Constraints**: Fractional shares are prohibited ($Q \ge 1$ integer). Shorting and leverage are disabled (leverage = 1.0).
- **Portfolio Cash Reservation & Accounting Identity**: Shared cash pool (₹30,000 initial scenario capital) with strict pre-fill cash reservation for pending BUY orders. Simultaneous signal prioritization orders candidates by score descending, reward-to-risk ratio descending, and symbol ascending. Full portfolio reconciliation validates that $\text{Cash} + \text{Reserved Cash} + \text{Positions at Cost} + \text{Accrued Fees} = \text{Initial Capital} + \text{Realized P&L}$ to the exact paisa (₹0.01).
- **Append-Only Ledger Events**: Every position transition, reservation, fill, fee deduction, and square-off emits an append-only, SHA-256 hash-chained ledger event.

---

## 2. Execution Architecture & Modules (`finpilot.execution`)

| Module | Responsibility | Key Classes / Functions |
|---|---|---|
| `fee_schedule.py` | Statutory fee calculation and paisa rounding | `BaseFeeSchedule`, `NSEEquityIntradayFeeSchedule`, `FeeBreakdown`, `round_paisa` |
| `models.py` | Pydantic V2 execution schemas & enums | `ExecutionOrder`, `FillEvent`, `PositionState`, `PortfolioState`, `SimulatedTradeResult`, `OrderType`, `OrderStatus` |
| `policy.py` | Trade policy contract validation & sizing | `TradePolicyEngine` (`TP-V1`), `calculate_position_size`, `validate_order_proposal` |
| `simulator.py` | Event-driven matching engine | `ExecutionSimulator`, next-bar open fill, penetration check, gap-stop, same-bar collision ambiguity |
| `portfolio.py` | Portfolio state, cash reservation & ledger | `PortfolioManager`, cash reservation, candidate prioritization, square-off, accounting reconciliation |

---

## 3. Hand-Verifiable Test Fixtures (11 Mandatory Scenarios)

All 11 required edge-case fixtures are implemented and verified in `backend/tests/test_execution_simulator_fixtures.py`:

| Fixture ID | Test Name | Purpose / Scenario | Expected & Verified Outcome |
|---|---|---|---|
| **F-01** | `test_fixture_1_normal_market_fill` | Clean next-bar execution after 5m signal | Signal at 09:20; filled at 09:20 bar open (1500.00) + 2 bps slippage = 1500.30; fees deducted; position opened |
| **F-02** | `test_fixture_2_stop_gap_down_execution` | Overnight / intraday gap down through stop | Stop at 1450.00; bar opens at 1420.00; fills at 1419.72 (gap open - slippage), NOT theoretical 1450.00 |
| **F-03** | `test_fixture_3_same_bar_stop_target_collision_and_sensitivity` | Bar breaches both stop (1450) and target (1550) | `is_ambiguous_exit = True`; conservative stop fill at 1450; sensitivity reports optimistic target fill at 1550 |
| **F-04** | `test_fixture_4_partial_fill_on_volume_participation_cap` | Order for 500 shares on bar with volume 2000 | 10% volume participation cap fills 200 shares; residual 300 shares remains active in `PARTIALLY_FILLED` status |
| **F-05** | `test_fixture_5_limit_touch_without_fill` | Limit BUY at 1490.00; bar low is exactly 1490.00 | Order does NOT fill (requires strict penetration $\text{low} < \text{limit}$); status remains `SUBMITTED` |
| **F-06** | `test_fixture_6_no_liquidity_zero_volume_bar` | Market order arrives during zero-volume bar | Zero liquidity yields 0 filled shares; order remains open without execution |
| **F-07** | `test_fixture_7_duplicate_event_rejection` | Duplicate candle/event passed to simulator | Simulator rejects duplicate timestamps without duplicating fills, orders, or fee deductions |
| **F-08** | `test_fixture_8_causal_timing_and_out_of_order_bar` | Out-of-order bar timestamp provided | Simulator raises `ValueError` / rejects backwards-in-time processing; causal monotonicity strictly enforced |
| **F-09** | `test_fixture_9_two_candidates_competing_for_cash` | ₹30,000 cash; two ₹20,000 proposals submitted simultaneously | Candidate 1 (higher score) wins allocation; ₹20,000 cash reserved; Candidate 2 rejected for insufficient cash |
| **F-10** | `test_fixture_10_market_close_with_unresolved_position` | Feed abruptly stops at 13:00 without close bars | Position marked `PositionStatus.UNRESOLVED`; no spurious square-off or artificial P&L created |
| **F-11** | `test_fixture_11_fee_rounding_and_full_accounting_reconciliation` | Complete buy/sell lifecycle with statutory fees | Exact paisa rounding on each statutory component; accounting identity reconciles to ₹0.00 discrepancy |

---

## 4. Files Added and Modified

### Added
- `backend/src/finpilot/execution/__init__.py`: Package entrypoint exporting all execution models and engines.
- `backend/src/finpilot/execution/fee_schedule.py`: Statutory NSE equity intraday fee schedule with exact paisa rounding.
- `backend/src/finpilot/execution/models.py`: Execution orders, fills, position states, portfolio state, and ledger structures.
- `backend/src/finpilot/execution/policy.py`: TP-V1 trade policy contract validation and integer position sizing.
- `backend/src/finpilot/execution/simulator.py`: Event-driven matching engine implementing all fill rules.
- `backend/src/finpilot/execution/portfolio.py`: Multi-instrument portfolio manager, cash reservation, candidate prioritization, square-off, and ledger reconciliation.
- `backend/tests/test_execution_fee_schedule.py`: Unit tests for fee calculations, statutory components, and paisa rounding.
- `backend/tests/test_execution_policy.py`: Unit tests for trade policy sizing, proposal validation, and 15:00 IST cutoff.
- `backend/tests/test_execution_simulator_fixtures.py`: 11 hand-verifiable fixture test cases covering edge cases.
- `docs/execution-policy.md`: Complete formal specification of the execution policy, matching rules, fee schedule, and accounting identity.
- `docs/layers/layer-06/README.md`: This layer report.

### Modified
- `SECURITY_CHECKLIST.md`: Updated SEC-06 and SEC-19 with Layer 6 implementation evidence.
- `docs/layers/README.md`: Marked Layer 6 as PASS.
- `README.md`: Updated current status and repository contents.
- `scripts/check_docs.ps1`: Added `docs/execution-policy.md` and `docs/layers/layer-06/README.md` to required documents.

---

## 5. Verification Commands and Actual Results

| Step | Command | Result / Exit Code | Evidence Summary |
|---|---|---|---|
| Layer 6 Execution Tests | `python -m pytest -k "test_execution" backend/tests -v` | Exit 0 | 19 passed in 3.20s |
| Full Backend Test Suite | `python -m pytest backend -v` | Exit 0 | 207 passed in 8.29s |
| ML Smoke Test | `python -m pytest ml` | Exit 0 | 1 passed in 0.04s |
| Frontend Test Suite | `npm --prefix frontend test` | Exit 0 | 2 files, 5 passed in 2.15s |
| Ruff Code Linting | `python -m ruff check backend` | Exit 0 | All checks passed (0 errors) |
| Mypy Static Type Check | `python -m mypy backend/src` | Exit 0 | Success: no issues found in 46 source files |
| Documentation & Link Check | `powershell -File scripts/check_docs.ps1` | Exit 0 | 26 required docs verified; 0 broken links; SEC-01..SEC-27 covered; RESULT: PASS |

---

## 6. Security Checklist Updates

- **SEC-06 (Server-Side Request Validation)**: `ExecutionOrder`, `FillEvent`, `PositionState`, and `PortfolioState` enforce typed Pydantic validation, non-negative finite prices, positive integer quantities ($Q \ge 1$), strict policy version validation (`TP-V1`), session cutoff verification ($\le 15:00$ IST for entries), and rejection of invalid order types or out-of-order execution events. Verified in `test_execution_*.py`. Status: `IMPLEMENTED`.
- **SEC-19 (Price/Trade Integrity Server-Side)**: `ExecutionSimulator`, `PortfolioManager`, and `NSEEquityIntradayFeeSchedule` enforce server-authoritative execution: client prices/fees are never trusted; fills occur strictly at next-bar open ($t_{\text{fill}} \ge t_{\text{signal}} + 5\text{m}$); limit orders require penetration; stops gap through market down jumps; same-bar collisions are flagged (`is_ambiguous_exit`) and conservatively treated; volume is capped at 10% bar participation; pending cash is reserved; and exact portfolio accounting reconciles to ₹0.01. Payment clauses N/A. L7-L8: Risk authority & Ledger integration. Status: `IMPLEMENTED`.

---

## 7. Limitations and Layer Boundary Adherence

- **No Live-Money Orders or Broker APIs**: Layer 6 is an event-driven paper and historical execution simulator. Real broker execution APIs are strictly out of scope.
- **No Risk Authorization Service (L7)**: Portfolio-level independent risk governance, circuit-breaker halts, and multi-strategy authorization will be implemented in Layer 7.
- **No Persistent Database Ledger (L8)**: The simulator implements in-memory SHA-256 hash-chained ledger events for accounting reconciliation. Persistent database storage and replay verification are deferred to Layer 8.
- **No ML Selection (L9)**: Layer 6 does not generate model predictions or optimize trade policies.
- **Strict Layer Boundary**: I have not started the next layer.
