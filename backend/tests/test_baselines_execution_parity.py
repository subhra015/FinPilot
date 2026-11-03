"""Tests verifying identical simulator and cost assumptions across baselines (Layer 7).

Governed by:
- PROJECT_SPEC.md §4 (Comparators evaluated under identical execution and cost assumptions)
- Layer 7 Gate: Parity verification of matching engine, fee schedule, sizing, and cutoff mechanics.
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


def test_baselines_run_under_strictly_identical_execution_parameters() -> None:
    # 1. Configure No-Trade baseline
    cfg_notrade = ExperimentConfig(
        experiment_id="EXP-PARITY-NOTRADE",
        strategy_type=BaselineStrategyType.NO_TRADE_REFERENCE,
        strategy_id="REF-NOTRADE-V1",
        universe=("RELIANCE", "TCS", "INFY"),
        start_date=date(2026, 1, 5),
        end_date=date(2026, 1, 9),
        initial_capital=Decimal("30000.00"),
        max_risk_pct_per_trade=Decimal("0.02"),
        max_single_position_exposure_pct=Decimal("0.50"),
        volume_participation_cap=Decimal("0.10"),
        modelled_slippage_bps=Decimal("2.0"),
        mode=DataMode.SYNTHETIC_DEMO,
    )

    # 2. Configure Simple Strategy baseline with identical execution setup
    cfg_simple = ExperimentConfig(
        experiment_id="EXP-PARITY-SIMPLE",
        strategy_type=BaselineStrategyType.PREDECLARED_SIMPLE_STRATEGY,
        strategy_id="STRAT-SIMPLE-V1",
        universe=("RELIANCE", "TCS", "INFY"),
        start_date=date(2026, 1, 5),
        end_date=date(2026, 1, 9),
        initial_capital=Decimal("30000.00"),
        max_risk_pct_per_trade=Decimal("0.02"),
        max_single_position_exposure_pct=Decimal("0.50"),
        volume_participation_cap=Decimal("0.10"),
        modelled_slippage_bps=Decimal("2.0"),
        mode=DataMode.SYNTHETIC_DEMO,
    )

    # 3. Assert config parity
    assert cfg_notrade.initial_capital == cfg_simple.initial_capital
    assert cfg_notrade.policy_version == cfg_simple.policy_version
    assert cfg_notrade.fee_schedule_version == cfg_simple.fee_schedule_version
    assert cfg_notrade.universe == cfg_simple.universe
    assert cfg_notrade.start_date == cfg_simple.start_date
    assert cfg_notrade.end_date == cfg_simple.end_date
    assert cfg_notrade.volume_participation_cap == cfg_simple.volume_participation_cap
    assert cfg_notrade.modelled_slippage_bps == cfg_simple.modelled_slippage_bps
    assert (
        cfg_notrade.max_single_position_exposure_pct
        == cfg_simple.max_single_position_exposure_pct
    )

    runner = BaselineExperimentRunner()
    res_notrade = runner.run_experiment(cfg_notrade)
    res_simple = runner.run_experiment(cfg_simple)

    # 4. Assert both runs processed the exact same number of market sessions
    assert res_notrade.total_sessions == res_simple.total_sessions == 5

    # 5. Assert both runs reconcile accounting to zero paisa discrepancy
    assert res_notrade.ledger_reconciled is True
    assert res_simple.ledger_reconciled is True
    assert res_notrade.ledger_discrepancy == Decimal("0.00")
    assert res_simple.ledger_discrepancy == Decimal("0.00")
