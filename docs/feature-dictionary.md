# FinPilot AI — Feature Dictionary (FS-V1)

Status: **Ratified (Layer 5)**  
Related: `PROJECT_SPEC.md`, `DATA_AND_PERFORMANCE_POLICY.md` §2, `ARCHITECTURE.md` §2, §3.  

---

## 1. Overview and Causal Contract

The **FS-V1** feature set defines the approved, strictly causal feature catalog for FinPilot AI. Features are calculated exclusively from **completed 5-minute OHLCV candle bars** within the regular National Stock Exchange (NSE) cash equity trading session (09:15:00 to 15:30:00 IST).

### Binding Causal Invariants
1. **Decision Time Boundary**: A feature vector evaluated at timestamp $t$ uses only bars completed strictly at or before $t$.
2. **Future Invariance**: Mutating, adding, or deleting bars at timestamps $> t$ has zero effect on features at $t$.
3. **Session Alignment & Resets**: Intraday metrics (e.g. cumulative session VWAP approximation, session bar index 0..74) strictly reset at the beginning of each trading session (09:15:00 IST). They never bleed across overnight or weekend boundaries.
4. **Causal Relative Volume**: Morning relative volume metrics use only completed prior periods. Eventual end-of-day total volume is **never** used as a denominator.
5. **Proxy Disclosures**: All approximations derived from OHLCV bars are explicitly labelled as proxies. They must never be misrepresented as tick-level trade executions, order book queue positions, or bid-ask spreads.
6. **Insufficient History Handling**: Bars with insufficient history produce `None` for the affected feature. Features are never forward-filled or interpolated with future data. Full warm-up requires 21 completed 5-minute bars.

---

## 2. Approved Features Catalog (FS-V1)

| Feature Name | Category | Warm-up Bars | Cross-Session | Units | Range | Formula / Description |
|---|---|---|---|---|---|---|
| `ret_1` | MOMENTUM | 1 bar (5m) | No | ratio | $[-1.0, 10.0]$ | 1-bar price return: $\frac{\text{Close}_t - \text{Close}_{t-1}}{\text{Close}_{t-1}}$ |
| `ret_3` | MOMENTUM | 3 bars (15m) | No | ratio | $[-1.0, 10.0]$ | 3-bar (15m) price return: $\frac{\text{Close}_t - \text{Close}_{t-3}}{\text{Close}_{t-3}}$ |
| `ret_6` | MOMENTUM | 6 bars (30m) | No | ratio | $[-1.0, 10.0]$ | 6-bar (30m) price return: $\frac{\text{Close}_t - \text{Close}_{t-6}}{\text{Close}_{t-6}}$ |
| `sma_9` | TREND | 9 bars (45m) | Yes | INR | $(0, \infty)$ | 9-period Simple Moving Average of close: $\frac{1}{9}\sum_{i=0}^8 \text{Close}_{t-i}$ |
| `sma_21` | TREND | 21 bars (105m)| Yes | INR | $(0, \infty)$ | 21-period Simple Moving Average of close: $\frac{1}{21}\sum_{i=0}^{20} \text{Close}_{t-i}$ |
| `sma_ratio_9_21` | TREND | 21 bars (105m)| Yes | ratio | $[-1.0, 5.0]$ | Moving average trend ratio: $\frac{\text{SMA}_9(t)}{\text{SMA}_{21}(t)} - 1.0$ |
| `rsi_14` | MOMENTUM | 14 bars (70m) | Yes | index | $[0.0, 100.0]$ | 14-period Wilder's Relative Strength Index |
| `atr_14` | VOLATILITY | 14 bars (70m) | Yes | INR | $[0, \infty)$ | 14-period Average True Range: $\text{TR} = \max(H-L, \|H-C_{\text{prev}}\|, \|L-C_{\text{prev}}\|)$ |
| `natr_14` | VOLATILITY | 14 bars (70m) | Yes | ratio | $[0.0, 2.0]$ | Normalized ATR (percentage volatility proxy): $\frac{\text{ATR}_{14}(t)}{\text{Close}_t}$ |
| `vwap_approx_distance` | PRICE_LOCATION | 1 bar (5m) | No (Resets at 09:15) | ratio | $[-1.0, 5.0]$ | Normalized distance from intraday session VWAP approximation: $\frac{\text{Close}_t - \text{VWAP}_{\text{approx}}(t)}{\text{VWAP}_{\text{approx}}(t)}$ |
| `causal_rel_vol` | VOLUME | 10 bars (50m) | Yes | ratio | $[0.0, 1000.0]$ | Causal relative volume: current volume divided by rolling mean of prior 10 completed bars |
| `turnover_proxy_5m` | LIQUIDITY | 0 bars | No | INR | $[0, \infty)$ | 5-minute bar traded value proxy: $\text{Close}_t \times \text{Volume}_t$ |

---

## 3. Mandatory Proxy Disclosures and Limitations

### 3.1 VWAP Approximation (`vwap_approx_distance`)
> **Mandatory Disclosure**: *OHLCV typical-price cumulative session approximation ($\sum \frac{H+L+C}{3} \times V / \sum V$). NOT an observed trade-level execution VWAP from tick data.*  
- **Calculation**: Computes bar typical price $TP = \frac{H+L+C}{3}$. Accumulates $\sum (TP \times V)$ and $\sum V$ starting strictly from bar index 0 of the current trading day.
- **Session Boundary**: Strictly resets at 09:15:00 IST every morning. Never accumulates yesterday's volume into today's VWAP.

### 3.2 Causal Relative Volume (`causal_rel_vol`)
> **Mandatory Disclosure**: *Rolling prior-period relative volume ratio. Does NOT represent observed order-book depth or queue position.*  
- **Calculation**: $\frac{V_t}{\frac{1}{10}\sum_{i=1}^{10} V_{t-i}}$.
- **Causal Guarantee**: Uses only strictly prior completed bars ($t-1, \dots, t-10$). Under no circumstance is the eventual full-day volume used as a reference.

### 3.3 5-Minute Turnover Proxy (`turnover_proxy_5m`)
> **Mandatory Disclosure**: *Bar turnover proxy derived from close $\times$ volume in INR. Does NOT reflect tick-level trade value distribution, bid-ask spread, or queue position.*  
- **Calculation**: $\text{Close}_t \times \text{Volume}_t$.

---

## 4. Point-in-Time Universe and Survivorship Bias

Point-in-time universe selection (`PointInTimeUniverseManager`) guarantees that historical research and evaluations are not contaminated by survivorship bias or lookahead bias:

1. **No Future Survivors (IPO Exclusion)**:
   - An instrument listed on date $D_{\text{list}}$ is strictly marked `is_eligible = False` for all queries where $as\_of < D_{\text{list}}$.
2. **No Survivorship Bias (Delisting Preservation)**:
   - An instrument delisted on date $D_{\text{delist}}$ remains `is_eligible = True` for all queries where $as\_of < D_{\text{delist}}$ (provided it was listed and met liquidity criteria).
3. **Historical Symbol Resolution**:
   - Ticker symbol changes (e.g., `UTIBANK` $\rightarrow$ `AXISBANK`) resolve to the exact active symbol at timestamp $as\_of$, tied to immutable ISIN and stable internal `instrument_id`.
4. **Causal Liquidity Filter**:
   - Daily turnover evaluation calculates the median turnover of sessions strictly prior to the evaluation session ($< as\_of.\text{date}()$). The current session's turnover is never included.

---

## 5. Learned Transforms & Preprocessing Hygiene

Learned preprocessing (e.g. z-score normalization) is implemented via `DeterministicFeatureScaler`:

1. **Training-Only Fit**:
   - `fit(train_records)` computes $\mu, \sigma$ strictly on training folds.
   - Non-finite values (NaN / Infinity) are rejected with `DomainValidationError`.
   - Constant features with zero standard deviation are protected by setting $\sigma = 1.0$.
2. **Frozen Transform**:
   - `transform(records)` applies $(x - \mu) / \sigma$ using frozen parameters.
   - Calling `transform()` never updates, mutates, or adapts fitted statistics.
3. **Reproducibility & Serialization**:
   - Scaler statistics are serialized with a SHA-256 integrity checksum (`fit_checksum`).
   - Tampered or corrupted scaler files are rejected during deserialization.
