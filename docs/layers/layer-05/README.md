# Layer 5 — Causal Features and Point-in-Time Universe

Status: **PASS**  
Date: 2026-11-02  
Commit: _pending human approval; no commit made by this layer_  
Approver: _pending human approval_  

---

## 1. Scope and Objective

Layer 5 implements the strictly causal feature engineering pipeline, session-aware 5-minute bar aggregation, learned preprocessing with training-only fit, and survivorship-bias-free point-in-time universe management for FinPilot AI:

- **Approved Feature Set (`FS-V1`)**: 12 causal features computed exclusively from completed 5-minute OHLCV bars: returns/momentum (`ret_1`, `ret_3`, `ret_6`), moving-average trend (`sma_9`, `sma_21`, `sma_ratio_9_21`), RSI (`rsi_14`), ATR/volatility (`atr_14`, `natr_14`), price location (`vwap_approx_distance`), volume ratios (`causal_rel_vol`), and liquidity proxies (`turnover_proxy_5m`).
- **Session-Aware Aggregation**: Sub-session source bars (e.g. 1-minute intervals) are aggregated into 5-minute candles strictly aligned to regular NSE trading sessions (09:15 to 15:30 IST; last bar opens at 15:25 IST). Out-of-session and weekend bars are rejected.
- **Strict Causal & Session Isolation**: Intraday metrics (cumulative session VWAP approximation, session bar index 0..74) strictly reset at session open (09:15 IST) and never bleed across sessions. Causal relative volume strictly uses prior completed bars ($t-1 \dots t-10$) and never uses eventual full-day volume.
- **Warm-up & Insufficient History Handling**: Incomplete history produces `None` for affected features, marked with `is_fully_warmed_up = False`. Full warm-up is reached at 21 completed bars. Future interpolation or backfilling is strictly prohibited.
- **Deterministic Preprocessing**: `DeterministicFeatureScaler` implements z-score standardization with training-only `fit` and frozen `transform`. Scaling parameters are serialized with SHA-256 checksums to ensure reproducibility.
- **Point-in-Time Universe Management**: `PointInTimeUniverseManager` resolves point-in-time ticker symbols from historical symbol changes, eliminates survivorship bias (preserving historical delistings prior to their delisting date), excludes future IPOs, and enforces causal liquidity checks using completed prior sessions.
- **Mandatory Proxy Disclosures**: OHLCV VWAP approximation, rolling volume ratio, and turnover proxy are explicitly labelled as approximations and never misrepresented as tick-level executions or order book queue positions.

---

## 2. Feature Set Specification (FS-V1)

| Feature | Category | Warm-up | Cross-Session | Units | Formula / Description |
|---|---|---|---|---|---|
| `ret_1` | MOMENTUM | 1 bar (5m) | No | ratio | $(\text{Close}_t - \text{Close}_{t-1}) / \text{Close}_{t-1}$ |
| `ret_3` | MOMENTUM | 3 bars (15m) | No | ratio | $(\text{Close}_t - \text{Close}_{t-3}) / \text{Close}_{t-3}$ |
| `ret_6` | MOMENTUM | 6 bars (30m) | No | ratio | $(\text{Close}_t - \text{Close}_{t-6}) / \text{Close}_{t-6}$ |
| `sma_9` | TREND | 9 bars (45m) | Yes | INR | 9-period Simple Moving Average of close price |
| `sma_21` | TREND | 21 bars (105m)| Yes | INR | 21-period Simple Moving Average of close price |
| `sma_ratio_9_21` | TREND | 21 bars (105m)| Yes | ratio | $(\text{SMA}_9(t) / \text{SMA}_{21}(t)) - 1.0$ |
| `rsi_14` | MOMENTUM | 14 bars (70m) | Yes | index | 14-period Wilder's Relative Strength Index $[0, 100]$ |
| `atr_14` | VOLATILITY | 14 bars (70m) | Yes | INR | 14-period Average True Range |
| `natr_14` | VOLATILITY | 14 bars (70m) | Yes | ratio | Normalized ATR: $\text{ATR}_{14}(t) / \text{Close}_t$ |
| `vwap_approx_distance` | PRICE_LOCATION | 1 bar (5m) | No (Resets at 09:15) | ratio | Normalized distance: $(\text{Close}_t - \text{VWAP}_{\text{approx}}) / \text{VWAP}_{\text{approx}}$ |
| `causal_rel_vol` | VOLUME | 10 bars (50m) | Yes | ratio | Current volume / rolling mean of prior 10 completed bars |
| `turnover_proxy_5m` | LIQUIDITY | 0 bars | No | INR | $\text{Close}_t \times \text{Volume}_t$ |

Full catalog details and formulas are recorded in `docs/feature-dictionary.md`.

---

## 3. Design and Implementation Details

### 3.1 Causal Feature Pipeline (`finpilot.features.pipeline`)
- `CausalFeaturePipeline`: Processes streams of completed `CandleBar` or `MarketDataRecord` objects.
- Invariance: Bar $t$ is calculated strictly from history $\le t$. Future bars are not accessible.
- Session Boundaries: Detects date transitions in IST, resetting intraday typical-price and volume accumulators.
- Determinism: Given identical input bars, produces identical feature values. Shuffled bars are deterministically sorted or rejected if `require_sorted_input=True`.

### 3.2 Session-Aware Bar Aggregator (`finpilot.features.aggregator`)
- `SessionAwareBarAggregator`: Aggregates 1-minute source bars into 5-minute candles.
- Rejects weekend timestamps and out-of-session times (< 09:15 or $\ge$ 15:30 IST).
- Generates completed `CandleBar` instances adhering to Layer 3 domain validation contracts.

### 3.3 Deterministic Learned Transforms (`finpilot.features.transforms`)
- `DeterministicFeatureScaler`: Implements standard normalization with strict train/test separation.
- `fit(train_records)`: Calculates mean and standard deviation on training partitions only. Constant features with zero standard deviation default to $\sigma = 1.0$.
- `transform(test_records)`: Applies frozen statistics without modifying the scaler. Calling `transform()` before `fit()` raises `DomainValidationError`.
- Rejects non-finite values (NaN / Infinity) and serializes state with SHA-256 checksums.

### 3.4 Point-in-Time Universe Manager (`finpilot.features.universe`)
- `PointInTimeUniverseManager`: Evaluates instrument eligibility as of a historical timestamp $as\_of$.
- Prevents survivorship bias by keeping delisted stocks eligible for dates prior to their delisting.
- Prevents lookahead bias by excluding IPOs listed after $as\_of$.
- Resolves the exact active ticker symbol at $as\_of$ via `InstrumentSymbolHistory`.
- Evaluates liquidity filters strictly using sessions completed prior to $as\_of.\text{date}()$.

---

## 4. Files Added and Modified

### Added
- `backend/src/finpilot/features/__init__.py`: Package entrypoint exporting all feature components.
- `backend/src/finpilot/features/definitions.py`: Feature metadata, versioning, proxy disclosures, and catalog.
- `backend/src/finpilot/features/models.py`: Pydantic V2 models (`FeatureVector`, `FeatureBatch`, `PointInTimeUniverseSnapshot`, `UniverseMember`).
- `backend/src/finpilot/features/indicators.py`: Pure causal mathematical indicator functions.
- `backend/src/finpilot/features/aggregator.py`: Session-aware 5-minute bar aggregator.
- `backend/src/finpilot/features/pipeline.py`: Causal feature pipeline engine.
- `backend/src/finpilot/features/transforms.py`: Deterministic learned transforms with training-only fit.
- `backend/src/finpilot/features/universe.py`: Point-in-time universe selection and symbol resolution.
- `backend/tests/test_features_indicators.py`: Unit tests for mathematical indicator formulas.
- `backend/tests/test_features_aggregator.py`: Aggregation, session alignment, and out-of-session rejection tests.
- `backend/tests/test_features_causal_leakage.py`: Adversarial future-leakage, session reset, and mutation tests.
- `backend/tests/test_features_transforms.py`: Training-only fit, frozen transform, and serialization tests.
- `backend/tests/test_features_universe.py`: Survivorship-bias elimination and point-in-time universe tests.
- `docs/feature-dictionary.md`: Comprehensive FS-V1 feature dictionary and proxy disclosures.
- `docs/layers/layer-05/README.md`: This layer report.

### Modified
- `SECURITY_CHECKLIST.md`: Updated SEC-06 and SEC-19 with Layer 5 evidence.
- `docs/layers/README.md`: Marked Layer 5 as PASS.
- `README.md`: Updated current status and repository contents.
- `scripts/check_docs.ps1`: Added Layer 5 documentation and feature dictionary to required checks.

---

## 5. Verification Commands and Actual Results

| Step | Command | Result / Exit Code | Evidence Summary |
|---|---|---|---|
| Layer 5 Feature Tests | `python -m pytest -k "test_features" backend/tests -v` | Exit 0 | 28 passed in 2.98s |
| Full Backend Test Suite | `python -m pytest backend -v` | Exit 0 | 188 passed in 8.33s |
| ML Smoke Test | `python -m pytest ml` | Exit 0 | 1 passed in 0.04s |
| Frontend Test Suite | `npm --prefix frontend test` | Exit 0 | 2 files, 5 passed in 2.22s |
| Ruff Code Linting | `python -m ruff check backend` | Exit 0 | All checks passed (0 errors) |
| Mypy Static Type Check | `python -m mypy backend/src` | Exit 0 | Success: no issues found in 40 source files |
| Documentation & Link Check | `powershell -File scripts/check_docs.ps1` | Exit 0 | 24 required docs verified; 0 broken links; SEC-01..SEC-27 covered; RESULT: PASS |

---

## 6. Security Checklist Updates

- **SEC-06 (Server-Side Request Validation)**: `FeatureVector`, `FeatureBatch`, and `PointInTimeUniverseSnapshot` enforce typed Pydantic validation, UTC normalization, rejection of non-finite values (NaN/Inf), and rejection of uncompleted bars. Verified in `test_features_causal_leakage.py`. Status: `IMPLEMENTED`.
- **SEC-19 (Price/Trade Integrity Server-Side)**: `CausalFeaturePipeline`, indicators, and `PointInTimeUniverseManager` guarantee causal calculations with no future leakage: mutating future candles does not alter earlier features, intraday session VWAP resets at 09:15 IST, causal relative volume never uses eventual full-day volume, and point-in-time universe excludes future survivors while preserving historical delistings. Status: `IMPLEMENTED`.

---

## 7. Limitations and Layer Boundary Adherence

- **No ML Selection / Training**: Layer 5 implements causal feature computation and deterministic feature scaling; it does not train ML models or generate trade predictions (strictly deferred to Layer 9).
- **No Trade Policy Execution**: Layer 5 does not evaluate trade entries, stops, or targets (strictly deferred to Layer 6 / TP-V1 engine).
- **Strict Layer Boundary**: No order placement, risk checks, or portfolio state changes have been implemented or scaffolded.
