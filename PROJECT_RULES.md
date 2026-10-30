# FinPilot AI — Project Rules

Status: **Layer 0 contract (ratified)**
Owner: Project maintainer (human approver)
Applies to: every layer from 0 onward

This document is the governing rulebook for FinPilot AI. It defines how work is
proposed, scoped, implemented, evidenced and approved. Where another document
conflicts with this one, this one is not silently overridden: the conflict must
be reported and the safest interpretation adopted, per the precedence rules
below.

---

## 1. Project in one paragraph

FinPilot AI is an **India-first, long-only NSE cash-equity intraday research and
paper-trading platform**. The first research strategy uses **completed 5-minute
candles**, a **fixed and versioned trade policy**, **realistic execution/cost
assumptions**, an **independent risk authorization service**, a **persistent
prediction/event ledger**, and **leakage-resistant historical evaluation**. The
first account simulation scenario is **₹30,000**. The ₹300–₹1,500 monthly
outcome range is an **evaluation scenario only** — never a forced model target
and never a promise. V1 performs **no live-money orders**, no derivatives, no
short selling, no leverage, no personalized financial advice and no payment
processing. Foreign markets are deferred until the Indian pipeline is validated.

## 2. Source-of-truth precedence

When documents disagree, apply this order and **report the conflict** in the
current layer's report:

1. A newer, explicitly ratified master specification (`FinPilot_AI_Master_Spec_v2.md` if present).
2. `PROJECT_RULES.md` (this file).
3. `PROJECT_SPEC.md`.
4. `ACCEPTANCE_GATES.md` and `DATA_AND_PERFORMANCE_POLICY.md`.
5. `ARCHITECTURE.md`.
6. `SECURITY.md` and `SECURITY_CHECKLIST.md`.
7. `docs/*` records (threat model, data-rights matrix, experiment register, security decisions, exception register).
8. Layer reports under `docs/layers/`.

A conflict is never resolved by silently choosing. The current layer must:
record the conflict, state the safest interpretation, and update the affected
documents as part of that layer's change set.

## 3. Layer discipline

- Implement **only** the layer explicitly requested. Do not start, scaffold or
  silently prepare future layers.
- A layer may fix a defect in an earlier layer **only** when it blocks the
  current layer or is security-critical. Such a fix must be recorded and its
  inclusion justified in the layer report.
- A layer is **PASS** only when every mandatory acceptance and security check for
  that layer passes and is evidenced. Otherwise it is **FAIL** or **BLOCKED**.
- After a layer report, **stop and wait for explicit human approval** before
  starting the next layer.
- Layers are defined and gated in `ACCEPTANCE_GATES.md`.

## 4. Decision status vocabulary

Every non-trivial unresolved decision in a document must carry one of these
explicit statuses:

- `OPEN` — a decision is required and evidence is not yet available. **OPEN
  decisions block implementation of any layer that depends on them.**
- `RESOLVED` — decided, with the deciding evidence or rationale cited.
- `BLOCKED` — cannot be resolved until an external dependency or open decision
  is cleared; the blocking item is named.
- `NOT APPLICABLE (V1)` — intentionally out of scope for V1, with rationale.

Inventing final values (indicator thresholds, fee rates, proof thresholds,
dataset approvals) to "unblock" progress is prohibited. Mark them `OPEN`.

## 5. Evidence and integrity rules

- Do not fabricate market data, performance numbers, terminal output, test
  results, security scans, or deployment status.
- Do not weaken, delete, skip, `xfail` or loosen tests to make them pass. If a
  test is wrong, explain the evidence and change it narrowly with a regression
  test.
- Do not hide errors with broad exception handlers or return fake successful
  responses.
- Do not add unnecessary packages or sophisticated ML models without a
  measurable, stated need.
- Synthetic data is permitted only when labelled **SYNTHETIC DEMO**, and its
  results are never reported as real-market evidence.

## 6. Scope and market boundaries (V1)

In scope: NSE cash equities, long-only, intraday, decisions on completed
5-minute candles, paper simulation only.

Out of scope for V1 (must not be implemented): live broker order placement,
derivatives/F&O, short selling, leverage/margin, personalized financial advice,
payment processing/billing, foreign/exchange markets, redistribution of licensed
market data.

## 7. Security as a cross-cutting requirement

Security is applied in **every** layer, not only the final one. The mandatory
controls are `SEC-01` … `SEC-27`, tracked in `SECURITY_CHECKLIST.md` with status,
evidence, owner/layer and any approved exception. Secure defaults and deny-by-
default apply. The FinPilot-specific security boundaries (untrusted market data,
non-authoritative frontend, sole-authority risk service, separated execution
modes, data rights) are binding in every layer.

## 8. Documentation obligations per layer

Every layer must create or update:

1. `docs/layers/layer-XX/README.md` — scope, design, files changed,
   implementation, exact commands, real outputs, security controls, known
   limitations, decisions, acceptance result.
2. `docs/layers/README.md` — the layer index (status, date, commit, report link).
3. Root `README.md` — honest current status and verification commands.
4. `SECURITY_CHECKLIST.md` — relevant controls updated with status/evidence.
5. Where relevant: `SECURITY.md`, `docs/threat-model.md`, `ARCHITECTURE.md`,
   `docs/data-rights-matrix.md`, `docs/security-decisions.md`,
   `docs/exception-register.md`.

Previous layer evidence is never overwritten; new dated/committed reports are
added and prior reports remain in Git history.

## 9. Definition of done (global)

A layer is done only when: scope matches the requested layer; acceptance
criteria in `ACCEPTANCE_GATES.md` pass; relevant security controls are
implemented and tested; focused tests for the layer pass; regression tests for
all prior layers pass; relevant static/security/dependency/secret scans pass or
are honestly reported; the diff is inspected for secrets, debug code and
generated files; and documentation is updated with exact commands and outputs.

## 10. Glossary

- **Decision candle** — a completed 5-minute NSE candle; the only input time
  granularity permitted for decisions.
- **Earliest executable entry event** — the first market event (typically the
  open of the next candle after the decision candle) at which a simulated entry
  may occur.
- **Trade policy** — the versioned contract of timestamps, order type, entry
  expiry, stop, target, holding period, session cutoff, re-entry, sizing,
  fill policy, fee schedule version and unresolved-execution treatment.
- **No-trade reference** — the baseline where no simulated entry is taken.
- **Predeclared simple strategy** — one simple, fixed, non-ML strategy declared
  before evaluation.
- **SYNTHETIC DEMO** — clearly labelled artificial data used only for
  demonstration/plumbing, never as market evidence.
- **Unseen data** — data not used in any selection, tuning or training step.
