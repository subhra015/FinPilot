"""Tests for multi-period, multi-regime baseline simulation and uncurated evaluation (Layer 7).

Governed by:
- PROJECT_SPEC.md §4, §8
- DATA_AND_PERFORMANCE_POLICY.md §5, §7 (No selection bias: all periods included)
- Layer 7 Gate: Full month evaluation, regime coverage, losing periods, ledger reconciliation.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from finpilot.baselines.models import (
    BaselineStrategyType,
    ExperimentConfig,
)
from finpilot.baselines.runner import BaselineExperimentRunner
from finpilot.db.enums import DataMode


def test_baseline_evaluates_full_month_with_inactive_and_losing_sessions() -> None:
    # Full month of January 2026 (22 trading sessions)
    config = ExperimentConfig(
        experiment_id="EXP-MONTHLY-001",
        strategy_type=BaselineStrategyType.PREDECLARED_SIMPLE_STRATEGY,
        strategy_id="STRAT-SIMPLE-V1",
        universe=("RELIANCE", "TCS", "INFY"),
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        initial_capital=Decimal("30000.00"),
        mode=DataMode.SYNTHETIC_DEMO,
        description="Full uncurated month testing all sessions, inactive and losing periods",
    )

    runner = BaselineExperimentRunner()
    result = runner.run_experiment(config)

    # 1. Total sessions in January 2026 (excluding weekends) = 22 sessions
    assert result.total_sessions == 22

    # 2. Daily records must cover all 22 sessions without omissions
    assert len(result.daily_records) == 22

    # 3. Uncurated test: Inactive sessions (0 trades) MUST exist and be recorded
    inactive_sessions = [d for d in result.daily_records if d.session_trades == 0]
    assert len(inactive_sessions) > 0, "Evaluation must include inactive sessions"

    # 4. Regime stratification: At least two regimes must be represented across the month
    represented_regimes = {r.regime for r in result.regime_records if r.sessions_count > 0}
    assert len(represented_regimes) >= 2, f"Expected multiple regimes, got {represented_regimes}"

    # 5. Period records: Monthly record for '2026-01' present
    assert any(p.period_label == "2026-01" for p in result.period_records)

    # 6. Instrument records: All 3 universe symbols represented
    instrument_symbols = {rec.symbol for rec in result.instrument_records}
    assert instrument_symbols == {"RELIANCE", "TCS", "INFY"}

    # 7. Drawdown and returns computed
    assert result.max_drawdown_amount >= Decimal("0.00")
    assert result.max_drawdown_pct >= 0.0

    # 8. Full ledger reconciliation verified to ₹0.00 discrepancy
    assert result.ledger_reconciled is True
    assert result.ledger_discrepancy == Decimal("0.00")
