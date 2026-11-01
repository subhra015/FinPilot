# FinPilot AI — Market Data Health & Audit Guide

Status: **Layer 4 Specification**  
Related: `DATA_AND_PERFORMANCE_POLICY.md`, `docs/data-rights-matrix.md`, `ARCHITECTURE.md`.

---

## 1. Overview & Golden Rules

FinPilot treats all market data as untrusted external input until subjected to systematic validation and health audits.

### Core Principles
1. **Never Silently Repair**: Corrupted or misaligned data must never be silently patched, interpolated, or coerced. Any row or file failing validation is explicitly routed to the quarantine store with a documented rejection reason.
2. **Completed 5-Minute Bars Only**: Trade policy and feature evaluation act exclusively on completed 5-minute bars. Incomplete or partially formed bars are rejected.
3. **Point-in-Time Correctness**: Timestamps represent the opening time of the 5-minute bar, converted and stored in UTC, and verified against Asia/Kolkata (IST) exchange sessions.
4. **Provenance Attachment**: Every record maintains its provider source, retrieval timestamp, exchange code, stable instrument ID, currency, and adjustment status throughout preprocessing.

---

## 2. Session Geometry & The 8 Audit Checks

For standard NSE cash equities, a normal trading session runs from **09:15 to 15:30 IST**, Monday through Friday. A complete session consists of exactly **75 completed 5-minute bars** (bars opening from 09:15 to 15:25 inclusive).

The `MarketDataAuditor` executes eight health checks per symbol/day:

### 1. Temporal Coverage & Session Alignment
- **Expected Bars**: 75 bars per regular session.
- **Alignment**: Every timestamp must satisfy `minute % 5 == 0` and `second == 0`.
- **Trading Session**: Timestamps must fall strictly between 09:15 IST and 15:25 IST.
- **Calendar**: Dates on weekends (Saturday, Sunday) are rejected as `SESSION_MISALIGNMENT`.

### 2. Duplicate & Out-of-Order Bars
- **Duplicates**: Multiple bars with the identical UTC timestamp are flagged as `DUPLICATE_BAR` and quarantined.
- **Monotonicity**: Bars must strictly advance in chronological order ($t_i > t_{i-1}$). Any timestamp regression ($t_i < t_{i-1}$) triggers `OUT_OF_ORDER_BAR`.

### 3. Missing Intervals & Incomplete Sessions
- Missing 5-minute slots in the 75-bar sequence are identified.
- Completion percentage is computed as $\frac{\text{valid unique session bars}}{75} \times 100\%$.
- Sessions missing $> 30$ bars receive a `CRITICAL` severity rating.

### 4. OHLCV Invariants & Non-Finite Value Rejection
- **High Consistency**: $high \ge \max(open, close, low)$.
- **Low Consistency**: $low \le \min(open, close, high)$.
- **Price Bounds**: All prices must be strictly positive finite decimals ($> 0$). NaN and Infinity are strictly rejected.
- **Volume Bounds**: Volume must be a non-negative integer ($\ge 0$). Negative volume triggers quarantine.

### 5. Zero Volume, Abnormal Spikes & Single-Bar Price Jumps
- **Zero Volume**: Extended zero-volume intervals are tracked for illiquidity.
- **Volume Spikes**: Volume $> 15\times$ rolling session median (and $> 50,000$ shares) triggers `VOLUME_SPIKE` warnings.
- **Single-Bar Price Jumps**: A single 5-minute move $|close - open| / open > 10\%$ triggers `SUSPICIOUS_PRICE_JUMP`, as this exceeds typical NSE circuit band thresholds for liquid large-cap equities.

### 6. Corporate Action Discontinuities & Adjustment Limitations
- **Overnight Gap Detection**: An opening gap $> 20\%$ relative to the previous session close is flagged as `CORPORATE_ACTION_GAP` (indicating potential stock splits, bonus issues, or extraordinary dividends).
- **Adjustment Limitations**: Unadjusted (`UNADJUSTED`) and split-adjusted (`SPLIT_ADJUSTED`) data must never be mixed without adjustment factor tracking. Mixing them distorts return calculations and model evaluations.

### 7. Symbol Changes & Listing / Delisting Limitations
- Trading records must fall within the instrument's active validity window (`valid_from` to `valid_to` in `instrument_symbol_history`).
- Symbols that have undergone historical ticker changes (e.g. `UTIBANK` $\rightarrow$ `AXISBANK`) must be resolved to their permanent ISIN identity.

### 8. Cross-Source Spot Checks
- When secondary reference data is available, `cross_source_check` compares primary bars against reference bars.
- Relative price deviations $> 0.5\%$ are flagged as `CROSS_SOURCE_DISCREPANCY`.

---

## 3. Quarantine Architecture

The `QuarantineManager` provides an immutable audit trail for all rejected market data:

1. **Quarantine Record**: Captures `source`, `quarantined_at`, `rejection_reason`, `symbol`, `timestamp`, and the complete `raw_payload`.
2. **Quarantine Storage**: Quarantined records are isolated in `data/quarantine/` outside the web root.
3. **Audit Manifest**: Writes JSON manifests with SHA-256 cryptographic checksums, recording exact rejection counts and defect categories for regulatory and operational inspection.

---

## 4. Safe Data Importer (SEC-06, SEC-18, SEC-19, SEC-23)

The `SafeDataImporter` implements secure ingest boundaries for historical tabular files:

| Protection | Implementation | Threat Mitigated |
|---|---|---|
| **Format Allowlist** | Only `.csv` and `.parquet` permitted | Code execution, archive bombs, script execution |
| **Magic Byte Verification** | Parquet magic `PAR1` at start/end; CSV binary null byte detection | Extension spoofing, executable smuggling |
| **Resource Limits** | Max 50 MB file size, max 1,000,000 rows, max 20 columns | Resource exhaustion, memory overflow, DoS |
| **Path Traversal Guard** | Strips `..`, `/`, `\`, null bytes; safe filename regex | Arbitrary file overwrite, directory traversal |
| **Storage Isolation** | Stored strictly in `data/imports/` outside web root | Public exposure, web shell execution |
| **Non-Authoritative Client** | Frontend-supplied prices are ignored; server validates all data | Client-side price tampering, forged fills |
