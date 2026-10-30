# FinPilot AI — Experiment Register

Status: **Layer 0 template**. One row per experiment campaign. This register is
the audit trail for the **research validity** verdict; no evaluation result is
banked unless registered here before running.

Related: `PROJECT_SPEC.md` §9, `DATA_AND_PERFORMANCE_POLICY.md` §7,
`docs/trade-policy-contract-v1.md`.

---

## 1. Registration rule

Every experiment is entered here **before** it runs, with predeclared hypothesis,
comparators, policy version, data window, metrics and uncertainty method. Running
an unregistered experiment that produces evidence is a policy violation.

## 2. Register

| ID | Date | Hypothesis | Policy ver. | Comparators | Data window / folds | Mode | Metrics | Uncertainty method | Code rev. | Cost ver. | Status | Result ref |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| _(none yet — template row)_ | | | | | | | | | | | | |

Status values: `PLANNED` · `RUNNING` · `DONE` · `ABANDONED` · `BLOCKED`.
Result ref points to the stored run artefact (not pasted numbers here).

## 3. Per-experiment fields (definitions)

- **ID** — stable identifier, e.g. `EXP-0001`.
- **Date** — registration date (ISO).
- **Hypothesis** — falsifiable statement, written before running.
- **Policy ver.** — e.g. `TP-V1`.
- **Comparators** — includes no-trade reference and the predeclared simple
  strategy (frozen definition id).
- **Data window / folds** — exact unseen-data window and walk-forward scheme.
- **Mode** — `HISTORICAL_REPLAY` / `FORWARD_PAPER` / `SYNTHETIC_DEMO`.
- **Metrics** — the families from `DATA_AND_PERFORMANCE_POLICY.md` §5 used.
- **Uncertainty method** — pre-selected (OD-05).
- **Code rev.** / **Cost ver.** — reproducibility anchors.
- **Status** / **Result ref** — lifecycle and stored artefact.

## 4. Prohibitions

- No post-hoc changing of hypothesis, comparators or uncertainty method after
  seeing results (a new experiment ID is required).
- No pooling across policy versions, modes or cost versions without stating so.
- No reporting of synthetic results as market evidence.
