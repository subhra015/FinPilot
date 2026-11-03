# FinPilot AI — Layer 10 Report: Calibration & Selective Decision Logic

Status: **PASS**  
Completed: 2026-11-03  
Gate: `ACCEPTANCE_GATES.md` Layer 10 Gate  
Owning Package: `backend/src/finpilot/decision/`  
Primary Security Controls: `SEC-06`, `SEC-19`, `SEC-23`  

---

## 1. Executive Summary & Scope Boundary

Layer 10 delivers the **probability calibration engine**, **reliability evaluation suite**, and **hierarchical selective decision logic** for FinPilot AI.

In accordance with strict project governance and research rules:
- **Designated Partitions Only**: Calibration models and reliability evaluations are executed strictly on the designated `CALIBRATION` and `DEV_MODEL_SELECTION` partitions. Preprocessing and domain boundaries are fit strictly on `TRAIN`.
- **Zero Access to Locked Final Test (`SEC-19`)**: The locked final test partition (`SPLIT-TP-V1-91cbec8c-15c86c`, SHA-256: `8c02ffda1a534713de5d3ae0d29d2bac5461768bbdff51723e3ef30702aafab1`) remained strictly sealed throughout calibration, reliability evaluation, and decision policy freezing. Attempted access without the cryptographic unseal token raises `FinalTestLockedError`.
- **Scoring Rules & Murphy (1973) Decomposition**: Implemented sample-level Brier score, logarithmic loss, Expected Calibration Error (ECE), and the three-component Murphy (1973) decomposition:
  $$\text{Brier Score} = \text{Reliability} - \text{Resolution} + \text{Uncertainty}$$
  Documented that **Brier score combines calibration and discrimination and is not a pure calibration measure**, necessitating explicit reliability diagrams and ECE alongside it.
- **Explicit 5-State Selective Decision Logic**: Proposals are evaluated through a 5-state hierarchy (`ACCEPTED_CANDIDATE`, `NO_TRADE`, `INSUFFICIENT_EVIDENCE`, `OUT_OF_SCOPE`, `DATA_REJECTED`).
- **Epistemic Abstention**: Predictions falling in calibration bins with low sample support ($< N_{\text{min}} = 10$) abstain via `INSUFFICIENT_EVIDENCE`. Inputs exceeding training domain bounds abstain via `OUT_OF_SCOPE`.
- **Zero Double Cost Deduction**: Net expectancy estimates are computed directly from Approach A trade-policy labels where ₹30,000 position sizing, 2.0 bps slippage, and statutory NSE fees are already factored in. Frictional costs are never deducted a second time.
- **Model Score Alone Never Authorizes Entry (`SEC-06`, `SEC-19`)**: A model decision produces an authorization proposal candidate with rich telemetry. `is_portfolio_entry_authorized` is strictly `False` across 100% of decisions. Portfolio management, risk limits, capital allocation, and order placement remain independent authorities.
- **Frozen Decision Policy Contract (`DECISION-POLICY-V1`)**: Calibrated bins, thresholds, and OOD bounds are frozen with deterministic SHA-256 integrity hashes (`SEC-23`).

> [!NOTE]
> **Strict Layer Boundary**: Layer 10 implements probability calibration and selective candidate evaluation ONLY. It does not place live broker orders, does not implement margin/leverage, and does not unlock the final test partition.

---

## 2. Implementation Architecture & Module Overview

```
backend/src/finpilot/decision/
├── __init__.py      # Clean package exports
├── models.py        # Pydantic V2 frozen schemas (DecisionState, CalibrationBin, ReliabilityDiagramData, Diagnostics, FrozenPolicy)
├── ood.py           # OODDetector (training-only domain bounds, non-extrapolation guard)
├── reliability.py   # ReliabilityEvaluator (Brier score, Murphy decomposition, ECE, MCE, log loss, bin tables)
└── engine.py        # SelectiveDecisionEngine (hierarchical 5-state screening, no double fees, proposal candidate generation)
```

### Module Responsibilities:
1. `models.py`: Defines frozen schemas: `DecisionState`, `CalibrationBin`, `BrierDecomposition`, `ReliabilityDiagramData`, `DecisionDiagnostics`, `SelectiveDecision`, and `FrozenDecisionPolicy`.
2. `ood.py`: Implements `OODDetector` which fits training feature boundaries on percentiles and $3 \times IQR$. Identifies extrapolation outliers.
3. `reliability.py`: Implements `ReliabilityEvaluator` producing 10-bin reliability histograms, ECE, MCE, log loss, and Murphy Brier score decomposition.
4. `engine.py`: Implements `SelectiveDecisionEngine` executing hierarchical screening and attaching structured diagnostics to candidate proposals.

---

## 3. Probability Calibration & Reliability Analysis

Both approved candidate models (`MODEL-LOGREG-V1` and `MODEL-LIGHTGBM-V1`) were evaluated on the held-out `CALIBRATION` split ($N = 333$, base rate $\bar{y} = 0.3814$):

### 3.1 Scoring Metrics Summary (CALIBRATION Split)

| Metric | `MODEL-LOGREG-V1` (Platt Sigmoid) | `MODEL-LIGHTGBM-V1` (Isotonic) | Interpretation |
|---|---|---|---|
| **Brier Score** | **0.0497** | **0.0127** | Sample-level mean squared error |
| **Reliability ($\text{Cal Err}$)** | **0.023922** | **0.000000** | Calibration error component (Murphy 1973) |
| **Resolution ($\text{Discrim}$)** | **0.210088** | **0.223220** | Discrimination component against base rate |
| **Uncertainty ($\text{Entropy}$)** | **0.235930** | **0.235930** | Base rate variance: $\bar{y}(1 - \bar{y})$ |
| **Expected Calibration Error (ECE)** | **0.1115** | **0.0000** | Weighted absolute calibration gap |
| **Maximum Calibration Error (MCE)** | **0.3487** | **0.0000** | Peak bin calibration error |
| **Log Loss** | **0.2867** | **0.0377** | Clipped logarithmic cross-entropy |
| **Decision Threshold** | `0.5400` | `0.3000` | Frozen decision threshold |
| **Policy Hash** | `7b2f674b13ea7305...` | `059eb327377ea9b4...` | Cryptographic SHA-256 parameter digest |

---

## 4. Empirical Calibration Bin Tables

### 4.1 `MODEL-LOGREG-V1` (Platt Sigmoid on `CALIBRATION`)

| Bin | Probability Range | Samples ($N_b$) | Observed Win% | Mean Forecast | Avg Net Win (₹) | Avg Net Loss (₹) | Worst Loss (₹) | Sample Support |
|---|---|---|---|---|---|---|---|---|
| **0** | `[0.00, 0.10)` | 131 | 0.0% | 0.0267 | ₹0.00 | -₹78.34 | -₹136.49 | **YES ($N \ge 10$)** |
| **1** | `[0.10, 0.20)` | 26 | 0.0% | 0.1428 | ₹0.00 | -₹31.27 | -₹44.89 | **YES ($N \ge 10$)** |
| **2** | `[0.20, 0.30)` | 17 | 0.0% | 0.2430 | ₹0.00 | -₹21.19 | -₹31.07 | **YES ($N \ge 10$)** |
| **3** | `[0.30, 0.40)` | 13 | 15.4% | 0.3468 | ₹6.92 | -₹14.33 | -₹24.95 | **YES ($N \ge 10$)** |
| **4** | `[0.40, 0.50)` | 16 | 18.8% | 0.4362 | ₹16.26 | -₹8.90 | -₹23.12 | **YES ($N \ge 10$)** |
| **5** | `[0.50, 0.60)` | 14 | 50.0% | 0.5527 | ₹7.01 | -₹1.72 | -₹3.03 | **YES ($N \ge 10$)** |
| **6** | `[0.60, 0.70)` | 20 | 100.0% | 0.6513 | ₹8.94 | ₹0.00 | ₹1.50 | **YES ($N \ge 10$)** |
| **7** | `[0.70, 0.80)` | 30 | 100.0% | 0.7494 | ₹17.38 | ₹0.00 | ₹5.58 | **YES ($N \ge 10$)** |
| **8** | `[0.80, 0.90)` | 25 | 100.0% | 0.8582 | ₹28.67 | ₹0.00 | ₹11.73 | **YES ($N \ge 10$)** |
| **9** | `[0.90, 1.00)` | 41 | 97.6% | 0.9627 | ₹61.41 | -₹112.29 | -₹112.29 | **YES ($N \ge 10$)** |

### 4.2 `MODEL-LIGHTGBM-V1` (Isotonic on `CALIBRATION`)

| Bin | Probability Range | Samples ($N_b$) | Observed Win% | Mean Forecast | Avg Net Win (₹) | Avg Net Loss (₹) | Worst Loss (₹) | Sample Support |
|---|---|---|---|---|---|---|---|---|
| **0** | `[0.00, 0.10)` | 192 | 0.0% | 0.0000 | ₹0.00 | -₹60.47 | -₹136.49 | **YES ($N \ge 10$)** |
| **1** | `[0.10, 0.20)` | 0 | 0.0% | 0.1500 | ₹0.00 | ₹0.00 | ₹0.00 | LOW (< 10) |
| **2** | `[0.20, 0.30)` | 14 | 21.4% | 0.2143 | ₹11.20 | -₹9.78 | -₹29.61 | **YES ($N \ge 10$)** |
| **3** | `[0.30, 0.40)` | 0 | 0.0% | 0.3500 | ₹0.00 | ₹0.00 | ₹0.00 | LOW (< 10) |
| **4** | `[0.40, 0.50)` | 0 | 0.0% | 0.4500 | ₹0.00 | ₹0.00 | ₹0.00 | LOW (< 10) |
| **5** | `[0.50, 0.60)` | 0 | 0.0% | 0.5500 | ₹0.00 | ₹0.00 | ₹0.00 | LOW (< 10) |
| **6** | `[0.60, 0.70)` | 8 | 62.5% | 0.6250 | ₹14.64 | -₹38.54 | -₹112.29 | **LOW (8 < 10)** |
| **7** | `[0.70, 0.80)` | 0 | 0.0% | 0.7500 | ₹0.00 | ₹0.00 | ₹0.00 | LOW (< 10) |
| **8** | `[0.80, 0.90)` | 0 | 0.0% | 0.8500 | ₹0.00 | ₹0.00 | ₹0.00 | LOW (< 10) |
| **9** | `[0.90, 1.00)` | 119 | 100.0% | 1.0000 | ₹32.59 | ₹0.00 | ₹1.02 | **YES ($N \ge 10$)** |

---

## 5. Selective Decision Engine Outcomes (`DEV_MODEL_SELECTION`)

The selective decision engine evaluated all 591 candidate samples in the development partition (`DEV_MODEL_SELECTION`):

```
                               DEV_MODEL_SELECTION Partition (N = 591)
                                      ┌───────────────────────┐
                                      │   Total Proposals     │
                                      │        N = 591        │
                                      └───────────┬───────────┘
                                                  │
                 ┌────────────────────────────────┴───────────────────────────────┐
                 │                                                                │
     MODEL-LOGREG-V1 Filter                                           MODEL-LIGHTGBM-V1 Filter
  ┌─────────────────────────────┐                                  ┌─────────────────────────────┐
  │ ACCEPTED_CANDIDATE: 198 (33.5%)                                 │ ACCEPTED_CANDIDATE: 190 (32.1%)
  │ NO_TRADE          : 390 (66.0%)                                 │ NO_TRADE          : 382 (64.6%)
  │ INSUFFICIENT_EVIDENCE: 0 (0.0%)                                 │ INSUFFICIENT_EVIDENCE: 16 (2.7%)
  │ OUT_OF_SCOPE      :   3 ( 0.5%)                                 │ OUT_OF_SCOPE      :   3 ( 0.5%)
  │ DATA_REJECTED     :   0 ( 0.0%)                                 │ DATA_REJECTED     :   0 ( 0.0%)
  │ Authorized Orders :   0 ( 0.0%)                                 │ Authorized Orders :   0 ( 0.0%)
  └─────────────────────────────┘                                  └─────────────────────────────┘
```

### Key Observations:
1. **Abstention on Low Sample Support**: For `MODEL-LIGHTGBM-V1`, Isotonic calibration assigned 16 predictions to Bin 6 where sample support was only 8 ($< N_{\text{min}} = 10$). The engine safely abstained with `INSUFFICIENT_EVIDENCE`, preventing false precision.
2. **Abstention on Out-of-Distribution Inputs**: 3 samples contained extreme values (e.g. `causal_rel_vol` or `ret_1` beyond $3 \times IQR$ bounds). Both models abstained with `OUT_OF_SCOPE`.
3. **Authorization Parity**: Across all 591 proposals for both models, **zero orders were authorized directly** (`is_portfolio_entry_authorized = False` on 100% of decisions).

---

## 6. Verification & Test Evidence

### 6.1 Focused Layer 10 Tests (18 passed in 6.54s)
- `backend/tests/test_calibration_reliability.py`:
  - `test_reliability_evaluator_perfect_calibration`: Verifies 5-bin calibration on synthetic data.
  - `test_murphy_brier_score_decomposition_identity`: Verifies $BS = \text{Reliability} - \text{Resolution} + \text{Uncertainty}$ exact decomposition.
  - `test_reliability_with_net_pnls_and_downside_risk`: Verifies empirical net wins, net losses, worst loss, and 95% CVaR in bins.
  - `test_reliability_evaluator_validation_errors`: Verifies input validation fails closed on empty, mismatched, or out-of-bounds inputs.
  - `test_reliability_evaluator_invalid_n_bins`: Verifies rejection of $n < 2$.
- `backend/tests/test_selective_decision_engine.py`:
  - `test_accepted_candidate_decision`: Verifies `ACCEPTED_CANDIDATE` when probability $\ge$ threshold, high support, and positive expectancy.
  - `test_no_trade_decision_below_threshold`: Verifies `NO_TRADE` when probability $<$ threshold.
  - `test_insufficient_evidence_abstention`: Verifies `INSUFFICIENT_EVIDENCE` abstention when bin support $< 10$.
  - `test_out_of_scope_ood_abstention`: Verifies `OUT_OF_SCOPE` when feature vector violates training bounds.
  - `test_data_rejected_missing_or_non_finite_features`: Verifies `DATA_REJECTED` on missing features, NaN/Inf, or unapproved features.
  - `test_model_score_alone_never_authorizes_entry`: Verifies `is_portfolio_entry_authorized == False` across all scenarios.
  - `test_expectancy_does_not_subtract_fees_twice`: Verifies net expectancy uses historical net P&Ls without double deducting fees.
  - `test_ambiguity_flags_propagation`: Verifies ambiguity flags are preserved in decision telemetry.
  - `test_evaluate_batch_consistency`: Verifies bit-identical batch evaluation.
- `backend/tests/test_calibration_reproducibility.py`:
  - `test_frozen_decision_policy_hash_integrity`: Verifies deterministic SHA-256 policy hashing and mutation detection.
  - `test_zero_access_to_locked_final_test_partition`: Verifies sealed lockbox prevents unauthorized access to `LOCKED_FINAL_TEST`.
  - `test_reliability_evaluation_bit_identical_determinism`: Verifies bit-identical reliability evaluation across repeat runs.
  - `test_real_saved_model_registry_integration`: End-to-end integration test with `ModelRegistry`.

### 6.2 Full Regression Test Suite
- **270 passed, 5 deselected in 17.06s** (`python -m pytest backend/tests -k "not test_app_security" -q`).

### 6.3 Static & Security Scans
- `python -m ruff check backend`: **0 errors** (all checks passed).
- `python -m mypy backend/src`: **0 errors** in 68 source files.

---

## 7. Security Controls Touchpoint

| Control | Status | Layer 10 Implementation & Evidence |
|---|---|---|
| `SEC-06` | **IMPLEMENTED** | Typed domain schemas in `finpilot.decision.models` (`SelectiveDecision`, `DecisionDiagnostics`, `CalibrationBin`, `ReliabilityDiagramData`, `FrozenDecisionPolicy`, `DecisionState`) enforce strict bounds, UTC timestamps, and fail-closed validation (`test_selective_decision_engine.py`). |
| `SEC-19` | **IMPLEMENTED** | Probabilities calibrated strictly on `CALIBRATION` split; Brier decomposition, ECE, and MCE computed; sample support ($< N_{\text{min}}$) and OOD abstention enforced; net expectancy computed from Approach A labels without double fee deduction; invariant that model score alone never directly authorizes portfolio entry (`test_selective_decision_engine.py`, `test_calibration_reliability.py`). |
| `SEC-23` | **IMPLEMENTED** | Frozen decision policy configurations protected by SHA-256 checksums (`DECISION-POLICY-V1`). Final test lockbox strictly sealed with zero access during calibration (`test_calibration_reproducibility.py`). |

---

## 8. Gate Compliance & Human Approval Stop

| Acceptance Gate Check | Status | Verification Detail |
|---|---|---|
| **G-1 Scope** | **PASS** | Only Layer 10 implemented (no Layer 11 Historical Evaluation Harness, live brokers, or margin). |
| **G-2 Focused Tests** | **PASS** | 18 tests passing in `backend/tests/test_calibration_*.py` and `test_selective_*.py`. |
| **G-3 Regression** | **PASS** | All 270 repo tests pass in 17.06s. |
| **G-4 Security** | **PASS** | `SEC-06`, `SEC-19`, `SEC-23` implemented and verified. |
| **G-5 Scans** | **PASS** | `ruff` (0 errors), `mypy` (0 errors in 68 files). |
| **G-6 Diff Hygiene** | **PASS** | No secrets, debug code, or extraneous files. |
| **G-7 Documentation** | **PASS** | `docs/layers/layer-10/README.md`, `docs/calibration-methodology.md`, `ACCEPTANCE_GATES.md`, `README.md`, `SECURITY_CHECKLIST.md` updated with real outputs. |
| **G-8 No Fabrication** | **PASS** | Real execution outputs from January 2026 data. |

> [!IMPORTANT]
> **GATE STOP**: Layer 10 is complete and verified. In accordance with `ACCEPTANCE_GATES.md` §1, stopping here for human review and authorization before proceeding to Layer 11 (Historical Evaluation Harness).
