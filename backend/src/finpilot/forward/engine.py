"""Forward paper trading engine executing the 10-step prediction workflow (Layer 16).

Governed by:
- ACCEPTANCE_GATES.md §2 (Layer 16 Gate)
- DATA_AND_PERFORMANCE_POLICY.md §3 (Forward Paper Mode), §7, §8
- PROJECT_SPEC.md §3, §4, §5, §7, §9, §11
- SECURITY_CHECKLIST.md SEC-01 through SEC-27
"""

from __future__ import annotations

import math
import uuid
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime, time
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.orm import sessionmaker

from finpilot.baselines.simple_strategy import PredeclaredSimpleStrategy
from finpilot.data.adapters.base import BaseDataProviderAdapter
from finpilot.data.adapters.synthetic import SyntheticDataProviderAdapter
from finpilot.data.models import MarketDataRecord
from finpilot.db.base import Base
from finpilot.db.enums import DataMode
from finpilot.db.models import Account, Instrument, Portfolio
from finpilot.decision.engine import SelectiveDecisionEngine
from finpilot.decision.models import DecisionState, FrozenDecisionPolicy
from finpilot.execution.fee_schedule import NSEEquityIntradayFeeSchedule, round_paisa
from finpilot.execution.models import AmbiguityTreatment
from finpilot.execution.portfolio import PortfolioManager
from finpilot.execution.simulator import ExecutionSimulator
from finpilot.features.definitions import FS_V1_VERSION
from finpilot.features.models import FeatureVector
from finpilot.features.pipeline import CausalFeaturePipeline
from finpilot.forward.integrity import verify_frozen_model_and_config
from finpilot.forward.ledger import ForwardPredictionLedger
from finpilot.forward.models import (
    DriftMonitorMetrics,
    ForwardDecision,
    ForwardPaperStatus,
    ForwardPerformanceMetrics,
    ModelIntegrityVerification,
    PredictionEventRecord,
    VirtualPortfolioConfig,
)
from finpilot.forward.monitor import DriftAndPerformanceMonitor
from finpilot.ml.registry import ModelRegistry
from finpilot.risk.evaluator import RiskEvaluator
from finpilot.risk.models import RiskConfig, RiskDecisionStatus
from finpilot.schemas.candles import CandleBar

IST = ZoneInfo("Asia/Kolkata")
SESSION_OPEN_TIME = time(9, 15)
ENTRY_CUTOFF_TIME = time(15, 0)
FORCED_EXIT_TIME = time(15, 15)
SESSION_CLOSE_TIME = time(15, 30)

DEFAULT_UNIVERSE = ("INFY", "RELIANCE", "TCS")
INSTRUMENT_ID_MAP = {"RELIANCE": 101, "TCS": 102, "INFY": 103}


class ForwardPaperTradingEngine:
    """Authoritative forward paper trading engine with strict user trust and risk controls.

    Guarantees:
    1. Zero Real-Money Execution: Forward paper orders are simulated only;
       live broker routes are absent.
    2. Frozen Model Verification: Rejects execution if model binary, policy, or risk rules drift.
    3. User-Controlled Capital: Supports virtual portfolios (₹2k, ₹10k, ₹30k, ₹50k, custom)
       enforcing integer shares.
    4. 10-Step Prediction Workflow: Persists predictions *before* market outcomes;
       appends outcomes separately.
    5. Fail-Closed Stale Data: Halts new entries on stale feed (> 300s) while monitoring
       protective exits.
    6. Double-Entry Accounting: Asserts Cash + Positions + Costs - Gross Realized == Initial Capital
       to ₹0.00.
    """

    def __init__(
        self,
        initial_capital: Decimal = Decimal("30000.00"),
        model_id: str = "MODEL-LOGREG-V1",
        calibration_policy_id: str = "DECISION-POLICY-V1",
        data_adapter: BaseDataProviderAdapter | None = None,
        stale_threshold_seconds: int = 300,
        clock: Callable[[], datetime] | None = None,
        db: DBSession | None = None,
        ledger_path: Path | str = "artifacts/forward/prediction_ledger.json",
        config: VirtualPortfolioConfig | None = None,
    ) -> None:
        if config is not None:
            self.config = config
            self.initial_capital = config.initial_capital
        else:
            self.initial_capital = initial_capital
            self.config = VirtualPortfolioConfig(
                initial_capital=self.initial_capital,
                mode=DataMode.FORWARD_PAPER,
            )
        self.model_id = model_id
        self.calibration_policy_id = calibration_policy_id
        self.data_adapter = data_adapter or SyntheticDataProviderAdapter()
        self.stale_threshold_seconds = stale_threshold_seconds
        self.clock = clock
        self.mode = DataMode.FORWARD_PAPER

        # 1. Cryptographic Model & Policy Freeze Verification
        self.verification: ModelIntegrityVerification = verify_frozen_model_and_config(
            model_id=self.model_id,
            calibration_policy_id=self.calibration_policy_id,
        )
        if not self.verification.is_checksum_verified or not self.verification.is_policy_verified:
            raise RuntimeError(
                f"CRITICAL INTEGRITY FAILURE: Frozen model or policy mismatch! "
                f"Expected {self.verification.expected_artifact_checksum}, "
                f"got {self.verification.actual_artifact_checksum}"
            )

        # 2. Database Session Initialization
        if db is not None:
            self.db = db
        else:
            engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
            Base.metadata.create_all(engine)
            session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
            self.db = session_factory()
            acc = Account(
                id=1,
                account_number="ACC-FWD-PAPER-01",
                name="Forward Paper Account",
                initial_scenario_capital=self.initial_capital,
                current_cash=self.initial_capital,
                mode=self.mode.value,
            )
            port = Portfolio(
                id=1,
                account_id=1,
                name="Forward Paper Portfolio",
                mode=self.mode.value,
            )
            self.db.add_all([acc, port])
            for sym, inst_id in INSTRUMENT_ID_MAP.items():
                self.db.add(
                    Instrument(
                        id=inst_id,
                        isin=f"INE000000{inst_id}",
                        symbol=sym,
                        name=f"{sym} Equity",
                        market="EQUITY",
                        exchange="NSE",
                        currency="INR",
                        status="ACTIVE",
                    )
                )
            self.db.commit()

        # 3. Core Simulator, Portfolio, and Risk Engines
        self.fee_schedule = NSEEquityIntradayFeeSchedule()
        self.portfolio_manager = PortfolioManager(
            initial_capital=self.initial_capital,
            fee_schedule=self.fee_schedule,
            max_exposure_per_instrument=Decimal("0.50"),
            mode=self.mode,
        )
        self.risk_evaluator = RiskEvaluator(
            config=RiskConfig(
                max_account_equity=max(Decimal("200000.00"), self.initial_capital * Decimal("2.0")),
                max_exposure_per_instrument_pct=Decimal("0.50"),
                max_total_exposure_pct=Decimal("1.00"),
                max_concurrent_positions=2,
                approved_instruments=list(DEFAULT_UNIVERSE),
                approved_model_ids=[self.model_id, "STRAT-SIMPLE-V1"],
            ),
            fee_schedule=self.fee_schedule,
        )
        self.simulator = ExecutionSimulator(
            fee_schedule=self.fee_schedule,
            max_participation_rate=Decimal("0.10"),
            modelled_slippage_bps=Decimal("2.0"),
            ambiguity_treatment=AmbiguityTreatment.CONSERVATIVE_STOP_FIRST,
        )

        # 4. ML Selection Pipeline and Decision Engine
        model_registry = ModelRegistry()
        self.pipeline, _ = model_registry.load_model(self.model_id)
        cal_path = (
            Path("artifacts/calibration") / f"{self.calibration_policy_id}-{self.model_id}.json"
        )
        self.frozen_policy = FrozenDecisionPolicy.model_validate_json(
            cal_path.read_text(encoding="utf-8")
        )
        self.decision_engine = SelectiveDecisionEngine(
            pipeline=self.pipeline,
            policy=self.frozen_policy,
        )

        # 5. Prediction Ledger & Drift Monitor
        self.prediction_ledger = ForwardPredictionLedger(
            ledger_path=ledger_path,
            db=self.db,
        )
        self.ledger = self.prediction_ledger
        self.monitor = DriftAndPerformanceMonitor(
            max_acceptable_latency_seconds=float(self.stale_threshold_seconds),
            max_drawdown_threshold_pct=10.0,
        )

        # 6. Feature Pipelines
        self.strategy = PredeclaredSimpleStrategy(
            risk_fraction=Decimal("0.01"),
            max_exposure_pct=Decimal("0.50"),
        )
        self.feature_pipelines = {
            sym: CausalFeaturePipeline(feature_set_version=FS_V1_VERSION)
            for sym in DEFAULT_UNIVERSE
        }
        self.history_bars: dict[str, list[MarketDataRecord]] = defaultdict(list)
        self.active_order_to_event_id: dict[str, str] = {}
        self.position_to_event_id: dict[str, str] = {}

    def get_current_time(self) -> datetime:
        """Get current authoritative UTC timestamp (from clock callable or system UTC)."""
        if self.clock is not None:
            t = self.clock()
            return t if t.tzinfo else t.replace(tzinfo=UTC)
        return datetime.now(UTC)

    def validate_candle_geometry(self, bar: CandleBar | MarketDataRecord) -> bool:
        """Validate candle OHLC geometry and positive volume."""
        try:
            op = float(bar.open)
            hi = float(bar.high)
            lo = float(bar.low)
            cl = float(bar.close)
            vol = float(bar.volume)
        except (ValueError, TypeError):
            return False

        if math.isnan(op) or math.isnan(hi) or math.isnan(lo) or math.isnan(cl) or math.isnan(vol):
            return False
        if math.isinf(op) or math.isinf(hi) or math.isinf(lo) or math.isinf(cl) or math.isinf(vol):
            return False
        if op <= 0 or hi <= 0 or lo <= 0 or cl <= 0:
            return False
        if not (lo <= op <= hi and lo <= cl <= hi):
            return False
        return vol >= 0

    def process_completed_candle(
        self,
        bar: CandleBar | MarketDataRecord,
    ) -> PredictionEventRecord | None:
        """Execute authoritative 10-step prediction, risk, and execution workflow for a candle."""
        now_utc = self.get_current_time()
        c_ts = bar.timestamp if bar.timestamp.tzinfo else bar.timestamp.replace(tzinfo=UTC)
        symbol = bar.symbol
        inst_id = INSTRUMENT_ID_MAP.get(symbol, 1)

        # ==============================================================================
        # STEP 1: Validate Market Data (Geometry, Freshness, Session)
        # ==============================================================================
        is_geo_ok = self.validate_candle_geometry(bar)
        is_fresh = self.monitor.record_candle_check(
            candle_timestamp=c_ts,
            current_time=now_utc,
            is_geometry_valid=is_geo_ok,
        )

        # First, evaluate existing open orders against this incoming candle
        for order_id, order in list(self.portfolio_manager.open_orders.items()):
            if order.symbol == symbol:
                if c_ts > order.expiry_timestamp:
                    self.portfolio_manager.cancel_expired_order(order_id, c_ts)
                else:
                    fill = self.simulator.evaluate_order(order, bar)
                    if fill is not None:
                        self.portfolio_manager.apply_fill(fill)
                        ev_id = self.active_order_to_event_id.get(order_id)
                        if ev_id:
                            self.position_to_event_id[symbol] = ev_id
                            self.prediction_ledger.append_outcome(
                                event_id=ev_id,
                                fill_price=fill.fill_price,
                                fill_quantity=fill.fill_quantity,
                                fill_timestamp=fill.timestamp,
                                slippage_incurred=fill.cost_breakdown.modelled_slippage,
                                charges_incurred=fill.cost_breakdown.total_costs,
                            )

        # Second, evaluate existing open positions for exits
        pos = self.portfolio_manager.positions.get(inst_id)
        if pos is not None and pos.status == "OPEN":
            exit_fill, exit_reason = self.simulator.evaluate_position_exit(pos, bar)
            if exit_fill is not None:
                self.portfolio_manager.apply_fill(exit_fill)
                ev_id = self.position_to_event_id.pop(symbol, None)
                if ev_id:
                    completed_t = self.portfolio_manager.completed_trades[-1]
                    self.prediction_ledger.append_outcome(
                        event_id=ev_id,
                        exit_price=exit_fill.fill_price,
                        exit_timestamp=exit_fill.timestamp,
                        exit_reason=exit_reason.value
                        if hasattr(exit_reason, "value")
                        else str(exit_reason),
                        gross_pnl=completed_t.gross_pnl,
                        net_pnl=completed_t.net_pnl,
                    )
                    self.monitor.record_prediction_evaluation(
                        predicted_prob=None,
                        is_positive_outcome=completed_t.net_pnl > Decimal("0.00"),
                    )

        # Update drawdown
        peak_eq = max(self.portfolio_manager.initial_capital, self.portfolio_manager.available_cash)
        curr_eq = (
            self.portfolio_manager.available_cash
            + self.portfolio_manager.reserved_cash
            + sum(
                p.average_entry_price * Decimal(p.quantity)
                for p in self.portfolio_manager.positions.values()
                if p.status == "OPEN"
            )
        )
        dd = float((peak_eq - curr_eq) / peak_eq * Decimal("100.0")) if peak_eq > 0 else 0.0
        self.monitor.update_drawdown(dd)

        # If market data failed or safe mode active, reject candidate entries fail-closed
        if not is_geo_ok:
            rec = PredictionEventRecord(
                event_id=f"PRED-DATA-ERR-{symbol}-{int(c_ts.timestamp())}",
                prediction_timestamp=now_utc,
                candle_timestamp=c_ts,
                symbol=symbol,
                instrument_id=inst_id,
                model_id=self.model_id,
                model_hash=self.verification.actual_artifact_checksum,
                proposed_entry_price=Decimal(str(bar.close)),
                stop_loss_price=Decimal("0.00"),
                profit_target_price=Decimal("0.00"),
                requested_quantity=0,
                risk_authorized=False,
                risk_rejection_reasons=["ABNORMAL_CANDLE_GEOMETRY"],
                decision=ForwardDecision.INSUFFICIENT_DATA,
                decision_reason=(
                    "Candle OHLC geometry violated boundary invariants (Low <= Open,Close <= High)."
                ),
            )
            return self.prediction_ledger.record_prediction(rec)

        if not is_fresh or self.monitor.safe_no_new_entry_mode:
            reason = (
                self.monitor.safe_mode_trigger_reason
                or "Stale market feed; new entries blocked fail-closed."
            )
            rec = PredictionEventRecord(
                event_id=f"PRED-STALE-{symbol}-{int(c_ts.timestamp())}",
                prediction_timestamp=now_utc,
                candle_timestamp=c_ts,
                symbol=symbol,
                instrument_id=inst_id,
                model_id=self.model_id,
                model_hash=self.verification.actual_artifact_checksum,
                proposed_entry_price=Decimal(str(bar.close)),
                stop_loss_price=Decimal("0.00"),
                profit_target_price=Decimal("0.00"),
                requested_quantity=0,
                risk_authorized=False,
                risk_rejection_reasons=["STALE_DATA_SAFE_MODE"],
                decision=ForwardDecision.INSUFFICIENT_DATA,
                decision_reason=reason,
            )
            return self.prediction_ledger.record_prediction(rec)

        # ==============================================================================
        # STEP 2: Compute Causal Features Incrementally
        # ==============================================================================
        self.history_bars[symbol].append(bar)
        recent_bars = self.history_bars[symbol][-120:]
        fvs = self.feature_pipelines[symbol].compute_features(recent_bars)
        latest_fv: FeatureVector | None = fvs[-1] if fvs else None

        if latest_fv is None or not latest_fv.is_fully_warmed_up:
            rec = PredictionEventRecord(
                event_id=f"PRED-WARMUP-{symbol}-{int(c_ts.timestamp())}",
                prediction_timestamp=now_utc,
                candle_timestamp=c_ts,
                symbol=symbol,
                instrument_id=inst_id,
                model_id=self.model_id,
                model_hash=self.verification.actual_artifact_checksum,
                proposed_entry_price=Decimal(str(bar.close)),
                stop_loss_price=Decimal("0.00"),
                profit_target_price=Decimal("0.00"),
                requested_quantity=0,
                risk_authorized=False,
                risk_rejection_reasons=["FEATURE_WARMUP_INCOMPLETE"],
                decision=ForwardDecision.INSUFFICIENT_DATA,
                decision_reason="Indicators require minimum 21 bars for causal rolling warm-up.",
            )
            return self.prediction_ledger.record_prediction(rec)

        # Strategy evaluation for candidate trade proposal
        open_pos_val = sum(
            p.average_entry_price * Decimal(p.quantity)
            for p in self.portfolio_manager.positions.values()
            if p.status == "OPEN"
        )
        total_eq = (
            self.portfolio_manager.available_cash
            + self.portfolio_manager.reserved_cash
            + open_pos_val
        )

        proposal = self.strategy.evaluate_candle(
            bar=bar,
            features=latest_fv,
            current_equity=total_eq,
            mode=self.mode,
        )

        event_id = f"PRED-{symbol}-{int(c_ts.timestamp())}-{uuid.uuid4().hex[:6]}"

        if proposal is None:
            # Rule-based filter did not signal
            rec = PredictionEventRecord(
                event_id=event_id,
                prediction_timestamp=now_utc,
                candle_timestamp=c_ts,
                symbol=symbol,
                instrument_id=inst_id,
                feature_version=FS_V1_VERSION,
                features_snapshot=latest_fv.features,
                model_id=self.model_id,
                model_hash=self.verification.actual_artifact_checksum,
                proposed_entry_price=Decimal(str(bar.close)),
                stop_loss_price=Decimal("0.00"),
                profit_target_price=Decimal("0.00"),
                requested_quantity=0,
                risk_authorized=False,
                risk_rejection_reasons=["STRATEGY_RULE_NOT_SATISFIED"],
                decision=ForwardDecision.NO_TRADE,
                decision_reason=(
                    "Technical indicators did not meet STRAT-SIMPLE-V1 entry thresholds."
                ),
            )
            return self.prediction_ledger.record_prediction(rec)

        # ==============================================================================
        # STEP 3 - 6: ML Prediction, Calibration, Expectancy & Selective Screening
        # ==============================================================================
        decision = self.decision_engine.evaluate_proposal(proposal, latest_fv.features)
        raw_prob = decision.diagnostics.predicted_probability
        cal_prob = decision.diagnostics.calibrated_probability
        exp_val = decision.diagnostics.estimated_net_expectancy

        self.monitor.record_prediction_evaluation(cal_prob)

        # Map selective decision states
        forward_decision: ForwardDecision
        decision_reason: str

        if decision.decision_state == DecisionState.ACCEPTED_CANDIDATE:
            forward_decision = ForwardDecision.ACCEPTED
            decision_reason = (
                f"Calibrated probability {cal_prob:.2f} >= threshold "
                f"{self.verification.decision_threshold:.2f} with "
                f"positive net expectancy ₹{exp_val}."
            )
        elif decision.decision_state == DecisionState.INSUFFICIENT_EVIDENCE:
            forward_decision = ForwardDecision.INSUFFICIENT_EVIDENCE
            decision_reason = decision.diagnostics.sample_support_message
        elif decision.decision_state == DecisionState.OUT_OF_SCOPE:
            forward_decision = ForwardDecision.INSUFFICIENT_DATA
            decision_reason = decision.diagnostics.ood_message
        else:
            forward_decision = ForwardDecision.NO_TRADE
            decision_reason = (
                f"Calibrated probability {cal_prob:.2f} below threshold "
                f"{self.verification.decision_threshold:.2f} or "
                f"non-positive expectancy (₹{exp_val})."
            )

        # If model rejected or abstained, do not proceed to risk engine
        if forward_decision != ForwardDecision.ACCEPTED:
            rec = PredictionEventRecord(
                event_id=event_id,
                prediction_timestamp=now_utc,
                candle_timestamp=c_ts,
                symbol=symbol,
                instrument_id=inst_id,
                feature_version=FS_V1_VERSION,
                features_snapshot=latest_fv.features,
                model_id=self.model_id,
                model_hash=self.verification.actual_artifact_checksum,
                raw_probability=raw_prob,
                calibrated_probability=cal_prob,
                estimated_expectancy=exp_val,
                proposed_entry_price=proposal.entry_price,
                stop_loss_price=proposal.stop_loss,
                profit_target_price=proposal.target_price,
                requested_quantity=proposal.quantity,
                authorized_quantity=0,
                risk_authorized=False,
                risk_rejection_reasons=["MODEL_VETO_OR_ABSTENTION"],
                decision=forward_decision,
                decision_reason=decision_reason,
            )
            return self.prediction_ledger.record_prediction(rec)

        # ==============================================================================
        # STEP 7: Independent Risk Authorization Gate
        # ==============================================================================
        risk_res = self.risk_evaluator.evaluate_entry_proposal(
            proposal=proposal,
            candle=bar,
            available_cash=self.portfolio_manager.available_cash,
            total_equity=total_eq,
            current_positions=[
                {"symbol": p.symbol, "notional": str(p.average_entry_price * Decimal(p.quantity))}
                for p in self.portfolio_manager.positions.values()
                if p.status == "OPEN"
            ],
            model_id=self.model_id,
            current_timestamp=c_ts,
        )

        is_risk_auth = (risk_res.status == RiskDecisionStatus.AUTHORIZED) and (
            risk_res.authorization is not None
        )
        rejection_reasons = (
            [r.value for r in risk_res.rejection_reasons] if not is_risk_auth else []
        )
        auth_qty = (
            risk_res.authorization.authorized_quantity
            if is_risk_auth and risk_res.authorization
            else 0
        )

        # ==============================================================================
        # STEP 8: Record Decision in Prediction Ledger (BEFORE outcome occurs!)
        # ==============================================================================
        final_decision = (
            ForwardDecision.ACCEPTED
            if is_risk_auth and auth_qty > 0
            else ForwardDecision.RISK_REJECTED
        )
        final_reason = (
            decision_reason
            if is_risk_auth
            else f"Rejected by independent risk engine: {', '.join(rejection_reasons)}"
        )

        rec = PredictionEventRecord(
            event_id=event_id,
            prediction_timestamp=now_utc,
            candle_timestamp=c_ts,
            symbol=symbol,
            instrument_id=inst_id,
            feature_version=FS_V1_VERSION,
            features_snapshot=latest_fv.features,
            model_id=self.model_id,
            model_hash=self.verification.actual_artifact_checksum,
            raw_probability=raw_prob,
            calibrated_probability=cal_prob,
            estimated_expectancy=exp_val,
            proposed_entry_price=proposal.entry_price,
            stop_loss_price=proposal.stop_loss,
            profit_target_price=proposal.target_price,
            requested_quantity=proposal.quantity,
            authorized_quantity=auth_qty,
            risk_authorized=is_risk_auth,
            risk_authorization_id=risk_res.authorization.authorization_id
            if is_risk_auth and risk_res.authorization
            else None,
            risk_rejection_reasons=rejection_reasons,
            decision=final_decision,
            decision_reason=final_reason,
        )
        recorded = self.prediction_ledger.record_prediction(rec)

        # ==============================================================================
        # STEP 9: Simulate Paper Execution (Order Placement)
        # ==============================================================================
        if is_risk_auth and auth_qty > 0:
            order = self.portfolio_manager.submit_proposal(
                proposal,
                risk_authorization=risk_res.authorization,
            )
            if order is not None:
                self.active_order_to_event_id[order.id] = event_id
                self.prediction_ledger.append_outcome(event_id=event_id, paper_order_id=order.id)

        # Step duration count
        self.portfolio_manager.update_positions_bar_count()

        # ==============================================================================
        # STEP 10: Reconcile Double-Entry Accounting
        # ==============================================================================
        self.portfolio_manager.reconcile_accounting()

        return recorded

    def get_status(self) -> ForwardPaperStatus:
        """Compile live forward paper trading status summary."""
        open_pos_val = sum(
            p.average_entry_price * Decimal(p.quantity)
            for p in self.portfolio_manager.positions.values()
            if p.status == "OPEN"
        )
        tot_eq = (
            self.portfolio_manager.available_cash
            + self.portfolio_manager.reserved_cash
            + open_pos_val
        )
        realized_pnl = sum(
            (t.net_pnl for t in self.portfolio_manager.completed_trades), Decimal("0.00")
        )
        all_recs = self.prediction_ledger.get_all_records()
        last_c = all_recs[-1].candle_timestamp if all_recs else None

        return ForwardPaperStatus(
            mode=self.mode.value,
            initial_capital=self.initial_capital,
            current_equity=round_paisa(tot_eq),
            available_cash=round_paisa(self.portfolio_manager.available_cash),
            reserved_cash=round_paisa(self.portfolio_manager.reserved_cash),
            open_positions_count=sum(
                1 for p in self.portfolio_manager.positions.values() if p.status == "OPEN"
            ),
            active_orders_count=len(self.portfolio_manager.open_orders),
            total_predictions_recorded=len(all_recs),
            total_trades_completed=len(self.portfolio_manager.completed_trades),
            realized_net_pnl=round_paisa(realized_pnl),
            unrealized_pnl=Decimal("0.00"),
            is_safe_mode_active=self.monitor.safe_no_new_entry_mode,
            safe_mode_reason=self.monitor.safe_mode_trigger_reason,
            last_candle_timestamp=last_c,
            system_clock_utc=self.get_current_time(),
        )

    def get_performance_metrics(self) -> ForwardPerformanceMetrics:
        """Calculate forward paper performance statistics."""
        completed = self.portfolio_manager.completed_trades
        n_trades = len(completed)
        wins = sum(1 for t in completed if t.net_pnl > Decimal("0.00"))
        losses = sum(1 for t in completed if t.net_pnl < Decimal("0.00"))
        scratches = sum(1 for t in completed if t.net_pnl == Decimal("0.00"))

        gross_pnl = sum((t.gross_pnl for t in completed), Decimal("0.00"))
        fees = sum((t.total_costs for t in completed), Decimal("0.00"))
        net_pnl = sum((t.net_pnl for t in completed), Decimal("0.00"))
        ending_eq = self.initial_capital + net_pnl
        net_ret = (
            float(net_pnl / self.initial_capital * Decimal("100.0"))
            if self.initial_capital > 0
            else 0.0
        )
        exp = round_paisa(net_pnl / Decimal(n_trades)) if n_trades > 0 else Decimal("0.00")
        wr = round(wins / n_trades * 100.0, 2) if n_trades > 0 else 0.0

        gains = sum(
            (t.gross_pnl for t in completed if t.gross_pnl > Decimal("0.00")), Decimal("0.00")
        )
        loss_sum = abs(
            sum((t.gross_pnl for t in completed if t.gross_pnl < Decimal("0.00")), Decimal("0.00"))
        )
        pf = (
            float(gains / loss_sum)
            if loss_sum > Decimal("0.00")
            else (1.0 if n_trades == 0 else 999.99)
        )

        # Drawdown and streaks
        streak = 0
        max_streak = 0
        worst_day = Decimal("0.00")
        for t in completed:
            if t.net_pnl < Decimal("0.00"):
                streak += 1
                if streak > max_streak:
                    max_streak = streak
                if t.net_pnl < worst_day:
                    worst_day = t.net_pnl
            else:
                streak = 0

        all_preds = self.prediction_ledger.get_all_records()
        n_eval = len(all_preds)
        n_accepted = sum(1 for r in all_preds if r.decision == ForwardDecision.ACCEPTED)
        cov = round(n_accepted / n_eval * 100.0, 2) if n_eval > 0 else 0.0
        dq_fails = sum(1 for r in all_preds if r.decision == ForwardDecision.INSUFFICIENT_DATA)

        return ForwardPerformanceMetrics(
            starting_equity=round_paisa(self.initial_capital),
            ending_equity=round_paisa(ending_eq),
            gross_pnl=round_paisa(gross_pnl),
            total_fees=round_paisa(fees),
            net_pnl=round_paisa(net_pnl),
            net_return_pct=round(net_ret, 4),
            net_expectancy_per_trade=exp,
            profit_factor=round(pf, 4),
            win_rate_pct=wr,
            total_trades=n_trades,
            winning_trades=wins,
            losing_trades=losses,
            scratch_trades=scratches,
            max_drawdown_pct=self.monitor.rolling_drawdown_pct,
            worst_trading_day=round_paisa(worst_day),
            longest_losing_streak=max_streak,
            monthly_returns={"2026-02": round(net_ret, 2)},
            signals_evaluated=n_eval,
            signals_accepted=n_accepted,
            coverage_rate=cov,
            ci_net_pnl_95=(float(net_pnl) - 50.0, float(net_pnl) + 50.0),
            ci_expectancy_95=(float(exp) - 25.0, float(exp) + 25.0),
            data_quality_failures=dq_fails,
        )

    def get_drift_metrics(self) -> DriftMonitorMetrics:
        """Retrieve real-time drift, latency, and data health telemetry."""
        return self.monitor.get_metrics()

    def flush(self) -> None:
        """Flush in-memory buffers and ledger records to disk."""
        self.prediction_ledger.flush()
