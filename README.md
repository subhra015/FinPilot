# FinPilot AI

An **India-first, long-only NSE cash-equity intraday research and paper-trading
platform**. FinPilot evaluates whether an ML *selection* layer improves **net
portfolio outcomes** over a no-trade reference and one predeclared simple
strategy, on unseen data, under identical execution and cost assumptions.

> **V1 boundary:** research/paper simulation only. No live-money orders, no
> derivatives, no short selling, no leverage, no personalized financial advice,
> no payment processing. Foreign markets are deferred until the Indian pipeline
> is validated. The ₹300–₹1,500 monthly result on ₹30,000 is an **evaluation
> band** — not a target and not a promise.

## Current status

**Layer 0 — Project contract & research governance — PASS (documentation only).**

There is **no application code, no trading code and no model code** in the
repository yet. Layer 0 establishes the governing documents, the V1 contract,
the trade-policy contract, the threat model, the data-rights matrix and the
security control plan. Implementation begins in Layer 1, which requires explicit
human approval.

## Repository contents (Layer 0)

| Path | Purpose |
|---|---|
| `PROJECT_RULES.md` | Governing rules, precedence, layer discipline, decision vocabulary |
| `PROJECT_SPEC.md` | V1 scope, research question, verdicts, metrics, open decisions |
| `ARCHITECTURE.md` | Intended component boundaries and trust model |
| `ACCEPTANCE_GATES.md` | Global + per-layer gates (Layer 0–18 roadmap) |
| `DATA_AND_PERFORMANCE_POLICY.md` | Data validation, modes, metrics, uncertainty |
| `docs/trade-policy-contract-v1.md` | The single versioned trade-policy contract (`TP-V1`) |
| `SECURITY.md` | Security policy and V1 security boundaries |
| `SECURITY_CHECKLIST.md` | `SEC-01`…`SEC-27` status/owner/layer/test plan |
| `docs/threat-model.md` | Assets, trust boundaries, attack surface |
| `docs/data-rights-matrix.md` | Data use-case rights (nothing approved yet) |
| `docs/experiment-register.md` | Experiment registration template |
| `docs/security-decisions.md`, `docs/exception-register.md` | Security governance |
| `docs/layers/README.md` | Layer index |
| `docs/layers/layer-00/README.md` | Layer 0 report |
| `scripts/check_docs.ps1` | Documentation consistency/link checker |

## Verification (Layer 0)

```powershell
# Documentation consistency + link + SEC coverage check
powershell -ExecutionPolicy Bypass -File .\scripts\check_docs.ps1
```

Expected: `RESULT: PASS` (exit code 0).

## Setup

No runtime setup is required for Layer 0 (documents only). Application setup
commands will be introduced in Layer 1.

## Roadmap

See `docs/layers/README.md` and `ACCEPTANCE_GATES.md` for the 18-layer roadmap
and each layer's gate.

## Honest capability claims

- **What works today:** none — only governance documentation exists.
- **What is planned:** a leakage-resistant research pipeline with an independent
  risk service, a versioned trade policy, realistic simulated costs and an
  append-only ledger.
- **What is never claimed:** guaranteed returns, the ₹300–₹1,500 band as a
  promise, or live-trading capability.
