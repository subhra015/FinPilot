"""Performance, risk, calibration, and accounting metric calculations (Layer 15).

Governed by:
- ACCEPTANCE_GATES.md §2 (Layer 15 Gate)
- DATA_AND_PERFORMANCE_POLICY.md §7, §8
- PROJECT_SPEC.md §4, §5, §7
"""

from __future__ import annotations

import math
from collections import defaultdict
from decimal import Decimal
from typing import Any

from finpilot.evaluation.models import BrierDecomposition
from finpilot.execution.fee_schedule import round_paisa


def compute_profit_factor(gains: Decimal, losses: Decimal) -> tuple[float, str]:
    """Calculate profit factor as Sum(Gains) / Abs(Sum(Losses)).

    Returns:
        tuple[float, str]: (profit_factor_value, formula_string)
    """
    formula = "Sum(Gains) / Abs(Sum(Losses))"
    abs_losses = abs(losses)
    if abs_losses > Decimal("0.00"):
        pf = float(gains / abs_losses)
        return round(pf, 4), formula
    if gains > Decimal("0.00"):
        return 999.99, formula
    return 1.0, formula


def compute_drawdown(equity_curve: list[Decimal]) -> tuple[Decimal, float]:
    """Calculate maximum drawdown amount and percentage from an equity curve.

    Returns:
        tuple[Decimal, float]: (max_drawdown_amount, max_drawdown_pct)
    """
    if not equity_curve:
        return Decimal("0.00"), 0.0

    peak = equity_curve[0]
    max_dd_amount = Decimal("0.00")
    max_dd_pct = 0.0

    for eq in equity_curve:
        if eq > peak:
            peak = eq
        dd = peak - eq
        if dd > max_dd_amount:
            max_dd_amount = dd
            if peak > Decimal("0.00"):
                max_dd_pct = float(dd / peak * Decimal("100.0"))

    return round_paisa(max_dd_amount), round(max_dd_pct, 2)


def compute_losing_streak_and_worst_day(
    daily_pnls: list[Decimal], trade_pnls: list[Decimal] | None = None
) -> tuple[int, Decimal]:
    """Calculate the longest consecutive losing trade streak and worst daily net P&L.

    Returns:
        tuple[int, Decimal]: (max_losing_streak, worst_day_pnl)
    """
    worst_day = min(daily_pnls) if daily_pnls else Decimal("0.00")
    if worst_day > Decimal("0.00"):
        worst_day = Decimal("0.00")

    trades = trade_pnls or []
    max_streak = 0
    current_streak = 0
    for pnl in trades:
        if pnl < Decimal("0.00"):
            current_streak += 1
            if current_streak > max_streak:
                max_streak = current_streak
        else:
            current_streak = 0

    return max_streak, round_paisa(worst_day)


def compute_monthly_returns(daily_records: list[tuple[str, Decimal, Decimal]]) -> dict[str, float]:
    """Compute percentage returns broken down by calendar month (YYYY-MM).

    Args:
        daily_records: list of (date_iso_str, starting_equity, ending_equity)
    """
    if not daily_records:
        return {}

    by_month: dict[str, list[tuple[Decimal, Decimal]]] = defaultdict(list)
    for dt_str, start_eq, end_eq in daily_records:
        month_key = dt_str[:7]  # YYYY-MM
        by_month[month_key].append((start_eq, end_eq))

    monthly_returns: dict[str, float] = {}
    for month, recs in by_month.items():
        if recs:
            month_start = recs[0][0]
            month_end = recs[-1][1]
            if month_start > Decimal("0.00"):
                ret = float((month_end - month_start) / month_start * Decimal("100.0"))
            else:
                ret = 0.0
            monthly_returns[month] = round(ret, 2)

    return monthly_returns


def compute_brier_decomposition(
    probabilities: list[float], outcomes: list[int], n_bins: int = 10
) -> BrierDecomposition:
    """Compute Murphy (1973) algebraic decomposition of Brier score.

    Mathematical formulation:
        Brier Score = (1/N) * sum_i (p_i - o_i)^2
        Brier Score = Reliability - Resolution + Uncertainty

    Where:
        Reliability = sum_k (n_k / N) * (p_bar_k - o_bar_k)^2
            (Pure calibration error across bins; lower is better, 0 is perfectly calibrated)
        Resolution = sum_k (n_k / N) * (o_bar_k - o_bar)^2
            (Discrimination ability; higher is better)
        Uncertainty = o_bar * (1 - o_bar)
            (Inherent outcome variance / base rate entropy)

    Also computes standard binary cross-entropy (Log Loss):
        LogLoss = -(1/N) * sum_i [o_i * ln(p_i) + (1 - o_i) * ln(1 - p_i)]
    """
    n = len(probabilities)
    if n == 0 or len(outcomes) != n:
        return BrierDecomposition(
            brier_score=0.0,
            reliability=0.0,
            resolution=0.0,
            uncertainty=0.0,
            log_loss=0.0,
            identity_holds=True,
        )

    # 1. Base rate o_bar
    total_positives = sum(outcomes)
    o_bar = total_positives / n

    # 2. Overall Brier Score
    brier = sum((p - o) ** 2 for p, o in zip(probabilities, outcomes, strict=True)) / n

    # 3. Bin partitioning
    bin_counts = [0] * n_bins
    bin_prob_sums = [0.0] * n_bins
    bin_outcome_sums = [0] * n_bins

    for p, o in zip(probabilities, outcomes, strict=True):
        b_idx = min(int(p * n_bins), n_bins - 1)
        if b_idx < 0:
            b_idx = 0
        bin_counts[b_idx] += 1
        bin_prob_sums[b_idx] += p
        bin_outcome_sums[b_idx] += o

    reliability = 0.0
    resolution = 0.0

    for k in range(n_bins):
        n_k = bin_counts[k]
        if n_k > 0:
            p_bar_k = bin_prob_sums[k] / n_k
            o_bar_k = bin_outcome_sums[k] / n_k
            weight = n_k / n
            reliability += weight * ((p_bar_k - o_bar_k) ** 2)
            resolution += weight * ((o_bar_k - o_bar) ** 2)

    uncertainty = o_bar * (1.0 - o_bar)

    # Murphy identity: Brier = Reliability - Resolution + Uncertainty
    # Note: For continuous probabilities partitioned into n_bins, a small within-bin variance
    # of order O(1/n_bins^2) exists; tolerance is 1e-3.
    reconstructed_brier = reliability - resolution + uncertainty
    identity_diff = abs(brier - reconstructed_brier)
    identity_holds = identity_diff < 1e-3

    # 4. Log Loss with epsilon clipping
    eps = 1e-15
    log_loss_sum = 0.0
    for p, o in zip(probabilities, outcomes, strict=True):
        clipped_p = max(eps, min(1.0 - eps, p))
        if o == 1:
            log_loss_sum += -math.log(clipped_p)
        else:
            log_loss_sum += -math.log(1.0 - clipped_p)
    log_loss = log_loss_sum / n

    return BrierDecomposition(
        brier_score=round(brier, 6),
        reliability=round(reliability, 6),
        resolution=round(resolution, 6),
        uncertainty=round(uncertainty, 6),
        log_loss=round(log_loss, 6),
        identity_holds=identity_holds,
    )


def compute_fee_breakdown(
    turnover_entries: list[tuple[Decimal, Decimal]], fee_schedule: Any | None = None
) -> dict[str, Decimal]:
    """Calculate complete itemized statutory charges under NSE Intraday Equity schedule.

    Args:
        turnover_entries: list of (buy_turnover, sell_turnover) per completed trade.
        fee_schedule: Optional custom schedule (ignored if None).

    Returns:
        Itemized breakdown of Brokerage, STT, Exchange Txn, SEBI Turnover, Stamp Duty, GST, Total.
    """
    tot_brokerage = Decimal("0.00")
    tot_stt = Decimal("0.00")
    tot_exchange = Decimal("0.00")
    tot_sebi = Decimal("0.00")
    tot_stamp = Decimal("0.00")
    tot_gst = Decimal("0.00")

    for buy_turnover, sell_turnover in turnover_entries:
        tot_turnover = buy_turnover + sell_turnover

        # Brokerage: ₹20 or 0.03% per leg, whichever lower
        buy_brok = min(Decimal("20.00"), buy_turnover * Decimal("0.0003"))
        sell_brok = min(Decimal("20.00"), sell_turnover * Decimal("0.0003"))
        brok = round_paisa(buy_brok + sell_brok)

        # STT: 0.025% on sell leg only
        stt = round_paisa(sell_turnover * Decimal("0.00025"))

        # Exchange Txn Charges: 0.00297% on both legs
        exch = round_paisa(tot_turnover * Decimal("0.0000297"))

        # SEBI Turnover Fee: ₹10 per crore (0.0001%)
        sebi = round_paisa(tot_turnover * Decimal("0.000001"))

        # Stamp Duty: 0.003% on buy leg only
        stamp = round_paisa(buy_turnover * Decimal("0.00003"))

        # GST: 18% on (Brokerage + Exchange Txn + SEBI)
        gst = round_paisa((brok + exch + sebi) * Decimal("0.18"))

        tot_brokerage += brok
        tot_stt += stt
        tot_exchange += exch
        tot_sebi += sebi
        tot_stamp += stamp
        tot_gst += gst

    total_fees = tot_brokerage + tot_stt + tot_exchange + tot_sebi + tot_stamp + tot_gst
    return {
        "brokerage": round_paisa(tot_brokerage),
        "stt": round_paisa(tot_stt),
        "exchange_txn_charges": round_paisa(tot_exchange),
        "sebi_turnover_charges": round_paisa(tot_sebi),
        "stamp_duty": round_paisa(tot_stamp),
        "gst": round_paisa(tot_gst),
        "total_statutory_fees": round_paisa(total_fees),
    }
