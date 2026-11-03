"""Tests for No-Trade Cash Reference Strategy (Layer 7).

Governed by:
- PROJECT_SPEC.md §5 (No-trade reference comparator)
- Layer 7 Gate: Zero entries, zero costs, zero drift, and perfect ledger reconciliation.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from finpilot.baselines.models import (
    BaselineStrategyType,
    ExperimentConfig,
)
from finpilot.baselines.no_trade import NoTradeCashReference
from finpilot.baselines.runner import BaselineExperimentRunner
from finpilot.data.adapters.synthetic import SyntheticDataProviderAdapter
from finpilot.db.enums import DataMode


def test_no_trade_strategy_never_emits_proposals() -> None:
    strategy = NoTradeCashReference()
    adapter = SyntheticDataProviderAdapter()
    bars = adapter.fetch_bars("RELIANCE", date(2026, 1, 5))
    assert len(bars) > 0

    for bar in bars:
        proposal = strategy.evaluate_candle(bar, None)
        assert proposal is None


def test_no_trade_experiment_run_produces_zero_drift_and_ledger_reconciliation() -> None:
    config = ExperimentConfig(
        experiment_id="EXP-TEST-NOTRADE-001",
        strategy_type=BaselineStrategyType.NO_TRADE_REFERENCE,
        strategy_id="REF-NOTRADE-V1",
        universe=("RELIANCE", "TCS"),
        start_date=date(2026, 1, 5),  # Monday
        end_date=date(2026, 1, 9),    # Friday (5 full sessions)
        initial_capital=Decimal("30000.00"),
        mode=DataMode.SYNTHETIC_DEMO,
    )

    runner = BaselineExperimentRunner()
    result = runner.run_experiment(config)

    # 1. Total Activity
    assert result.total_sessions == 5
    assert result.active_sessions == 0
    assert result.coverage_pct == 0.0
    assert result.total_proposals == 0
    assert result.approved_orders == 0
    assert result.filled_orders == 0
    assert result.total_trades == 0

    # 2. Financial Outcomes (Zero drift)
    assert result.gross_pnl == Decimal("0.00")
    assert result.total_fees == Decimal("0.00")
    assert result.net_pnl == Decimal("0.00")
    assert result.expectancy == Decimal("0.00")
    assert result.profit_factor == 0.0
    assert result.max_drawdown_amount == Decimal("0.00")
    assert result.max_drawdown_pct == 0.0
    assert result.daily_returns_mean == 0.0
    assert result.daily_returns_std == 0.0
    assert result.average_capital_utilization_pct == 0.0

    # 3. Ledger Reconciliation
    assert result.ledger_reconciled is True
    assert result.ledger_discrepancy == Decimal("0.00")

    # 4. Daily records verification
    assert len(result.daily_records) == 5
    for rec in result.daily_records:
        assert rec.ending_cash == Decimal("30000.00")
        assert rec.ending_equity == Decimal("30000.00")
        assert rec.session_trades == 0
        assert rec.daily_return == Decimal("0.00")
