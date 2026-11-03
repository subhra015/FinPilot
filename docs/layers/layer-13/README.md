# FinPilot AI — Layer 13 Report: Frontend Application & Client-Side Security

Status: **PASS**  
Completed: 2026-11-04  
Gate: `ACCEPTANCE_GATES.md` Layer 13 Gate  
Owning Packages: `frontend/src/` (React 19, TypeScript 5.7, Vite 6, Vitest 5)  
Primary Security Controls: `SEC-02`, `SEC-06`, `SEC-07`, `SEC-09`, `SEC-13`, `SEC-14`, `SEC-15`, `SEC-16`, `SEC-19`  

---

## 1. Executive Summary & Scope Boundary

Layer 13 delivers the operator and quantitative research dashboard interface for FinPilot AI. Built with React 19, TypeScript, and Vite, the frontend communicates with the authenticated Layer 12 backend APIs while maintaining strict client-side security boundaries:

- **Eight Mandatory Views**:
  1. **Research Status View**: Specification boundaries, research questions, globally chronological partitions (`TRAIN`, `DEVELOPMENT`, `CALIBRATION`, `THRESHOLD_SELECTION`, `LOCKED_FINAL_TEST`), 1-session boundary embargo, approved model candidates (`MODEL-LOGREG-V1`, `MODEL-LIGHTGBM-V1`), and the benchmark evaluation hurdle band of ₹300–₹1,500 on standard ₹30,000 scenario capital.
  2. **Stock Scanner View**: Point-in-time universe explorer with strictly causal 5-minute candle aggregation, causal relative volume (RVOL) computed against comparable historical time-of-day intervals (zero peeking into full-day volume), RSI-14, ATR-14, 20-EMA distance, and session geometry.
  3. **Trade Proposal View**: Signal timestamp vs next-bar execution timestamp separation ($t_{\text{fill}} \ge t_{\text{signal}} + 5\text{m}$), integer share sizing ($Q \ge 1$), statutory Indian equity intraday transaction fee schedule breakdown (Brokerage, STT, Exchange turnover, SEBI turnover, Stamp duty, GST), selective decision states, and calibrated probabilities.
  4. **Risk Console View**: Independent risk engine interface featuring all 11 deny-by-default rules, emergency kill switch toggle, manual trading pause, limits configuration, and signed administrative audit log stream.
  5. **Paper Portfolio View**: Server-authoritative ₹30,000 capital accounting, available cash, reserved margins, active positions table, orderly square-off, and emergency exit triggers.
  6. **Prediction Ledger View**: Append-only event log with SHA-256 hash chaining display ($H_n = \text{SHA256}(H_{n-1} \parallel \dots)$), explicit `CORRECTION` records, and deterministic replay verification trigger.
  7. **Evaluation Report View**: Comparative multi-baseline report (`REF-NOTRADE-V1`, `STRAT-SIMPLE-V1`, `MODEL-LOGREG-V1`, `MODEL-LIGHTGBM-V1`), net economics, profit factors, drawdowns, and Murphy Brier score decomposition (Reliability, Resolution, Uncertainty).
  8. **Data Health Screen**: 8-point data pipeline audit checklist, dataset licensing terms and permitted research use cases, and bar quarantine log.
- **Three Distinct Execution Modes**:
  - `HISTORICAL REPLAY` (Cyan badge/banner): Historical causal backtest simulation.
  - `FORWARD PAPER` (Amber badge/banner): Forward-looking paper simulation under ₹30,000 scenario capital.
  - `SYNTHETIC DEMO` (Purple badge/banner): Isolated synthetic fixtures prohibited from market evidence reporting.
- **Strict Client-Side Security**:
  - Zero secrets, private keys, or API tokens in client bundles, source maps, or environment variables (`SEC-02`).
  - Safe text rendering with zero `dangerouslySetInnerHTML` across all source files (`SEC-07`).
  - Opaque sessions managed strictly via `HttpOnly`, `SameSite=Lax` cookies; zero tokens stored in `window.localStorage` or `window.sessionStorage` (`SEC-15`).
  - Automatic `X-CSRF-Token` header injection on mutating requests from client-readable cookie (`SEC-16`).
  - Role-based UI controls (`SEC-09`): Non-admin users are restricted to read-only monitoring; admin mutations are authoritatively verified server-side.
  - Non-authoritative client economics (`SEC-19`): Client calculations serve exclusively as UX guidance; ledger and backend risk engine remain authoritative.

> [!NOTE]
> **Strict Layer Boundary**: Layer 13 implements the Frontend Application and Client-Side Security ONLY. It does not implement automated forward feed ingestion loops (Layer 14) or live broker connections.

---

## 2. Directory Structure & Key Files

```
frontend/
├── package.json                   # React 19, TypeScript 5.7, Vite 6, Vitest 5.0.5
├── tsconfig.json                  # Strict TypeScript configuration
├── vite.config.ts                 # Secure Vite configuration with proxy
├── src/
│   ├── api/
│   │   ├── client.ts              # Fetch wrapper with CSRF injection, path sanitization, 401 callback
│   │   ├── auth.ts                # Login, register, MFA, logout API service callers
│   │   ├── types.ts               # Complete TypeScript interfaces for models, risk, ledger, portfolio
│   │   └── services.ts            # Typed view service callers and resilient fallback state
│   ├── components/
│   │   ├── Header.tsx             # Brand, mode selector, user profile, auth buttons
│   │   ├── ModeBanner.tsx         # Persistent full-width warning banner for active mode
│   │   ├── Navigation.tsx         # 8 primary navigation tabs with RBAC pills
│   │   ├── LoginModal.tsx         # NIST SP 800-63B-4 login, registration, and TOTP MFA modal
│   │   └── SessionExpiredModal.tsx# Accessible 401 session expiration re-login dialog
│   ├── context/
│   │   ├── AuthContext.tsx        # Authentication & RBAC state management
│   │   └── ModeContext.tsx        # Execution mode state management
│   ├── views/
│   │   ├── ResearchStatusView.tsx # Partitions, embargo, hypothesis, hurdle band
│   │   ├── StockScannerView.tsx   # PIT universe, causal volume, session geometry
│   │   ├── TradeProposalView.tsx  # Next-bar fill, integer Q>=1, statutory fee schedule
│   │   ├── RiskConsoleView.tsx    # 11 safety rules, kill switch, pause, signed audit log
│   │   ├── PaperPortfolioView.tsx # Authoritative ₹30k capital, positions, square-off
│   │   ├── PredictionLedgerView.tsx# Append-only SHA-256 hash chaining & replay verification
│   │   ├── EvaluationReportView.tsx# Baselines, Murphy Brier decomposition, hurdle disclaimer
│   │   └── DataHealthView.tsx     # 8-point audit checklist, licenses, quarantine log
│   ├── styles/
│   │   └── app.css                # Professional dark-mode financial terminal theme
│   ├── test/
│   │   ├── setup.ts               # Jest-dom Vitest setup
│   │   ├── Security.test.tsx      # XSS payload, zero dangerouslySetInnerHTML, zero localStorage
│   │   ├── AuthFlow.test.tsx      # NIST password policy, 401 session expiration, RBAC restrictions
│   │   └── Views.test.tsx         # All 8 views, mode switching, proposal validation, fee calculation
│   ├── App.tsx                    # Main layout coordinator
│   └── main.tsx                   # React root entrypoint
```

---

## 3. Verification & Empirical Test Results

### 3.1 TypeScript Type Checking (`tsc --noEmit`)
```
> finpilot-frontend@0.1.0 typecheck
> tsc --noEmit
Exit code: 0 (Zero type errors)
```

### 3.2 ESLint Verification (`eslint .`)
```
> finpilot-frontend@0.1.0 lint
> eslint .
Exit code: 0 (Zero errors, zero warnings)
```

### 3.3 Vitest Test Suite (`vitest run`)
```
 RUN  v5.0.5 D:/Projects/FinPilot/frontend

 ✓ src/config/env.test.ts (4 tests) 12ms
 ✓ src/App.test.tsx (1 test) 208ms
 ✓ src/test/AuthFlow.test.tsx (3 tests) 271ms
 ✓ src/test/Security.test.tsx (5 tests) 185ms
 ✓ src/test/Views.test.tsx (8 tests) 505ms

 Test Files  5 passed (5)
      Tests  21 passed (21)
   Duration  3.72s
```

### 3.4 Production Vite Build (`vite build`)
```
✓ 48 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                   0.41 kB │ gzip:  0.28 kB
dist/assets/index-BcwJ5HyL.css   12.41 kB │ gzip:  3.00 kB
dist/assets/index-R4ReKTi7.js   297.35 kB │ gzip: 88.92 kB
✓ built in 1.66s
```

### 3.5 Bundle Secret Leakage Audit (`SEC-02`)
- Automated regex audit of `dist/assets/*.js` confirmed:
  - Zero private keys (`BEGIN PRIVATE KEY`, `RSA PRIVATE KEY`)
  - Zero cloud/API credentials (`sk_live`, `AKIA`)
  - Zero hardcoded plaintext passwords or session tokens

---

## 4. Acceptance Gate Checklist

| Requirement | Implementation Verification | Status |
| :--- | :--- | :--- |
| **8 Required Views** | Research Status, Stock Scanner, Trade Proposal, Risk Console, Paper Portfolio, Prediction Ledger, Evaluation Report, Data Health all implemented | **PASS** |
| **Mode Isolation** | `HISTORICAL REPLAY`, `FORWARD PAPER`, `SYNTHETIC DEMO` prominently badged with warning banners | **PASS** |
| **SEC-02: Zero Client Secrets** | Checked Vite bundle and client storage; zero secrets or tokens present | **PASS** |
| **SEC-06: Authoritative Server** | Client validation guides UX; backend remains 100% authoritative | **PASS** |
| **SEC-07: Safe Text Rendering** | Zero `dangerouslySetInnerHTML`; XSS injection payloads safely escaped | **PASS** |
| **SEC-09: RBAC Enforcement** | Risk console switches disabled for non-admin users with clear UX feedback | **PASS** |
| **SEC-15: Cookie Session Contract** | Opaque `HttpOnly` sessions; 401 triggers session expiration modal safely | **PASS** |
| **SEC-16: CSRF Header Protection** | Mutating requests attach `X-CSRF-Token` from cookie | **PASS** |
| **SEC-19: Non-authoritative Client** | Balances, P&L, fees, and execution states derived from immutable server ledger | **PASS** |
| **Test Coverage** | 21 Vitest unit and integration tests passing cleanly | **PASS** |
