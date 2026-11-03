# FinPilot AI — Layer 8 Report: Labeling and Temporal Validation Design

Status: **PASS**  
Completed: 2026-11-03  
Gate: `ACCEPTANCE_GATES.md` Layer 8 Gate  
Owning Package: `backend/src/finpilot/labeling/`  
Primary Security Controls: `SEC-06`, `SEC-19`

---

## 1. Executive Summary & Scope Boundary

Layer 8 establishes the **ground-truth trade-policy labeling engine** and **globally chronological temporal validation architecture** for FinPilot AI. 

In accordance with strict project rules and causal invariants:
- **No Generic Price-Rise Labeling**: Binary classification targets are defined strictly by whether an executable trade under the versioned trade policy (`TP-V1`) achieves a net-positive P&L ($> ₹0.00$) after accounting for 2.0 bps modelled slippage, integer share sizing on a ₹30,000 account, and complete Indian statutory and broker transaction costs (`NSE_EQUITY_INTRADAY_V1`).
- **Approach Selection**: FinPilot selected and documented **Approach A (Shared Sizing & Statutory Costs)** as the single authoritative MVP standard, ensuring downstream ML models train against true economic edge rather than gross phantom profits.
- **Globally Chronological Multi-Symbol Splits**: All instruments (`RELIANCE`, `TCS`, `INFY`) are partitioned along an identical global calendar timeline across 5 sequential partitions: `TRAIN` (50%), `DEV_MODEL_SELECTION` (15%), `CALIBRATION` (10%), `THRESHOLD_SELECTION` (10%), and `LOCKED_FINAL_TEST` (15%). No symbol may contribute training observations from a date later than another symbol's evaluation data.
- **Boundary Purging & Horizon-Justified Embargo**: Trade outcome intervals extending past partition boundaries are purged (72 samples purged), and a 1-session (75-bar) embargo buffer is enforced between partitions to eliminate serial autocorrelation, volatility clustering, and feature indicator lookback contamination.
- **Final-Test Lockbox**: The `LOCKED_FINAL_TEST` partition is cryptographically sealed (SHA-256 digest: `8c02ffda1a534713de5d3ae0d29d2bac5461768bbdff51723e3ef30702aafab1`). Routine model-tuning or selection algorithms are strictly prohibited from evaluating against the test partition, raising `FinalTestLockedError`.
- **Explicit Survivorship Limitation**: Documented incomplete historical delisting data in public vendor feeds as an explicit limitation rather than pretending it is solved.

> [!NOTE]
> **Strict Layer Boundary**: Layer 8 implements data labeling, temporal partitioning, purge/embargo mechanics, and lockbox isolation ONLY. It does NOT train machine learning models (Layer 10), does NOT run prediction ledgers (Layer 9), and does NOT place broker orders.

---

## 2. Approach Selection: Approach A vs Approach B

As mandated by Layer 8 requirements, the project evaluated two consistent methodologies for cost and sizing treatment during label generation:

```
[Candle t Close] --> [Executable Entry t+1 Open + 2 bps] --> [Simulate Stop/Target/Cutoff]
                                                                     |
                                                                     v
                                                            [Approach Selection]
                                                              /              \
                                                             /                \
                                    [Approach A (SELECTED)]      [Approach B (REJECTED)]
                                    Shared Integer Sizing        Gross 1-Unit Return
                                    Full NSE Statutory Costs     Costs Deferred Downstream
                                    y = 1 iff Net P&L > ₹0.00    y = 1 if Gross P&L > 0
```

### 2.1 Formal Comparison Matrix

| Evaluation Dimension | Approach A: Shared Sizing & Statutory Costs | Approach B: Gross Modeling with Downstream Costs |
|---|---|---|
| **Sizing Basis** | Integer shares calculated on ₹30,000 capital (1% risk = ₹300, 20%–50% max exposure cap) | Fixed 1 unit (or normalized continuous exposure) |
| **Transaction Friction** | Applied directly using `NSE_EQUITY_INTRADAY_V1` (brokerage, STT, exchange charges, GST, stamp duty) | Ignored during labeling; deferred to portfolio engine |
| **Micro-Edge False Positives** | **Eliminated**: Trades with small gross gains that lose money after ₹20–₹40 in fees receive label `0` | **High Risk**: Trades with 5-paisa gross gains receive label `1`, training ML to seek unprofitable churn |
| **Downstream Accounting Rule** | Downstream model scoring reflects net edge; **costs must NOT be subtracted twice** | Costs must be calculated and subtracted downstream |
| **Status in FinPilot** | **SELECTED MVP STANDARD** | Documented Alternative (Not used) |

### 2.3 Empirical Verification of Approach A

In unit test `test_net_positive_pnl_labeling_under_fees` (`test_labeling_trade_policy.py`), a trade on TCS exits after 6 bars with a small gross gain of +₹3.00. Under generic price-rise or Approach B labeling, this trade would be marked `1`. Under FinPilot's Approach A, statutory fees total ₹5.42, resulting in a Net P&L of **-₹2.42**. The labeler correctly assigns binary label **`0`**, preventing false model confidence.

---

## 3. Labeled Dataset & Split Manifest (`SPLIT-MANIFEST-V1`)

Using `scripts/generate_splits.py`, FinPilot processed full-month January 2026 5-minute market sessions across three liquid Indian cash equity instruments:

- **Instruments**: `RELIANCE` (ID: 101), `TCS` (ID: 102), `INFY` (ID: 103)
- **Input Dataset SHA-256 Hash**: `91cbec8c7f84289ebbcc11ddcf58b54175ff500ff9c3b4e24a37035b024384ac`
- **Total Completed Bars**: 4,950 bars (1,650 bars per instrument across 22 trading sessions)
- **Excluded Raw Rows**: 456 rows (152 per symbol due to 21-bar indicator warmup and $\ge 15:00$ IST session cutoff)
- **Total Labeled Candidate Decisions**: 4,494 samples
- **Total Active Partitioned Samples**: 4,122 samples
- **Total Purged (Boundary Overlap)**: 72 samples
- **Manifest File**: `data/splits/SPLIT-MANIFEST-V1.json`
- **Manifest ID**: `SPLIT-TP-V1-91cbec8c-f91544`

### 3.1 Partition Breakdown Table

| Partition | Share | Start Date (UTC) | End Date (UTC) | Samples | Win Rate (%) | Mean Net P&L (₹) | Overlap Purged | Embargo Bars | Partition Digest (SHA-256) |
|---|---|---|---|---|---|---|---|---|---|
| **`TRAIN`** | 50% | 2026-01-01 05:25 | 2026-01-15 09:25 | 2,217 | 37.80% | -₹22.67 | 18 | 75 | `a2f4b6a130f3c675e0d0be902aff4b4bee888eb504d166c2f148c27c206ed2dc` |
| **`DEV_MODEL_SELECTION`** | 15% | 2026-01-16 04:35 | 2026-01-20 09:25 | 591 | 34.01% | -₹27.64 | 18 | 75 | `d25daa65230325f8c7686765c187941504e7e956b1b5636699873b959f8df67b` |
| **`CALIBRATION`** | 10% | 2026-01-21 06:00 | 2026-01-22 09:25 | 333 | 38.14% | -₹23.57 | 18 | 75 | `9a303750887fb325ceb6294d7ea6d3cbe85d83536cf5e428c4dcc301f6949dd0` |
| **`THRESHOLD_SELECTION`** | 10% | 2026-01-23 06:55 | 2026-01-26 09:25 | 300 | 37.67% | -₹25.03 | 18 | 75 | `6bf5f0695c6cbb73d23e25dc6c181a4529a9ecb12eee3cee881c5fa453d8a7f3` |
| **`LOCKED_FINAL_TEST`** | 15% | 2026-01-27 07:50 | 2026-01-30 09:25 | 681 | 34.36% | -₹24.51 | 0 | 0 | `8c02ffda1a534713de5d3ae0d29d2bac5461768bbdff51723e3ef30702aafab1` |

---

## 4. Purge and Embargo Justification

### 4.1 Boundary Overlap Purging
In financial markets, a sample's information lifetime is not a single point in time, but the interval $[t_{\text{decision}}, t_{\text{exit}}]$. If a trade is opened inside Partition $k$, but exits on or after the starting timestamp of Partition $k+1$, training on that trade allows Partition $k+1$ market returns to bleed into Partition $k$'s training loss.
- **Rule**: $\forall x \in P_k$, if $x.t_{\text{exit}} \ge T_{k+1, \text{start}}$, sample $x$ is purged.
- Across the 4 non-test boundaries, exactly **72 samples** (18 samples per boundary across the 3 symbols) were purged.

### 4.2 Horizon-Justified Embargo
FinPilot rejects arbitrary gaps and defines the embargo strictly from the maximum information and outcome horizon:
1. **Intraday Trade Horizon**: Positions under `TP-V1` are strictly intraday and forced flat by 15:15 IST ($\le 72$ bars).
2. **Feature Indicator Horizon**: SMA-21 spans 105 minutes; RSI-14 spans 70 minutes.
3. **Autocorrelation & GARCH Persistence**: Serial return autocorrelation and volume clustering in NSE equities decay over 1 trading session.
4. **Buffer Size**: Exactly **75 completed 5-minute bars (1 full trading session / 1 day)**.

---

## 5. Final-Test Lockbox Anti-Snooping Controls

To enforce **ACCEPTANCE_GATES.md (G-8, Unseen data)**:
1. **Sealed Partition**: `FinalTestLockbox` encapsulates the test partition.
2. **Access Rejection**: Calling `lockbox.get_final_test_samples()` without the authorization token raises `FinalTestLockedError` (`code: PERMISSION_DENIED`).
3. **Token Verification**: Unsealing requires the exact SHA-256 token derived from the manifest hash (`UNSEAL_FINAL_TEST_8c02ffda1a53...`).
4. **Tamper Detection**: Altering or injecting samples causes `lockbox.verify_integrity()` to reject execution (`DomainValidationError`).

---

## 6. Historical Universe & Survivorship Limitations

FinPilot formally records the following scientific limitation in `SplitManifest.survivorship_bias_limitation` and `docs/validation-protocol.md`:
> *"NSE equity historical constituent and delisting records from public retail data providers are subject to survivorship bias limitations. While FinPilot enforces strict Point-In-Time universe filtering on known registered instruments, complete historical delisting coverage for prior years is unavailable in the current vendor tier. This limitation is explicitly disclosed and not assumed solved."*

---

## 7. Verification Evidence & Test Summary

The Layer 8 suite adds **20 comprehensive unit and integration tests** verifying all acceptance gates:

| Test Module | Tests | Description | Result |
|---|---|---|---|
| `test_labeling_trade_policy.py` | 5 | Next-bar executable delay, fee-adjusted Net P&L labeling, stop/gap-through-stop, same-bar collision ambiguity, and compulsory 15:15 IST cutoff. | **PASS** |
| `test_temporal_splits_ordering.py` | 4 | Global chronological timeline across all 5 partitions, multi-symbol cross-sectional alignment, deterministic hashing, and minimum timestamp enforcement. | **PASS** |
| `test_purging_and_embargo.py` | 3 | Boundary overlap purging, post-boundary embargo candidate exclusion, and metadata justification validation. | **PASS** |
| `test_pit_universe_and_features.py` | 3 | Unlisted instrument exclusion via PIT universe manager, feature warmup/cutoff exclusions, and future candle mutation anti-leakage. | **PASS** |
| `test_lockbox_final_test.py` | 5 | Final test lockbox anti-snooping rejection, token-authorized unsealing, routine partition accessibility, cryptographic tamper detection, and manifest disk roundtrip. | **PASS** |

### Execution Commands & Real Outputs

```powershell
# 1. Layer 8 Focused Test Suite
python -m pytest backend/tests/test_labeling_trade_policy.py backend/tests/test_temporal_splits_ordering.py backend/tests/test_purging_and_embargo.py backend/tests/test_pit_universe_and_features.py backend/tests/test_lockbox_final_test.py -v
# Output: 20 passed in 2.65s

# 2. Combined Layer 7 & Layer 8 Test Suite
python -m pytest backend/tests/test_labeling_*.py backend/tests/test_temporal_*.py backend/tests/test_purging_*.py backend/tests/test_pit_*.py backend/tests/test_lockbox_*.py backend/tests/test_baselines_*.py -v
# Output: 33 passed in 9.34s

# 3. Full Repository Regression Test Suite (Excluding local socket TestClient)
python -m pytest backend/tests -k "not test_app_security" -q
# Output: 235 passed, 5 deselected in 15.81s

# 4. Ruff Linting & Formatting Check
python -m ruff check backend
# Output: All checks passed!

# 5. Mypy Strict Type Analysis
python -m mypy backend/src
# Output: Success: no issues found in 57 source files
```

---

## 8. Security Checklist & Acceptance Gates Alignment

| Control ID | Summary | Layer 8 Implementation Evidence | Status |
|---|---|---|---|
| **SEC-06** | Server-side validation | `TradePolicyLabel`, `PartitionManifest`, and `SplitManifest` enforce immutable Pydantic V2 contracts, UTC datetime normalization, non-negative fee bounds, integer quantities, and valid state transitions. | **IMPLEMENTED** |
| **SEC-19** | Price & trade integrity | Label generation enforces causal next-bar entry, limit penetration, gap fills, collision conservatism, statutory fees (`NSE_EQUITY_INTRADAY_V1`), and lockbox anti-snooping isolation. | **IMPLEMENTED** |

---

## 9. Boundary Statement

I have completed all acceptance criteria for **FINPILOT LAYER 8: LABELING AND TEMPORAL VALIDATION DESIGN**.  
**I have not started the next layer.** Stopping for human approval.
