# FinPilot AI — Data & Performance Policy

Status: **Layer 0 contract (ratified)**
Related: `PROJECT_SPEC.md`, `docs/trade-policy-contract-v1.md`,
`docs/data-rights-matrix.md`, `ACCEPTANCE_GATES.md`.

This policy governs how market data is treated and how performance is measured
and reported. It exists to prevent leakage, misrepresentation and fabricated
evidence.

---

## 1. Market data as untrusted input

Data from any provider is **untrusted** until validated. The validator must
check, at minimum:

| Check | Rule |
|---|---|
| Symbol | Known/allow-listed NSE symbol; case/format normalised |
| Exchange | NSE only in V1 |
| Series/segment | Cash-equity series only |
| Timestamp | Well-formed, monotonically increasing, aligned to 5-min boundaries, in the expected timezone (IST) |
| Session | Within NSE trading session; no out-of-session rows |
| Freshness | Within the freshness bound for the mode (`FORWARD_PAPER` stricter than replay) |
| OHLCV consistency | `low ≤ open,close ≤ high`; `volume ≥ 0`; no NaN/inf; duplicate timestamps rejected |
| Adjustment status | Known corporate-action/adjustment state recorded; unadjusted vs adjusted never mixed silently |
| Provenance | Source id, fetch time and raw reference recorded per record |

Any record failing validation is **quarantined and excluded**, not silently
coerced. Quarantine counts are surfaced in reports.

## 2. Decision granularity

Decisions use **completed 5-minute candles only**. Incomplete/last bars are never
used for decisions. Feature computation must be point-in-time correct: a feature
at time `t` may only use data available strictly before/at the decision candle's
completion in the manner the feature spec defines.

## 3. Data modes and separation

- `HISTORICAL_REPLAY` — stored, validated data only.
- `FORWARD_PAPER` — newly arriving validated data; no real orders.
- `SYNTHETIC_DEMO` — artificial, clearly labelled `SYNTHETIC DEMO`; never
  reported as market evidence; never pooled with real data.

Derived outputs inherit the mode of their inputs. Cross-mode mixing in any
evidence output is prohibited.

## 4. Data rights

No dataset may be used until its actual source, license/terms and intended use
are verified and recorded in `docs/data-rights-matrix.md`. Unverified sources are
`OPEN` and block dependent layers. Data is not published, redistributed or
exposed unless the source terms permit the intended use.

## 5. Performance metrics (definitions)

Reported per mode and policy version, never pooled across versions/modes without
stating so.

- **Net P&L (₹)** — sum of simulated trade P&L after all applied costs.
- **Net return** — net P&L ÷ ₹30,000 scenario notional (stated as scenario).
- **Cost drag** — total fees + modelled slippage ÷ gross P&L (and absolute ₹).
- **Maximum drawdown** — largest peak-to-trough decline of the equity curve.
- **Return volatility** — dispersion of daily net returns.
- **Exposure / time-in-market** — fraction of session in a position.
- **Tail loss** — distribution tail (e.g. worst per-trade/day losses) with the
  chosen statistic named.
- **Activity counts** — authorized entries, fills, partial fills, unfilled,
  risk-rejected, expiries.
- **Selection stats** — comparator-relative selection precision/recall where
  meaningful; explicitly defined at implementation time.

## 6. Uncertainty method — `OPEN`

The uncertainty method (e.g. block bootstrap over time, fold-level aggregation,
or another justified approach accounting for autocorrelation and multiple
comparisons) **must be chosen and documented before the final evaluation layer
runs**. No universal numeric "proof threshold" is defined. The band
₹300–₹1,500/month on ₹30,000 is an **evaluation band**, not a target, training
objective or promise.

## 7. Evaluation hygiene

- **Unseen data**: data used for selection/tuning/training is never used for the
  final evidence run.
- **Predeclared comparators**: no-trade reference and one predeclared simple
  strategy, frozen before evaluation.
- **Walk-forward / windows**: fold scheme is `OPEN`, chosen before evaluation,
  and applied consistently across comparators.
- **Multiple comparisons**: the number of candidate configurations is recorded
  and handled by the selected uncertainty method.
- **Leakage tests**: automated tests assert point-in-time correctness and mode
  isolation.
- **Reproducibility**: a run is reproducible from (code revision, data snapshot
  id, policy version, model version, seed, mode).

## 8. Cost assumptions

Costs (fees, taxes, slippage) come from a named, versioned fee schedule. Until
that schedule exists and is versioned, execution in any evidence-producing mode
must refuse to run. No performance number is reported without applied costs.

## 9. Reporting discipline

- Always state mode, policy version, data window, code revision and cost
  version.
- Never report synthetic results as market evidence.
- Never report a number that was not produced by an actual run; no placeholders
  presented as results.
