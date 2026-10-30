# FinPilot AI — Data-Rights Matrix

Status: **Layer 0 initial version**. **No dataset is approved.** Every candidate
source below is `NOT VERIFIED / OPEN` until its actual source, license/terms and
intended use are independently verified and recorded here with a citation.

Related: `DATA_AND_PERFORMANCE_POLICY.md` §4, `PROJECT_SPEC.md` (OD-01),
`SECURITY.md`.

---

## 1. Rule

A dataset may be used for a given purpose **only** if that cell is marked
`PERMITTED` with the verified basis (license/terms reference + verifier + date).
Until then the cell is `OPEN` and any layer depending on it is `BLOCKED`. No
redistribution or public display is assumed.

## 2. Use cases

1. **Private research** — internal analysis on controlled infrastructure.
2. **Hosted notebook processing** — processing on third-party notebook runtimes.
3. **Model training** — training/deriving model artifacts.
4. **Forward paper simulation** — runtime consumption for simulated decisions.
5. **Public display** — showing data or derived values to the public.
6. **Redistribution** — sharing raw or derived data with third parties.
7. **Derived outputs** — publishing derived metrics/models.

## 3. Candidate sources (all unverified)

| Source | Actual provider/license | 1 Research | 2 Notebook | 3 Training | 4 Forward | 5 Public | 6 Redistribute | 7 Derived | Status |
|---|---|---|---|---|---|---|---|---|---|
| NSE official bhavcopy / files | `OPEN` — verify NSE terms of use | OPEN | OPEN | OPEN | OPEN | OPEN | OPEN | OPEN | NOT VERIFIED |
| Broker API (e.g. Zerodha Kite / Upstox / Angel One) | `OPEN` — verify broker+exchange terms | OPEN | OPEN | OPEN | OPEN | OPEN | OPEN | OPEN | NOT VERIFIED |
| Commercial vendor (e.g. TrueData / GDFL / others) | `OPEN` — verify vendor license | OPEN | OPEN | OPEN | OPEN | OPEN | OPEN | OPEN | NOT VERIFIED |
| Free aggregator (e.g. Yahoo Finance) | `OPEN` — verify aggregator+underlying terms | OPEN | OPEN | OPEN | OPEN | OPEN | OPEN | OPEN | NOT VERIFIED |
| `SYNTHETIC DEMO` (generated) | project-generated, self-owned | OPEN* | OPEN* | OPEN* | OPEN* | OPEN* | OPEN* | OPEN* | SELF-GENERATED; label required |

\* Synthetic data is self-generated and may be used for plumbing/demo, but must
always be labelled `SYNTHETIC DEMO` and never presented as market evidence
(`DATA_AND_PERFORMANCE_POLICY.md` §3).

## 4. Verification checklist (per source)

For each source, record before any `PERMITTED` marking:

- [ ] Actual provider/legal owner identified.
- [ ] Applicable license/terms document captured (URL + retrieval date).
- [ ] Intended-use clauses checked against use cases 1–7.
- [ ] Redistribution/public-display clauses checked specifically.
- [ ] Derived-output / model-training clauses checked specifically.
- [ ] Hosted-notebook processing clause checked (OD-06).
- [ ] Verifier name and date recorded.
- [ ] Any restrictions or attribution requirements noted.

## 5. Consequences

- `OD-01` remains `OPEN`; data-dependent layers (2, 9, 18) are `BLOCKED` on the
  relevant cells until verification.
- No market data or derived output is published, redistributed or exposed until
  the corresponding cell is `PERMITTED`.
