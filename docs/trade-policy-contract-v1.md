# FinPilot AI — Trade Policy Contract v1

Status: **Layer 0 contract (ratified); numeric parameters partly `OPEN`**
Policy version: `TP-V1`
Related: `PROJECT_SPEC.md`, `DATA_AND_PERFORMANCE_POLICY.md`, `ARCHITECTURE.md`.

This is the **single initial versioned trade policy** for FinPilot AI V1. Every
simulated trade must be reproducible from (a) this contract version, (b) the
decision candle, and (c) the mode. Changing any field creates a **new policy
version**; versions are immutable once used in a recorded evaluation.

Legend: `OPEN` = requires evidence before the dependent layer may implement;
`schema-only` = the structural rule is fixed in V1 while its numeric value is `OPEN`.

---

## 1. Contract fields

| # | Field | V1 structural rule | Value | Status |
|---|---|---|---|---|
| 1 | `policy_version` | Immutable string id | `TP-V1` | RESOLVED |
| 2 | `instrument_universe` | NSE cash equity, long-only | `OPEN` (which symbols/filters) | OPEN |
| 3 | `decision_timestamp` | Timestamp of the **completed** 5-min candle used for the decision; decisions never use an incomplete candle | schema-only | RESOLVED (rule) |
| 4 | `earliest_executable_entry_event` | The **open of the next candle** strictly after the decision candle (its start time +1 bar) | schema-only | RESOLVED (rule) |
| 5 | `order_type` | Marketable simulated entry at the earliest executable event; no late-touch/limit-hunting beyond the fill policy in §2 | schema-only | OPEN (final choice pending evidence) |
| 6 | `entry_expiry` | If not filled by expiry, the opportunity is void; no chase | schema-only (`OPEN` bars) | OPEN |
| 7 | `stop` | Protective stop expressed in the price domain; must be ≥0 and below entry for longs | schema-only | OPEN |
| 8 | `target` | Profit target in the price domain; must be above entry for longs | schema-only | OPEN |
| 9 | `max_holding_period` | Maximum bars/time the simulated position may be held | schema-only | OPEN |
| 10 | `session_cutoff` | Hard time after which no entry may occur and open positions are flat by NSE close | schema-only | OPEN |
| 11 | `re_entry_rules` | Whether/when the same instrument may be re-entered after an exit | schema-only | OPEN |
| 12 | `sizing_convention` | **Integer** quantity only; no fractional shares; may be 0 (no trade) | schema-only | OPEN (risk %/max exposure) |
| 13 | `unfilled_partial_fill_policy` | Define fill, partial-fill and unfilled handling deterministically | schema-only | OPEN |
| 14 | `fee_schedule_version` | Named, versioned fee/cost schedule id | `OPEN` | OPEN |
| 15 | `unresolved_execution_treatment` | How to book positions whose exit cannot be resolved (e.g. data gap/halt) | schema-only | OPEN |
| 16 | `mode` | One of `HISTORICAL_REPLAY`, `FORWARD_PAPER`, `SYNTHETIC_DEMO` | required on every trade | RESOLVED |

## 2. Determinism and fill semantics (structural, binding)

- Decisions are made **only** on completed 5-minute candles.
- Entry may occur **only** at or after `earliest_executable_entry_event`; any
  signal that cannot be executed within the policy window is void.
- Quantity is an **integer**. Fractional quantities are rejected by the server.
- Fill/partial/unfilled outcomes must be deterministic functions of the replay
  data and the fill policy; no randomness is permitted in `HISTORICAL_REPLAY`.
- Costs are applied from the named `fee_schedule_version`; if the version is
  `OPEN`, execution must refuse to run in any evidence-producing mode.

## 3. Open numeric parameters

All `OPEN` values above must be resolved with cited evidence in the owning layer
before any dependent layer may run in a mode that produces evidence. Owning
layers:

- `instrument_universe` → data/universe layer.
- `entry_expiry`, `stop`, `target`, `max_holding_period`, `session_cutoff`,
  `re_entry_rules` → trade-policy engine layer.
- `sizing_convention` (risk fraction / max exposure) → risk layering; enforced by
  the risk service.
- `order_type`, `unfilled_partial_fill_policy`, `unresolved_execution_treatment`
  → execution/cost simulator layer.
- `fee_schedule_version` → execution/cost simulator layer.

## 4. Authority boundary

Model output selects among policy-authorized candidates **only**. It may not
alter this contract, sizing, stops, targets, session cutoff, fee schedule or the
risk service's decision. The risk service is the sole authority to authorize an
entry (`PROJECT_SPEC.md` §10).

## 5. Versioning rules

- `TP-V1` is frozen for the first evaluation campaign.
- Any parameter change ⇒ new version (`TP-V2`, …) with a changelog entry and a
  fresh experiment-register record. Results from different policy versions are
  never pooled without stating the version.
