"""Statistical and performance metrics calculator for baseline strategies (Layer 7).

Governed by:
- DATA_AND_PERFORMANCE_POLICY.md §5 (Performance metrics)
- PROJECT_SPEC.md §8 (Economic evaluation band)
- Layer 7 Gate: Multi-period metrics, drawdowns, capital utilization, regimes.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from finpilot.execution.models import SimulatedTradeResult

from .models import (
    DailyPerformanceRecord,
    InstrumentPerformanceRecord,
    MarketRegime,
    PeriodPerformanceRecord,
    RegimePerformanceRecord,
)


def calculate_profit_factor(gross_gains: Decimal, gross_losses: Decimal) -> float:
    """Calculate Profit Factor (Gross Gains / |Gross Losses|)."""
    abs_losses = abs(gross_losses)
    if abs_losses == Decimal("0.00") or abs_losses == Decimal("0"):
        if gross_gains > Decimal("0.00"):
            return 999.0  # Infinite profit factor capped for serialization
        return 0.0
    return float(round(gross_gains / abs_losses, 4))


def calculate_drawdown(
    equity_curve: Sequence[Decimal],
) -> tuple[Decimal, float]:
    """Calculate maximum drawdown in rupees and percentage from an equity curve."""
    if not equity_curve:
        return Decimal("0.00"), 0.0

    peak = equity_curve[0]
    max_dd_amount = Decimal("0.00")
    max_dd_pct = 0.0

    for eq in equity_curve:
        if eq > peak:
            peak = eq
        dd = peak - eq
        dd_pct = float(dd / peak) * 100.0 if peak > Decimal("0.00") else 0.0

        if dd > max_dd_amount:
            max_dd_amount = dd
        if dd_pct > max_dd_pct:
            max_dd_pct = dd_pct

    return max_dd_amount, round(max_dd_pct, 4)


def calculate_daily_return_stats(
    daily_returns: Sequence[Decimal],
) -> tuple[float, float]:
    """Calculate mean and standard deviation of daily returns."""
    if not daily_returns:
        return 0.0, 0.0

    float_returns = [float(r) for r in daily_returns]
    n = len(float_returns)
    mean_val = sum(float_returns) / n

    if n < 2:
        return round(mean_val, 6), 0.0

    variance = sum((r - mean_val) ** 2 for r in float_returns) / (n - 1)
    std_val = math.sqrt(variance)

    return round(mean_val, 6), round(std_val, 6)


def aggregate_by_period(
    trades: Sequence[SimulatedTradeResult],
) -> tuple[PeriodPerformanceRecord, ...]:
    """Aggregate trade performance by calendar month (YYYY-MM)."""
    monthly: dict[str, list[SimulatedTradeResult]] = defaultdict(list)
    for t in trades:
        period_key = t.exit_timestamp.strftime("%Y-%m")
        monthly[period_key].append(t)

    records: list[PeriodPerformanceRecord] = []
    for period_key in sorted(monthly.keys()):
        m_trades = monthly[period_key]
        t_count = len(m_trades)
        wins = sum(1 for tr in m_trades if tr.net_pnl > Decimal("0.00"))
        losses = sum(1 for tr in m_trades if tr.net_pnl < Decimal("0.00"))
        win_rate = round((wins / t_count) * 100.0, 2) if t_count > 0 else 0.0
        gross = sum((tr.gross_pnl for tr in m_trades), Decimal("0.00"))
        fees = sum((tr.total_costs for tr in m_trades), Decimal("0.00"))
        net = sum((tr.net_pnl for tr in m_trades), Decimal("0.00"))

        records.append(
            PeriodPerformanceRecord(
                period_label=period_key,
                trades=t_count,
                wins=wins,
                losses=losses,
                win_rate_pct=win_rate,
                gross_pnl=gross,
                fees=fees,
                net_pnl=net,
            )
        )
    return tuple(records)


def aggregate_by_instrument(
    trades: Sequence[SimulatedTradeResult],
    universe: Sequence[str],
) -> tuple[InstrumentPerformanceRecord, ...]:
    """Aggregate trade performance per instrument symbol."""
    sym_trades: dict[str, list[SimulatedTradeResult]] = defaultdict(list)
    for t in trades:
        sym_trades[t.symbol].append(t)

    records: list[InstrumentPerformanceRecord] = []
    # Ensure all universe symbols are represented, even if 0 trades
    for symbol in sorted(set(list(universe) + list(sym_trades.keys()))):
        s_trades = sym_trades.get(symbol, [])
        t_count = len(s_trades)
        wins = sum(1 for tr in s_trades if tr.net_pnl > Decimal("0.00"))
        losses = sum(1 for tr in s_trades if tr.net_pnl < Decimal("0.00"))
        win_rate = round((wins / t_count) * 100.0, 2) if t_count > 0 else 0.0
        gross = sum((tr.gross_pnl for tr in s_trades), Decimal("0.00"))
        fees = sum((tr.total_costs for tr in s_trades), Decimal("0.00"))
        net = sum((tr.net_pnl for tr in s_trades), Decimal("0.00"))

        records.append(
            InstrumentPerformanceRecord(
                symbol=symbol,
                trades=t_count,
                wins=wins,
                losses=losses,
                win_rate_pct=win_rate,
                gross_pnl=gross,
                fees=fees,
                net_pnl=net,
            )
        )
    return tuple(records)


def aggregate_by_regime(
    daily_records: Sequence[DailyPerformanceRecord],
    trades: Sequence[SimulatedTradeResult],
) -> tuple[RegimePerformanceRecord, ...]:
    """Aggregate performance stratified by market regime."""
    session_regimes: dict[date, MarketRegime] = {d.session_date: d.regime for d in daily_records}

    regime_sessions: dict[MarketRegime, int] = defaultdict(int)
    for d in daily_records:
        regime_sessions[d.regime] += 1

    regime_trades: dict[MarketRegime, list[SimulatedTradeResult]] = defaultdict(list)
    for t in trades:
        trade_date = t.entry_timestamp.date()
        regime = session_regimes.get(trade_date, MarketRegime.SIDEWAYS_CHOPPY)
        regime_trades[regime].append(t)

    records: list[RegimePerformanceRecord] = []
    for regime in [
        MarketRegime.TRENDING_BULLISH,
        MarketRegime.TRENDING_BEARISH,
        MarketRegime.SIDEWAYS_CHOPPY,
    ]:
        sess_count = regime_sessions[regime]
        r_trades = regime_trades[regime]
        t_count = len(r_trades)
        wins = sum(1 for tr in r_trades if tr.net_pnl > Decimal("0.00"))
        win_rate = round((wins / t_count) * 100.0, 2) if t_count > 0 else 0.0
        gross = sum((tr.gross_pnl for tr in r_trades), Decimal("0.00"))
        fees = sum((tr.total_costs for tr in r_trades), Decimal("0.00"))
        net = sum((tr.net_pnl for tr in r_trades), Decimal("0.00"))

        records.append(
            RegimePerformanceRecord(
                regime=regime,
                sessions_count=sess_count,
                trades_count=t_count,
                gross_pnl=gross,
                fees=fees,
                net_pnl=net,
                win_rate_pct=win_rate,
            )
        )
    return tuple(records)
