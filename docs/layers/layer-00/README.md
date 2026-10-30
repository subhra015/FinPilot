# Layer 0 — Project Contract and Research Governance

Status: **PASS** (documentation only)
Date: 2026-10-31
Commit: git repository initialised this layer; no commit made (commits only on
explicit request)
Approver: _pending human approval_

---

## 1. Scope and objective

Establish the governing contracts for FinPilot AI before any implementation:

- Define the V1 boundary and the research question.
- Define one versioned trade-policy contract.
- Define separate software/research/economic verdicts and the evaluation band.
- Define data and performance policy, threat model, data-rights matrix and the
  full security-control plan.
- Ensure every later layer has a clear gate.

**Explicitly out of scope for Layer 0:** any application, trading or model code.

## 2. Initial repository findings

- `D:\Projects\FinPilot` was **empty** (no files, no git repository).
- No master specification (`FinPilot_AI_Master_Spec_v2.md`) or prior governance
  documents existed anywhere under the workspace.
- Therefore all Layer 0 documents were **authored from the prompt contract**.
  There was no prior content to reconcile; no conflict existed. This is recorded
  as a finding rather than silently ignored: if a master spec is later supplied,
  it takes precedence (`PROJECT_RULES.md` §2) and may require reconciliation in a
  future layer.

## 3. Files added / modified / deleted

Added:
- `PROJECT_RULES.md`
- `PROJECT_SPEC.md`
- `ARCHITECTURE.md`
- `ACCEPTANCE_GATES.md`
- `DATA_AND_PERFORMANCE_POLICY.md`
- `SECURITY.md`
- `SECURITY_CHECKLIST.md`
- `README.md`
- `docs/trade-policy-contract-v1.md`
- `docs/threat-model.md`
- `docs/data-rights-matrix.md`
- `docs/experiment-register.md`
- `docs/security-decisions.md`
- `docs/exception-register.md`
- `docs/layers/README.md`
- `docs/layers/layer-00/README.md`
- `scripts/check_docs.ps1`

Modified: none (empty repository).
Deleted: none.

## 4. Design decisions recorded

- **V1 scope** fixed in `PROJECT_SPEC.md` §2 and repeated consistently in
  `ARCHITECTURE.md`, `README.md`, `PROJECT_RULES.md`.
- **Trade-policy contract** `TP-V1` in `docs/trade-policy-contract-v1.md`; all
  required fields present; evidence-dependent numerics marked `OPEN` and block
  dependent layers.
- **Research question and verdicts** in `PROJECT_SPEC.md` §4/§7; the
  ₹300–₹1,500 band stated as an evaluation band only.
- **Uncertainty method** (`OD-05`) and other evidence decisions left `OPEN`; no
  universal proof thresholds invented.
- **Threat model** covers all named surfaces; all `SEC-01`…`SEC-27` mapped to
  owner/layer/test plan in `SECURITY_CHECKLIST.md`.
- **Payments** marked `NOT APPLICABLE (V1)` with rationale and a future billing
  gate (`SECURITY.md` §3).
- **Data rights**: no dataset approved; all cells `OPEN`.
- **Layer roadmap** (0–18) with per-layer gates in `ACCEPTANCE_GATES.md`.

## 5. Commands executed and actual results

### 5.1 Repository inspection (before authoring)

```
PS> Get-ChildItem -Force D:\Projects\FinPilot        # -> no output (empty)
PS> Get-ChildItem -Force -Recurse D:\Projects\FinPilot  # -> no output
PS> Test-Path .git  -> False (before layer)
```

Result: repository confirmed empty; no prior specs to reconcile.

### 5.2 Git initialisation

```
PS> git init -q
PS> git status --short
exit: 0
```

### 5.3 Documentation consistency / link / SEC-coverage check

```
PS> powershell -ExecutionPolicy Bypass -File .\scripts\check_docs.ps1
== Required documents ==
  OK   PROJECT_RULES.md
  OK   PROJECT_SPEC.md
  OK   ARCHITECTURE.md
  OK   ACCEPTANCE_GATES.md
  OK   DATA_AND_PERFORMANCE_POLICY.md
  OK   SECURITY.md
  OK   SECURITY_CHECKLIST.md
  OK   README.md
  OK   docs/threat-model.md
  OK   docs/data-rights-matrix.md
  OK   docs/experiment-register.md
  OK   docs/security-decisions.md
  OK   docs/exception-register.md
  OK   docs/trade-policy-contract-v1.md
  OK   docs/layers/README.md
  OK   docs/layers/layer-00/README.md

== Relative markdown link check ==
  checked 1 relative link(s); 0 broken

== SEC-01..SEC-27 coverage in SECURITY_CHECKLIST.md ==
  OK   all 27 controls present

RESULT: PASS
```

Exit code: `0`

## 6. Tests: passed / failed / skipped / not run

- Application unit/integration tests: **not run** — no application code exists
  (correct for Layer 0).
- Documentation consistency check (`scripts/check_docs.ps1`): **PASS**
  (see §5.3).

## 7. Security controls checked

| ID | Relevance in Layer 0 | Evidence |
|---|---|---|
| SEC-26 | Initial threat model, attack-surface inventory, security decisions and exception register created | `docs/threat-model.md`, `docs/security-decisions.md`, `docs/exception-register.md` |
| SEC-27 | Verification plan defined; full verification scheduled for Layer 17 | `SECURITY_CHECKLIST.md` |
| SEC-01…SEC-25 | Mapped to owner/layer/test plan | `SECURITY_CHECKLIST.md` |

All 27 controls have an owner/layer/test plan. `SEC-17` (password reset) and
`SEC-18` (file import) and payment clauses of `SEC-19` are `NOT APPLICABLE (V1)`
with rationale.

## 8. Known limitations and assumptions

- No master spec was available; documents derive from the prompt contract.
- All numeric/evidence decisions are `OPEN` and block dependent layers.
- No code, therefore no runtime verification.
- Layer numbering is a plan and may be re-ordered by the approver.

## 9. Acceptance result

**PASS** — meets `ACCEPTANCE_GATES.md` §3 (L0-1…L0-10):

- All required documents exist and are consistent.
- V1 scope stated consistently.
- Exactly one versioned trade-policy contract with `OPEN` numerics.
- Research question, three verdicts and evaluation band defined; uncertainty
  method `OPEN`; no invented thresholds.
- Threat model covers all named surfaces.
- All 27 controls have owner/layer/test plan; payments `N/A` with future gate.
- Data-rights matrix covers all use cases; nothing approved.
- Document/link/consistency checks run and recorded.
- No application/trading/model code exists.
- Layer 0 + index + root README updated.
