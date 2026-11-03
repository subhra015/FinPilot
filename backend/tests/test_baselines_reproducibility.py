"""Tests for Baseline Experiment Reproducibility and Result Persistence (Layer 7).

Governed by:
- PROJECT_SPEC.md §4, §9
- Layer 7 Gate: Baseline is reproducible; bit-identical replay hashes; JSON round-trip.
"""

from __future__ import annotations

import tempfile
from datetime import date
from decimal import Decimal

from finpilot.baselines.models import (
    BaselineStrategyType,
    ExperimentConfig,
)
from finpilot.baselines.runner import BaselineExperimentRunner
from finpilot.db.enums import DataMode


def test_baseline_experiment_is_strictly_deterministic_and_reproducible() -> None:
    config = ExperimentConfig(
        experiment_id="EXP-REPRO-001",
        strategy_type=BaselineStrategyType.PREDECLARED_SIMPLE_STRATEGY,
        strategy_id="STRAT-SIMPLE-V1",
        universe=("RELIANCE", "TCS"),
        start_date=date(2026, 1, 5),
        end_date=date(2026, 1, 9),
        initial_capital=Decimal("30000.00"),
        mode=DataMode.SYNTHETIC_DEMO,
    )

    runner = BaselineExperimentRunner()

    result_run1 = runner.run_experiment(config)
    result_run2 = runner.run_experiment(config)

    # 1. Config hash must be identical
    assert result_run1.config_hash == result_run2.config_hash

    # 2. Result hashes must match bit-for-bit
    assert result_run1.result_hash == result_run2.result_hash

    # 3. All primary metrics match exactly
    assert result_run1.total_sessions == result_run2.total_sessions
    assert result_run1.active_sessions == result_run2.active_sessions
    assert result_run1.total_trades == result_run2.total_trades
    assert result_run1.winning_trades == result_run2.winning_trades
    assert result_run1.gross_pnl == result_run2.gross_pnl
    assert result_run1.total_fees == result_run2.total_fees
    assert result_run1.net_pnl == result_run2.net_pnl
    assert result_run1.expectancy == result_run2.expectancy
    assert result_run1.profit_factor == result_run2.profit_factor
    assert result_run1.max_drawdown_amount == result_run2.max_drawdown_amount
    assert result_run1.max_drawdown_pct == result_run2.max_drawdown_pct
    assert result_run1.daily_returns_mean == result_run2.daily_returns_mean
    assert result_run1.daily_returns_std == result_run2.daily_returns_std

    # 4. Daily records match item by item
    assert len(result_run1.daily_records) == len(result_run2.daily_records)
    for d1, d2 in zip(result_run1.daily_records, result_run2.daily_records, strict=True):
        assert d1.session_date == d2.session_date
        assert d1.gross_pnl == d2.gross_pnl
        assert d1.fees == d2.fees
        assert d1.net_pnl == d2.net_pnl
        assert d1.ending_equity == d2.ending_equity


def test_baseline_experiment_result_persistence_roundtrip() -> None:
    config = ExperimentConfig(
        experiment_id="EXP-PERSIST-001",
        strategy_type=BaselineStrategyType.PREDECLARED_SIMPLE_STRATEGY,
        strategy_id="STRAT-SIMPLE-V1",
        universe=("RELIANCE",),
        start_date=date(2026, 1, 5),
        end_date=date(2026, 1, 7),
        initial_capital=Decimal("30000.00"),
        mode=DataMode.SYNTHETIC_DEMO,
    )

    runner = BaselineExperimentRunner()
    result = runner.run_experiment(config)

    with tempfile.TemporaryDirectory() as tmp_dir:
        saved_file = runner.save_experiment_result(result, output_dir=tmp_dir)
        assert saved_file.exists()
        assert saved_file.name == "EXP-PERSIST-001.json"

        loaded_result = runner.load_experiment_result(saved_file)
        assert loaded_result.experiment_id == result.experiment_id
        assert loaded_result.config_hash == result.config_hash
        assert loaded_result.result_hash == result.result_hash
        assert loaded_result.net_pnl == result.net_pnl
        assert loaded_result.total_trades == result.total_trades
        assert loaded_result.ledger_reconciled == result.ledger_reconciled
