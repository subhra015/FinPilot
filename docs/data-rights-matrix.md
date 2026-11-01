# FinPilot AI — Data-Rights Matrix

Status: **Layer 4 Audit Complete**.
Related: `DATA_AND_PERFORMANCE_POLICY.md` §4, `PROJECT_SPEC.md` (OD-01), `SECURITY.md`.

---

## 1. Governance Rule

A dataset or provider may be used for a given purpose **only** if its corresponding cell is explicitly marked `PERMITTED` with the verified legal basis, terms reference, and verifier date recorded.

- If the legal rights or intended use clauses are ambiguous, unverified, or third-party scraped, the source is marked **`BLOCKED`**.
- Per project policy: **Do not assume a dataset on Kaggle or Hugging Face is automatically permitted** for hosted processing, model training, paper simulation, public display, or redistribution.
- Self-generated synthetic fixtures are permitted for software plumbing and unit tests but must always be clearly labelled `SYNTHETIC DEMO` and never reported as market evidence.

---

## 2. Standardized Use Cases

1. **Private Research**: Internal analysis and offline backtesting on private, controlled infrastructure.
2. **Hosted Notebook Processing**: Ingesting and processing data within third-party or cloud-hosted notebook runtimes.
3. **Model Training**: Generating, fitting, or tuning predictive ML models or selection layers.
4. **Forward Paper Simulation**: Runtime consumption for forward simulated paper-trading without real execution.
5. **Public Display**: Displaying raw prices, completed bars, or detailed order books to end-users or public web pages.
6. **Redistribution**: Sharing, sublicensing, mirroring, or republishing raw or parsed market data to third parties.
7. **Derived Outputs**: Publishing aggregate research verdicts, performance metrics, and model evaluations without exposing underlying price series.

---

## 3. Comprehensive Dataset Candidate Audit

| Dataset / Source | Publisher & Provenance | License & Terms Reference | 1 Private Research | 2 Hosted Notebook | 3 Model Training | 4 Paper Sim | 5 Public Display | 6 Redistribute | 7 Derived Outputs | Overall Status |
|---|---|---|---|---|---|---|---|---|---|---|
| **NSE Official Bhavcopy** | National Stock Exchange of India Ltd. Direct daily publication (`cm<dd><MMM><yyyy>bhav.csv.zip`). | NSE India Terms of Use (Non-commercial research). Prohibits commercial resale and unauthorized redistribution. | **PERMITTED** | **RESTRICTED** (Private VPC only) | **PERMITTED** | **PERMITTED** | **BLOCKED** | **BLOCKED** | **PERMITTED** | **PERMITTED for internal research; BLOCKED for redistribution/public display** |
| **Broker API (Zerodha Kite Connect)** | Zerodha Broking Ltd. (SEBI Registered Broker). Developer API v3. | Kite Connect Developer Terms. Intended for personal backtesting and account trading. Prohibits data redistribution. | **PERMITTED** (With active key) | **RESTRICTED** (Protected secrets) | **PERMITTED** | **PERMITTED** | **BLOCKED** | **BLOCKED** | **PERMITTED** | **BLOCKED / OPEN in V1 (No active broker credentials configured)** |
| **Commercial Vendor (TrueData / GDFL)** | TrueData India / Global Financial Datafeeds LLP (NSE authorized). | Commercial Datafeed Agreement. Commercial redistribution requires sublicensing. | **PERMITTED** (Paid tier) | **PERMITTED** | **PERMITTED** | **PERMITTED** | **RESTRICTED** | **BLOCKED** | **PERMITTED** | **BLOCKED in V1 (No commercial license procured)** |
| **Free Aggregators (Yahoo Finance)** | Yahoo Inc. / third-party licensors. Web scraping / unofficial endpoints. | Yahoo Terms of Service §3. Prohibits automated harvesting, scraping, commercial derivation, and redistributing. | **BLOCKED** | **BLOCKED** | **BLOCKED** | **BLOCKED** | **BLOCKED** | **BLOCKED** | **BLOCKED** | **BLOCKED (Terms prohibit automated pipeline harvesting)** |
| **Public Scraped Datasets (Kaggle / Hugging Face)** | Third-party anonymous uploaders scraping NSE historical data. | Often tagged "CC0" or "CC-BY-NC" without legal copyright ownership of NSE exchange data. Unverified provenance. | **BLOCKED** | **BLOCKED** | **BLOCKED** | **BLOCKED** | **BLOCKED** | **BLOCKED** | **BLOCKED** | **BLOCKED (Unverified provenance & potential IP infringement)** |
| **FinPilot Synthetic Generator (`SYNTHETIC DEMO`)** | FinPilot AI Development Team (Self-generated algorithmically). | Project MIT / Internal License. Complete project ownership. | **PERMITTED** | **PERMITTED** | **PERMITTED** (Architecture tests only) | **PERMITTED** (Demo mode) | **PERMITTED** (Label required) | **PERMITTED** | **PERMITTED** | **PERMITTED (Strictly labelled SYNTHETIC DEMO; never market evidence)** |

---

## 4. Verification Details & Audit Trails

### 4.1 NSE Bhavcopy (Official)
- **Publisher**: National Stock Exchange of India Ltd., Exchange Plaza, Bandra-Kurla Complex, Mumbai 400051.
- **Access Method**: HTTP archive downloads of daily capital market bhavcopy zip files.
- **Verification Date**: 2026-11-01 by FinPilot Security & Data Engineering Team.
- **Attribution & Rights Constraint**: Non-commercial internal evaluation permitted. Raw series must never be served over public endpoints or bundled in redistributable repositories.

### 4.2 Kaggle and Hugging Face Scraped Repositories
- **Audit Findings**: Scans of public Kaggle and Hugging Face datasets revealed that while individual uploaders claim "Public Domain" or "Creative Commons", the underlying data constitutes proprietary financial market feeds belonging to the National Stock Exchange of India. Furthermore, uploaded CSVs show unannounced corporate action splits, survivorship bias, and missing timestamps.
- **Verdict**: Per project policy, all third-party scraped NSE datasets on Kaggle/Hugging Face are **`BLOCKED`**.

### 4.3 Synthetic Demo Fixtures
- **Publisher**: FinPilot AI internal codebase (`finpilot.data.adapters.synthetic`).
- **Access Method**: Deterministic algorithmic generator based on fixed mathematical seeds.
- **Audit Findings**: Fully self-owned, zero external dependencies, no third-party copyright restrictions.
- **Constraint**: Must always carry `mode = DataMode.SYNTHETIC_DEMO` and be surfaced as `SYNTHETIC DEMO` in any UI or log.

---

## 5. Consequences for Architecture and Pipeline

1. **Storage Isolation**: Raw market data files are stored in `data/` outside the web root and excluded from Git tracking via `.gitignore`.
2. **Rejection of Unverified Sources**: The data ingestion pipeline strictly requires provider adapter classes (`NseBhavcopyAdapter`, `SyntheticDataProviderAdapter`, `ParquetFileAdapter`) with verified `DataSourceMetadata`.
3. **Public Exposure Guard**: The API layer (Layer 13) and UI layer (Layer 14) will never expose raw high-frequency historical bars to unauthenticated public traffic.
