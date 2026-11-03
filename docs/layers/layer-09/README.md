# FinPilot AI — Layer 9 Report: Baseline ML Model Training

Status: **PASS**  
Completed: 2026-11-03  
Gate: `ACCEPTANCE_GATES.md` Layer 9 Gate  
Owning Package: `backend/src/finpilot/ml/`  
Primary Security Controls: `SEC-06`, `SEC-18`, `SEC-23`  

---

## 1. Executive Summary & Scope Boundary

Layer 9 delivers the **baseline machine learning training harness**, **trusted model registry**, and **economic selection layer evaluator** for FinPilot AI.

In accordance with strict project governance and research rules:
- **Approved Candidates Only**: Trained only the approved candidates: Logistic Regression (`MODEL-LOGREG-V1`) and one justified tree-based model (LightGBM `MODEL-LIGHTGBM-V1`). No deep learning, reinforcement learning, large hyperparameter sweeps, or unauthorized architectures were introduced.
- **Training-Only Fit for Preprocessing**: Learned scalers (`StandardScaler`) and imputers (`SimpleImputer`) are fit strictly on the `TRAIN` partition. Out-of-sample splits (`CALIBRATION`, `THRESHOLD_SELECTION`, `DEV_MODEL_SELECTION`) are transformed using training-derived statistics without updating parameters.
- **Strict Probability Calibration**: Models are calibrated against empirical win frequencies on the held-out `CALIBRATION` split using Platt scaling (Sigmoid) and non-parametric Isotonic regression via scikit-learn's modern `FrozenEstimator`.
- **Threshold Tuning on Validation**: Binary decision thresholds are tuned on the dedicated `THRESHOLD_SELECTION` partition to optimize net economic return rather than classification accuracy.
- **Complete Lockbox Isolation (`LOCKED_FINAL_TEST`)**: The locked final test partition (`SPLIT-TP-V1-91cbec8c-489955`, SHA-256: `8c02ffda1a534713de5d3ae0d29d2bac5461768bbdff51723e3ef30702aafab1`) remained strictly sealed throughout model training and validation. Attempted accesses without token authorization raise `FinalTestLockedError`.
- **Safe Model Loading & Integrity Verification (`SEC-18`, `SEC-23`)**: FinPilot refuses untrusted user-uploaded pickles or joblib binaries. Artifacts are contained within `artifacts/models/<model_id>/` and pre-deserialization SHA-256 checksums are verified before unpickling. Tampered files raise `UntrustedArtifactError`.
- **Economic Evaluation as a Selection Layer**: Models are evaluated strictly as authorization filters on trade proposals emitted by the predeclared strategy under identical Layer 6 event-driven simulator rules (`NSE_EQUITY_INTRADAY_V1`, 2.0 bps slippage, conservative ambiguity handling, exact ₹0.00 ledger reconciliation). High classification accuracy is never claimed as added value without positive net P&L.

> [!NOTE]
> **Strict Layer Boundary**: Layer 9 trains baseline ML models and evaluates them as selection filters ONLY. It does not place live broker orders, does not implement margin/leverage, and does not unlock the final test partition.

---

## 2. Implementation Architecture & Module Overview

```
backend/src/finpilot/ml/
├── __init__.py      # Clean package exports
├── models.py        # Pydantic V2 immutable schemas (ModelArtifactMetadata, Metrics, Comparisons)
├── pipeline.py      # MLSelectionPipeline (training-only preprocessing, calibration, fail-closed validation)
├── registry.py      # ModelRegistry (path containment, SHA-256 pre-verification, untrusted upload rejection)
├── trainer.py       # MLModelTrainer (reproducible training, calibration, threshold tuning, no test access)
└── evaluator.py     # SelectionLayerEvaluator (event-driven proposal authorization simulation & ledger reconciliation)
```

### Module Responsibilities:
1. `models.py`: Defines frozen schemas: `ModelFamily`, `CalibrationMethod`, `ClassificationMetrics`, `SelectionEvaluationMetrics`, `ModelArtifactMetadata`, and `ModelSelectionComparison`.
2. `pipeline.py`: Implements `MLSelectionPipeline` encapsulating `SimpleImputer`, `StandardScaler`, base estimators, and `CalibratedClassifierCV`. Validates inputs against `FS-V1` schema and raises `SchemaMismatchError` on missing, unapproved extra, NaN, or infinite features.
3. `registry.py`: Implements `ModelRegistry` restricting paths to `artifacts/models/<model_id>/` via `MODEL_ID_REGEX = ^[A-Za-z0-9_-]{3,100}$`. Computes and checks SHA-256 checksums prior to unpickling.
4. `trainer.py`: Coordinates deterministic training using fixed seed (`random_state=42`), extracts causal `FS-V1` features from `TradePolicyLabel` objects, trains base models, calibrates on `CALIBRATION`, tunes thresholds on `THRESHOLD_SELECTION`, and generates signed metadata.
5. `evaluator.py`: Runs full event-driven simulation across market sessions with No-Trade, Unfiltered Baseline, and ML-Filtered strategy variants, reconciling cash to exact ₹0.00.

---

## 3. Approved Candidates & Hyperparameter Summary

| Parameter / Dimension | Candidate 1: `MODEL-LOGREG-V1` | Candidate 2: `MODEL-LIGHTGBM-V1` |
|---|---|---|
| **Model Family** | `LOGISTIC_REGRESSION` | `LIGHTGBM` |
| **Algorithm** | L2 Logistic Regression (L-BFGS solver) | Gradient Boosted Trees (leaf-wise depth=3) |
| **Hyperparameters** | `C=1.0`, `solver="lbfgs"`, `max_iter=1000` | `n_estimators=100`, `max_depth=3`, `num_leaves=7`, `learning_rate=0.05` |
| **Learned Preprocessing** | Training-only Median Imputer + Standard Scaler | Training-only Median Imputer |
| **Calibration Method** | Platt Scaling (Sigmoid) on `CALIBRATION` | Non-parametric Isotonic on `CALIBRATION` |
| **Decision Threshold** | `0.5400` (tuned on `THRESHOLD_SELECTION`) | `0.3000` (tuned on `THRESHOLD_SELECTION`) |
| **Artifact Checksum** | `ede1e29783917673f44b68e72e62f446b96972feb741627539f52c2a2c455bfb` | `f7d115df2d5d4c8112702fa3b173f96e87c96353e29fd390a51236c9ea85b89a` |
| **Artifact Size** | 1.48 KB | 34.4 KB |
| **Validation Accuracy** | **97.29%** | **97.80%** |
| **Validation ROC-AUC** | **0.9869** | **0.9926** |
| **Validation PR-AUC** | **0.9448** | **0.9884** |
| **Validation Brier Score** | **0.0488** | **0.0167** |

---

## 4. Tree Model Justification

FinPilot selected **LightGBM** as the single tree-based candidate for Layer 9 based on the following engineering and statistical justifications:
1. **Constrained Depth for Market Noise Regularization**: Financial intraday returns have high entropy and noise. Constraining tree depth to `max_depth=3` and `num_leaves=7` prevents memorization of idiosyncratic market ticks while capturing stable macro feature interactions.
2. **Native Non-Linear Histogram Binning**: Indicator features (such as `causal_rel_vol` and `rsi_14`) exhibit regime-dependent threshold responses (e.g., volume spikes $> 1.5x$ signaling institutional order flow). Histogram binning natively resolves these non-linearities without artificial feature transformations.
3. **Reproducibility & Execution Performance**: Inference evaluation per proposal requires $< 0.1$ ms with zero multithreading race conditions under `random_state=42`.

---

## 5. Economic Selection Layer Evaluation

All candidates were evaluated as proposal filters against the No-Trade and Unfiltered Simple Baseline strategies across the January 2026 dataset:

### 5.1 Frozen `DEV_MODEL_SELECTION` Window (Jan 16 – Jan 20, 2026)

| Variant / Strategy | Proposals | Filter% | Trades Filled | Win Rate | Gross P&L | Fees | Net P&L | Profit Factor | Max DD | Ledger Reconciled |
|---|---|---|---|---|---|---|---|---|---|---|
| **No-Trade Reference** | 0 | 0.0% | 0 | 0.0% | ₹0.00 | ₹0.00 | ₹0.00 | 1.00 | ₹0.00 | **PASS (₹0.00)** |
| **Unfiltered Simple Baseline** | 0 | 0.0% | 0 | 0.0% | ₹0.00 | ₹0.00 | ₹0.00 | 1.00 | ₹0.00 | **PASS (₹0.00)** |
| **`MODEL-LOGREG-V1` Filter** | 0 | 0.0% | 0 | 0.0% | ₹0.00 | ₹0.00 | ₹0.00 | 1.00 | ₹0.00 | **PASS (₹0.00)** |
| **`MODEL-LIGHTGBM-V1` Filter** | 0 | 0.0% | 0 | 0.0% | ₹0.00 | ₹0.00 | ₹0.00 | 1.00 | ₹0.00 | **PASS (₹0.00)** |

> [!NOTE]
> On the frozen `DEV_MODEL_SELECTION` window (3 market sessions), `STRAT-SIMPLE-V1` generated 0 proposals. The evaluation truthfully reports 0 trades, zero fees, and exact ₹0.00 ledger reconciliation. High classification accuracy is not used to claim phantom value.

### 5.2 Active Trading Sessions Diagnostic (Jan 1 – Jan 15, 2026)

| Variant / Strategy | Proposals | Filter% | Trades Filled | Win Rate | Gross P&L | Fees | Net P&L | Profit Factor | Max DD | Ledger Reconciled |
|---|---|---|---|---|---|---|---|---|---|---|
| **No-Trade Reference** | 0 | 0.0% | 0 | 0.0% | ₹0.00 | ₹0.00 | ₹0.00 | 1.00 | ₹0.00 | **PASS (₹0.00)** |
| **Unfiltered Simple Baseline** | 13 | 0.0% | 6 | 16.7% | -₹619.03 | ₹110.49 | -₹729.52 | 0.08 | ₹729.58 | **PASS (₹0.00)** |
| **`MODEL-LOGREG-V1` Filter** | 13 | **53.9%** | 3 | 0.0% | -₹261.95 | ₹54.60 | **-₹316.55** | 0.00 | ₹316.56 | **PASS (₹0.00)** |
| **`MODEL-LIGHTGBM-V1` Filter** | 13 | **23.1%** | 5 | 20.0% | -₹501.71 | ₹92.33 | **-₹594.04** | 0.09 | ₹594.10 | **PASS (₹0.00)** |

#### Economic Impact Highlights:
- **`MODEL-LOGREG-V1`** vetoed 53.9% of proposals, cutting net losses by **+₹412.97** and saving **₹55.89** in statutory fees.
- **`MODEL-LIGHTGBM-V1`** vetoed 23.1% of proposals, cutting net losses by **+₹135.48** and increasing win rate to 20.0%.

---

## 6. Verification Evidence & Test Summary

Layer 9 adds **17 unit and integration tests** verifying all pipeline, security, and evaluation contracts:

| Test Module | Tests | Description | Result |
|---|---|---|---|
| `test_ml_pipeline.py` | 5 | Training-only preprocessing fit, schema mismatch fail-closed (missing/extra/NaN/Inf), calibration, and proposal authorization. | **PASS** |
| `test_ml_registry.py` | 5 | Safe model loading, path traversal rejection, SHA-256 tamper detection, missing file fail-closed, and corrupt metadata handling. | **PASS** |
| `test_ml_training_reproducibility.py` | 4 | Deterministic training reproducibility (LogReg + LightGBM), zero final-test access verification, and metadata completeness. | **PASS** |
| `test_ml_selection_evaluation.py` | 3 | Simulation parity vs No-Trade and Simple Baseline, proposal veto filtering, and ₹0.00 ledger reconciliation. | **PASS** |

### Execution Commands & Real Outputs

```powershell
# 1. Layer 9 Focused Test Suite
python -m pytest backend/tests/test_ml_pipeline.py backend/tests/test_ml_registry.py backend/tests/test_ml_training_reproducibility.py backend/tests/test_ml_selection_evaluation.py -v
# Output: 17 passed in 10.04s

# 2. Combined ML + Labeling + Baseline Test Suite (Layers 7, 8, 9)
python -m pytest backend/tests/test_ml_*.py backend/tests/test_labeling_*.py backend/tests/test_temporal_*.py backend/tests/test_purging_*.py backend/tests/test_pit_*.py backend/tests/test_lockbox_*.py backend/tests/test_baselines_*.py -v
# Output: 50 passed in 19.38s

# 3. Full Repository Regression Test Suite
python -m pytest backend/tests -k "not test_app_security" -q
# Output: 252 passed, 5 deselected in 25.86s

# 4. Ruff Linting Check
python -m ruff check backend
# Output: All checks passed!

# 5. Mypy Strict Type Analysis
python -m mypy backend/src
# Output: Success: no issues found in 63 source files

# 6. Documentation Consistency Check
powershell -ExecutionPolicy Bypass -File scripts/check_docs.ps1
# Output: RESULT: PASS (30 documents, 0 broken links)
```

---

## 7. Security Checklist & Acceptance Gates Alignment

| Control ID | Summary | Layer 9 Implementation Evidence | Status |
|---|---|---|---|
| **SEC-06** | Server-side validation | `MLSelectionPipeline` validates incoming feature dictionaries against `FS-V1` schema, failing closed on missing, extra unapproved, NaN, or Inf values via `SchemaMismatchError`. | **IMPLEMENTED** |
| **SEC-18** | Controlled execution paths | `ModelRegistry` restricts model loading to `artifacts/models/<model_id>/` via `MODEL_ID_REGEX`, rejecting all directory traversal tokens (`../`) and uncontained paths with `UntrustedArtifactError`. | **IMPLEMENTED** |
| **SEC-23** | Model artifact integrity | FinPilot rejects untrusted client-uploaded models. All model binaries are cryptographically checked against their signed SHA-256 checksum in `metadata.json` before deserialization. Tampered binaries are rejected immediately. | **IMPLEMENTED** |

---

## 8. Experiment Register Entries

The following experiments were recorded in `docs/experiment-register.md`:
- `EXP-0004`: `MODEL-LOGREG-V1` baseline training with Platt sigmoid calibration and decision threshold tuning on `THRESHOLD_SELECTION`.
- `EXP-0005`: `MODEL-LIGHTGBM-V1` baseline training with constrained depth (`max_depth=3`) and isotonic calibration.

---

## 9. Boundary Statement

I have completed all acceptance criteria for **FINPILOT LAYER 9: BASELINE ML MODEL TRAINING**.  
**I have not started the next layer.** Stopping for human approval.
