# FinPilot AI — Experiment Register

Status: **Layer 0 template**. One row per experiment campaign. This register is
the audit trail for the **research validity** verdict; no evaluation result is
banked unless registered here before running.

Related: `PROJECT_SPEC.md` §9, `DATA_AND_PERFORMANCE_POLICY.md` §7,
`docs/trade-policy-contract-v1.md`.

---

## 1. Registration rule

Every experiment is entered here **before** it runs, with predeclared hypothesis,
comparators, policy version, data window, metrics and uncertainty method. Running
an unregistered experiment that produces evidence is a policy violation.

## 2. Register

| ID | Date | Hypothesis | Policy ver. | Comparators | Data window / folds | Mode | Metrics | Uncertainty method | Code rev. | Cost ver. | Status | Result ref |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `EXP-0001` | 2026-11-03 | No-trade cash reference produces zero drift, zero costs, and zero drawdown across all sessions | `TP-V1` | `REF-NOTRADE-V1` (Cash Control) | 2026-01-01 to 2026-01-31 (22 sessions) | `SYNTHETIC_DEMO` | Net P&L, Drawdown, Daily Returns, Ledger Reconciled | Direct Cash Settlement | L7 (`HEAD`) | `NSE_EQUITY_INTRADAY_V1` | `DONE` | `data/experiments/EXP-0001.json` |
| `EXP-0002` | 2026-11-03 | Predeclared simple trend-VWAP-momentum strategy under TP-V1 is reproducible across all sessions with negative drift due to costs & chops | `TP-V1` | `STRAT-SIMPLE-V1` vs `REF-NOTRADE-V1` | 2026-01-01 to 2026-01-31 (22 sessions) | `SYNTHETIC_DEMO` | Net P&L, Expectancy, Profit Factor, Drawdown, Coverage, Utilization, Regimes | Direct Accounting & Ledger Identity | L7 (`HEAD`) | `NSE_EQUITY_INTRADAY_V1` | `DONE` | `data/experiments/EXP-0002.json` |
| `EXP-0003` | 2026-11-03 | Trade-policy labeling under Approach A with globally chronological splits, boundary purging, and 1-day embargo produces un-contaminated partitions | `TP-V1` | Approach A (Shared Sizing) | 2026-01-01 to 2026-01-31 (22 sessions) | `SYNTHETIC_DEMO` | Sample count, Win Rate, Mean P&L, Purged count, Embargo bars | Temporal Walk-Forward / Boundary Purging | L8 (`HEAD`) | `NSE_EQUITY_INTRADAY_V1` | `DONE` | `data/splits/SPLIT-MANIFEST-V1.json` |
| `EXP-0004` | 2026-11-03 | L2-regularized Logistic Regression with sigmoid calibration acts as an authorization filter mitigating baseline fee drag and loss churn | `TP-V1` | `MODEL-LOGREG-V1` vs `STRAT-SIMPLE-V1` & `REF-NOTRADE-V1` | `TRAIN` (Jan 1-15), `CAL` (Jan 21-22), `DEV` (Jan 16-20) | `SYNTHETIC_DEMO` | Accuracy, ROC-AUC, Brier score, Net P&L, Filter rate, Max DD, Ledger Reconciled | Split Calibration & Threshold Tuning | L9 (`HEAD`) | `NSE_EQUITY_INTRADAY_V1` | `DONE` | `artifacts/models/MODEL-LOGREG-V1/metadata.json` |
| `EXP-0005` | 2026-11-03 | Constrained-depth LightGBM (max_depth=3) with isotonic calibration captures non-linear indicator regimes without overfitting | `TP-V1` | `MODEL-LIGHTGBM-V1` vs `STRAT-SIMPLE-V1` & `REF-NOTRADE-V1` | `TRAIN` (Jan 1-15), `CAL` (Jan 21-22), `DEV` (Jan 16-20) | `SYNTHETIC_DEMO` | Accuracy, ROC-AUC, PR-AUC, Net P&L, Filter rate, Max DD, Ledger Reconciled | Split Calibration & Threshold Tuning | L9 (`HEAD`) | `NSE_EQUITY_INTRADAY_V1` | `DONE` | `artifacts/models/MODEL-LIGHTGBM-V1/metadata.json` |

Status values: `PLANNED` · `RUNNING` · `DONE` · `ABANDONED` · `BLOCKED`.
Result ref points to the stored run artefact (not pasted numbers here).

## 3. Per-experiment fields (definitions)

- **ID** — stable identifier, e.g. `EXP-0001`.
- **Date** — registration date (ISO).
- **Hypothesis** — falsifiable statement, written before running.
- **Policy ver.** — e.g. `TP-V1`.
- **Comparators** — includes no-trade reference and the predeclared simple
  strategy (frozen definition id).
- **Data window / folds** — exact unseen-data window and walk-forward scheme.
- **Mode** — `HISTORICAL_REPLAY` / `FORWARD_PAPER` / `SYNTHETIC_DEMO`.
- **Metrics** — the families from `DATA_AND_PERFORMANCE_POLICY.md` §5 used.
- **Uncertainty method** — pre-selected (OD-05).
- **Code rev.** / **Cost ver.** — reproducibility anchors.
- **Status** / **Result ref** — lifecycle and stored artefact.

## 4. Prohibitions

- No post-hoc changing of hypothesis, comparators or uncertainty method after
  seeing results (a new experiment ID is required).
- No pooling across policy versions, modes or cost versions without stating so.
- No reporting of synthetic results as market evidence.
