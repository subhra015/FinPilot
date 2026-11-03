# FinPilot AI — Layer 11 Report: Independent Risk Engine & Authorization Contract

Status: **PASS**  
Completed: 2026-11-03  
Gate: `ACCEPTANCE_GATES.md` Layer 11 Gate  
Owning Package: `backend/src/finpilot/risk/`  
Primary Security Controls: `SEC-01`, `SEC-06`, `SEC-08`, `SEC-09`, `SEC-19`  

---

## 1. Executive Summary & Scope Boundary

Layer 11 delivers the **Independent Risk Engine** for FinPilot AI.

In accordance with strict project governance, security, and research contracts:
- **Complete Independent Authority (`SEC-19`)**: The risk engine operates as an autonomous gatekeeper. Machine learning models and selective decision engines can propose candidate trades (`SelectiveDecision`), but **cannot authorize them** or bypass any risk rule.
- **Simulator Enforcement (`SEC-19`)**: The execution simulator and portfolio manager reject any order without a valid, cryptographically verified `RiskAuthorization` token matching the exact proposal ID, model ID, and policy version (`OrderRejectionReason.UNAUTHORIZED`).
- **11 Deny-by-Default Controls**: Evaluates market data freshness, OHLC geometry, trading hours, session entry cutoff (15:00 IST), duplicate orders, unresolved position state, concurrent positions cap (1 position baseline), daily loss limits (₹1,500), drawdown suspension (10%), cash affordability, planned stop risk (2% cap = ₹600 on ₹30k), and per-position / total exposure limits.
- **Entry vs. Exit Asymmetry**: Distinguishes opening new positions from closing existing positions. Exits are permitted past the 15:00 IST entry cutoff (forced square-off at 15:15 IST) and with zero cash. However, an exit is **never assumed to fill** if market data is absent, invalid, or zero-volume (`MARKET_DATA_INVALID`).
- **Conservative Static Caps**: Strictly long-only equity, integer shares ($Q \ge 1$), no Kelly sizing, no dynamic leverage, and no speculative margin.
- **Administrative RBAC & Signed Audit Trail (`SEC-01`, `SEC-08`, `SEC-09`)**: Protected from regular users; only authorized administrators (`is_admin=True`) can update configuration or trigger the kill switch. Every mutation creates an immutable, SHA-256 signed `RiskConfigAuditEvent`.
- **Deterministic Bit-Identical Replay**: Evaluation decisions and authorization tokens computed with fixed timestamps reproduce bit-identical decisions and cryptographic signatures across independent runs.

> [!NOTE]
> **Strict Layer Boundary**: Layer 11 implements the Independent Risk Engine and Authorization Contract ONLY. It does not scaffold live broker adapters, margin borrowing, short selling, or derivatives.

---

## 2. Implementation Architecture & Module Overview

```
backend/src/finpilot/risk/
├── __init__.py           # Clean package exports
├── models.py             # Pydantic V2 frozen schemas (RiskConfig, RiskAuthorization, AuditEvent, etc.)
├── evaluator.py          # Core RiskEvaluator implementing 11 deny-by-default checks
├── config_service.py     # Administrative RiskConfigService enforcing RBAC & audit logging
└── service.py            # High-level RiskService coordinator & decision ledger
```

### Module Responsibilities:
1. `models.py`: Defines frozen schemas: `RiskDecisionStatus`, `RiskRejectionReason` (25 machine-readable codes), `RiskAuthorization` (SHA-256 sealed token), `RiskConfig` (static conservative caps), `RiskConfigAuditEvent` (signed audit event), `RiskMetricsSnapshot`, and `PositionCloseIntent`.
2. `evaluator.py`: Implements `RiskEvaluator`. Evaluates new long-only entries against all 11 controls, computes required cash with slippage buffers, planned stop loss risk, and issues signed `RiskAuthorization`. Evaluates position close intents with fail-closed market data checks.
3. `config_service.py`: Implements `RiskConfigService`. Manages active `RiskConfig` lifecycle, enforces `UserScope.is_admin`, rejects unauthorized or out-of-bound changes, and appends signed audit events.
4. `service.py`: High-level service facade providing unified evaluation, config management, and in-memory decision ledger replay.
5. `backend/src/finpilot/execution/portfolio.py`: Updated `PortfolioManager` with optional `enforce_risk_authorization: bool = True`. Rejects unauthorized, tampered, or mismatched proposals with `OrderRejectionReason.UNAUTHORIZED`.

---

## 3. The 11 Deny-by-Default Controls Specification & Empirical Results

All 11 independent controls were evaluated via `scripts/evaluate_risk_engine.py` and unit tests:

| Control # | Control Name | Bound / Constraint | Observed Status | Machine-Readable Rejection Reason |
|---|---|---|---|---|
| **1** | Emergency Kill Switch | Disables all entries globally | `REJECTED` | `KILL_SWITCH_ACTIVE` |
| **2** | Manual Trading Pause | Admin-mandated pause | `REJECTED` | `MANUAL_TRADING_PAUSED` |
| **3** | Governance Allowlist | NSE approved universe only | `REJECTED` | `UNSUPPORTED_INSTRUMENT` |
| **4** | Version Matching | Policy `TP-V1`, approved model IDs | `REJECTED` | `MODEL_VERSION_MISMATCH` |
| **5** | Data Freshness | Candle exists, staleness $\le 300\text{s}$ | `REJECTED` | `DATA_STALE_OR_MISSING` |
| **6** | OHLC Bar Integrity | $H \ge \max(O,C,L)$, $L \le \min(O,C,H)$, $V > 0$ | `REJECTED` | `MARKET_DATA_INVALID` |
| **7** | Session & Cutoff | 09:15–15:30 IST; Entries blocked after **15:00 IST** | `REJECTED` | `SESSION_ENTRY_CUTOFF` |
| **8** | Order / Position Hygiene | No duplicate orders; no unresolved positions | `REJECTED` | `UNRESOLVED_POSITION_STATE` |
| **9** | Concurrent Positions Cap | Maximum 1 position active (baseline) | `REJECTED` | `MAX_CONCURRENT_POSITIONS_EXCEEDED` |
| **10** | Circuit Breakers | Realized loss $\ge ₹1,500$ or Drawdown $\ge 10\%$ | `CIRCUIT_BROKEN` | `DAILY_LOSS_LIMIT_EXCEEDED` |
| **11** | Cash Affordability | Capital $\le$ Available Cash (incl. 10 bps buffer) | `REJECTED` | `INSUFFICIENT_AVAILABLE_CASH` |
| **12** | Planned Stop Risk Cap | Stop risk $\le 2.0\%$ of equity ($₹600$ on $₹30\text{k}$) | `REJECTED` | `EXCESSIVE_STOP_RISK` |
| **13** | Exposure Caps | Position $\le 50.0\%$ ($₹15\text{k}$), Total $\le 100\%$ | `REJECTED` | `POSITION_EXPOSURE_CAP_EXCEEDED` |

---

## 4. Model Confidence Invariance & Authorization Contract

### 4.1 Invariant: Model High Confidence Cannot Override Risk (`SEC-06`, `SEC-19`)
In adversarial testing (`test_risk_model_cannot_bypass.py` and `evaluate_risk_engine.py`):
- A proposal generated alongside a `SelectiveDecision` with $P = 0.9990$ (`ACCEPTED_CANDIDATE`) was submitted with insufficient available cash (₹1,000 available vs. ₹12,500 required).
- `RiskEvaluator` rejected the proposal with `RiskRejectionReason.INSUFFICIENT_AVAILABLE_CASH`.
- **Verdict**: Model probabilities have zero authority over capital, risk, or execution bounds.

### 4.2 Simulator Verification of Signed Authorizations (`SEC-19`)
The simulator (`PortfolioManager(enforce_risk_authorization=True)`) strictly verifies tokens:
1. **Un-authorized proposal**: Rejection logged to portfolio ledger as `PROPOSAL_REJECTED_UNAUTHORIZED` (`OrderRejectionReason.UNAUTHORIZED`).
2. **Mismatched proposal ID**: Rejection logged as `UNAUTHORIZED`.
3. **Tampered authorization**: Altering `authorized_quantity` from 5 to 500 invalidates the cryptographic SHA-256 seal; rejected as `UNAUTHORIZED`.
4. **Authentic authorization**: Accepted, order state transitions to `PENDING`, and `risk_authorization_id` is linked to the `ExecutionOrder`.

---

## 5. Entry vs. Exit Asymmetry (Forced Square-Off Evaluation)

The risk engine rigorously distinguishes entries from exits:
1. **Past Cutoff Square-Off (15:15 IST)**:
   - Entry proposal at 15:15 IST: **REJECTED** (`SESSION_ENTRY_CUTOFF`).
   - Position exit intent at 15:15 IST: **AUTHORIZED** (`OrderSide.SELL`).
2. **Zero Cash Liquidity**:
   - Entry proposal with ₹0.00 cash: **REJECTED** (`INSUFFICIENT_AVAILABLE_CASH`).
   - Exit intent with ₹0.00 cash: **AUTHORIZED** (releases capital).
3. **Fail-Closed on Missing / Halted Market Data**:
   - Exit intent with `candle=None`: **REJECTED** (`DATA_STALE_OR_MISSING`).
   - Exit intent with `volume=0` (market halt): **REJECTED** (`MARKET_DATA_INVALID`).
   - **Guaranteed Invariant**: The engine never fabricates an exit fill when market liquidity is absent.

---

## 6. Administrative RBAC & Audit Hash Trail Verification (`SEC-01`, `SEC-08`, `SEC-09`)

All risk settings mutations are gated by `RiskConfigService`:
1. **Non-Admin Rejection**:
   - `UserScope(user_id="USER-TRADER-001", is_admin=False)` calling `set_kill_switch()` or `update_config()` raises `PermissionDeniedError`.
2. **Admin Mutation & Signed Audit Trail**:
   - `UserScope(user_id="USER-RISK-ADMIN", is_admin=True)` updating limits generates a signed `RiskConfigAuditEvent`.
   - Captures previous config hash, new config hash, changed fields, timestamp, and SHA-256 seal.
   - `verify_signature()` confirms the audit event is untampered.

---

## 7. Verification & Test Evidence

### 7.1 Focused Layer 11 Tests (33 passed in 6.15s)
- `backend/tests/test_risk_evaluator_controls.py` (14 tests):
  - Unit tests covering all 11 deny-by-default controls, circuit breakers, session geometry, and signed authorization issuance.
- `backend/tests/test_risk_model_cannot_bypass.py` (6 tests):
  - Adversarial tests proving $P = 0.999$ model cannot override cash limits or kill switch; simulator rejects un-authorized, mismatched, or tampered tokens.
- `backend/tests/test_risk_security_rbac_audit.py` (6 tests):
  - RBAC authorization tests; non-admin rejection; admin audit event generation and cryptographic signature verification.
- `backend/tests/test_risk_entry_vs_exit_distinction.py` (7 tests):
  - Exit authorization after 15:00 IST cutoff; zero-cash exit allowance; fail-closed rejection on missing candle or zero volume; deterministic replay producing bit-identical decisions and signatures.

### 7.2 Full Regression Test Suite
- **303 passed, 5 deselected in 16.54s** (`python -m pytest backend/tests -k "not test_app_security" -q`).

### 7.3 CLI Evaluation Runner
- `python scripts/evaluate_risk_engine.py`:
  - Exercised all 11 controls, verified model confidence invariance, confirmed simulator authorization rejection, verified forced exits, and tested admin audit hash chaining.
  - Report saved to `artifacts/risk/risk_engine_report.json`.

### 7.4 Static & Type Analysis
- `python -m ruff check backend`: **0 errors** (all checks passed).
- `python -m ruff check scripts/evaluate_risk_engine.py`: **0 errors**.
- `python -m mypy backend/src`: **0 errors** in 73 source files.

---

## 8. Security Controls Touchpoint

| Control | Status | Layer 11 Implementation & Verification |
|---|---|---|
| `SEC-01` | **IMPLEMENTED** | Risk configuration mutations strictly require administrative user scope (`UserScope(is_admin=True)`). Unauthorized requests fail closed with `PermissionDeniedError` (`test_risk_security_rbac_audit.py`). |
| `SEC-06` | **IMPLEMENTED** | Typed Pydantic V2 models (`RiskConfig`, `RiskAuthorization`, `PositionCloseIntent`, `RiskEvaluationResult`, `RiskConfigAuditEvent`) enforce bounds, positive equity, integer quantities, and fail-closed validation (`test_risk_evaluator_controls.py`, `test_risk_security_rbac_audit.py`). |
| `SEC-08` | **IMPLEMENTED** | All administrative changes produce immutable `RiskConfigAuditEvent` records capturing admin ID, timestamp, diffs, previous/new SHA-256 config hashes, and cryptographic signatures (`test_risk_security_rbac_audit.py`). |
| `SEC-09` | **IMPLEMENTED** | Admin-only role checks on `update_config`, `set_kill_switch`, and `set_manual_pause`. Deny-by-default for non-admin roles (`test_risk_security_rbac_audit.py`). |
| `SEC-19` | **IMPLEMENTED** | Server-authoritative independent risk checks. Model scores cannot authorize trades or bypass limits. Simulator rejects proposals lacking authentic `RiskAuthorization`. 11 deny-by-default controls, cash affordability, slippage buffers, daily loss limits (₹1,500), and drawdown limits (10%) strictly enforced (`test_risk_model_cannot_bypass.py`, `test_risk_evaluator_controls.py`, `test_risk_entry_vs_exit_distinction.py`). |

---

## 9. Gate Compliance & Human Approval Stop

| Acceptance Gate Check | Status | Verification Detail |
|---|---|---|
| **G-1 Scope** | **PASS** | Only Layer 11 implemented (no live brokers, no margin/leverage, no short selling). |
| **G-2 Focused Tests** | **PASS** | 33 tests passing in `backend/tests/test_risk_*.py`. |
| **G-3 Regression** | **PASS** | All 303 repo tests pass in 16.54s. |
| **G-4 Security** | **PASS** | `SEC-01`, `SEC-06`, `SEC-08`, `SEC-09`, `SEC-19` implemented and verified. |
| **G-5 Scans** | **PASS** | `ruff` (0 errors), `mypy` (0 errors in 73 files). |
| **G-6 Diff Hygiene** | **PASS** | No secrets, debug code, or extraneous generated files. |
| **G-7 Documentation** | **PASS** | `docs/layers/layer-11/README.md`, `docs/risk-engine-policy.md`, `ACCEPTANCE_GATES.md`, `SECURITY_CHECKLIST.md`, `docs/layers/README.md`, root `README.md`, and `scripts/check_docs.ps1` updated with exact commands and real outputs. |
| **G-8 No Fabrication** | **PASS** | Real execution outputs from test suite and evaluation runner. |

> [!IMPORTANT]
> **GATE STOP**: Layer 11 is complete and verified. In accordance with `ACCEPTANCE_GATES.md` §1, stopping here for human review and authorization before proceeding to Layer 12.
