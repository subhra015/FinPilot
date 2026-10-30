# FinPilot AI — Project Specification (V1)

Status: **Layer 0 contract (ratified)**
Related: `PROJECT_RULES.md`, `ARCHITECTURE.md`, `ACCEPTANCE_GATES.md`,
`DATA_AND_PERFORMANCE_POLICY.md`, `SECURITY.md`,
`docs/trade-policy-contract-v1.md`.

---

## 1. Product summary

FinPilot AI is a research and **paper-trading** platform for **NSE cash
equities**. It evaluates whether an ML selection layer, layered on a fixed and
versioned trade policy, produces better **net portfolio outcomes** than
comparators, under identical execution and cost assumptions, on data it has not
seen. It never places live orders and never processes payments in V1.

## 2. V1 scope (binding)

### 2.1 In scope

| Area | V1 rule |
|---|---|
| Market | India / NSE cash equities only |
| Direction | Long-only; no short selling |
| Leverage | None; no margin, no derivatives/F&O |
| Decision input | Completed **5-minute** candles only |
| Decision cadence | One decision opportunity per completed candle per instrument, subject to policy |
| Execution | **Simulated** fills only, against historical replay or forward paper data |
| Costs | Explicit, versioned fee/cost schedule (stub marked `OPEN`) |
| Risk | Independent risk authorization service is the **sole** authority to authorize an entry |
| Ledger | Every prediction and every resulting event is written to a persistent append-only ledger |
| Evaluation | Leakage-resistant; unseen data; uncertainty method chosen before final evaluation |
| Portfolio scenario | ₹30,000 simulated account |

### 2.2 Out of scope for V1 (must not be implemented)

Live broker order placement; payment processing/billing; derivatives, futures
and options; short selling; leverage/margin; personalized financial advice;
foreign/exchange markets; redistribution of licensed market data; real-money
account connectivity.

Foreign markets remain deferred until the Indian pipeline is validated and a
later ratified layer authorizes them.

## 3. Execution modes (must be visibly and structurally separated)

The API, data model and UI must never conflate these modes:

1. **HISTORICAL_REPLAY** — deterministic replay of stored historical data for
   research/backtest.
2. **FORWARD_PAPER** — forward simulation on newly arriving market data, no real
   orders.
3. **SYNTHETIC_DEMO** — clearly labelled `SYNTHETIC DEMO` artificial data for
   plumbing/demonstration; never reported as market evidence.

Every ledger record, prediction and evaluation artefact must carry its mode.

## 4. Research question

> **Does an ML selection layer improve net portfolio outcomes over (a) a
> no-trade reference and (b) one predeclared simple strategy, evaluated on unseen
> data under identical execution and cost assumptions?**

The ML layer's only job is **selection** (which authorized candidate, if any, to
take). It is not permitted to override risk authorization, fees, sizing rules or
the trade policy.

## 5. Comparators (predeclared)

1. **No-trade reference** — no simulated entries. Establishes that any claimed
   improvement is not simply market drift on the sample.
2. **Predeclared simple strategy** — exactly one simple, fixed, non-ML rule set,
   frozen and documented before evaluation. `OPEN`: the specific simple strategy
   definition is chosen in the layer that implements the policy engine, with
   evidence, and frozen before any evaluation run.

## 6. Trade-policy contract

V1 defines **one** versioned trade-policy contract in
`docs/trade-policy-contract-v1.md`. It must specify, at minimum:

- decision timestamp;
- earliest executable entry event;
- order type;
- entry expiry;
- stop;
- target;
- maximum holding period;
- session cutoff;
- re-entry rules;
- integer quantity/sizing convention;
- unfilled / partial-fill policy;
- fee-schedule version;
- unresolved-execution treatment.

Numeric values that require empirical or broker evidence (final indicator
thresholds, fee rates, slippage parameters) are marked `OPEN` in that document
and **block any dependent implementation** until resolved.

## 7. Verdicts (separate and non-interchangeable)

FinPilot reports three independent verdicts. A pass in one never implies a pass
in another.

| Verdict | Question | Evidence source |
|---|---|---|
| **Software validity** | Does the system build, run, validate inputs, enforce the policy, authorize via the risk service, record the ledger and reproduce deterministic replay? | Engineering test suites, security verification, deterministic replay hashes |
| **Research validity** | Was the evaluation methodologically sound (no leakage, predeclared comparators, unseen data, uncertainty method pre-selected, correct handling of multiple comparisons)? | Evaluation protocol, experiment register, leakage tests |
| **Economic evidence** | Is there credible evidence that net outcomes improve, within an uncertainty band? | Out-of-sample results with the pre-selected uncertainty method |

## 8. Economic evaluation band (evaluation scenario only)

The **₹300–₹1,500 monthly net result on a ₹30,000 account** is an **evaluation
band**. It is:

- **not** a training objective;
- **not** a forced model target;
- **not** a promise or forecast.

It is used only to frame the scale of interest when reporting out-of-sample
results and uncertainty. Results outside the band are reported honestly; the
project does not tune models toward the band.

## 9. Metrics and uncertainty method

### 9.1 Metric families to report

- **Returns**: net P&L (₹), net return on the ₹30,000 scenario, per-trade and
  portfolio-level.
- **Cost realism**: total fees, slippage and cost drag vs gross P&L.
- **Risk**: maximum drawdown, volatility of daily net returns, exposure/holding
  time, loss distribution tail.
- **Activity**: number of authorized entries, fill/partial-fill/unfilled counts,
  rejected-by-risk counts, time-in-market.
- **Selection quality**: precision/recall-style selection statistics where
  meaningful, calibrated against the comparators.
- **Robustness**: stability across time folds and instruments.

### 9.2 Uncertainty method — `OPEN`

The uncertainty method (e.g. block bootstrap, fold-level aggregation, or another
justified method) **must be selected and documented before the final evaluation
layer begins**. No universal numeric "proof threshold" is invented here. The
selected method, its assumptions and its reporting format are `OPEN` and owned by
the evaluation layer.

### 9.3 What is explicitly not claimed

No universal threshold defines "success". Statistical and economic significance
will be expressed with the pre-selected uncertainty method, not a fabricated
pass/fail number.

## 10. Risk authorization (non-negotiable)

The risk authorization service is the **only** component permitted to authorize a
simulated entry. Model output alone must never create an accepted trade. The
service is independent of the ML layer and independently testable. All sizes,
stops, targets, exposure and session rules are enforced server-side.

## 11. Ledger requirements

A persistent, append-only prediction/event ledger records, for every decision:
inputs references (candle ids, policy version), model version and score,
risk-authorization outcome, resulting simulated events (entry/exit/expiry/
partial fill), costs applied, and mode. The ledger is the audit trail for both
software and research validity.

## 12. Open decisions (block dependent layers)

| ID | Decision | Status | Blocks |
|---|---|---|---|
| OD-01 | Data provider(s) and license/terms verification | `OPEN` | Layers 2+ (data), 9/18 (evaluation), data-rights matrix |
| OD-02 | Final trade-policy numeric parameters (entry expiry, stop, target, holding, cutoff, re-entry) | `OPEN` (some) | Layers 4–6 (policy/execution/risk) |
| OD-03 | Fee schedule version and values | `OPEN` | Layer 5 (execution/cost) |
| OD-04 | Predeclared simple-strategy definition | `OPEN` | Layer 4, evaluation |
| OD-05 | Uncertainty method | `OPEN` | Final evaluation layer |
| OD-06 | Hosted-notebook processing policy and environment | `OPEN` | Data-rights matrix, SEC-02/18/24 enforcement |
| OD-07 | Evaluation windows / walk-forward scheme | `OPEN` | Evaluation layer |
| OD-08 | Hosting/deployment target and TLS/domain | `OPEN` | Deployment/security layers |

These are tracked and resolved in their owning layers, not silently here.

## 13. Acceptance for Layer 0

See `ACCEPTANCE_GATES.md` §Layer 0. Layer 0 is documentation-only; it must not
contain trading/model code.
