"""Baseline experiment runner and persistence harness (Layer 7).

Governed by:
- PROJECT_SPEC.md §4, §5
- DATA_AND_PERFORMANCE_POLICY.md §5, §7
- Layer 7 Gate: Reproducibility, execution simulator parity, ledger reconciliation.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from finpilot.data.adapters.base import BaseDataProviderAdapter
from finpilot.data.adapters.synthetic import SyntheticDataProviderAdapter
from finpilot.data.models import MarketDataRecord
from finpilot.db.enums import OrderStatus
from finpilot.execution.fee_schedule import NSEEquityIntradayFeeSchedule, round_paisa
from finpilot.execution.models import AmbiguityTreatment
from finpilot.execution.portfolio import PortfolioManager
from finpilot.execution.simulator import ExecutionSimulator
from finpilot.features.definitions import FS_V1_VERSION
from finpilot.features.models import FeatureVector
from finpilot.features.pipeline import CausalFeaturePipeline
from finpilot.schemas.errors import DomainValidationError, ErrorCode
from finpilot.schemas.trade_policy import TradeProposal

from .metrics import (
    aggregate_by_instrument,
    aggregate_by_period,
    aggregate_by_regime,
    calculate_daily_return_stats,
    calculate_drawdown,
    calculate_profit_factor,
)
from .models import (
    BaselineStrategyType,
    DailyPerformanceRecord,
    ExperimentConfig,
    ExperimentResult,
    MarketRegime,
)
from .no_trade import NoTradeCashReference
from .simple_strategy import PredeclaredSimpleStrategy


class BaselineExperimentRunner:
    """Orchestrates baseline strategy experiments over the Layer 6 execution simulator."""

    def __init__(
        self,
        data_adapter: BaseDataProviderAdapter | None = None,
    ) -> None:
        self.data_adapter = data_adapter or SyntheticDataProviderAdapter()

    def run_experiment(self, config: ExperimentConfig) -> ExperimentResult:
        """Run an end-to-end baseline experiment and return an immutable ExperimentResult."""
        config_hash = config.compute_config_hash()

        # 1. Instantiate shared execution and portfolio engines
        fee_schedule = NSEEquityIntradayFeeSchedule()
        simulator = ExecutionSimulator(
            fee_schedule=fee_schedule,
            max_participation_rate=config.volume_participation_cap,
            modelled_slippage_bps=config.modelled_slippage_bps,
            ambiguity_treatment=AmbiguityTreatment.CONSERVATIVE_STOP_FIRST,
        )
        portfolio_manager = PortfolioManager(
            initial_capital=config.initial_capital,
            fee_schedule=fee_schedule,
            max_exposure_per_instrument=config.max_single_position_exposure_pct,
            mode=config.mode,
        )

        # 2. Select strategy
        if config.strategy_type == BaselineStrategyType.NO_TRADE_REFERENCE:
            strategy: Any = NoTradeCashReference()
        elif config.strategy_type == BaselineStrategyType.PREDECLARED_SIMPLE_STRATEGY:
            strategy = PredeclaredSimpleStrategy(
                risk_fraction=config.max_risk_pct_per_trade,
                max_exposure_pct=config.max_single_position_exposure_pct,
            )
        else:
            raise DomainValidationError(
                f"Unsupported baseline strategy type: {config.strategy_type}",
                field="strategy_type",
                code=ErrorCode.VALIDATION_ERROR,
            )

        # 3. Iterate session by session across the date range
        daily_records: list[DailyPerformanceRecord] = []
        current_date = config.start_date
        total_proposals = 0

        # Causal feature pipelines maintained across sessions for rolling indicators
        pipelines: dict[str, CausalFeaturePipeline] = {
            sym: CausalFeaturePipeline(feature_set_version=FS_V1_VERSION) for sym in config.universe
        }
        symbol_history_bars: dict[str, list[MarketDataRecord]] = defaultdict(list)

        previous_equity = config.initial_capital

        while current_date <= config.end_date:
            if current_date.weekday() >= 5:  # Skip weekends
                current_date += timedelta(days=1)
                continue

            # Fetch bars for all symbols in the universe
            session_bars_by_symbol: dict[str, list[MarketDataRecord]] = {}
            for sym in config.universe:
                bars = list(self.data_adapter.fetch_bars(sym, current_date))
                if bars:
                    session_bars_by_symbol[sym] = bars

            if not session_bars_by_symbol:
                current_date += timedelta(days=1)
                continue

            # Classify session market regime based on universe average session return
            session_returns: list[float] = []
            for sym_bars in session_bars_by_symbol.values():
                if len(sym_bars) >= 2:
                    open_p = float(sym_bars[0].open)
                    close_p = float(sym_bars[-1].close)
                    if open_p > 0:
                        session_returns.append((close_p - open_p) / open_p)

            avg_return = sum(session_returns) / len(session_returns) if session_returns else 0.0
            if avg_return > 0.005:
                regime = MarketRegime.TRENDING_BULLISH
            elif avg_return < -0.005:
                regime = MarketRegime.TRENDING_BEARISH
            else:
                regime = MarketRegime.SIDEWAYS_CHOPPY

            # Compute causal features for each symbol incrementally
            feature_map: dict[tuple[str, Any], FeatureVector] = {}
            for sym, s_bars in session_bars_by_symbol.items():
                symbol_history_bars[sym].extend(s_bars)
                # Compute features over cumulative history to maintain causal warm-up
                all_fvs = pipelines[sym].compute_features(symbol_history_bars[sym])
                # Map session bars to their respective feature vectors
                session_start_idx = len(symbol_history_bars[sym]) - len(s_bars)
                for bar_idx, bar in enumerate(s_bars):
                    feature_map[(sym, bar.timestamp)] = all_fvs[session_start_idx + bar_idx]

            # Merge and sort all session bars chronologically
            all_session_bars: list[MarketDataRecord] = []
            for s_bars in session_bars_by_symbol.values():
                all_session_bars.extend(s_bars)
            all_session_bars.sort(key=lambda b: (b.timestamp, b.symbol))

            # Group bars by timestamp
            timestamps: list[Any] = sorted(list({b.timestamp for b in all_session_bars}))

            trades_before_session = len(portfolio_manager.completed_trades)
            max_capital_deployed_today = Decimal("0.00")

            for ts in timestamps:
                ts_bars = [b for b in all_session_bars if b.timestamp == ts]

                # Step 1: Evaluate existing open orders against arriving bars
                for bar in ts_bars:
                    for order_id, order in list(portfolio_manager.open_orders.items()):
                        if order.symbol == bar.symbol:
                            if bar.timestamp > order.expiry_timestamp:
                                portfolio_manager.cancel_expired_order(order_id, bar.timestamp)
                            else:
                                fill = simulator.evaluate_order(order, bar)
                                if fill is not None:
                                    portfolio_manager.apply_fill(fill)

                # Step 2: Evaluate existing open positions for exits (stop, target, cutoff)
                for bar in ts_bars:
                    pos = portfolio_manager.positions.get(bar.instrument_id)
                    if pos is not None and pos.status == "OPEN":
                        exit_fill, exit_reason = simulator.evaluate_position_exit(pos, bar)
                        if exit_fill is not None:
                            portfolio_manager.apply_fill(exit_fill)

                # Track capital deployed
                open_pos_value = sum(
                    pos.average_entry_price * Decimal(pos.quantity)
                    for pos in portfolio_manager.positions.values()
                    if pos.status == "OPEN"
                )
                curr_deployed = portfolio_manager.reserved_cash + open_pos_value
                if curr_deployed > max_capital_deployed_today:
                    max_capital_deployed_today = curr_deployed

                # Step 3: Evaluate strategy on completed candles
                candidate_proposals: list[TradeProposal] = []
                for bar in ts_bars:
                    f_vec = feature_map.get((bar.symbol, bar.timestamp))
                    current_equity = (
                        portfolio_manager.available_cash
                        + portfolio_manager.reserved_cash
                        + open_pos_value
                    )
                    prop = strategy.evaluate_candle(
                        bar,
                        f_vec,
                        current_equity=current_equity,
                        mode=config.mode,
                    )
                    if prop is not None:
                        candidate_proposals.append(prop)
                        total_proposals += 1

                # Prioritize and submit proposals
                if candidate_proposals:
                    portfolio_manager.submit_proposals_batch(candidate_proposals)

                # Step 4: Increment duration for active open positions
                portfolio_manager.update_positions_bar_count()

            # End-of-session settlement
            session_trades = portfolio_manager.completed_trades[trades_before_session:]
            session_trades_count = len(session_trades)
            gross_today = sum((t.gross_pnl for t in session_trades), Decimal("0.00"))
            fees_today = sum((t.total_costs for t in session_trades), Decimal("0.00"))
            net_today = sum((t.net_pnl for t in session_trades), Decimal("0.00"))

            ending_cash = portfolio_manager.available_cash + portfolio_manager.reserved_cash
            open_pos_cost = sum(
                p.average_entry_price * Decimal(p.quantity)
                for p in portfolio_manager.positions.values()
                if p.status == "OPEN"
            )
            ending_equity = ending_cash + open_pos_cost

            if previous_equity > Decimal("0.00"):
                daily_return = (ending_equity - previous_equity) / previous_equity
            else:
                daily_return = Decimal("0.00")

            cap_util_pct = (max_capital_deployed_today / config.initial_capital) * Decimal("100.0")

            daily_records.append(
                DailyPerformanceRecord(
                    session_date=current_date,
                    session_trades=session_trades_count,
                    gross_pnl=round_paisa(gross_today),
                    fees=round_paisa(fees_today),
                    net_pnl=round_paisa(net_today),
                    ending_cash=round_paisa(ending_cash),
                    ending_equity=round_paisa(ending_equity),
                    daily_return=round(daily_return, 6),
                    capital_utilized_pct=round(cap_util_pct, 2),
                    regime=regime,
                )
            )

            previous_equity = ending_equity
            current_date += timedelta(days=1)

        # 4. Final Accounting Reconciliation (Layer 6 identity)
        is_reconciled = portfolio_manager.reconcile_accounting()
        gross_realized = sum(t.gross_pnl for t in portfolio_manager.completed_trades)
        computed_capital = (
            portfolio_manager.available_cash
            + portfolio_manager.reserved_cash
            + sum(
                round_paisa(pos.average_entry_price * Decimal(pos.quantity))
                for pos in portfolio_manager.positions.values()
                if pos.status == "OPEN"
            )
            + portfolio_manager.total_costs_paid
            - gross_realized
        )
        ledger_discrepancy = abs(
            round_paisa(computed_capital) - round_paisa(config.initial_capital)
        )

        # 5. Compute Aggregate Performance Statistics
        total_sessions = len(daily_records)
        active_sessions = sum(1 for d in daily_records if d.session_trades > 0)
        coverage_pct = (
            round((active_sessions / total_sessions) * 100.0, 2) if total_sessions > 0 else 0.0
        )

        all_trades = portfolio_manager.completed_trades
        total_trades = len(all_trades)
        winning_trades = sum(1 for t in all_trades if t.net_pnl > Decimal("0.00"))
        losing_trades = sum(1 for t in all_trades if t.net_pnl < Decimal("0.00"))
        scratch_trades = sum(1 for t in all_trades if t.net_pnl == Decimal("0.00"))
        win_rate_pct = (
            round((winning_trades / total_trades) * 100.0, 2) if total_trades > 0 else 0.0
        )

        gross_pnl = sum((t.gross_pnl for t in all_trades), Decimal("0.00"))
        total_fees = sum((t.total_costs for t in all_trades), Decimal("0.00"))
        net_pnl = sum((t.net_pnl for t in all_trades), Decimal("0.00"))

        expectancy = (
            round_paisa(net_pnl / Decimal(total_trades)) if total_trades > 0 else Decimal("0.00")
        )

        gross_gains = sum(
            (t.gross_pnl for t in all_trades if t.gross_pnl > Decimal("0.00")), Decimal("0.00")
        )
        gross_losses = sum(
            (t.gross_pnl for t in all_trades if t.gross_pnl < Decimal("0.00")), Decimal("0.00")
        )
        profit_factor = calculate_profit_factor(gross_gains, gross_losses)

        equity_curve = [config.initial_capital] + [d.ending_equity for d in daily_records]
        max_dd_amount, max_dd_pct = calculate_drawdown(equity_curve)
        daily_ret_mean, daily_ret_std = calculate_daily_return_stats(
            [d.daily_return for d in daily_records]
        )

        avg_cap_util = (
            float(
                round(
                    sum(d.capital_utilized_pct for d in daily_records) / Decimal(total_sessions), 2
                )
            )
            if total_sessions > 0
            else 0.0
        )
        peak_cap_util = float(
            round(max((d.capital_utilized_pct for d in daily_records), default=Decimal("0.00")), 2)
        )

        ambiguous_exits = sum(1 for t in all_trades if t.is_ambiguous_exit)
        ambiguity_rate_pct = (
            round((ambiguous_exits / total_trades) * 100.0, 2) if total_trades > 0 else 0.0
        )

        rejection_counts: dict[str, int] = defaultdict(int)
        for _, reason in portfolio_manager.rejected_proposals:
            rejection_counts[reason.value] += 1

        approved_orders = total_proposals - len(portfolio_manager.rejected_proposals)
        filled_orders = total_trades
        unfilled_orders = len(portfolio_manager.open_orders)
        partial_fills = sum(
            1
            for o in portfolio_manager.open_orders.values()
            if o.status == OrderStatus.PARTIALLY_FILLED
        )

        period_records = aggregate_by_period(all_trades)
        instrument_records = aggregate_by_instrument(all_trades, config.universe)
        regime_records = aggregate_by_regime(daily_records, all_trades)

        raw_payload = {
            "experiment_id": config.experiment_id,
            "config_hash": config_hash,
            "strategy_id": config.strategy_id,
            "total_sessions": total_sessions,
            "active_sessions": active_sessions,
            "total_trades": total_trades,
            "win_rate_pct": win_rate_pct,
            "gross_pnl": gross_pnl,
            "total_fees": total_fees,
            "net_pnl": net_pnl,
            "expectancy": expectancy,
            "profit_factor": profit_factor,
            "max_drawdown_amount": max_dd_amount,
            "ledger_reconciled": is_reconciled,
            "ledger_discrepancy": ledger_discrepancy,
        }
        result_hash = ExperimentResult.calculate_result_hash(raw_payload)

        return ExperimentResult(
            experiment_id=config.experiment_id,
            config_hash=config_hash,
            strategy_id=config.strategy_id,
            total_sessions=total_sessions,
            active_sessions=active_sessions,
            coverage_pct=coverage_pct,
            total_proposals=total_proposals,
            approved_orders=approved_orders,
            filled_orders=filled_orders,
            partial_fills=partial_fills,
            unfilled_orders=unfilled_orders,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            scratch_trades=scratch_trades,
            win_rate_pct=win_rate_pct,
            gross_pnl=round_paisa(gross_pnl),
            total_fees=round_paisa(total_fees),
            net_pnl=round_paisa(net_pnl),
            expectancy=expectancy,
            profit_factor=profit_factor,
            max_drawdown_amount=round_paisa(max_dd_amount),
            max_drawdown_pct=max_dd_pct,
            daily_returns_mean=daily_ret_mean,
            daily_returns_std=daily_ret_std,
            average_capital_utilization_pct=avg_cap_util,
            peak_capital_utilization_pct=peak_cap_util,
            ambiguity_rate_pct=ambiguity_rate_pct,
            rejection_reasons=dict(rejection_counts),
            daily_records=tuple(daily_records),
            period_records=period_records,
            instrument_records=instrument_records,
            regime_records=regime_records,
            ledger_reconciled=is_reconciled,
            ledger_discrepancy=ledger_discrepancy,
            result_hash=result_hash,
        )

    def save_experiment_result(
        self,
        result: ExperimentResult,
        output_dir: str = "data/experiments",
    ) -> Path:
        """Persist an experiment result artifact with its immutable experiment ID."""
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        file_path = out_path / f"{result.experiment_id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(result.model_dump_json(indent=2))
        return file_path

    def load_experiment_result(self, file_path: str | Path) -> ExperimentResult:
        """Load and validate a previously persisted experiment result artifact."""
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
        return ExperimentResult.model_validate(data)
