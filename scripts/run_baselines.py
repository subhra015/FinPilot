"""Run and persist Layer 7 baseline experiments (EXP-0001 and EXP-0002)."""

import sys
from pathlib import Path

# Add backend/src to path
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root / "backend" / "src"))

from datetime import date
from decimal import Decimal
from finpilot.baselines.models import (
    BaselineStrategyType,
    ExperimentConfig,
)
from finpilot.baselines.runner import BaselineExperimentRunner
from finpilot.db.enums import DataMode


def main() -> None:
    runner = BaselineExperimentRunner()

    # 1. EXP-0001: No-Trade Cash Reference
    cfg1 = ExperimentConfig(
        experiment_id="EXP-0001",
        strategy_type=BaselineStrategyType.NO_TRADE_REFERENCE,
        strategy_id="REF-NOTRADE-V1",
        universe=("RELIANCE", "TCS", "INFY"),
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        initial_capital=Decimal("30000.00"),
        mode=DataMode.SYNTHETIC_DEMO,
        description="No-trade cash reference benchmark across January 2026",
    )
    res1 = runner.run_experiment(cfg1)
    file1 = runner.save_experiment_result(res1)
    print(f"EXP-0001 saved to {file1}")
    print(f"  Result Hash: {res1.result_hash}")
    print(f"  Total Trades: {res1.total_trades}, Net PnL: {res1.net_pnl}, Ledger Reconciled: {res1.ledger_reconciled}")

    # 2. EXP-0002: Predeclared Simple Strategy
    cfg2 = ExperimentConfig(
        experiment_id="EXP-0002",
        strategy_type=BaselineStrategyType.PREDECLARED_SIMPLE_STRATEGY,
        strategy_id="STRAT-SIMPLE-V1",
        universe=("RELIANCE", "TCS", "INFY"),
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        initial_capital=Decimal("30000.00"),
        max_risk_pct_per_trade=Decimal("0.02"),
        max_single_position_exposure_pct=Decimal("0.50"),
        volume_participation_cap=Decimal("0.10"),
        modelled_slippage_bps=Decimal("2.0"),
        mode=DataMode.SYNTHETIC_DEMO,
        description="Predeclared simple trend-VWAP-momentum strategy across January 2026",
    )
    res2 = runner.run_experiment(cfg2)
    file2 = runner.save_experiment_result(res2)
    print(f"EXP-0002 saved to {file2}")
    print(f"  Result Hash: {res2.result_hash}")
    print(f"  Total Trades: {res2.total_trades}")
    print(f"  Win Rate: {res2.win_rate_pct}% ({res2.winning_trades} wins, {res2.losing_trades} losses, {res2.scratch_trades} scratch)")
    print(f"  Gross PnL: Rs. {res2.gross_pnl}, Fees: Rs. {res2.total_fees}, Net PnL: Rs. {res2.net_pnl}")
    print(f"  Expectancy: Rs. {res2.expectancy}, Profit Factor: {res2.profit_factor}")
    print(f"  Max Drawdown: Rs. {res2.max_drawdown_amount} ({res2.max_drawdown_pct}%)")
    print(f"  Coverage: {res2.coverage_pct}% ({res2.active_sessions}/{res2.total_sessions} sessions)")
    print(f"  Avg Capital Utilization: {res2.average_capital_utilization_pct}%, Peak: {res2.peak_capital_utilization_pct}%")
    print(f"  Ambiguity Rate: {res2.ambiguity_rate_pct}%")
    print(f"  Rejection Reasons: {res2.rejection_reasons}")
    print(f"  Ledger Reconciled: {res2.ledger_reconciled} (Discrepancy: Rs. {res2.ledger_discrepancy})")
    print("  Period Records:")
    for p in res2.period_records:
        print(f"    {p.period_label}: trades={p.trades}, win_rate={p.win_rate_pct}%, net_pnl=Rs. {p.net_pnl}")
    print("  Instrument Records:")
    for inst in res2.instrument_records:
        print(f"    {inst.symbol}: trades={inst.trades}, win_rate={inst.win_rate_pct}%, net_pnl=Rs. {inst.net_pnl}")
    print("  Regime Records:")
    for reg in res2.regime_records:
        print(f"    {reg.regime}: sessions={reg.sessions_count}, trades={reg.trades_count}, net_pnl=Rs. {reg.net_pnl}")


if __name__ == "__main__":
    main()
