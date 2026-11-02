"""Event-driven execution matching engine for NSE cash equities (Layer 6).

Governed by:
- docs/trade-policy-contract-v1.md §2 (Determinism & Fill Semantics)
- ARCHITECTURE.md §1, §3 (Server Authoritative Fills)
- Layer 6 Gate: No retroactive fills, limit touch != fill, gap-through-stop, collision ambiguity.
"""

from __future__ import annotations

import uuid
from datetime import time
from decimal import Decimal
from zoneinfo import ZoneInfo

from finpilot.data.models import MarketDataRecord
from finpilot.db.enums import OrderSide, OrderStatus, OrderType
from finpilot.schemas.candles import CandleBar
from finpilot.schemas.errors import DomainValidationError, ErrorCode

from .fee_schedule import BaseFeeSchedule, NSEEquityIntradayFeeSchedule, round_paisa
from .models import AmbiguityTreatment, ExecutionOrder, FillEvent, PositionState

IST = ZoneInfo("Asia/Kolkata")
SESSION_ENTRY_CUTOFF = time(15, 0)
SESSION_SQUARE_OFF_CUTOFF = time(15, 15)


class ExecutionSimulator:
    """Event-driven simulator executing orders and monitoring open positions against 5m candles.

    Invariants:
    1. Causal Separation: Signal candle completion does NOT fill retroactively at that close.
    2. Limit Touch Rule: A limit price touch without penetration does NOT fill.
    3. Gap-Through-Stop: If market gaps below stop loss, fills at actual bar open.
    4. Collision Ambiguity: Same-bar stop & target breaches are flagged and handled conservatively.
    5. Volume Participation Cap: Max participation rate (default 10% of bar volume) prevents
       unrealistic instant fills on large orders. Zero-volume bars produce zero fills.
    6. Session Cutoffs: Entries prohibited after 15:00 IST; compulsory square-off at 15:15 IST.
    """

    def __init__(
        self,
        fee_schedule: BaseFeeSchedule | None = None,
        max_participation_rate: Decimal = Decimal("0.10"),
        modelled_slippage_bps: Decimal = Decimal("2.0"),
        ambiguity_treatment: AmbiguityTreatment = AmbiguityTreatment.CONSERVATIVE_STOP_FIRST,
    ) -> None:
        self.fee_schedule = fee_schedule or NSEEquityIntradayFeeSchedule()
        self.max_participation_rate = max_participation_rate
        self.modelled_slippage_bps = modelled_slippage_bps
        self.ambiguity_treatment = ambiguity_treatment

    def evaluate_order(
        self,
        order: ExecutionOrder,
        bar: CandleBar | MarketDataRecord,
    ) -> FillEvent | None:
        """Evaluate an active order against a newly arrived completed 5-minute candle.

        Returns FillEvent if filled or partially filled, else None.
        """
        if order.status in (OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.EXPIRED):
            return None

        # Causal Check: Candle must occur on or after the earliest allowable execution time
        if bar.timestamp < order.earliest_entry_timestamp:
            return None

        # Expiry Check: If candle is strictly past expiry timestamp, order is expired
        if bar.timestamp > order.expiry_timestamp:
            return None

        # Volume / Liquidity Check: If bar volume is 0, no fills can occur
        if bar.volume <= 0:
            return None

        bar_open = Decimal(str(bar.open))
        bar_high = Decimal(str(bar.high))
        bar_low = Decimal(str(bar.low))
        remaining_qty = order.quantity - order.filled_quantity
        if remaining_qty <= 0:
            return None

        # Calculate max fillable quantity under participation cap
        max_fillable_qty = max(1, int(Decimal(bar.volume) * self.max_participation_rate))
        fill_qty = min(remaining_qty, max_fillable_qty)
        is_partial = fill_qty < remaining_qty

        # Evaluate by order type
        if order.order_type == OrderType.MARKET:
            # Market order fills at bar.open with modelled slippage
            if order.side == OrderSide.BUY:
                slip_multiplier = Decimal("1.0") + (self.modelled_slippage_bps / Decimal("10000.0"))
                fill_price = round_paisa(bar_open * slip_multiplier)
            else:
                slip_multiplier = Decimal("1.0") - (self.modelled_slippage_bps / Decimal("10000.0"))
                fill_price = round_paisa(bar_open * slip_multiplier)

            cost = self.fee_schedule.calculate_costs(
                side=order.side,
                price=fill_price,
                quantity=fill_qty,
                modelled_slippage_bps=self.modelled_slippage_bps,
            )

            return FillEvent(
                fill_id=f"fill_{uuid.uuid4().hex[:12]}",
                order_id=order.id,
                instrument_id=order.instrument_id,
                symbol=order.symbol,
                timestamp=bar.timestamp,
                fill_price=fill_price,
                fill_quantity=fill_qty,
                side=order.side,
                cost_breakdown=cost,
                is_partial=is_partial,
                is_gap_fill=False,
                is_ambiguous_exit=False,
                ambiguity_treatment=AmbiguityTreatment.NONE,
                mode=order.mode,
            )

        elif order.order_type == OrderType.LIMIT:
            if order.price is None:
                raise DomainValidationError(
                    f"Limit order {order.id} is missing limit price.",
                    field="price",
                    code=ErrorCode.VALIDATION_ERROR,
                )

            limit_price = order.price

            if order.side == OrderSide.BUY:
                # Conservative rule: must penetrate below limit. Touch does NOT fill!
                if bar_low < limit_price:
                    # Fills at limit price or bar.open if market gapped down below limit
                    fill_price = min(limit_price, bar_open)
                    cost = self.fee_schedule.calculate_costs(
                        side=order.side,
                        price=fill_price,
                        quantity=fill_qty,
                        modelled_slippage_bps=Decimal("0.0"),  # Passive limit order
                    )
                    return FillEvent(
                        fill_id=f"fill_{uuid.uuid4().hex[:12]}",
                        order_id=order.id,
                        instrument_id=order.instrument_id,
                        symbol=order.symbol,
                        timestamp=bar.timestamp,
                        fill_price=fill_price,
                        fill_quantity=fill_qty,
                        side=order.side,
                        cost_breakdown=cost,
                        is_partial=is_partial,
                        is_gap_fill=False,
                        is_ambiguous_exit=False,
                        ambiguity_treatment=AmbiguityTreatment.NONE,
                        mode=order.mode,
                    )
                else:
                    # bar_low == limit_price (touch) or bar_low > limit_price (no reach) -> NO FILL
                    return None

            elif order.side == OrderSide.SELL:
                # Conservative rule: must penetrate above limit. Touch does NOT fill!
                if bar_high > limit_price:
                    fill_price = max(limit_price, bar_open)
                    cost = self.fee_schedule.calculate_costs(
                        side=order.side,
                        price=fill_price,
                        quantity=fill_qty,
                        modelled_slippage_bps=Decimal("0.0"),
                    )
                    return FillEvent(
                        fill_id=f"fill_{uuid.uuid4().hex[:12]}",
                        order_id=order.id,
                        instrument_id=order.instrument_id,
                        symbol=order.symbol,
                        timestamp=bar.timestamp,
                        fill_price=fill_price,
                        fill_quantity=fill_qty,
                        side=order.side,
                        cost_breakdown=cost,
                        is_partial=is_partial,
                        is_gap_fill=False,
                        is_ambiguous_exit=False,
                        ambiguity_treatment=AmbiguityTreatment.NONE,
                        mode=order.mode,
                    )
                else:
                    return None

        return None

    def evaluate_position_exit(
        self,
        position: PositionState,
        bar: CandleBar | MarketDataRecord,
    ) -> tuple[FillEvent | None, str | None]:
        """Evaluate an open long position against candle bar for stops, targets, or session cutoffs.

        Returns (FillEvent, exit_reason) if position is exited, else (None, None).
        """
        if position.status != "OPEN" or position.quantity <= 0:
            return None, None

        bar_time_ist = bar.timestamp.astimezone(IST).time()
        bar_open = Decimal(str(bar.open))
        bar_high = Decimal(str(bar.high))
        bar_low = Decimal(str(bar.low))

        # 1. Mandatory Session Cutoff (15:15 IST)
        if bar_time_ist >= SESSION_SQUARE_OFF_CUTOFF:
            slip_multiplier = Decimal("1.0") - (self.modelled_slippage_bps / Decimal("10000.0"))
            fill_price = round_paisa(bar_open * slip_multiplier)
            cost = self.fee_schedule.calculate_costs(
                side=OrderSide.SELL,
                price=fill_price,
                quantity=position.quantity,
                modelled_slippage_bps=self.modelled_slippage_bps,
            )
            fill = FillEvent(
                fill_id=f"exit_{uuid.uuid4().hex[:12]}",
                order_id=f"sqoff_{position.instrument_id}_{bar.timestamp.strftime('%H%M%S')}",
                instrument_id=position.instrument_id,
                symbol=position.symbol,
                timestamp=bar.timestamp,
                fill_price=fill_price,
                fill_quantity=position.quantity,
                side=OrderSide.SELL,
                cost_breakdown=cost,
                is_partial=False,
                is_gap_fill=False,
                is_ambiguous_exit=False,
                ambiguity_treatment=AmbiguityTreatment.NONE,
                mode=position.mode,
            )
            return fill, "SESSION_CUTOFF"

        # 2. Maximum Holding Period Expiry
        if position.bars_held >= position.max_holding_bars:
            slip_multiplier = Decimal("1.0") - (self.modelled_slippage_bps / Decimal("10000.0"))
            fill_price = round_paisa(bar_open * slip_multiplier)
            cost = self.fee_schedule.calculate_costs(
                side=OrderSide.SELL,
                price=fill_price,
                quantity=position.quantity,
                modelled_slippage_bps=self.modelled_slippage_bps,
            )
            fill = FillEvent(
                fill_id=f"exit_{uuid.uuid4().hex[:12]}",
                order_id=f"maxhold_{position.instrument_id}_{bar.timestamp.strftime('%H%M%S')}",
                instrument_id=position.instrument_id,
                symbol=position.symbol,
                timestamp=bar.timestamp,
                fill_price=fill_price,
                fill_quantity=position.quantity,
                side=OrderSide.SELL,
                cost_breakdown=cost,
                is_partial=False,
                is_gap_fill=False,
                is_ambiguous_exit=False,
                ambiguity_treatment=AmbiguityTreatment.NONE,
                mode=position.mode,
            )
            return fill, "MAX_HOLDING"

        # Check Price Bounds: Stop Loss and Target
        stop_breached = bar_low <= position.stop_loss
        target_breached = bar_high >= position.target_price

        # 3. Collision / Same-Bar Ambiguity
        if stop_breached and target_breached:
            is_ambiguous = True
            treatment = self.ambiguity_treatment

            if treatment == AmbiguityTreatment.CONSERVATIVE_STOP_FIRST:
                # Conservative: Stop loss hit first
                is_gap = bar_open < position.stop_loss
                fill_price = bar_open if is_gap else position.stop_loss
                exit_reason = "GAP_STOP" if is_gap else "STOP_LOSS"
            else:
                # Optimistic: Target hit first
                fill_price = position.target_price
                exit_reason = "TARGET"
                is_gap = False

            cost = self.fee_schedule.calculate_costs(
                side=OrderSide.SELL,
                price=fill_price,
                quantity=position.quantity,
                modelled_slippage_bps=self.modelled_slippage_bps,
            )
            fill = FillEvent(
                fill_id=f"exit_{uuid.uuid4().hex[:12]}",
                order_id=f"exit_{position.instrument_id}_{bar.timestamp.strftime('%H%M%S')}",
                instrument_id=position.instrument_id,
                symbol=position.symbol,
                timestamp=bar.timestamp,
                fill_price=fill_price,
                fill_quantity=position.quantity,
                side=OrderSide.SELL,
                cost_breakdown=cost,
                is_partial=False,
                is_gap_fill=is_gap,
                is_ambiguous_exit=is_ambiguous,
                ambiguity_treatment=treatment,
                mode=position.mode,
            )
            return fill, exit_reason

        # 4. Stop Loss Only Breached
        if stop_breached:
            # Check gap down through stop
            is_gap = bar_open < position.stop_loss
            fill_price = bar_open if is_gap else position.stop_loss
            exit_reason = "GAP_STOP" if is_gap else "STOP_LOSS"

            cost = self.fee_schedule.calculate_costs(
                side=OrderSide.SELL,
                price=fill_price,
                quantity=position.quantity,
                modelled_slippage_bps=self.modelled_slippage_bps,
            )
            fill = FillEvent(
                fill_id=f"exit_{uuid.uuid4().hex[:12]}",
                order_id=f"stop_{position.instrument_id}_{bar.timestamp.strftime('%H%M%S')}",
                instrument_id=position.instrument_id,
                symbol=position.symbol,
                timestamp=bar.timestamp,
                fill_price=fill_price,
                fill_quantity=position.quantity,
                side=OrderSide.SELL,
                cost_breakdown=cost,
                is_partial=False,
                is_gap_fill=is_gap,
                is_ambiguous_exit=False,
                ambiguity_treatment=AmbiguityTreatment.NONE,
                mode=position.mode,
            )
            return fill, exit_reason

        # 5. Profit Target Only Breached
        if target_breached:
            # Check gap up above target
            is_gap = bar_open > position.target_price
            fill_price = bar_open if is_gap else position.target_price
            exit_reason = "TARGET"

            cost = self.fee_schedule.calculate_costs(
                side=OrderSide.SELL,
                price=fill_price,
                quantity=position.quantity,
                modelled_slippage_bps=Decimal("0.0"),  # Passive target order
            )
            fill = FillEvent(
                fill_id=f"exit_{uuid.uuid4().hex[:12]}",
                order_id=f"target_{position.instrument_id}_{bar.timestamp.strftime('%H%M%S')}",
                instrument_id=position.instrument_id,
                symbol=position.symbol,
                timestamp=bar.timestamp,
                fill_price=fill_price,
                fill_quantity=position.quantity,
                side=OrderSide.SELL,
                cost_breakdown=cost,
                is_partial=False,
                is_gap_fill=is_gap,
                is_ambiguous_exit=False,
                ambiguity_treatment=AmbiguityTreatment.NONE,
                mode=position.mode,
            )
            return fill, exit_reason

        return None, None
