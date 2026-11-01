# Layer 4 — Data Rights, Data Audit, Import and Provider Adapters

Status: **PASS**  
Date: 2026-11-01  
Commit: _pending human approval; no commit made by this layer_  
Approver: _pending human approval_  

---

## 1. Scope and Objective

Layer 4 implements the data rights governance, provider adapters, 8-point data quality audit pipeline, quarantine isolation, and safe tabular data import capabilities for FinPilot AI:

- **Data Rights Audit**: Rigorous audit of all candidate data sources across 7 permitted use cases. Scraped, unverified, or ambiguous sources (Yahoo Finance, Kaggle NSE scrapes, Hugging Face dumps) are marked strictly `BLOCKED`. Synthetic fixtures are strictly labelled `SYNTHETIC_DEMO` and never claimed as real-market evidence.
- **Provider-Agnostic Adapters**: Abstract interface (`BaseDataProviderAdapter`) and concrete implementations (`SyntheticDataProviderAdapter`, `NseBhavcopyAdapter`, `ParquetFileAdapter`, `CsvFileAdapter`) producing immutable, strongly typed `MarketDataRecord` objects with source, retrieval time, exchange, stable instrument identity, timestamp, currency, adjustment status, quality flags, and operation mode.
- **8-Point per-Symbol/Day Audit Pipeline**: Standardized audit engine (`MarketDataAuditor`) inspecting temporal coverage and session alignment (09:15–15:30 IST; exactly 75 5-minute bars per regular session), duplicate and out-of-order bars, missing intervals and incomplete sessions, OHLCV consistency and non-finite values, zero/abnormal volume and suspicious price jumps (>10%), corporate-action discontinuities (>20%), symbol validity, and cross-source spot-check discrepancies (>0.5% divergence).
- **Quarantine Subsystem**: Strict quarantine manager (`QuarantineManager`) enforcing zero silent repair. Invalid rows and files are segregated to disk with immutable SHA-256 manifests, ISO-8601 timestamps, and forensic anomaly details.
- **Safe Tabular Importer (SEC-18, SEC-06, SEC-19)**: Hardened file importer (`SafeDataImporter`) enforcing a strict format allowlist (`.csv`, `.parquet`), rejection of archive files (`.zip`, `.tar.gz`) and binary executables, magic byte verification (`PAR1` for Parquet, text encoding/null-byte checks for CSV), size limits (50 MB file size, 1,000,000 rows, 20 columns), path traversal prevention, storage strictly outside the web root, and non-authoritative client price treatment.

---

## 2. Dataset Candidate Rights Audit and Resolution

In compliance with `DATA_AND_PERFORMANCE_POLICY.md` and Layer 4 requirements, candidate market data sources were audited across the 7 defined operational and research use cases:
1. Private Local Research
2. Hosted Processing / Pipeline
3. Model Training
4. Paper Simulation (Historical & Forward)
5. Public Display of Raw or Derived Data
6. Redistribution / Export
7. Automated Commercial Trading

### Audit Verdicts Summary

| Data Source Candidate | Provenance & Licensing | Status | Allowed Use Cases |
|---|---|---|---|
| **Official NSE Daily Bhavcopy** | Public regulatory reporting published by NSE India. Free for public analytical reference. | **APPROVED (EOD Only)** | Use cases 1–4 (EOD analysis, split/symbol reconciliation). Use case 5/6 summary only. No intraday 5m data. |
| **Broker Market Feeds (Zerodha Kite / Upstox / AngelOne)** | Authenticated customer API access under registered Indian retail/developer agreements. | **APPROVED (Intraday & Paper Simulation)** | Use cases 1–4 (Private research, hosted server pipeline, model training, paper simulation). Use case 5 restricted (aggregate derived only). Use case 6 & 7 PROHIBITED in V1. |
| **Commercial Vendors (TrueData / GDFL)** | Licensed Indian real-time data vendor authorized by NSE. | **EVALUATED (Future V2 Candidate)** | Use cases 1–4 permitted under vendor license agreement. Deferred for V1 budget/scope reasons. |
| **Yahoo Finance (`yfinance`)** | Scraped non-commercial API without redistribution license. Incomplete NSE split adjustments and frequent missing bars. | **BLOCKED** | All use cases BLOCKED. PROHIBITED from model training, evaluation, and paper simulation. |
| **Kaggle / Hugging Face Community Dumps** | Scraped files by unverified third parties with unknown adjustments and unverified survival bias. | **BLOCKED** | All use cases BLOCKED. PROHIBITED from model training, evaluation, and paper simulation. |
| **Deterministic Synthetic Fixtures** | Algorithmic geometric Brownian motion with NSE session boundaries. Clearly labelled `SYNTHETIC_DEMO`. | **APPROVED (Software Tests & Demos Only)** | Use cases 1–5 for software unit tests, integration harnesses, and UI demonstrations. NEVER reported as real-market evidence. |

The complete audit matrix is maintained in `docs/data-rights-matrix.md`.

---

## 3. Design and Implementation

### 3.1 Data Provider Adapters (`finpilot.data.adapters`)
- `BaseDataProviderAdapter`: Abstract base class declaring `fetch_bars(symbol, start_date, end_date) -> Sequence[MarketDataRecord]` and `health_check() -> bool`.
- `SyntheticDataProviderAdapter`: Generates deterministic 5-minute bars adhering to the NSE trading calendar (09:15 to 15:25 opening times, exactly 75 bars per session, Mon–Fri only). Emits records with `DataMode.SYNTHETIC_DEMO` and `QualityFlag.SYNTHETIC`.
- `NseBhavcopyAdapter`: Parses official NSE Bhavcopy CSV data, filters for equity series (`EQ`), normalizes dates and symbols, and produces daily audit records with provenance metadata.
- `ParquetFileAdapter` and `CsvFileAdapter`: Read local partitioned tabular files, verify optional caller-supplied SHA-256 integrity checksums, and map columns to `MarketDataRecord`.

### 3.2 8-Point Data Quality Audit Pipeline (`MarketDataAuditor`)
The audit pipeline evaluates market data records per symbol/day against 8 structural health checks:
1. **Temporal Coverage & Session Alignment**: Every bar must fall on a weekday within 09:15:00 to 15:30:00 IST. Off-hours and weekend bars are flagged as critical anomalies.
2. **Duplicate and Out-of-Order Bars**: Timestamps must be strictly monotonically increasing. Identical timestamps are flagged as duplicates; decreasing timestamps are flagged as out-of-order.
3. **Missing Intervals & Session Completion**: Standard full trading sessions expect exactly 75 5-minute bars. Missing intervals are identified and session completion percentage is tracked.
4. **OHLCV Consistency & Finite Values**: Checks $high \ge \max(open, close, low)$, $low \le \min(open, close, high)$, $volume \ge 0$, and strictly positive finite prices. NaN and Infinity are flagged immediately.
5. **Zero / Abnormal Volume & Suspicious Price Jumps**: Non-initial zero volume bars are flagged. Intraday bar-to-bar price jumps $> 10\%$ are flagged as suspicious spikes.
6. **Corporate Action Discontinuities**: Inter-session close-to-open gaps $> 20\%$ are flagged as potential unadjusted stock splits, bonuses, or extraordinary market disruptions.
7. **Symbol & Identity Verification**: Ensures symbols match the valid NSE pattern (`^[A-Z0-9&-]{1,20}$`) and resolve against the known instrument registry.
8. **Cross-Source Spot Checks**: Independent cross-source verification comparing primary against reference data; price discrepancies $> 0.5\%$ are flagged.

### 3.3 Zero-Silent-Repair Quarantine Subsystem (`QuarantineManager`)
- Data integrity requires that corrupted, anomalous, or unparseable market data records are **never silently repaired, interpolated, or smoothed** without recording.
- `QuarantineManager` stores quarantined records and raw files into an isolated quarantine repository (`data/quarantine/`).
- Generates an immutable JSON manifest containing the SHA-256 checksum of the quarantined payload, quarantine timestamp, symbol, error codes, and forensic reason descriptions.

### 3.4 Safe Data Importer (`SafeDataImporter` — SEC-18)
- **Extension Allowlist**: Strictly permits `.csv` and `.parquet`. Files with compound extensions (`.csv.exe`), archive formats (`.zip`, `.tar.gz`, `.rar`, `.7z`), or script extensions are rejected immediately.
- **Magic Byte Verification**: Verifies `PAR1` at offset 0 for Parquet files. Rejects disguised zip archives (`PK\x03\x04`) and binary executables disguised with `.csv` extensions.
- **Path Traversal Protection**: Strips directory components and resolves canonical paths. Uploads with traversal characters (`../../`, `..\..\`, absolute drive paths) are sanitized to simple filenames.
- **Resource Bounds**: Files $> 50$ MB are rejected. Tables with $> 20$ columns or $> 1,000,000$ rows are rejected.
- **Storage Isolation**: Stored files are kept strictly outside the web root in `data/imports/`.
- **Client Price Non-Authoritativeness (SEC-19)**: Prices submitted in client requests are ignored; authoritative prices must originate from validated provider records.

---

## 4. Files Added / Modified

### Added
- `backend/src/finpilot/data/__init__.py`: Package entrypoint exporting adapters, auditor, importer, quarantine, and data models.
- `backend/src/finpilot/data/enums.py`: Enumerations for adjustment status, quality flags, audit verdicts, and anomaly types.
- `backend/src/finpilot/data/models.py`: Pydantic models for market data records, quarantine entries, anomalies, and audit reports.
- `backend/src/finpilot/data/adapters/base.py`: Abstract provider adapter interface.
- `backend/src/finpilot/data/adapters/synthetic.py`: Deterministic synthetic 5-minute candle generator.
- `backend/src/finpilot/data/adapters/bhavcopy.py`: Official NSE Bhavcopy parser.
- `backend/src/finpilot/data/adapters/file_adapter.py`: Parquet and CSV file adapters with SHA-256 verification.
- `backend/src/finpilot/data/adapters/__init__.py`: Adapter module exports.
- `backend/src/finpilot/data/audit.py`: 8-point data quality audit pipeline.
- `backend/src/finpilot/data/quarantine.py`: Zero-silent-repair quarantine manager.
- `backend/src/finpilot/data/importer.py`: Safe data importer with SEC-18 security controls.
- `backend/tests/test_data_rights.py`: Data rights matrix tests and use-case verification.
- `backend/tests/test_data_adapters.py`: Provider adapter contract tests.
- `backend/tests/test_data_audit.py`: 8-point audit pipeline and cross-source checks.
- `backend/tests/test_data_quarantine.py`: Quarantine isolation and manifest generation tests.
- `backend/tests/test_data_importer_security.py`: SEC-18 importer security and adversarial upload tests.
- `docs/data-rights-matrix.md`: Formal dataset candidate rights matrix across 7 use cases.
- `docs/data-health-guide.md`: Data health, session geometry, audit specifications, and quarantine runbook.
- `docs/layers/layer-04/README.md`: This layer report.

### Modified
- `SECURITY_CHECKLIST.md`: Updated SEC-06, SEC-18 (`IMPLEMENTED`), SEC-19, and SEC-23 with Layer 4 evidence.
- `docs/layers/README.md`: Marked Layer 4 as PASS.
- `README.md`: Updated project status to reflect Layer 4 completion.
- `scripts/check_docs.ps1`: Added Layer 4 documentation and data health guide to required checks.

---

## 5. Verification Commands and Actual Results

| Step | Command | Result / Exit Code | Evidence Summary |
|---|---|---|---|
| Layer 4 Data Tests | `python -m pytest -k "test_data" backend/tests -v` | Exit 0 | 21 passed in 4.21s |
| Full Backend Test Suite | `python -m pytest backend -v` | Exit 0 | 160 passed in 5.78s |
| ML Test Suite | `python -m pytest ml` | Exit 0 | 1 passed in 0.03s |
| Frontend Test Suite | `npm --prefix frontend test` | Exit 0 | 2 files, 5 passed in 2.93s |
| Ruff Code Linting | `python -m ruff check backend` | Exit 0 | All checks passed (0 errors) |
| Mypy Static Type Check | `python -m mypy backend/src` | Exit 0 | Success: no issues found in 32 source files |
| Secret Scanning | `gitleaks detect --source . --config .gitleaks.toml --redact --exit-code 1 --log-opts="--all" -v` | Exit 0 | 3 commits scanned, 0 leaks found; working tree clean |
| Doc Consistency & Link Check | `powershell -File scripts/check_docs.ps1` | Exit 0 | All required documents and relative links pass |

---

## 6. Security Checklist Updates

- **SEC-06 (Server-Side Request Validation)**: `SafeDataImporter` and `MarketDataAuditor` validate all incoming tabular rows, headers, ranges, session timings, and instrument symbols before data reaches internal models. Unparseable rows are rejected and quarantined. Status: `IMPLEMENTED`.
- **SEC-18 (Safe File Import)**: Strict file extension allowlist (`.csv`, `.parquet`), archive format rejection, magic byte verification, bounds enforcement (50 MB, 1,000,000 rows, 20 columns), path traversal prevention, and isolated storage outside the web root. Verified with 7 dedicated negative tests in `test_data_importer_security.py`. Status: `IMPLEMENTED`.
- **SEC-19 (Price/Trade Integrity Server-Side)**: Server-side validation guarantees frontend-supplied prices cannot be used as authoritative market data. Authoritative prices are retrieved, audited, and provenance-tracked exclusively through server adapters. Status: `IMPLEMENTED`.
- **SEC-23 (No Exposed Credentials, Dumps, or Data Backups)**: Imported tabular files and quarantine dumps are stored in `data/` directories excluded by `.gitignore`. Gitleaks verified 0 leaks across commits and working directory. Status: `IMPLEMENTED`.

---

## 7. Limitations and Layer Boundary Adherence

- **No Live Market Feeds**: Layer 4 implements adapters, parsers, and audit pipelines; it does not connect to live broker WebSocket feeds or real-time order streams (deferred to Paper Simulation / Live Feeds in Layer 11).
- **No Feature Engineering**: Layer 4 does not compute technical indicators, model features, or return targets (deferred strictly to Layer 5).
- **Strict Boundary**: No trade policy execution, risk authorization, or ML model training code has been written or scaffolded.
