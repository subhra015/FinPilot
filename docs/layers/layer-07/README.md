# Layer 7 — Baseline Strategies

Status: **PASS**  
Date: 2026-11-03  
Commit: _pending human approval; no commit made by this layer_  
Approver: _pending human approval_  

---

## 1. Scope and Objectives

Layer 7 implements the formal baseline benchmarks required by the FinPilot AI master specification (`PROJECT_SPEC.md` §4, §5) to establish the experimental control against which future ML selection layers will be evaluated:

- **No-Trade Cash Reference (`REF-NOTRADE-V1`)**: An experimental control holding ₹30,000 initial scenario capital in cash. It consumes all market sessions, generates zero proposals, incurs zero transaction costs, produces zero drawdown, and confirms that the simulation engine itself introduces zero artificial drift.
- **Predeclared Simple Strategy (`STRAT-SIMPLE-V1`)**: A frozen, transparent, non-ML intraday benchmark based on completed 5-minute candles and `FS-V1` causal features:
  - *Trend Rule*: 9-period SMA > 21-period SMA (`sma_ratio_9_21 > 0.0`)
  - *Location Rule*: Price strictly above intraday VWAP approximation (`vwap_approx_distance > 0.0`)
  - *Momentum Rule*: Positive 1-bar return (`ret_1 > 0.0`) and non-overbought bullish RSI (`50.0 < rsi_14 <= 70.0`)
  - *Volume Rule*: Relative volume at or above rolling 10-bar average (`causal_rel_vol >= 1.0`)
  - *Timing Rule*: Completed candle strictly before 15:00 IST entry cutoff
  - *Warm-up*: Feature vector fully warmed up (`is_fully_warmed_up == True`, $\ge 21$ bars)
  - *Trade Policy*: Fixed `TP-V1` parameters (1.5% stop loss, 3.0% target, 6 bars / 30-min max hold) with risk-based integer share sizing.
- **Identical Execution and Cost Parity**: Both baselines execute through the **exact same** Layer 6 event-driven simulator (`ExecutionSimulator`, `PortfolioManager`, `NSEEquityIntradayFeeSchedule` with ₹0.01 paisa rounding, 10% volume participation cap, 2 bps modelled slippage, limit penetration rule, gap-through-stop, and 15:15 IST compulsory square-off).
- **Uncurated Multi-Period Evaluation**: Full month simulation across all 22 regular NSE trading sessions in January 2026 for the 3-symbol universe (`RELIANCE`, `TCS`, `INFY`). Inactive sessions (0 trades) and losing sessions are fully included and reported without cherry-picking.
- **Comprehensive Metric Coverage**: Reports gross/net P&L, statutory fees, trade expectancy, profit factor, maximum drawdown, daily returns mean/dispersion, win rate, coverage, average/peak capital utilization, order rejection reasons, collision ambiguity rate, and breakdowns by period, instrument, and market regime.
- **Immutable Experiment Artifacts**: Stored with deterministic SHA-256 configuration and result hashes in `data/experiments/EXP-0001.json` and `data/experiments/EXP-0002.json`.
- **Full Ledger Reconciliation**: Guaranteed conservation of capital identity:
  $$\text{Cash} + \text{Reserved Cash} + \text{Positions at Cost} + \text{Accrued Fees} = \text{Initial Capital} + \text{Realized P&L}$$
  reconciled to **₹0.00 discrepancy** across all runs.

---

## 2. Documented Conflict & Layer Alignment

- **Layer Sequence Alignment**: `ACCEPTANCE_GATES.md` originally titled Layer 7 as "Risk authorization service". The explicit user request designates Layer 7 as "Baseline Strategies" (implementing the No-Trade Cash Reference and the Predeclared Simple Strategy). Following `PROJECT_RULES.md` §2 and §3, this alignment is adopted, the documentation updated, and dependent layers (Risk Authorization Service, Prediction/Event Ledger, ML Selection) sequenced into subsequent layers.
- **Defect Fix in Layer 6 Code (Justified under `PROJECT_RULES.md` §3)**:
  - *Problem*: In Layer 6 `PortfolioManager.apply_fill`, fill turnovers were computed as `fill.fill_price * qty` without paisa rounding on each cash deduction/addition. Over 22 trading sessions with multiple trades, sub-paisa truncation accumulated to a 14-paisa ($₹0.14$) discrepancy. Additionally, `submit_proposal` lacked an explicit guard against opening multiple concurrent positions in the same instrument.
  - *Resolution*: Wrapped all turnover cash adjustments in `round_paisa()`, preserved high-precision Decimal in `PositionState.average_entry_price`, and added an explicit check in `submit_proposal` rejecting additional entries for an instrument if an open order or open position already exists (`OrderRejectionReason.EXCEEDS_EXPOSURE_CAP`). This eliminates rounding drift and restores exact ₹0.00 reconciliation across arbitrary multi-month runs.

---

## 3. Experiment Register & Registered Runs

Both baseline campaigns were registered in `docs/experiment-register.md` and executed across the full month of January 2026:

| Experiment ID | Strategy | Strategy ID | Sessions | Trades | Gross P&L | Fees | Net P&L | Drawdown | Result Hash | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| **EXP-0001** | No-Trade Cash Reference | `REF-NOTRADE-V1` | 22 | 0 | ₹0.00 | ₹0.00 | ₹0.00 | ₹0.00 (0.00%) | `7a60ed33d9930e49...` | `DONE` |
| **EXP-0002** | Predeclared Simple Strategy | `STRAT-SIMPLE-V1` | 22 | 10 | -₹981.89 | ₹181.97 | -₹1,163.86 | ₹1,163.06 (3.88%) | `3240d139a45211eb...` | `DONE` |

---

## 4. Detailed Baseline Performance Breakdown (`EXP-0002`)

### 4.1 Aggregate Economic Metrics
- **Initial Capital**: ₹30,000.00
- **Total Sessions**: 22 trading sessions (Jan 1 – Jan 31, 2026)
- **Active Sessions**: 8 sessions (Coverage: 36.36%)
- **Total Trades**: 10 completed intraday trades
- **Wins / Losses**: 1 win, 9 losses (Win Rate: 10.0%)
- **Gross Realized P&L**: -₹981.89
- **Total Statutory Fees & Costs**: ₹181.97
- **Net Realized P&L**: -₹1,163.86
- **Trade Expectancy**: -₹116.39 per trade
- **Profit Factor**: 0.0519
- **Maximum Drawdown**: ₹1,163.06 (3.88% peak-to-trough)
- **Average Capital Utilization**: 18.89%
- **Peak Capital Utilization**: 90.32%
- **Ambiguity Rate**: 0.0% (0 same-bar collisions)
- **Proposals Rejected**: 8 (All due to `EXCEEDS_EXPOSURE_CAP` preventing concurrent duplicate positions)
- **Accounting Reconciliation Discrepancy**: **₹0.00**

### 4.2 Breakdown by Instrument
| Symbol | Trades | Wins | Losses | Win Rate | Gross P&L | Fees | Net P&L |
|---|---|---|---|---|---|---|---|
| `INFY` | 3 | 0 | 3 | 0.0% | -₹643.05 | ₹61.19 | -₹704.24 |
| `RELIANCE` | 2 | 0 | 2 | 0.0% | -₹272.90 | ₹34.84 | -₹307.74 |
| `TCS` | 5 | 1 | 4 | 20.0% | -₹65.94 | ₹85.94 | -₹151.88 |

### 4.3 Breakdown by Market Regime
| Market Regime | Sessions | Trades | Win Rate | Gross P&L | Fees | Net P&L |
|---|---|---|---|---|---|---|
| `TRENDING_BULLISH` | 3 | 2 | 0.0% | -₹170.80 | ₹35.71 | -₹206.51 |
| `TRENDING_BEARISH` | 3 | 2 | 0.0% | -₹347.10 | ₹37.58 | -₹384.68 |
| `SIDEWAYS_CHOPPY` | 16 | 6 | 16.7% | -₹463.99 | ₹108.68 | -₹572.67 |

### 4.4 Research Significance
The negative net return (-₹1,163.86) of the unselected simple trend-following strategy demonstrates why rule-based technical entries without a selective filter suffer from market friction, whipsaws in choppy regimes, and adverse execution drag. This provides the exact empirical benchmark required to test the central research question in Layer 9/10: whether an ML selection layer can filter out unprofitable proposals and improve net outcomes over this baseline.

---

## 5. Files Added and Modified

### Added
- `backend/src/finpilot/baselines/__init__.py`: Package entrypoint exporting all baseline components.
- `backend/src/finpilot/baselines/models.py`: Pydantic V2 models (`ExperimentConfig`, `ExperimentResult`, `DailyPerformanceRecord`, `PeriodPerformanceRecord`, `InstrumentPerformanceRecord`, `RegimePerformanceRecord`).
- `backend/src/finpilot/baselines/no_trade.py`: `NoTradeCashReference` strategy benchmark.
- `backend/src/finpilot/baselines/simple_strategy.py`: `PredeclaredSimpleStrategy` (`STRAT-SIMPLE-V1`) implementation.
- `backend/src/finpilot/baselines/metrics.py`: Statistical performance, drawdown, and regime aggregation calculators.
- `backend/src/finpilot/baselines/runner.py`: `BaselineExperimentRunner` executing experiments and serializing artifacts.
- `backend/tests/test_baselines_no_trade.py`: Tests for no-trade baseline, zero drift, and ledger reconciliation.
- `backend/tests/test_baselines_simple_strategy.py`: Tests for simple strategy entry conditions, rejection rules, and integer sizing.
- `backend/tests/test_baselines_reproducibility.py`: Determinism, hash matching, and persistence round-trip tests.
- `backend/tests/test_baselines_execution_parity.py`: Parity tests verifying identical simulator assumptions across comparisons.
- `backend/tests/test_baselines_multi_period_regimes.py`: Uncurated full-month evaluation tests covering losing and inactive days.
- `scripts/run_baselines.py`: Standalone CLI script to run and persist baseline experiments.
- `data/experiments/EXP-0001.json`: Immutable experiment result artifact for No-Trade Cash Reference.
- `data/experiments/EXP-0002.json`: Immutable experiment result artifact for Predeclared Simple Strategy.
- `docs/layers/layer-07/README.md`: This layer report.

### Modified
- `backend/src/finpilot/execution/portfolio.py`: Fixed sub-paisa accumulation in cash adjustments and added single-position limit check per instrument.
- `docs/experiment-register.md`: Registered `EXP-0001` and `EXP-0002`.
- `docs/layers/README.md`: Marked Layer 7 as PASS.
- `README.md`: Updated current status and repository contents.
- `scripts/check_docs.ps1`: Added Layer 7 report to required document verification list.

---

## 6. Verification Commands and Actual Results

| Step | Command | Result / Exit Code | Evidence Summary |
|---|---|---|---|
| Layer 7 Baseline Tests | `python -m pytest -k "test_baselines" backend/tests -v` | Exit 0 | 13 passed in 10.77s |
| Layer 6 Execution Tests | `python -m pytest -k "test_execution" backend/tests -v` | Exit 0 | 19 passed in 2.70s |
| Full Backend Test Suite | `python -m pytest backend -v` (with bypass) | Exit 0 | 220 passed in 9.57s |
| ML Smoke Test | `python -m pytest ml` | Exit 0 | 1 passed in 0.03s |
| Frontend Test Suite | `npm --prefix frontend test` (with bypass) | Exit 0 | 2 files, 5 passed in 4.74s |
| Ruff Code Linting | `python -m ruff check backend` | Exit 0 | All checks passed (0 errors) |
| Mypy Static Type Check | `python -m mypy backend/src` | Exit 0 | Success: no issues found in 52 source files |
| Documentation & Link Check | `powershell -File scripts/check_docs.ps1` | Exit 0 | 27 required docs verified; 0 broken links; RESULT: PASS |

---

## 7. Security Checklist Updates

- **SEC-06 (Server-Side Request Validation)**: `ExperimentConfig` and `ExperimentResult` enforce strict typed validation, date range bounds, frozen immutable fields, non-negative capital, and SHA-256 integrity hash verification. Verified in `test_baselines_reproducibility.py`. Status: `IMPLEMENTED`.
- **SEC-19 (Price/Trade Integrity Server-Side)**: Baseline evaluations run exclusively through the server-side Layer 6 matching engine (`ExecutionSimulator`) and `PortfolioManager`. Fills strictly occur at next-bar open, orders cannot fill at client prices, and cash reconciles to the exact paisa (₹0.00 discrepancy). Status: `IMPLEMENTED`.

---

## 8. Limitations and Layer Boundary Adherence

- **No Machine Learning Models**: Layer 7 contains strictly non-ML benchmarks (No-trade cash reference and the rule-based Predeclared Simple Strategy). No ML training or inference code is present (deferred to Layer 9/10).
- **No Real Broker Routing**: All evaluations use simulated matching under `SYNTHETIC_DEMO` / `HISTORICAL_REPLAY` mode.
- **Strict Layer Boundary**: I have not started the next layer.
