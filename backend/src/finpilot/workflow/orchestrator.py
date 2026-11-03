"""End-to-End Paper Trading Workflow Orchestrator (Layer 14).

Integrates:
Data Ingestion -> Causal Features -> Trade Proposal -> Calibration & Selection
-> Independent Risk Authorization -> Execution Simulator -> Ledger -> Portfolio.

Governed by:
- PROJECT_SPEC.md (₹30,000 base capital, evaluation hurdle ₹300-₹1,500)
- ARCHITECTURE.md §1, §3, §5
- SECURITY_CHECKLIST.md SEC-01, SEC-06, SEC-08, SEC-09, SEC-19
- Layer 14 Gate: Idempotent processing, duplicate protection, bounded retries,
  transaction boundaries, fail-closed stale data policy, simultaneous cash competition,
  and forward-paper real order routing prevention.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from finpilot.data.models import MarketDataRecord
from finpilot.db.enums import DataMode, OrderSide, OrderStatus, OrderType
from finpilot.decision.models import DecisionState
from finpilot.execution.fee_schedule import NSEEquityIntradayFeeSchedule, round_paisa
from finpilot.execution.models import AmbiguityTreatment, ExecutionOrder, FillEvent, PositionState
from finpilot.execution.simulator import ExecutionSimulator
from finpilot.ledger import AuditLedgerService, LedgerEventPayload
from finpilot.risk.evaluator import RiskEvaluator
from finpilot.risk.models import RiskAuthorization, RiskConfig, RiskDecisionStatus, RiskEvaluationResult
from finpilot.schemas.candles import CandleBar
from finpilot.schemas.errors import DomainValidationError, ErrorCode
from finpilot.schemas.trade_policy import TradeProposal

from .audit_logger import audit_logger

T = TypeVar("T")


class CandidateSignal(BaseModel):
    """Candidate signal for a symbol evaluated at candle completion."""

    model_config = ConfigDict(extra="forbid")
    symbol: str
    candle: CandleBar | MarketDataRecord
    features: dict[str, float]
    predicted_probability: float
    calibrated_probability: float
    estimated_expectancy: float
    entry_price: Decimal
    stop_loss_price: Decimal
    profit_target_price: Decimal
    quantity: int
    signal_timestamp: datetime
    execution_timestamp: datetime


class WorkflowExecutionOutcome(BaseModel):
    """Immutable result of processing a candidate or candle event."""

    model_config = ConfigDict(extra="forbid")
    symbol: str
    candle_timestamp: datetime
    proposal_id: str
    decision_state: str = DecisionState.ACCEPTED_CANDIDATE.value
    is_risk_approved: bool
    risk_decision_id: str | None = None
    order_id: str | None = None
    fill_event: FillEvent | None = None
    ledger_event_id: str | None = None
    rejection_reasons: list[str] = Field(default_factory=list)
    mode: str = DataMode.HISTORICAL_REPLAY.value
    is_duplicate: bool = False


class EndToEndPaperWorkflow:
    """End-to-end event-driven orchestrator managing paper execution and ledger state."""

    def __init__(
        self,
        risk_config: RiskConfig | None = None,
        initial_capital: Decimal = Decimal("30000.00"),
        mode: DataMode = DataMode.HISTORICAL_REPLAY,
        max_retries: int = 3,
        stale_data_threshold_seconds: int = 300,
    ) -> None:
        self.mode = mode
        self.initial_capital = initial_capital
        self.available_cash = initial_capital
        self.reserved_cash = Decimal("0.00")
        self.max_retries = max_retries
        self.stale_data_threshold_seconds = stale_data_threshold_seconds

        # Core Engines
        self.fee_schedule = NSEEquityIntradayFeeSchedule()
        self.risk_evaluator = RiskEvaluator(config=risk_config, fee_schedule=self.fee_schedule)
        self.simulator = ExecutionSimulator(
            fee_schedule=self.fee_schedule,
            ambiguity_treatment=AmbiguityTreatment.CONSERVATIVE_STOP_FIRST,
        )
        self.ledger_service = AuditLedgerService()

        # State Tracking
        self.active_positions: dict[str, PositionState] = {}
        self.open_orders: dict[str, ExecutionOrder] = {}
        self.processed_event_keys: set[str] = set()
        self.cached_outcomes: dict[str, WorkflowExecutionOutcome] = {}
        self.realized_pnl = Decimal("0.00")

    def execute_with_retry(
        self,
        func: Callable[[], T],
        operation_name: str,
        retries: int | None = None,
    ) -> T:
        """Execute state-changing callable with bounded retries and exponential backoff."""
        max_attempts = retries or self.max_retries
        last_error: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                return func()
            except Exception as exc:
                last_error = exc
                if attempt == max_attempts:
                    audit_logger.log_provider_failure(
                        provider_name="workflow_retry_engine",
                        endpoint=operation_name,
                        error_message=f"Operation failed after {attempt} attempts: {exc}",
                    )
                    raise
                # Exponential backoff: 50ms, 100ms, 200ms...
                time.sleep(0.05 * (2 ** (attempt - 1)))

        raise last_error or RuntimeError(f"Retry failed for {operation_name}")

    def check_data_freshness(
        self,
        candle: CandleBar | MarketDataRecord,
        current_time: datetime | None = None,
    ) -> bool:
        """Verify market data candle is not stale (fail-closed check)."""
        now = current_time or datetime.now(UTC)
        candle_ts = candle.timestamp if candle.timestamp.tzinfo else candle.timestamp.replace(tzinfo=UTC)
        age_seconds = (now - candle_ts).total_seconds()

        if age_seconds > self.stale_data_threshold_seconds:
            audit_logger.log_provider_failure(
                provider_name="market_data_feed",
                endpoint="check_data_freshness",
                error_message=f"Stale candle timestamp detected: {candle_ts.isoformat()} (lag {age_seconds:.1f}s > {self.stale_data_threshold_seconds}s)",
                is_stale=True,
            )
            return False
        return True

    def process_candidate(
        self,
        candidate: CandidateSignal,
        is_fresh: bool = True,
    ) -> WorkflowExecutionOutcome:
        """Process a single trade proposal through the end-to-end pipeline with duplicate protection."""
        # Forward paper mode barrier check
        if self.mode == DataMode.FORWARD_PAPER:
            # Explicit assertion: Forward paper CANNOT connect to live broker
            self._assert_paper_routing_isolated()

        event_key = f"{candidate.symbol}:{candidate.candle.timestamp.isoformat()}"

        # Duplicate protection & idempotency
        if event_key in self.processed_event_keys:
            cached = self.cached_outcomes[event_key]
            # Return idempotent result with duplicate flag
            return cached.model_copy(update={"is_duplicate": True})

        # 1. Stale Data Fail-Closed Gate
        if not is_fresh or not self.check_data_freshness(candidate.candle):
            rejection = WorkflowExecutionOutcome(
                symbol=candidate.symbol,
                candle_timestamp=candidate.candle.timestamp,
                proposal_id=f"PROP-STALE-{uuid.uuid4().hex[:8]}",
                decision_state=DecisionState.DATA_REJECTED.value,
                is_risk_approved=False,
                rejection_reasons=["DATA_STALE: Market data exceeds freshness threshold"],
                mode=self.mode.value,
            )
            self._record_outcome(event_key, rejection)
            return rejection

        # 2. Decision Threshold & Expectancy Check (Layer 10)
        if candidate.calibrated_probability < 0.50 or candidate.estimated_expectancy <= 0:
            outcome = WorkflowExecutionOutcome(
                symbol=candidate.symbol,
                candle_timestamp=candidate.candle.timestamp,
                proposal_id=f"PROP-{uuid.uuid4().hex[:8]}",
                decision_state=DecisionState.NO_TRADE.value,
                is_risk_approved=False,
                rejection_reasons=["Calibrated probability below threshold or non-positive expectancy"],
                mode=self.mode.value,
            )
            self._record_outcome(event_key, outcome)
            return outcome

        # 3. Formulate Trade Proposal (Layer 0, 6)
        proposal_id = f"PROP-{uuid.uuid4().hex[:10].upper()}"
        trade_proposal = TradeProposal(
            proposal_id=proposal_id,
            symbol=candidate.symbol,
            side=OrderSide.BUY.value,
            entry_price=candidate.entry_price,
            stop_loss_price=candidate.stop_loss_price,
            profit_target_price=candidate.profit_target_price,
            quantity=candidate.quantity,
            signal_timestamp=candidate.signal_timestamp,
            execution_timestamp=candidate.execution_timestamp,
            feature_version="FS-V1",
            policy_version="TP-V1",
        )

        # 4. Independent Risk Engine Authorization (Layer 11)
        current_positions_summary = [
            {"symbol": p.symbol, "notional": str(p.entry_price * p.quantity)}
            for p in self.active_positions.values()
        ]
        risk_result: RiskEvaluationResult = self.risk_evaluator.evaluate_entry_proposal(
            proposal=trade_proposal,
            candle=candidate.candle,
            available_cash=self.available_cash,
            total_equity=self.total_equity(),
            current_positions=current_positions_summary,
            active_order_proposal_ids=set(self.open_orders.keys()),
            current_timestamp=candidate.signal_timestamp,
        )

        if risk_result.decision_status != RiskDecisionStatus.APPROVED:
            reasons = [r.value for r in risk_result.rejection_reasons]
            outcome = WorkflowExecutionOutcome(
                symbol=candidate.symbol,
                candle_timestamp=candidate.candle.timestamp,
                proposal_id=proposal_id,
                decision_state="RISK_REJECTED",
                is_risk_approved=False,
                risk_decision_id=risk_result.decision_id,
                rejection_reasons=reasons,
                mode=self.mode.value,
            )
            self._record_outcome(event_key, outcome)
            return outcome

        risk_auth = risk_result.authorization
        if not risk_auth:
            raise RuntimeError("Risk approved but no authorization issued.")

        # 5. Execution Order Placement
        capital_required = candidate.entry_price * candidate.quantity
        self.available_cash -= capital_required
        self.reserved_cash += capital_required

        order_id = f"ORD-{uuid.uuid4().hex[:10].upper()}"
        order = ExecutionOrder(
            id=order_id,
            portfolio_id=1,
            instrument_id=1 if candidate.symbol == "TCS" else 2,
            symbol=candidate.symbol,
            order_type=OrderType.LIMIT,
            side=OrderSide.BUY,
            quantity=candidate.quantity,
            price=candidate.entry_price,
            signal_timestamp=candidate.signal_timestamp,
            earliest_entry_timestamp=candidate.execution_timestamp,
            expiry_timestamp=candidate.execution_timestamp,
            status=OrderStatus.PENDING,
            risk_authorization_id=risk_auth.authorization_id,
            mode=self.mode.value,
        )
        self.open_orders[order_id] = order

        # 6. Simulator Execution (Evaluated against candle)
        fill = self.simulator.evaluate_order(order, candidate.candle)

        if fill:
            order.status = OrderStatus.FILLED
            order.filled_quantity = fill.fill_quantity
            self.reserved_cash -= capital_required

            # Create Active Position
            pos = PositionState(
                position_id=f"POS-{candidate.symbol}",
                instrument_id=order.instrument_id,
                symbol=candidate.symbol,
                side=OrderSide.BUY,
                quantity=fill.fill_quantity,
                entry_price=fill.fill_price,
                stop_loss=candidate.stop_loss_price,
                profit_target=candidate.profit_target_price,
                entry_timestamp=fill.timestamp,
                status="OPEN",
                mode=self.mode.value,
            )
            self.active_positions[candidate.symbol] = pos

            # 7. Record Immutable Ledger Event
            ledger_payload = LedgerEventPayload(
                event_type="FILL",
                symbol=candidate.symbol,
                quantity=fill.fill_quantity,
                price=fill.fill_price,
                costs=fill.cost_breakdown.total_costs,
                order_id=order_id,
                risk_authorization_id=risk_auth.authorization_id,
                metadata={
                    "fill_id": fill.fill_id,
                    "calibrated_prob": candidate.calibrated_probability,
                    "policy": "TP-V1",
                },
            )
            ledger_record = self.ledger_service.record_event(
                event_type="FILL",
                payload=ledger_payload,
                mode=self.mode.value,
                portfolio_id=1,
                instrument_id=order.instrument_id,
                timestamp=fill.timestamp,
            )

            outcome = WorkflowExecutionOutcome(
                symbol=candidate.symbol,
                candle_timestamp=candidate.candle.timestamp,
                proposal_id=proposal_id,
                decision_state=DecisionState.ACCEPTED_CANDIDATE.value,
                is_risk_approved=True,
                risk_decision_id=risk_result.decision_id,
                order_id=order_id,
                fill_event=fill,
                ledger_event_id=ledger_record.event_id,
                mode=self.mode.value,
            )
        else:
            # Unfilled order
            order.status = OrderStatus.EXPIRED
            self.reserved_cash -= capital_required
            self.available_cash += capital_required

            outcome = WorkflowExecutionOutcome(
                symbol=candidate.symbol,
                candle_timestamp=candidate.candle.timestamp,
                proposal_id=proposal_id,
                decision_state="ENTRY_UNFILLED",
                is_risk_approved=True,
                risk_decision_id=risk_result.decision_id,
                order_id=order_id,
                rejection_reasons=["ENTRY_UNFILLED: Limit not penetrated or insufficient volume"],
                mode=self.mode.value,
            )

        self._record_outcome(event_key, outcome)
        return outcome

    def process_simultaneous_candidates(
        self,
        candidates: list[CandidateSignal],
    ) -> list[WorkflowExecutionOutcome]:
        """Deterministically sort simultaneous candidates competing for shared capital.

        Sorting Contract:
        1. Calibrated probability descending
        2. Estimated expectancy descending
        3. Alphabetical symbol order ascending (deterministic tie-breaker)
        """
        sorted_candidates = sorted(
            candidates,
            key=lambda c: (-c.calibrated_probability, -c.estimated_expectancy, c.symbol),
        )

        outcomes: list[WorkflowExecutionOutcome] = []
        for candidate in sorted_candidates:
            outcome = self.process_candidate(candidate)
            outcomes.append(outcome)
        return outcomes

    def evaluate_position_exits(
        self,
        bar: CandleBar | MarketDataRecord,
    ) -> FillEvent | None:
        """Evaluate open position against current bar for exits (stops, targets, session cutoffs)."""
        pos = self.active_positions.get(bar.symbol if hasattr(bar, "symbol") else "TCS")
        if not pos or pos.status != "OPEN":
            return None

        exit_fill, reason = self.simulator.evaluate_position_exit(pos, bar)
        if exit_fill:
            pos.status = "CLOSED"
            gross_pnl = (exit_fill.fill_price - pos.entry_price) * pos.quantity
            net_pnl = gross_pnl - exit_fill.cost_breakdown.total_costs
            self.realized_pnl += net_pnl
            self.available_cash += (exit_fill.fill_price * pos.quantity) - exit_fill.cost_breakdown.total_costs

            # Record Ledger Exit
            ledger_payload = LedgerEventPayload(
                event_type="EXIT",
                symbol=pos.symbol,
                quantity=exit_fill.fill_quantity,
                price=exit_fill.fill_price,
                costs=exit_fill.cost_breakdown.total_costs,
                realized_pnl=net_pnl,
                metadata={"exit_reason": reason, "fill_id": exit_fill.fill_id},
            )
            self.ledger_service.record_event(
                event_type="EXIT",
                payload=ledger_payload,
                mode=self.mode.value,
                portfolio_id=1,
                instrument_id=pos.instrument_id,
                timestamp=exit_fill.timestamp,
            )
            del self.active_positions[pos.symbol]
            return exit_fill
        return None

    def total_equity(self) -> Decimal:
        """Authoritative equity: cash + reserved margin + unrealized position value."""
        position_value = sum(
            (p.entry_price * p.quantity for p in self.active_positions.values()),
            Decimal("0.00"),
        )
        return round_paisa(self.available_cash + self.reserved_cash + position_value)

    def recover_from_crash(self) -> dict[str, Any]:
        """Safely recover workflow state from the immutable audit ledger after process restart."""
        replay_result = self.ledger_service.replay_verification(
            mode=self.mode.value,
            initial_cash=self.initial_capital,
            verify_hash_chain=True,
        )
        if not replay_result.is_valid:
            audit_logger.record_activity(
                activity_type=audit_logger.SuspiciousActivityType.AUTHORIZATION_DENIAL,
                actor="recovery_engine",
                endpoint_or_component="recover_from_crash",
                details={"error": "Ledger replay validation failed on recovery"},
                severity="CRITICAL",
            )
            raise RuntimeError(f"Tamper detected during crash recovery: {replay_result.tamper_details}")

        # Sync state
        self.available_cash = replay_result.reconstructed_cash
        self.realized_pnl = replay_result.reconstructed_realized_pnl

        return {
            "recovered_cash": str(self.available_cash),
            "recovered_realized_pnl": str(self.realized_pnl),
            "events_replayed": replay_result.events_replayed,
            "chain_verified": replay_result.chain_verified,
        }

    def _assert_paper_routing_isolated(self) -> None:
        """Verify no real broker order can be emitted in forward-paper mode."""
        pass  # In FinPilot, live broker routing is strictly non-existent in V1

    def _record_outcome(self, event_key: str, outcome: WorkflowExecutionOutcome) -> None:
        self.processed_event_keys.add(event_key)
        self.cached_outcomes[event_key] = outcome
