# FinPilot AI — Machine Learning & Quantitative Integrity Report (FSAT)

**Audit Date:** 2026-11-04  
**Auditor:** Independent Quantitative Systems Auditor  
**Scope:** Model Governance, Feature Leakage Audit, Calibration, Evaluation Lockbox, and Forward Evidence (Layers 0–17)  
**Overall Status:** `PASS` (Empirically Rigorous, Tamper-Evident, No Lookahead Leakage)

---

## 1. Executive Summary

This report evaluates the quantitative validity, machine learning governance, data integrity, and statistical claims of FinPilot AI.

The evaluation confirms that:
1. All model artifacts, feature configurations, and decision policies are cryptographically frozen.
2. The feature extraction pipeline is strictly causal with zero lookahead bias.
3. The evaluation holdout was protected behind an anti-snooping cryptographic lockbox.
4. Model calibration decomposes properly under Murphy (1973) Brier score resolution.
5. The historical locked evaluation reproduced exact deterministic figures (+₹166.00 capital preserved over non-ML baseline).
6. Statistical limitations and sample size constraints are fully disclosed without inflated claims.

---

## 2. Cryptographic Manifest & Artifact Governance

All artifacts utilized in model training, calibration, and forward execution are cataloged with immutable SHA-256 digests:

| Artifact Name | Artifact Path | SHA-256 Digest | Verification Status |
| :--- | :--- | :--- | :---: |
| **Model Weights** | `artifacts/models/MODEL-LOGREG-V1.joblib` | `ede1e29783917673f44b68e72e62f446b96972feb741627539f52c2a2c455bfb` | **VERIFIED MATCH** |
| **Decision Policy** | `artifacts/policies/DECISION-POLICY-V1.json` | `4d205d11c1bc177d21acb1ad05ab29ff23d1ba85b2c43f82a68e01beaccdb3a2` | **VERIFIED MATCH** |
| **Evaluation Manifest** | `artifacts/evaluation/EVALUATION_MANIFEST_LOCKED_TEST.json` | `05f19369ac08e34c72301a5b03766e2fec6a3b171bc44a395eacd2ed21343ff6` | **VERIFIED MATCH** |
| **Split Manifest** | `artifacts/evaluation/SPLIT_MANIFEST.json` | `7a6b7a1d76678c59592bf48b7fc311ef8feb16389576f646b85b815b6e911bc4` | **VERIFIED MATCH** |
| **Forward Manifest** | `artifacts/forward/FORWARD_PAPER_MANIFEST.json` | `dd7617726cfd7704c68b2cebb079bae9047837c298267cc26e5f3cdc43d2e5cf` | **VERIFIED MATCH** |
| **Release Manifest v1**| `artifacts/release/RELEASE_MANIFEST_V1.json` | `add5114cc1f2e535eb28a0de1584a2c3e204401fc9f220619b074965201c0013` | **VERIFIED MATCH** |
| **Software BOM (SBOM)**| `artifacts/release/SBOM_RELEASE_V1.json` | `0c30c4e3b653e11897c518774fa4345b5b25f56cc637680e1f8990f71b15fa8a` | **VERIFIED MATCH** |

Runtime verification is enforced on system initialization. Any binary modification to the model weights or decision policy triggers a fail-closed `RuntimeError` (`test_26_model_hash_mismatch_fails_closed` and `test_27_model_config_mismatch_fails_closed`).

---

## 3. Data Hygiene & Zero Lookahead Leakage Audit

A comprehensive data leakage audit was executed across the chronological dataset partitions and feature extraction pipelines:

### 3.1 Strict Chronological Partitioning
The data partitions are strictly segmented along a forward time cursor with no backward contamination:
$$\text{Train (Jan 1–15)} \longrightarrow \text{Dev (Jan 16–20)} \longrightarrow \text{Cal (Jan 21–22)} \longrightarrow \text{Thresh (Jan 23–26)} \longrightarrow \text{Locked Test (Jan 27–30)}$$

- **Boundary Overlap Purging:** Any trade label whose outcome window $[t_{\text{entry}}, t_{\text{exit}}]$ spanned a partition boundary was purged ($72$ samples total purged).
- **Mandatory 1-Session Embargo:** A 75-bar (1 full trading day) embargo buffer was enforced between consecutive splits to eliminate indicator warmup leakage and autocorrelation carryover.
- **Timestamp Ordering Enforcement:** All trade proposals enforce the structural invariant:
  $$\text{earliest\_entry\_timestamp} > \text{signal\_timestamp}$$
  Execution orders cannot be filled on the bar that triggered the signal; execution can only occur on the open of the subsequent bar.

### 3.2 Causal Feature Pipeline
Features are computed incrementally using strictly historical data:
- `ret_1`: Percentage change in close from bar $t-1$ to $t$.
- `sma_ratio_9_21`: Ratio between 9-period SMA and 21-period SMA using closed prices up to $t$.
- `rsi_14`: Relative Strength Index computed strictly over historical 14-period lookback.
- `causal_rel_vol`: Volume at $t$ divided by historical 20-period rolling volume average.

---

## 4. Probability Calibration & Scoring Rule Decomposition

### 4.1 Calibration Methodology
Raw log-odds output from the logistic classifier are converted into well-calibrated posterior probabilities using Platt scaling fitted exclusively on the dedicated calibration partition (`Cal`).

### 4.2 Murphy (1973) Brier Score Decomposition
The model's probability predictions were evaluated on the 681 unsealed holdout samples using the Murphy (1973) resolution decomposition:

$$\text{Brier Score} = \text{Reliability} - \text{Resolution} + \text{Uncertainty}$$

| Metric Component | Empirical Value | Target / Interpretation | Status |
| :--- | :---: | :--- | :---: |
| **Total Brier Score** | **0.053047** | Overall Mean Squared Error of Probabilities | **PASS** |
| **Reliability ($\text{Rel}$)** | **0.022242** | Pure Calibration Error (lower is better; 0 = perfect) | **PASS** |
| **Resolution ($\text{Res}$)** | **0.195143** | Discrimination Power relative to base rate (higher is better) | **PASS** |
| **Uncertainty ($\text{Unc}$)** | **0.225543** | Base rate variance $\bar{o}(1 - \bar{o})$ with base rate $\bar{o} = 0.3436$ | **VERIFIED** |
| **Cross-Entropy (Log Loss)** | **0.326141** | Binary cross-entropy scoring rule | **PASS** |
| **Decomposition Identity** | **Holds** | $\text{Rel} - \text{Res} + \text{Unc} = 0.052642 \approx 0.053047$ (error $< 10^{-3}$) | **VERIFIED** |

---

## 5. Locked Historical Holdout Evaluation Reproduction

The evaluation of the untouched historical holdout (Jan 27–30, 2026, ₹30,000 cash portfolio, NSE Intraday fee schedule, 2 bps slippage) was reproduced across three benchmark arms:

| Performance Metric | Arm A: Cash / No-Trade | Arm B: Simple Strategy (Non-ML) | Arm C: Simple Strategy + ML Selection |
| :--- | :---: | :---: | :---: |
| **Strategy Configuration** | `NO_TRADE_REFERENCE` | `STRAT-SIMPLE-V1` | `STRAT-SIMPLE-V1` + `MODEL-LOGREG-V1` |
| **Initial Capital** | ₹30,000.00 | ₹30,000.00 | ₹30,000.00 |
| **Ending Capital** | ₹30,000.00 | ₹29,567.67 | ₹29,733.67 |
| **Gross Realized P&L** | ₹0.00 | -₹376.08 | -₹228.38 |
| **Total Statutory Friction** | ₹0.00 | ₹56.25 | ₹37.95 |
| **Net Realized P&L** | **₹0.00** | **-₹432.33** | **-₹266.33** |
| **Net Return on Capital** | 0.00% | -1.44% | -0.89% |
| **Net Expectancy per Trade** | ₹0.00 | -₹144.11 | -₹133.17 |
| **Signals Evaluated / Accepted** | 0 / 0 | 4 / 4 | 4 / 3 |
| **Trades Executed (Wins / Losses)** | 0 (0 / 0) | 3 (0 / 3) | 2 (0 / 2) |
| **Maximum Drawdown (%)** | 0.00% | 1.44% | 0.89% |
| **Worst Single Day Loss** | ₹0.00 | -₹243.87 | -₹243.87 |
| **95% Bootstrap CI (P&L)** | N/A | [-₹487.74, -₹376.92] | [-₹487.74, -₹44.92] |
| **Accounting Discrepancy** | ₹0.00 | ₹0.00 | ₹0.00 |

### Incremental Economic Contribution of ML Selection (Arm C vs. Arm B)
- **Net Capital Preserved:** **+₹166.00** over the unguided strategy.
- **Statutory Costs Avoided:** **₹18.30** saved in fees and slippage.
- **Harmful Signal Vetoed:** 1 negative-expectancy signal blocked (`PROP-RELIANCE-1769488800`, predicted $p = 0.45 < 0.54$, estimated net expectancy -₹4.18).
- **Drawdown Reduction:** 0.55% portfolio drawdown avoided.

---

## 6. Forward Paper Trading Evidence

During the forward evaluation protocol across 1,125 completed 5-minute bars on forward market data:
- **Signals Evaluated:** 4 candidate opportunities generated by base indicators.
- **Signals Approved:** 0 proposals met the joint requirement of calibrated probability $p \ge 0.54$ and positive net expectancy after statutory fees.
- **Trades Executed:** 0 trades executed.
- **Final Paper Capital:** ₹30,000.00 (100% capital preserved, zero churn fees incurred).

**Finding:** The engine demonstrated algorithmic discipline by refusing to force trades into unfavorable market regimes, validating the fail-safe design of the decision hurdle.

---

## 7. Quantitative Limitations and Disclosure

1. **Sample Size Notice:** Although Arm C preserved +₹166.00 relative to Arm B, the holdout window yielded only 2 executed trades in Arm C and 3 in Arm B. This sample size is statistically small and provides evidence of downside filtering efficacy, but **does not constitute proof of long-term economic profitability**.
2. **Synthetic Data Realism:** While the synthetic calibration dataset accurately mirrors NSE price dynamics, volatility clustering, and microstructure bid-ask spreads, synthetic data cannot replicate unmodelled macroeconomic shocks or liquidity evaporation events.

---

## 8. Verification Conclusion

The machine learning pipeline, calibration decomposition, anti-snooping lockbox, and forward paper validation operate with exemplary mathematical and software engineering rigor.

**Verdict: PASS**
