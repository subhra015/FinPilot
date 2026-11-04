"""Dependence-aware statistical bootstrap inference (Layer 15).

Governed by:
- ACCEPTANCE_GATES.md §2 (Layer 15 Gate)
- DATA_AND_PERFORMANCE_POLICY.md §7 (Statistical Rigor)
- PROJECT_SPEC.md §4, §5, §7
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any

import numpy as np

from finpilot.evaluation.models import UncertaintyInterval


def session_block_bootstrap(
    trades_by_session: dict[date | str, Sequence[dict[str, Any]]],
    initial_capital: Decimal,
    b_replications: int = 1000,
    random_seed: int = 42,
) -> dict[str, UncertaintyInterval]:
    """Perform date-clustered / session-block bootstrap resampling.

    Preserves intra-day cross-stock correlation and volatility clustering by
    resampling entire trading sessions with replacement rather than assuming
    independent and identically distributed (i.i.d.) individual trades.

    Args:
        trades_by_session: Mapping from session date to list of trade dicts,
            where each trade dict contains 'net_pnl' (Decimal or float).
        initial_capital: Initial portfolio cash for computing percentage returns.
        b_replications: Number of bootstrap iterations (default 1000).
        random_seed: Random seed for deterministic reproducibility.

    Returns:
        dict[str, UncertaintyInterval]: 95% percentile confidence intervals for:
            - 'net_pnl'
            - 'net_return_pct'
            - 'expectancy'
            - 'win_rate_pct'
    """
    rng = np.random.default_rng(random_seed)
    session_dates = list(trades_by_session.keys())
    n_sessions = len(session_dates)

    # Calculate actual observed point estimates
    all_observed_trades: list[dict[str, Any]] = []
    for d in session_dates:
        all_observed_trades.extend(trades_by_session[d])

    total_observed_trades = len(all_observed_trades)
    obs_net_pnl = float(
        sum((Decimal(str(t["net_pnl"])) for t in all_observed_trades), Decimal("0.00"))
    )
    init_cap_float = float(initial_capital)
    obs_return_pct = (obs_net_pnl / init_cap_float * 100.0) if init_cap_float > 0 else 0.0
    obs_expectancy = (obs_net_pnl / total_observed_trades) if total_observed_trades > 0 else 0.0
    obs_wins = sum(1 for t in all_observed_trades if Decimal(str(t["net_pnl"])) > Decimal("0.00"))
    obs_win_rate_pct = (
        (obs_wins / total_observed_trades * 100.0) if total_observed_trades > 0 else 0.0
    )

    if n_sessions == 0 or total_observed_trades == 0:
        empty_ci = UncertaintyInterval(
            point_estimate=0.0,
            ci_lower_95=0.0,
            ci_upper_95=0.0,
            std_err=0.0,
            method="date_clustered_block_bootstrap_b1000",
        )
        return {
            "net_pnl": empty_ci,
            "net_return_pct": empty_ci,
            "expectancy": empty_ci,
            "win_rate_pct": empty_ci,
        }

    rep_net_pnl = np.zeros(b_replications)
    rep_net_return = np.zeros(b_replications)
    rep_expectancy = np.zeros(b_replications)
    rep_win_rate = np.zeros(b_replications)

    for b in range(b_replications):
        sampled_indices = rng.choice(n_sessions, size=n_sessions, replace=True)
        sampled_trades: list[dict[str, Any]] = []
        for idx in sampled_indices:
            s_date = session_dates[idx]
            sampled_trades.extend(trades_by_session[s_date])

        n_rep_trades = len(sampled_trades)
        if n_rep_trades == 0:
            rep_net_pnl[b] = 0.0
            rep_net_return[b] = 0.0
            rep_expectancy[b] = 0.0
            rep_win_rate[b] = 0.0
            continue

        b_pnl = float(sum((Decimal(str(t["net_pnl"])) for t in sampled_trades), Decimal("0.00")))
        b_ret = (b_pnl / init_cap_float * 100.0) if init_cap_float > 0 else 0.0
        b_exp = b_pnl / n_rep_trades
        b_wins = sum(1 for t in sampled_trades if Decimal(str(t["net_pnl"])) > Decimal("0.00"))
        b_wr = b_wins / n_rep_trades * 100.0

        rep_net_pnl[b] = b_pnl
        rep_net_return[b] = b_ret
        rep_expectancy[b] = b_exp
        rep_win_rate[b] = b_wr

    def _build_ci(point: float, dist: np.ndarray) -> UncertaintyInterval:
        ci_low = float(np.percentile(dist, 2.5))
        ci_high = float(np.percentile(dist, 97.5))
        std_err = float(np.std(dist, ddof=1)) if len(dist) > 1 else 0.0
        return UncertaintyInterval(
            point_estimate=round(point, 4),
            ci_lower_95=round(ci_low, 4),
            ci_upper_95=round(ci_high, 4),
            std_err=round(std_err, 4),
            method="date_clustered_block_bootstrap_b1000",
        )

    return {
        "net_pnl": _build_ci(obs_net_pnl, rep_net_pnl),
        "net_return_pct": _build_ci(obs_return_pct, rep_net_return),
        "expectancy": _build_ci(obs_expectancy, rep_expectancy),
        "win_rate_pct": _build_ci(obs_win_rate_pct, rep_win_rate),
    }
