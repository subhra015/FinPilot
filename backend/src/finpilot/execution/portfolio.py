"""Portfolio state, pending cash reservations, and full ledger reconciliation (Layer 6).

Governed by:
- docs/trade-policy-contract-v1.md §2, §3
- ARCHITECTURE.md §1, §3 (Server Authoritative Ledger and Accounting)
- Layer 6 Gate: Shared cash, pending reservation, simultaneous ordering, paisa reconciliation.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any

from finpilot.db.enums import DataMode, OrderSide, OrderStatus, OrderType
from finpilot.db.models import LedgerEvent
from finpilot.schemas.candles import CandleBar
from finpilot.schemas.common import normalize_to_utc
from finpilot.schemas.errors import DomainValidationError, ErrorCode
from finpilot.schemas.trade_policy import TradeProposal

from .fee_schedule import BaseFeeSchedule, NSEEquityIntradayFeeSchedule, round_paisa
from .models import (
    ExecutionOrder,
    FillEvent,
    OrderRejectionReason,
    PortfolioState,
    PositionState,
    SimulatedTradeResult,
)


class PortfolioManager:
    """Manages cash, pending reservations, positions, order state, and append-only ledger events.

    Invariants:
    1. Cash Reservation: BUY order placement reserves estimated total capital from available cash.
    2. Shared Cash: All orders share the scenario cash pool (default ₹30,000.00).
    3. Simultaneous Signal Ordering: Deterministic priority ordering (score -> edge -> symbol).
    4. Whole Integer Quantities: No fractional shares, no shorting, no leverage.
    5. Accounting Reconciliation: Ending cash reconciles exactly to the paisa (₹0.01).
    6. Append-Only Ledger: Monotonic sequence numbers and SHA-256 hash chaining.
    """

    def __init__(
        self,
        account_id: int = 1,
        portfolio_id: int = 1,
        initial_capital: Decimal = Decimal("30000.00"),
        fee_schedule: BaseFeeSchedule | None = None,
        max_exposure_per_instrument: Decimal = Decimal("1.00"),  # Up to 100% of capital
        mode: DataMode = DataMode.HISTORICAL_REPLAY,
    ) -> None:
        self.account_id = account_id
        self.portfolio_id = portfolio_id
        self.initial_capital = initial_capital
        self.fee_schedule = fee_schedule or NSEEquityIntradayFeeSchedule()
        self.max_exposure_per_instrument = max_exposure_per_instrument
        self.mode = mode

        # Accounting state
        self.available_cash = initial_capital
        self.reserved_cash = Decimal("0.00")
        self.realized_pnl = Decimal("0.00")
        self.total_costs_paid = Decimal("0.00")

        # Operational collections
        self.positions: dict[int, PositionState] = {}
        self.open_orders: dict[str, ExecutionOrder] = {}
        self.completed_trades: list[SimulatedTradeResult] = []
        self.rejected_proposals: list[tuple[TradeProposal, OrderRejectionReason]] = []

        # Order cost tracking for entry-cost propagation to trade results
        self._order_entry_costs: dict[int, list[FillEvent]] = {}  # instrument_id -> [entry fills]
        self._order_reservations: dict[str, Decimal] = {}  # order_id -> reserved amount

        # Append-only Ledger
        self.ledger_events: list[LedgerEvent] = []
        self._last_ledger_hash: str | None = None
        self._ledger_sequence: int = 0

    def get_state(self) -> PortfolioState:
        """Return point-in-time snapshot of the portfolio state."""
        position_market_value = Decimal("0.00")
        for pos in self.positions.values():
            if pos.status == "OPEN" and pos.quantity > 0:
                position_market_value += pos.current_mark_price * Decimal(pos.quantity)

        total_equity = self.available_cash + self.reserved_cash + position_market_value

        return PortfolioState(
            account_id=self.account_id,
            portfolio_id=self.portfolio_id,
            initial_scenario_capital=self.initial_capital,
            available_cash=round_paisa(self.available_cash),
            reserved_cash=round_paisa(self.reserved_cash),
            total_equity=round_paisa(total_equity),
            positions=dict(self.positions),
            open_orders=dict(self.open_orders),
            realized_pnl=round_paisa(self.realized_pnl),
            total_costs_paid=round_paisa(self.total_costs_paid),
            mode=self.mode,
        )

    def submit_proposals_batch(
        self,
        proposals: list[TradeProposal],
        scores: dict[str, float] | None = None,
    ) -> list[ExecutionOrder]:
        """Prioritize and submit simultaneous proposals deterministically.

        Ordering rules:
        1. Higher model score / rank (descending).
        2. Higher expected profit ratio (target - entry) / (entry - stop) (descending).
        3. Symbol alphabetical order (deterministic tie-breaker).
        """
        scores_map = scores or {}

        def sort_key(p: TradeProposal) -> tuple[float, float, str]:
            score = scores_map.get(p.proposal_id, 0.0)
            risk = float(p.entry_price - p.stop_loss)
            reward = float(p.target_price - p.entry_price)
            rr_ratio = reward / risk if risk > 0 else 0.0
            # Sort score desc, rr_ratio desc, symbol asc
            return (-score, -rr_ratio, p.symbol)

        sorted_proposals = sorted(proposals, key=sort_key)
        accepted_orders: list[ExecutionOrder] = []

        for p in sorted_proposals:
            order = self.submit_proposal(p)
            if order is not None:
                accepted_orders.append(order)

        return accepted_orders

    def submit_proposal(self, proposal: TradeProposal) -> ExecutionOrder | None:
        """Submit a single trade proposal, reserving required cash.

        Rejects if duplicate, insufficient cash, or exposure cap exceeded.
        """
        # Duplicate check
        if proposal.proposal_id in [o.proposal_id for o in self.open_orders.values()]:
            self.rejected_proposals.append(
                (proposal, OrderRejectionReason.DUPLICATE_ORDER_ID)
            )
            return None

        # Existing open order on same instrument
        if any(o.instrument_id == proposal.instrument_id for o in self.open_orders.values()):
            self.rejected_proposals.append(
                (proposal, OrderRejectionReason.EXCEEDS_EXPOSURE_CAP)
            )
            return None

        # Existing open position on same instrument (re-entry only after exit)
        existing_pos = self.positions.get(proposal.instrument_id)
        if existing_pos is not None and existing_pos.status == "OPEN":
            self.rejected_proposals.append(
                (proposal, OrderRejectionReason.EXCEEDS_EXPOSURE_CAP)
            )
            return None

        # Sizing and Cash Reservation
        estimated_costs = self.fee_schedule.calculate_costs(
            side=OrderSide.BUY,
            price=proposal.entry_price,
            quantity=proposal.quantity,
        )
        total_notional = proposal.entry_price * Decimal(proposal.quantity)
        total_required_cash = round_paisa(total_notional + estimated_costs.total_costs)

        # Check Available Cash
        if total_required_cash > self.available_cash:
            self.rejected_proposals.append(
                (proposal, OrderRejectionReason.INSUFFICIENT_CASH)
            )
            self._record_ledger_event(
                event_type="PROPOSAL_REJECTED_INSUFFICIENT_CASH",
                instrument_id=proposal.instrument_id,
                payload={
                    "proposal_id": proposal.proposal_id,
                    "symbol": proposal.symbol,
                    "required_cash": str(total_required_cash),
                    "available_cash": str(self.available_cash),
                    "reason": OrderRejectionReason.INSUFFICIENT_CASH,
                },
                timestamp=proposal.decision_timestamp,
            )
            return None

        # Lock cash in pending reservation
        self.available_cash -= total_required_cash
        self.reserved_cash += total_required_cash

        # Create Execution Order
        order_id = f"ord_{proposal.proposal_id[:12]}_{uuid.uuid4().hex[:6]}"
        order = ExecutionOrder(
            id=order_id,
            proposal_id=proposal.proposal_id,
            portfolio_id=self.portfolio_id,
            instrument_id=proposal.instrument_id,
            symbol=proposal.symbol,
            order_type=OrderType.MARKET,  # TP-V1 default
            side=proposal.side,
            quantity=proposal.quantity,
            filled_quantity=0,
            price=proposal.entry_price,
            status=OrderStatus.PENDING,
            created_at=proposal.decision_timestamp,
            signal_timestamp=proposal.decision_timestamp,
            earliest_entry_timestamp=proposal.earliest_entry_timestamp,
            expiry_timestamp=proposal.earliest_entry_timestamp + timedelta(minutes=5),
            stop_loss=proposal.stop_loss,
            target_price=proposal.target_price,
            risk_authorization_id=None,
            mode=proposal.mode,
        )

        self.open_orders[order.id] = order
        self._order_reservations[order.id] = total_required_cash

        self._record_ledger_event(
            event_type="ORDER_SUBMITTED",
            instrument_id=proposal.instrument_id,
            payload={
                "order_id": order.id,
                "proposal_id": proposal.proposal_id,
                "symbol": proposal.symbol,
                "quantity": proposal.quantity,
                "reserved_cash": str(total_required_cash),
            },
            timestamp=proposal.decision_timestamp,
        )

        return order

    def apply_fill(self, fill: FillEvent) -> None:
        """Apply an executed order fill event to cash, positions, and ledger."""
        order = self.open_orders.get(fill.order_id)
        fill_turnover = round_paisa(fill.fill_price * Decimal(fill.fill_quantity))
        total_fill_cost = fill.cost_breakdown.total_costs

        if fill.side == OrderSide.BUY:
            # Release pending reservation for this fill
            reserved_portion = self._order_reservations.get(fill.order_id, Decimal("0.00"))
            self.reserved_cash -= reserved_portion
            if fill.order_id in self._order_reservations:
                del self._order_reservations[fill.order_id]

            # Deduct actual turnover and applied fees from total cash
            actual_cash_spent = fill_turnover + total_fill_cost
            # Refund difference back to available cash if actual was less than reserved
            cash_difference = reserved_portion - actual_cash_spent
            self.available_cash += cash_difference
            self.total_costs_paid += total_fill_cost

            # Update or create PositionState
            inst_id = fill.instrument_id
            if inst_id not in self.positions or self.positions[inst_id].status != "OPEN":
                stop_loss = (
                    order.stop_loss
                    if order and order.stop_loss
                    else fill.fill_price * Decimal("0.98")
                )
                target_price = (
                    order.target_price
                    if order and order.target_price
                    else fill.fill_price * Decimal("1.04")
                )
                self.positions[inst_id] = PositionState(
                    portfolio_id=self.portfolio_id,
                    instrument_id=inst_id,
                    symbol=fill.symbol,
                    quantity=fill.fill_quantity,
                    average_entry_price=fill.fill_price,
                    current_mark_price=fill.fill_price,
                    realized_pnl=Decimal("0.00"),
                    unrealized_pnl=Decimal("0.00"),
                    total_cost_accrued=total_fill_cost,
                    entry_timestamp=fill.timestamp,
                    last_update_timestamp=fill.timestamp,
                    stop_loss=stop_loss,
                    target_price=target_price,
                    max_holding_bars=75,
                    bars_held=0,
                    status="OPEN",
                    mode=fill.mode,
                )
            else:
                pos = self.positions[inst_id]
                new_qty = pos.quantity + fill.fill_quantity
                new_avg_price = (
                    (pos.average_entry_price * Decimal(pos.quantity)) + fill_turnover
                ) / Decimal(new_qty)
                self.positions[inst_id] = PositionState(
                    portfolio_id=pos.portfolio_id,
                    instrument_id=pos.instrument_id,
                    symbol=pos.symbol,
                    quantity=new_qty,
                    average_entry_price=new_avg_price,
                    current_mark_price=fill.fill_price,
                    realized_pnl=pos.realized_pnl,
                    unrealized_pnl=Decimal("0.00"),
                    total_cost_accrued=pos.total_cost_accrued + total_fill_cost,
                    entry_timestamp=pos.entry_timestamp,
                    last_update_timestamp=fill.timestamp,
                    stop_loss=pos.stop_loss,
                    target_price=pos.target_price,
                    max_holding_bars=pos.max_holding_bars,
                    bars_held=pos.bars_held,
                    status="OPEN",
                    mode=pos.mode,
                )

            # Store entry fill for trade reporting
            if inst_id not in self._order_entry_costs:
                self._order_entry_costs[inst_id] = []
            self._order_entry_costs[inst_id].append(fill)

            # Update Order status
            if order:
                new_filled = order.filled_quantity + fill.fill_quantity
                is_full = new_filled >= order.quantity
                new_status = OrderStatus.FILLED if is_full else OrderStatus.PARTIALLY_FILLED
                updated_order = ExecutionOrder(
                    id=order.id,
                    proposal_id=order.proposal_id,
                    portfolio_id=order.portfolio_id,
                    instrument_id=order.instrument_id,
                    symbol=order.symbol,
                    order_type=order.order_type,
                    side=order.side,
                    quantity=order.quantity,
                    filled_quantity=new_filled,
                    price=order.price,
                    status=new_status,
                    created_at=order.created_at,
                    signal_timestamp=order.signal_timestamp,
                    earliest_entry_timestamp=order.earliest_entry_timestamp,
                    expiry_timestamp=order.expiry_timestamp,
                    stop_loss=order.stop_loss,
                    target_price=order.target_price,
                    risk_authorization_id=order.risk_authorization_id,
                    mode=order.mode,
                )
                if new_status == OrderStatus.FILLED:
                    del self.open_orders[order.id]
                else:
                    self.open_orders[order.id] = updated_order

        elif fill.side == OrderSide.SELL:
            # Closing long position
            inst_id = fill.instrument_id
            pos_entry = self.positions.get(inst_id)
            if pos_entry is None or pos_entry.status != "OPEN":
                raise DomainValidationError(
                    f"Cannot apply SELL fill to missing or closed position for instrument "
                    f"{inst_id}.",
                    field="instrument_id",
                    code=ErrorCode.VALIDATION_ERROR,
                )
            pos = pos_entry

            # Add net sales proceeds (turnover minus exit costs) to cash
            net_proceeds = fill_turnover - total_fill_cost
            self.available_cash += net_proceeds
            self.total_costs_paid += total_fill_cost

            # Calculate Gross and Net Realized P&L
            entry_fills = self._order_entry_costs.get(inst_id, [])
            entry_costs_breakdown = (
                entry_fills[0].cost_breakdown
                if entry_fills
                else self.fee_schedule.calculate_costs(
                    side=OrderSide.BUY,
                    price=pos.average_entry_price,
                    quantity=fill.fill_quantity,
                )
            )

            entry_notional = round_paisa(pos.average_entry_price * Decimal(fill.fill_quantity))
            gross_pnl = fill_turnover - entry_notional
            total_trade_costs = entry_costs_breakdown.total_costs + total_fill_cost
            net_pnl = gross_pnl - total_trade_costs

            self.realized_pnl += net_pnl

            # Update position status
            remaining_pos_qty = pos.quantity - fill.fill_quantity
            pos_status = "CLOSED" if remaining_pos_qty <= 0 else "OPEN"

            self.positions[inst_id] = PositionState(
                portfolio_id=pos.portfolio_id,
                instrument_id=pos.instrument_id,
                symbol=pos.symbol,
                quantity=max(0, remaining_pos_qty),
                average_entry_price=pos.average_entry_price,
                current_mark_price=fill.fill_price,
                realized_pnl=pos.realized_pnl + net_pnl,
                unrealized_pnl=Decimal("0.00"),
                total_cost_accrued=pos.total_cost_accrued + total_fill_cost,
                entry_timestamp=pos.entry_timestamp,
                last_update_timestamp=fill.timestamp,
                stop_loss=pos.stop_loss,
                target_price=pos.target_price,
                max_holding_bars=pos.max_holding_bars,
                bars_held=pos.bars_held,
                status=pos_status,
                mode=pos.mode,
            )

            # Record completed trade
            entry_notional = pos.average_entry_price * Decimal(fill.fill_quantity)
            return_pct = (net_pnl / entry_notional) if entry_notional > 0 else Decimal("0.0")

            trade = SimulatedTradeResult(
                trade_id=f"tr_{uuid.uuid4().hex[:12]}",
                instrument_id=inst_id,
                symbol=fill.symbol,
                quantity=fill.fill_quantity,
                entry_timestamp=pos.entry_timestamp,
                exit_timestamp=fill.timestamp,
                entry_price=pos.average_entry_price,
                exit_price=fill.fill_price,
                exit_reason="CLOSED",
                gross_pnl=round_paisa(gross_pnl),
                entry_costs=entry_costs_breakdown,
                exit_costs=fill.cost_breakdown,
                total_costs=round_paisa(total_trade_costs),
                net_pnl=round_paisa(net_pnl),
                return_pct=Decimal(f"{return_pct:.6f}"),
                is_ambiguous_exit=fill.is_ambiguous_exit,
                ambiguity_treatment=fill.ambiguity_treatment,
                mode=fill.mode,
            )
            self.completed_trades.append(trade)

        self._record_ledger_event(
            event_type="FILL_EXECUTED",
            instrument_id=fill.instrument_id,
            payload={
                "fill_id": fill.fill_id,
                "order_id": fill.order_id,
                "symbol": fill.symbol,
                "side": fill.side.value,
                "price": str(fill.fill_price),
                "quantity": fill.fill_quantity,
                "total_costs": str(total_fill_cost),
                "is_ambiguous": fill.is_ambiguous_exit,
            },
            timestamp=fill.timestamp,
        )

    def mark_position_unresolved(self, instrument_id: int, last_bar: CandleBar) -> None:
        """Mark an open position as UNRESOLVED if session closes or feed halts without exit."""
        if instrument_id in self.positions:
            pos = self.positions[instrument_id]
            if pos.status == "OPEN":
                self.positions[instrument_id] = PositionState(
                    portfolio_id=pos.portfolio_id,
                    instrument_id=pos.instrument_id,
                    symbol=pos.symbol,
                    quantity=pos.quantity,
                    average_entry_price=pos.average_entry_price,
                    current_mark_price=Decimal(str(last_bar.close)),
                    realized_pnl=pos.realized_pnl,
                    unrealized_pnl=(
                        (Decimal(str(last_bar.close)) - pos.average_entry_price)
                        * Decimal(pos.quantity)
                    ),
                    total_cost_accrued=pos.total_cost_accrued,
                    entry_timestamp=pos.entry_timestamp,
                    last_update_timestamp=last_bar.timestamp,
                    stop_loss=pos.stop_loss,
                    target_price=pos.target_price,
                    max_holding_bars=pos.max_holding_bars,
                    bars_held=pos.bars_held,
                    status="UNRESOLVED",
                    mode=pos.mode,
                )
                self._record_ledger_event(
                    event_type="POSITION_UNRESOLVED",
                    instrument_id=instrument_id,
                    payload={
                        "symbol": pos.symbol,
                        "quantity": pos.quantity,
                        "mark_price": str(last_bar.close),
                        "reason": "FEED_HALTED_OR_EOD_UNRESOLVED",
                    },
                    timestamp=last_bar.timestamp,
                )

    def cancel_expired_order(self, order_id: str, timestamp: Any) -> None:
        """Cancel an expired order and return its reserved cash."""
        if order_id in self.open_orders:
            order = self.open_orders[order_id]
            reserved = self._order_reservations.pop(order_id, Decimal("0.00"))
            self.reserved_cash -= reserved
            self.available_cash += reserved
            del self.open_orders[order_id]

            self._record_ledger_event(
                event_type="ORDER_EXPIRED",
                instrument_id=order.instrument_id,
                payload={"order_id": order_id, "released_cash": str(reserved)},
                timestamp=normalize_to_utc(timestamp),
            )

    def update_positions_bar_count(self) -> None:
        """Increment holding duration for all open positions."""
        for inst_id, pos in list(self.positions.items()):
            if pos.status == "OPEN":
                self.positions[inst_id] = PositionState(
                    portfolio_id=pos.portfolio_id,
                    instrument_id=pos.instrument_id,
                    symbol=pos.symbol,
                    quantity=pos.quantity,
                    average_entry_price=pos.average_entry_price,
                    current_mark_price=pos.current_mark_price,
                    realized_pnl=pos.realized_pnl,
                    unrealized_pnl=pos.unrealized_pnl,
                    total_cost_accrued=pos.total_cost_accrued,
                    entry_timestamp=pos.entry_timestamp,
                    last_update_timestamp=pos.last_update_timestamp,
                    stop_loss=pos.stop_loss,
                    target_price=pos.target_price,
                    max_holding_bars=pos.max_holding_bars,
                    bars_held=pos.bars_held + 1,
                    status="OPEN",
                    mode=pos.mode,
                )

    def reconcile_accounting(self) -> bool:
        """Assert exact accounting reconciliation to the paisa (₹0.01).

        Guarantees:
        Current Cash (available + reserved) + Sum(Open Position Cost Basis)
        + Sum(Total Costs Paid) - Sum(Gross Realized P&L) == Initial Capital
        """
        open_pos_cost = sum(
            round_paisa(pos.average_entry_price * Decimal(pos.quantity))
            for pos in self.positions.values()
            if pos.status == "OPEN"
        )
        gross_realized = sum(t.gross_pnl for t in self.completed_trades)

        computed_capital = (
            self.available_cash
            + self.reserved_cash
            + open_pos_cost
            + self.total_costs_paid
            - gross_realized
        )

        diff = abs(round_paisa(computed_capital) - round_paisa(self.initial_capital))
        if diff > Decimal("0.01"):
            raise DomainValidationError(
                f"Accounting reconciliation discrepancy: computed capital {computed_capital} "
                f"differs from initial capital {self.initial_capital} by {diff} > ₹0.01",
                code=ErrorCode.VALIDATION_ERROR,
            )
        return True

    def _record_ledger_event(
        self,
        event_type: str,
        instrument_id: int | None,
        payload: dict[str, Any],
        timestamp: Any,
    ) -> LedgerEvent:
        """Create and append an immutable, hash-chained ledger event."""
        self._ledger_sequence += 1
        event_id = f"evt_{uuid.uuid4().hex}"
        norm_ts = normalize_to_utc(timestamp)
        payload_str = json.dumps(payload, sort_keys=True)

        # Integrity hash: sha256(sequence + event_id + type + payload + prev_hash)
        prev_h = self._last_ledger_hash or "GENESIS_LEDGER_HASH"
        hash_input = f"{self._ledger_sequence}:{event_id}:{event_type}:{payload_str}:{prev_h}"
        integrity_hash = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()

        event = LedgerEvent(
            sequence_number=self._ledger_sequence,
            event_id=event_id,
            event_type=event_type,
            account_id=self.account_id,
            portfolio_id=self.portfolio_id,
            instrument_id=instrument_id,
            mode=self.mode.value if hasattr(self.mode, "value") else str(self.mode),
            payload=payload_str,
            integrity_hash=integrity_hash,
            prev_hash=self._last_ledger_hash,
            timestamp=norm_ts,
        )

        self._last_ledger_hash = integrity_hash
        self.ledger_events.append(event)
        return event
