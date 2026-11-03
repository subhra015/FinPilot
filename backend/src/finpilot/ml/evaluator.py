"""Economic evaluation harness for ML models acting as a trade selection layer (Layer 9).

Governed by:
- PROJECT_SPEC.md §4, §5, §7
- DATA_AND_PERFORMANCE_POLICY.md §2, §5, §7, §8
- Layer 9 Gate: Evaluate candidate as a selection layer against no-trade and simple
  strategy baselines using identical simulator assumptions; produce model-contribution comparison.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from finpilot.baselines.no_trade import NoTradeCashReference
from finpilot.baselines.simple_strategy import PredeclaredSimpleStrategy
from finpilot.data.adapters.base import BaseDataProviderAdapter
from finpilot.data.adapters.synthetic import SyntheticDataProviderAdapter
from finpilot.data.models import MarketDataRecord
from finpilot.db.enums import DataMode
from finpilot.execution.fee_schedule import NSEEquityIntradayFeeSchedule, round_paisa
from finpilot.execution.models import AmbiguityTreatment
from finpilot.execution.portfolio import PortfolioManager
from finpilot.execution.simulator import ExecutionSimulator
from finpilot.features.definitions import FS_V1_VERSION
from finpilot.features.models import FeatureVector
from finpilot.features.pipeline import CausalFeaturePipeline
from finpilot.labeling.models import PartitionType, SplitManifest
from finpilot.schemas.errors import DomainValidationError
from finpilot.schemas.trade_policy import TradeProposal

from .models import (
    ModelSelectionComparison,
    SelectionEvaluationMetrics,
)
from .pipeline import MLSelectionPipeline

IST = ZoneInfo("Asia/Kolkata")


class SelectionLayerEvaluator:
    """Evaluates ML models as an entry selection layer over Layer 6 execution simulation.

    Invariants:
    1. Execution Parity: Evaluates ML candidates and baselines under the exact same
       initial capital (₹30,000), 2.0 bps slippage, volume cap, and NSE fee schedule.
    2. Model Role: The ML model acts strictly as a selection filter (vetoing proposals
       with P(profitable) < threshold). It cannot alter sizing, stops, or order routing.
    3. Exact Accounting Reconciliation: Asserts that every evaluation run satisfies
       the accounting identity to ₹0.00 discrepancy.
    4. Economic Contribution: Quantifies fee savings, churn reduction, and net P&L delta.
    """

    def __init__(
        self,
        data_adapter: BaseDataProviderAdapter | None = None,
        initial_capital: Decimal = Decimal("30000.00"),
    ) -> None:
        self.data_adapter = data_adapter or SyntheticDataProviderAdapter()
        self.initial_capital = initial_capital

    def evaluate_selection_model(
        self,
        ml_pipeline: MLSelectionPipeline | None,
        start_date: date,
        end_date: date,
        universe: tuple[str, ...],
        is_no_trade: bool = False,
    ) -> SelectionEvaluationMetrics:
        """Run a complete multi-session simulation evaluating baseline or ML-filtered strategy."""
        fee_schedule = NSEEquityIntradayFeeSchedule()
        simulator = ExecutionSimulator(
            fee_schedule=fee_schedule,
            max_participation_rate=Decimal("0.10"),
            modelled_slippage_bps=Decimal("2.0"),
            ambiguity_treatment=AmbiguityTreatment.CONSERVATIVE_STOP_FIRST,
        )
        portfolio_manager = PortfolioManager(
            initial_capital=self.initial_capital,
            fee_schedule=fee_schedule,
            max_exposure_per_instrument=Decimal("0.50"),
        )

        strategy: Any
        if is_no_trade:
            strategy = NoTradeCashReference()
        else:
            strategy = PredeclaredSimpleStrategy(
                risk_fraction=Decimal("0.01"),
                max_exposure_pct=Decimal("0.50"),
            )

        pipelines = {
            sym: CausalFeaturePipeline(feature_set_version=FS_V1_VERSION) for sym in universe
        }
        symbol_history_bars: dict[str, list[MarketDataRecord]] = defaultdict(list)

        total_proposals = 0
        authorized_proposals = 0
        vetoed_proposals = 0

        peak_equity = self.initial_capital
        max_drawdown = Decimal("0.00")

        current_date = start_date
        while current_date <= end_date:
            if current_date.weekday() >= 5:
                current_date += timedelta(days=1)
                continue

            session_bars_by_symbol: dict[str, list[MarketDataRecord]] = {}
            for sym in universe:
                bars = list(self.data_adapter.fetch_bars(sym, current_date))
                if bars:
                    session_bars_by_symbol[sym] = bars

            if not session_bars_by_symbol:
                current_date += timedelta(days=1)
                continue

            # Compute causal features incrementally
            feature_map: dict[tuple[str, Any], FeatureVector] = {}
            for sym, s_bars in session_bars_by_symbol.items():
                symbol_history_bars[sym].extend(s_bars)
                all_fvs = pipelines[sym].compute_features(symbol_history_bars[sym])
                session_start_idx = len(symbol_history_bars[sym]) - len(s_bars)
                for bar_idx, bar in enumerate(s_bars):
                    feature_map[(sym, bar.timestamp)] = all_fvs[session_start_idx + bar_idx]

            all_session_bars: list[MarketDataRecord] = []
            for s_bars in session_bars_by_symbol.values():
                all_session_bars.extend(s_bars)
            all_session_bars.sort(key=lambda b: (b.timestamp, b.symbol))

            timestamps = sorted(list({b.timestamp for b in all_session_bars}))

            for ts in timestamps:
                ts_bars = [b for b in all_session_bars if b.timestamp == ts]

                # 1. Evaluate open orders
                for bar in ts_bars:
                    for order_id, order in list(portfolio_manager.open_orders.items()):
                        if order.symbol == bar.symbol:
                            if bar.timestamp > order.expiry_timestamp:
                                portfolio_manager.cancel_expired_order(order_id, bar.timestamp)
                            else:
                                fill = simulator.evaluate_order(order, bar)
                                if fill is not None:
                                    portfolio_manager.apply_fill(fill)

                # 2. Evaluate open positions for exits
                for bar in ts_bars:
                    pos = portfolio_manager.positions.get(bar.instrument_id)
                    if pos is not None and pos.status == "OPEN":
                        exit_fill, _ = simulator.evaluate_position_exit(pos, bar)
                        if exit_fill is not None:
                            portfolio_manager.apply_fill(exit_fill)

                # 3. Strategy proposals & ML selection filter
                candidate_proposals: list[TradeProposal] = []
                open_pos_value = sum(
                    pos.average_entry_price * Decimal(pos.quantity)
                    for pos in portfolio_manager.positions.values()
                    if pos.status == "OPEN"
                )
                current_equity = (
                    portfolio_manager.available_cash
                    + portfolio_manager.reserved_cash
                    + open_pos_value
                )

                for bar in ts_bars:
                    f_vec = feature_map.get((bar.symbol, bar.timestamp))
                    prop = strategy.evaluate_candle(
                        bar,
                        f_vec,
                        current_equity=current_equity,
                        mode=DataMode.SYNTHETIC_DEMO,
                    )
                    if prop is not None:
                        total_proposals += 1
                        if ml_pipeline is not None and f_vec is not None:
                            # Apply ML selection filter
                            is_auth, _ = ml_pipeline.should_authorize_proposal(f_vec.features)
                            if is_auth:
                                authorized_proposals += 1
                                candidate_proposals.append(prop)
                            else:
                                vetoed_proposals += 1
                        else:
                            authorized_proposals += 1
                            candidate_proposals.append(prop)

                if candidate_proposals:
                    portfolio_manager.submit_proposals_batch(candidate_proposals)

                portfolio_manager.update_positions_bar_count()

                # Track drawdown
                curr_tot_equity = (
                    portfolio_manager.available_cash
                    + portfolio_manager.reserved_cash
                    + sum(
                        p.average_entry_price * Decimal(p.quantity)
                        for p in portfolio_manager.positions.values()
                        if p.status == "OPEN"
                    )
                )
                if curr_tot_equity > peak_equity:
                    peak_equity = curr_tot_equity
                dd = peak_equity - curr_tot_equity
                if dd > max_drawdown:
                    max_drawdown = dd

            current_date += timedelta(days=1)

        # Reconcile accounting ledger
        try:
            portfolio_manager.reconcile_accounting()
            is_reconciled = True
            discrepancy = Decimal("0.00")
        except DomainValidationError as e:
            is_reconciled = False
            discrepancy = Decimal("999.99")
            raise e

        completed_trades = portfolio_manager.completed_trades
        total_trades = len(completed_trades)
        winning_trades = sum(1 for t in completed_trades if t.net_pnl > Decimal("0.00"))
        win_rate = winning_trades / total_trades if total_trades > 0 else 0.0

        gross_pnl = sum((t.gross_pnl for t in completed_trades), Decimal("0.00"))
        total_fees = sum((t.total_costs for t in completed_trades), Decimal("0.00"))
        net_pnl = sum((t.net_pnl for t in completed_trades), Decimal("0.00"))

        gross_wins = sum(
            (t.gross_pnl for t in completed_trades if t.gross_pnl > Decimal("0.00")),
            Decimal("0.00"),
        )
        gross_losses = abs(
            sum(
                (t.gross_pnl for t in completed_trades if t.gross_pnl < Decimal("0.00")),
                Decimal("0.00"),
            )
        )
        if gross_losses > Decimal("0.00"):
            profit_factor = float(gross_wins / gross_losses)
        else:
            profit_factor = 1.0 if total_trades == 0 else 0.0

        filter_rate = (vetoed_proposals / total_proposals * 100.0) if total_proposals > 0 else 0.0
        max_dd_pct = float(max_drawdown / self.initial_capital * Decimal("100.0"))

        strat_name = "NO_TRADE_REFERENCE" if is_no_trade else "STRAT-SIMPLE-V1"
        mod_id = ml_pipeline.model_id if ml_pipeline is not None else None

        return SelectionEvaluationMetrics(
            strategy_name=strat_name,
            model_id=mod_id,
            total_proposals_evaluated=total_proposals,
            proposals_authorized=authorized_proposals,
            proposals_vetoed=vetoed_proposals,
            filter_rate_pct=round(filter_rate, 2),
            total_trades_filled=total_trades,
            winning_trades=winning_trades,
            win_rate=round(win_rate, 4),
            gross_pnl=round_paisa(gross_pnl),
            fees=round_paisa(total_fees),
            net_pnl=round_paisa(net_pnl),
            profit_factor=round(profit_factor, 4),
            max_drawdown_amount=round_paisa(max_drawdown),
            max_drawdown_pct=round(max_dd_pct, 2),
            ledger_reconciled=is_reconciled,
            accounting_discrepancy=round_paisa(discrepancy),
        )

    def evaluate_strategy_variant(
        self,
        start_date: date,
        end_date: date,
        universe: tuple[str, ...],
        selection_pipeline: MLSelectionPipeline | None = None,
        is_no_trade: bool = False,
    ) -> SelectionEvaluationMetrics:
        """Alias for evaluate_selection_model accepting flexible parameter order."""
        return self.evaluate_selection_model(
            ml_pipeline=selection_pipeline,
            start_date=start_date,
            end_date=end_date,
            universe=universe,
            is_no_trade=is_no_trade,
        )

    def compare_models_on_validation(
        self,
        split_manifest: SplitManifest,
        candidate_models: dict[str, MLSelectionPipeline],
        universe: tuple[str, ...],
    ) -> ModelSelectionComparison:
        """Evaluate and compare baselines and all ML candidate selection models on DEV split."""
        dev_man = split_manifest.partitions[PartitionType.DEV_MODEL_SELECTION]
        start_date = dev_man.start_time.astimezone(IST).date()
        end_date = dev_man.end_time.astimezone(IST).date()
        period_label = f"DEV_MODEL_SELECTION ({start_date} to {end_date})"

        # 1. No-Trade Reference
        no_trade_res = self.evaluate_selection_model(
            ml_pipeline=None,
            start_date=start_date,
            end_date=end_date,
            universe=universe,
            is_no_trade=True,
        )

        # 2. Simple Strategy Baseline (Unfiltered)
        baseline_res = self.evaluate_selection_model(
            ml_pipeline=None,
            start_date=start_date,
            end_date=end_date,
            universe=universe,
            is_no_trade=False,
        )

        # 3. Evaluate each ML Candidate Selection Filter
        candidate_results: dict[str, SelectionEvaluationMetrics] = {}
        contributions: dict[str, dict[str, Any]] = {}

        best_model_id: str | None = None
        best_net_pnl = baseline_res.net_pnl

        for model_id, pipeline in candidate_models.items():
            ml_res = self.evaluate_selection_model(
                ml_pipeline=pipeline,
                start_date=start_date,
                end_date=end_date,
                universe=universe,
                is_no_trade=False,
            )
            candidate_results[model_id] = ml_res

            fee_savings = baseline_res.fees - ml_res.fees
            delta_pnl = ml_res.net_pnl - baseline_res.net_pnl
            delta_win_rate = (ml_res.win_rate - baseline_res.win_rate) * 100.0
            trades_filtered = baseline_res.total_trades_filled - ml_res.total_trades_filled

            dd_reduction = baseline_res.max_drawdown_amount - ml_res.max_drawdown_amount
            contributions[model_id] = {
                "fee_savings_inr": str(fee_savings),
                "delta_net_pnl_inr": str(delta_pnl),
                "delta_win_rate_pct": round(delta_win_rate, 2),
                "trades_filtered": trades_filtered,
                "drawdown_reduction_inr": str(dd_reduction),
            }

            if ml_res.net_pnl > best_net_pnl:
                best_net_pnl = ml_res.net_pnl
                best_model_id = model_id

        # Determine Recommendation Rationale
        if best_model_id is not None:
            rationale = (
                f"Candidate {best_model_id} improves net portfolio outcomes over the unfiltered "
                f"simple baseline by reducing fee drag and filtering unprofitable trades."
            )
        else:
            rationale = (
                "Neither ML candidate improved net portfolio P&L over the baseline on validation. "
                "The simple baseline or no-trade reference remains superior in net outcome."
            )

        return ModelSelectionComparison(
            evaluation_period=period_label,
            split_manifest_id=split_manifest.manifest_id,
            no_trade_result=no_trade_res,
            simple_baseline_result=baseline_res,
            ml_candidate_results=candidate_results,
            model_contributions=contributions,
            recommended_model_id=best_model_id,
            recommendation_rationale=rationale,
        )
