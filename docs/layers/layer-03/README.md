# Layer 3 — Domain Schemas and Validation Contracts

Status: **PASS**  
Date: 2026-11-01  
Commit: _pending human approval; no commit made by this layer_  
Approver: _pending human approval_  

---

## 1. Scope and Objective

Layer 3 establishes the typed domain schemas and validation contracts for FinPilot AI:

- **Strict Instrument Identity**: Immutable and verified instrument identity (`InstrumentBase`, `InstrumentCreate`, `InstrumentRead`, `KnownInstrumentRegistry`) enforcing strict ISIN format (12 characters, uppercase country prefix) and NSE trading symbol patterns (`^[A-Z0-9&-]{1,20}$`). Arbitrary client-supplied instrument identifiers are rejected by registry resolution.
- **Completed 5-Minute Candles**: Validated OHLCV candle bars (`CandleBar`, `CandleBatch`) strictly bound to 5-minute boundaries, regular NSE market hours (09:15–15:30 IST; last 5-minute bar opens at 15:25 IST), and weekday trading sessions (Mon–Fri). Timestamps are strictly timezone-aware and normalized to UTC internally.
- **OHLCV Integrity**: Prices must be strictly positive finite decimals ($high \ge \max(open, close, low)$, $low \le \min(open, close, high)$); volume must be a non-negative integer; NaN and Infinity are strictly rejected across all numeric fields. Decisions require completed bars (`is_completed=True`).
- **Dataset Manifests & Provenance**: Dataset manifests (`DatasetManifestCreate`, `DatasetManifestRead`) and provider metadata (`DataSourceMetadata`) enforcing 64-character lowercase SHA-256 integrity checksums, chronological timestamps ($start \le end$), non-negative row counts, and licensing provenance.
- **Trade Policy Contract (TP-V1)**: Long-only cash equity invariants (`TradePolicyV1Contract`, `TradeProposal`): $stop\_loss < entry\_price < target\_price$, causal execution timing ($earliest\_entry\_timestamp > decision\_timestamp$), and whole-share integer quantities ($quantity \ge 1$). Short selling, derivatives, and leverage are prohibited.
- **Indian Regulatory Cost Breakdown**: Server-side cost breakdown (`CostBreakdown`) computing statutory components: brokerage, STT (Securities Transaction Tax), exchange turnover charges, SEBI turnover fees, stamp duty, GST (18% on service charges), and modelled slippage.
- **State Transition Contracts**: Formal state machine validation for execution orders (`VALID_ORDER_TRANSITIONS`, `validate_order_transition`) and audit ledger sequences (`validate_ledger_sequence`), enforcing strictly monotonic sequence numbering ($N+1$) and SHA-256 `prev_hash` chaining.
- **Boundary Scoping (SEC-01, SEC-06, SEC-09)**: Request scoping (`UserScope`, `enforce_resource_owner`, `enforce_account_access`) preventing unauthorized cross-user access at schema and service boundaries without leaking victim existence or metadata.
- **Safe Error Responses (SEC-06, SEC-07, SEC-19)**: Universal error sanitization (`sanitize_error_message`, `ErrorResponse`, `ErrorDetail`, `DomainValidationError`) redacting internal filesystem paths, raw SQL query fragments, and connection credentials from API responses and client-facing exceptions.

---

## 2. Initial Repository Findings

- Layer 0 (Governance), Layer 1 (Foundation), and Layer 2 (Database & Persistence Foundation) were present and fully verified.
- The operational database models in `finpilot.db.models` established relational tables, but service/API inputs required strongly typed domain schemas and validation contracts.
- Database access audit confirmed all database queries in the codebase utilize SQLAlchemy ORM with bound parameters; no string-concatenated SQL queries exist.

---

## 3. Design and Implementation

### 3.1 Pydantic V2 Domain Schemas
All domain models use Pydantic V2 with `model_config = ConfigDict(extra="forbid", frozen=True)` to prevent arbitrary or unvalidated fields from entering domain boundaries:
1. `finpilot.schemas.instruments`: `InstrumentBase`, `InstrumentCreate`, `InstrumentRead`, and `KnownInstrumentRegistry`.
2. `finpilot.schemas.candles`: `CandleBar` with IST market calendar validation and `CandleBatch` bounded to 1,000 candles.
3. `finpilot.schemas.datasets`: `DataSourceMetadata`, `DatasetManifestBase`, `DatasetManifestCreate`, and `DatasetManifestRead`.
4. `finpilot.schemas.trade_policy`: `TradePolicyV1Contract` (TP-V1) and `TradeProposal`.
5. `finpilot.schemas.execution_cost`: `CostBreakdown`, `OrderBase`, `OrderCreate`, `OrderRead`, and `PositionRead`.
6. `finpilot.schemas.state_transitions`: Order status transition map and ledger sequence validator.
7. `finpilot.schemas.scoping`: `UserScope`, resource owner enforcement, and account access enforcement.
8. `finpilot.schemas.common`: Standardized `PaginationParams` (page $\ge 1$, size 1–100), `DateRangeFilter` (span $\le 366$ days), UTC normalization (`normalize_to_utc`), and `SortOrderSpec` with dynamic sort field allowlists.
9. `finpilot.schemas.errors`: `sanitize_error_message`, `ErrorCode`, `ErrorDetail`, `ErrorResponse`, and domain exceptions (`DomainValidationError`, `InvalidStateTransitionError`, `PermissionDeniedError`, `ResourceNotFoundError`).

### 3.2 SQL Injection Audit & Allowlist Sorting (SEC-10)
- `SortOrderSpec` inspects dynamic sort fields against a strict identifier pattern and SQL injection signature regex (`SQL_INJECTION_CHARS`), and requires verification against an explicit caller-defined field allowlist (`validate_allowed(allowed_fields)`).
- Adversarial tests verify that SQL injection payloads (`'; DROP TABLE...`, `UNION SELECT`) are either rejected or treated strictly as literal data without execution.

### 3.3 Safe Error Handling (SEC-06, SEC-07, SEC-19)
- `backend/src/finpilot/app.py` attaches global exception handlers for `DomainValidationError`, `RequestValidationError`, `PermissionDeniedError`, and `ResourceNotFoundError`.
- Every error message passes through `sanitize_error_message`, replacing drive letters/file paths with `[PATH_REDACTED]`, SQL query fragments with `[DATABASE_QUERY_REDACTED]`, and URL credentials with `[REDACTED]@`.

---

## 4. Files Added / Modified

### Added
- `backend/src/finpilot/schemas/__init__.py`: Package entrypoint exporting all domain contracts and models.
- `backend/src/finpilot/schemas/errors.py`: Safe error models, exception classes, and error sanitizer.
- `backend/src/finpilot/schemas/common.py`: Common pagination, date filters, UTC normalization, and sort specs.
- `backend/src/finpilot/schemas/instruments.py`: Instrument models and known symbol registry.
- `backend/src/finpilot/schemas/candles.py`: Completed 5-minute candle schemas and market session contracts.
- `backend/src/finpilot/schemas/datasets.py`: Dataset manifest and provider metadata schemas.
- `backend/src/finpilot/schemas/trade_policy.py`: TP-V1 trade policy and long-only trade proposal contracts.
- `backend/src/finpilot/schemas/execution_cost.py`: Cost breakdown, order, and position schemas.
- `backend/src/finpilot/schemas/state_transitions.py`: Order and ledger state machine validation.
- `backend/src/finpilot/schemas/scoping.py`: User/owner scoping and cross-tenant boundary enforcers.
- `backend/tests/test_schemas_common.py`: Pagination, date range, UTC normalization, and sort allowlist tests.
- `backend/tests/test_schemas_instruments.py`: Instrument and ISIN validation tests.
- `backend/tests/test_schemas_candles.py`: OHLCV, market session, and completed-bar tests.
- `backend/tests/test_schemas_datasets.py`: Dataset manifest and SHA-256 validation tests.
- `backend/tests/test_schemas_trade_policy.py`: Trade policy and proposal invariant tests.
- `backend/tests/test_schemas_state_transitions.py`: Order and ledger sequence transition tests.
- `backend/tests/test_schemas_scoping.py`: Owner and account access scoping tests.
- `backend/tests/test_schemas_adversarial.py`: Adversarial SQL injection, NaN/Inf, and malformed input tests.
- `docs/layers/layer-03/README.md`: This layer report.

### Modified
- `backend/src/finpilot/app.py`: Integrated global sanitized exception handlers for domain and request validation.
- `SECURITY_CHECKLIST.md`: Updated SEC-06, SEC-10, and SEC-19 status and evidence.
- `docs/layers/README.md`: Marked Layer 3 as PASS.
- `README.md`: Updated project status and current layer.
- `scripts/check_docs.ps1`: Added Layer 3 documentation to required checks.

---

## 5. Verification Commands and Actual Results

| Step | Command | Result / Exit Code | Evidence Summary |
|---|---|---|---|
| Schema Unit & Negative Tests | `python -m pytest -k "test_schemas" backend/tests` | Exit 0 | 91 passed in 2.37s |
| Full Backend Test Suite | `python -m pytest backend` | Exit 0 | 142 passed in 3.89s |
| ML Test Suite | `python -m pytest ml` | Exit 0 | 1 passed in 0.03s |
| Frontend Test Suite | `npm --prefix frontend test` | Exit 0 | 2 files, 5 passed in 34.96s |
| Ruff Code Linting | `python -m ruff check backend` | Exit 0 | All checks passed (0 errors) |
| Mypy Static Type Check | `python -m mypy backend/src` | Exit 0 | Success: no issues found in 21 source files |
| Secret Scanning (Git Commits) | `gitleaks detect --source . --config .gitleaks.toml --redact --exit-code 1 --log-opts="--all" -v` | Exit 0 | 2 commits scanned, 0 leaks found |
| Secret Scanning (Working Tree) | `gitleaks detect --source . --no-git --config .gitleaks.toml --redact --exit-code 1 -v` | Exit 0 | 342.87 KB scanned, 0 leaks found |
| Documentation Consistency | `powershell -File scripts/check_docs.ps1` | Exit 0 | All required documents present, SEC controls covered, 0 broken links |

---

## 6. Security Controls Checked (SEC IDs)

- **SEC-06 (Server-Side Request Validation)**:
  - Strong typing, boundary bounds, regex patterns, and enums enforced across instruments, candles, datasets, trade proposals, orders, and pagination.
  - Server-side rejection of malformed JSON, out-of-bounds quantities, NaN/Infinity, out-of-session timestamps, and cross-user identifiers.
  - Tested in `test_schemas_*.py` and `test_schemas_adversarial.py`.
  - **Status: IMPLEMENTED for Layer 3 domain schemas & contracts; API L12 pending.**
- **SEC-10 (SQL Injection Safety & Parameterized Queries)**:
  - `SortOrderSpec` enforces identifier syntax validation and strict field allowlists (`validate_allowed`).
  - Adversarial tests in `test_schemas_adversarial.py` demonstrate that SQL injection payload strings are rejected by syntax validators or treated strictly as literal data in dictionary/registry lookups.
  - **Status: IMPLEMENTED.**
- **SEC-19 (Price & Trade Integrity Server-Side)**:
  - `TradePolicyV1Contract` and `TradeProposal` enforce long-only invariants ($stop\_loss < entry\_price < target\_price$), integer quantities, finite positive prices, completed-bar timing ($earliest\_entry > decision\_timestamp$), and statutory Indian cost computation server-side.
  - Payment processing clauses are `NOT APPLICABLE (V1)`.
  - Tested in `test_schemas_trade_policy.py` and `test_schemas_adversarial.py`.
  - **Status: IMPLEMENTED for Layer 3 validation contracts; L5–L7 engine integration pending.**

---

## 7. Data, Model, and Trading Limitations

- **Simulation Only**: Operational accounts are simulated with ₹30,000 initial scenario capital.
- **Long-Only Cash Equity**: Whole-share integer quantities only; short selling, margin borrowing, and derivatives are prohibited by schema invariants.
- **5-Minute Completed Bar Restriction**: Research strategy decisions act exclusively on completed 5-minute bars during regular NSE session hours (09:15–15:30 IST, Mon–Fri).
- **No Live Trading / Payment**: Live broker execution and payment processing are out of scope for V1.

---

## 8. Acceptance Status

**PASS**

All Layer 3 acceptance criteria, typed schemas, validation contracts, state machine transitions, ownership boundaries, and adversarial negative tests are fully passing and verified.
