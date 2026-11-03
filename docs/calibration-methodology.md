# FinPilot AI — Probability Calibration and Selective Decision Methodology (Layer 10)

Status: **Ratified & Implemented**  
Owning Package: `backend/src/finpilot/decision/`  
Related Documents:
- [`PROJECT_SPEC.md`](../PROJECT_SPEC.md) (§4, §5, §7, §9)
- [`DATA_AND_PERFORMANCE_POLICY.md`](../DATA_AND_PERFORMANCE_POLICY.md) (§2, §7, §8)
- [`trade-policy-contract-v1.md`](trade-policy-contract-v1.md) (TP-V1 Execution & Sizing Contract)
- [`model-registry.md`](model-registry.md) (Layer 9 Model Persistence & Integrity)
- [`docs/layers/layer-10/README.md`](layers/layer-10/README.md) (Layer 10 Execution Report)
- [`SECURITY_CHECKLIST.md`](../SECURITY_CHECKLIST.md) (`SEC-06`, `SEC-19`, `SEC-23`)

---

## 1. Overview and Core Philosophy

In algorithmic trade selection, a raw machine learning classification score represents an uncalibrated ranking index rather than a true frequentist probability. Deploying raw scores directly into risk decisions causes severe operational failure:
1. **Overconfidence in Extreme Regions**: Logistic loss and tree gradient boosting push predictions toward 0.0 or 1.0, exaggerating apparent certainty.
2. **False Precision in Sparse Bins**: Rare feature combinations produce extreme model scores where empirical historical sample support is virtually zero.
3. **Double Counting of Transaction Frictional Costs**: Incorporating statutory fees both during label creation and again during expected value filtering penalizes viable trades and skews expectancy estimates.

FinPilot Layer 10 implements **rigorous probability calibration** and a **hierarchical selective decision engine** that separates:
- **Calibrated Empirical Probability** ($P(\text{Trade is Net Profitable})$);
- **Expected Net Value in INR** (derived directly from historical Approach A labels);
- **Downside & Execution Risk** (worst historical loss and 95% Expected Shortfall / CVaR);
- **Epistemic Abstention** (refusing to trade when empirical sample support is insufficient or inputs are out-of-distribution).

> [!IMPORTANT]
> **Fundamental Safety Invariant**: A model score alone must **NEVER** authorize a portfolio entry. The selective decision engine produces an **authorization proposal candidate** with structured diagnostics (`is_portfolio_entry_authorized = False`). Downstream portfolio management, risk limits, capital reservation, and exchange execution remain independent authorities.

---

## 2. Proper Scoring Rules and Murphy (1973) Brier Decomposition

### 2.1 Sample-Level Brier Score
For $N$ binary outcomes $y_i \in \{0, 1\}$ and predicted probabilities $p_i \in [0, 1]$:
$$BS = \frac{1}{N} \sum_{i=1}^N (p_i - y_i)^2$$

### 2.2 Murphy (1973) Three-Component Decomposition
To understand calibration quality, FinPilot implements the canonical **Murphy (1973) decomposition** of the Brier score into three orthogonal components:
$$BS_{\text{bin}} = \text{Reliability} - \text{Resolution} + \text{Uncertainty}$$

Where samples are partitioned into $B$ calibration bins, with each bin $b$ having $N_b$ samples, empirical win rate $\hat{p}_b = \frac{k_b}{N_b}$, mean forecast probability $\bar{p}_b = \frac{1}{N_b} \sum_{i \in b} p_i$, and overall base rate $\bar{y} = \frac{1}{N} \sum_{i=1}^N y_i$:

1. **Reliability (Calibration Error)**:
   $$\text{Reliability} = \sum_{b=1}^B \frac{N_b}{N} (\bar{p}_b - \hat{p}_b)^2$$
   Measures how close the predicted probability is to the observed empirical win frequency. A perfectly calibrated model achieves $\text{Reliability} = 0.0$.
2. **Resolution (Discrimination Power)**:
   $$\text{Resolution} = \sum_{b=1}^B \frac{N_b}{N} (\hat{p}_b - \bar{y})^2$$
   Measures the model's ability to divide opportunities into subsets whose empirical outcome rates differ substantially from the base rate $\bar{y}$. Higher resolution is better (it reduces total Brier score).
3. **Uncertainty (Inherent Entropy)**:
   $$\text{Uncertainty} = \bar{y} (1 - \bar{y})$$
   The inherent variance of the binary trading process, entirely independent of model forecasts.

### 2.3 Scientific Disclosure: Why Brier Score is NOT a Pure Calibration Metric
> [!NOTE]
> Because Brier score combines calibration error ($\text{Reliability}$), discrimination power ($\text{Resolution}$), and process variance ($\text{Uncertainty}$), **Brier score is NOT a pure calibration measure**. A model with strong discrimination (high resolution) can produce an artificially low (good) Brier score despite substantial miscalibration.
> Therefore, FinPilot evaluates calibration using **Reliability Diagrams**, **Expected Calibration Error (ECE)**, and **Maximum Calibration Error (MCE)** alongside the Brier score decomposition.

### 2.4 Expected Calibration Error (ECE) & Maximum Calibration Error (MCE)
$$ECE = \sum_{b=1}^B \frac{N_b}{N} |\bar{p}_b - \hat{p}_b|$$
$$MCE = \max_{b, N_b > 0} |\bar{p}_b - \hat{p}_b|$$

---

## 3. Five-State Selective Decision Engine Hierarchy

The decision engine evaluates candidate proposals through an explicit, sequential five-state screening hierarchy:

```
[Candidate Proposal & Point-in-Time Features]
                      │
   1. Data Quality & Server-Side Contract Check
      - All FS-V1 features present?
      - No unapproved or extra features?
      - Finite values only (no NaN / Inf)?
      - Valid long-only prices (stop < entry < target)?
                      ├── FAIL ──> [DATA_REJECTED]
                      │
   2. Out-of-Distribution (OOD) Domain Check
      - Feature values within training support domain?
                      ├── FAIL ──> [OUT_OF_SCOPE]
                      │
   3. Probability Calibration & Bin Lookup
      - Predict calibrated probability p = P(Net > 0)
      - Find matching calibration bin b
      - Sample support check: is N_bin >= N_min (10)?
                      ├── FAIL ──> [INSUFFICIENT_EVIDENCE]
                      │
   4. Net Expectancy & Frozen Threshold Check
      - Does p >= decision_threshold?
      - Is E[Net PnL] > min_expectancy (₹0.00)?
                      ├── NO ───> [NO_TRADE]
                      │
                      └── YES ──> [ACCEPTED_CANDIDATE]
                                  (is_portfolio_entry_authorized = False)
```

### Definitions of the 5 Decision States:
1. `ACCEPTED_CANDIDATE`:
   - Feature vector passes strict schema validation.
   - Input lies safely within the training distribution support domain (not OOD).
   - Matching calibration bin has robust empirical sample support ($N_b \ge N_{\text{min}}$).
   - Calibrated win probability $\ge$ frozen threshold.
   - Estimated net expectancy in INR is positive ($> ₹0.00$).
2. `NO_TRADE`:
   - Valid data and in-distribution, but calibrated probability is below the frozen threshold OR estimated net expectancy is non-positive ($\le ₹0.00$).
3. `INSUFFICIENT_EVIDENCE`:
   - Valid data and in-distribution, but the prediction falls into a calibration bin with fewer than $N_{\text{min}}$ historical samples ($N_b < 10$). Abstention prevents unwarranted precision or spurious high confidence.
4. `OUT_OF_SCOPE`:
   - Feature values fall outside the training domain bounds ($P_{0.5} - 3 \times IQR$ to $P_{99.5} + 3 \times IQR$). The model explicitly refuses to extrapolate.
5. `DATA_REJECTED`:
   - Missing required features, unapproved feature names, non-finite values (NaN / Inf), stale timestamps, or invalid proposal price relationships.

---

## 4. Economic Expectancy & Zero Double Cost Deduction

A critical architectural pitfall in quantitative trading systems is subtracting execution costs twice.

### 4.1 Approach A Contract Sizing and Net P&L
Under Layer 8 Approach A ([`TradePolicyLabel`](layers/layer-08/README.md)):
- Every labeled sample models an integer share allocation on ₹30,000 capital.
- Entry fill occurs causally at the next 5-minute candle open ($t_{\text{entry}} \ge t_{\text{decision}} + 5\text{m}$).
- Modelled slippage (2.0 bps) and full statutory NSE transaction costs (`NSE_EQUITY_INTRADAY_V1`: brokerage, STT, exchange turnover fees, SEBI charges, stamp duty, GST) are **already deducted from `net_pnl`**.
- Binary label is strictly defined as $y = 1 \iff \text{net\_pnl} > ₹0.00$.

### 4.2 Mathematical Expectancy Formulation
$$\mathbb{E}[\text{Net P&L}] = \hat{p}_b \cdot \overline{\text{Gain}}_{\text{win}, b} + (1 - \hat{p}_b) \cdot \overline{\text{Loss}}_{\text{loss}, b}$$
Where:
- $\hat{p}_b$: Empirical win rate in calibration bin $b$.
- $\overline{\text{Gain}}_{\text{win}, b}$: Mean net P&L of winning trades in bin $b$ (in INR).
- $\overline{\text{Loss}}_{\text{loss}, b}$: Mean net P&L of losing trades in bin $b$ (in INR, negative).

> [!CAUTION]
> **Zero Double Deduction**: Because $\overline{\text{Gain}}_{\text{win}, b}$ and $\overline{\text{Loss}}_{\text{loss}, b}$ are computed directly from `net_pnl`, statutory fees are **already fully accounted for**. The decision engine **never subtracts fees a second time**.

### 4.3 Downside Risk Metrics
Alongside net expectancy, each decision exposes:
- **Maximum Loss in Bin**: Worst observed historical net loss in the matched calibration bin.
- **95% Conditional Value at Risk (CVaR)**: The mean of the worst 5% of net P&L outcomes in the matched calibration bin.

---

## 5. Frozen Decision Policy Contract (`DECISION-POLICY-V1`)

To prevent post-hoc overfitting and data snooping:
1. Decision thresholds are tuned strictly on `THRESHOLD_SELECTION` or `DEV_MODEL_SELECTION` partitions.
2. Calibration bins and OOD domain boundaries are fit strictly on `CALIBRATION` and `TRAIN` partitions.
3. The resulting configuration is sealed into an immutable [`FrozenDecisionPolicy`](layers/layer-10/README.md) schema.
4. A deterministic SHA-256 integrity hash is computed over all policy parameters. Any alteration in thresholds, bin bounds, sample counts, or OOD limits mutates the hash and invalidates the policy.
5. The `LOCKED_FINAL_TEST` partition remains cryptographically sealed and is never accessed during calibration or threshold freezing.
