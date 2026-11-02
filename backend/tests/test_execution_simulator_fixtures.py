"""Hand-verifiable execution simulator fixtures and edge cases (Layer 6).

Covers all 11 mandated fixtures:
1. Normal market fill (next bar open + slippage)
2. Stop gap down execution (fills at bar open, not theoretical stop)
3. Target/stop collision (same-bar ambiguity, conservative vs optimistic sensitivity)
4. Partial fill (volume participation cap)
5. Limit touch without fill (touch without penetration does not fill)
6. No liquidity (zero volume bar)
7. Duplicate event rejection
8. Causal timing / out-of-order bar
9. Two candidates competing for cash (cash reservation and deterministic priority)
10. Market close with unresolved position
11. Fee rounding & full accounting reconciliation to ₹0.01
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from finpilot.db.enums import OrderSide, OrderType
from finpilot.execution import (
    AmbiguityTreatment,
    ExecutionOrder,
    ExecutionSimulator,
    FillEvent,
    NSEEquityIntradayFeeSchedule,
    OrderRejectionReason,
    PortfolioManager,
    round_paisa,
)
from finpilot.schemas.candles import CandleBar
from finpilot.schemas.trade_policy import TradeProposal

IST = ZoneInfo("Asia/Kolkata")


def make_candle(
    symbol: str,
    hour: int,
    minute: int,
    open_p: float,
    high_p: float,
    low_p: float,
    close_p: float,
    volume: int,
    day_offset: int = 0,
) -> CandleBar:
    dt = datetime(2026, 11, 2 + day_offset, hour, minute, tzinfo=IST)
    return CandleBar(
        symbol=symbol,
        timestamp=dt,
        open=Decimal(str(open_p)),
        high=Decimal(str(high_p)),
        low=Decimal(str(low_p)),
        close=Decimal(str(close_p)),
        volume=volume,
        interval="5m",
        is_completed=True,
    )


# --- FIXTURE 1: Normal Market Fill ---
def test_fixture_1_normal_market_fill() -> None:
    simulator = ExecutionSimulator(modelled_slippage_bps=Decimal("2.0"))
    decision_bar_ts = datetime(2026, 11, 2, 9, 15, tzinfo=IST)
    next_bar_ts = datetime(2026, 11, 2, 9, 20, tzinfo=IST)

    order = ExecutionOrder(
        id="ord_norm_1",
        proposal_id="prop_norm_1",
        portfolio_id=1,
        instrument_id=101,
        symbol="RELIANCE",
        order_type=OrderType.MARKET,
        side=OrderSide.BUY,
        quantity=10,
        signal_timestamp=decision_bar_ts,
        earliest_entry_timestamp=next_bar_ts,
        expiry_timestamp=next_bar_ts + timedelta(minutes=5),
        created_at=decision_bar_ts,
    )

    # Next bar arrives: open = 2500.00
    bar = make_candle("RELIANCE", 9, 20, 2500.0, 2510.0, 2495.0, 2505.0, 1000)

    fill = simulator.evaluate_order(order, bar)
    assert fill is not None
    assert fill.order_id == "ord_norm_1"
    assert fill.fill_quantity == 10
    # Expected fill price: 2500 * (1 + 0.0002) = 2500.50
    assert fill.fill_price == Decimal("2500.50")
    assert fill.timestamp == next_bar_ts
    assert fill.is_partial is False


# --- FIXTURE 2: Stop Gap Down Execution ---
def test_fixture_2_stop_gap_down_execution() -> None:
    simulator = ExecutionSimulator()
    manager = PortfolioManager(initial_capital=Decimal("30000.00"))

    # Long position opened at 2500 with stop loss at 2450
    entry_fill = simulator.evaluate_order(
        ExecutionOrder(
            id="ord_gap_1",
            proposal_id="prop_gap_1",
            portfolio_id=1,
            instrument_id=102,
            symbol="TCS",
            order_type=OrderType.MARKET,
            side=OrderSide.BUY,
            quantity=5,
            signal_timestamp=datetime(2026, 11, 2, 9, 15, tzinfo=IST),
            earliest_entry_timestamp=datetime(2026, 11, 2, 9, 20, tzinfo=IST),
            expiry_timestamp=datetime(2026, 11, 2, 9, 25, tzinfo=IST),
            stop_loss=Decimal("2450.00"),
            target_price=Decimal("2600.00"),
            created_at=datetime(2026, 11, 2, 9, 15, tzinfo=IST),
        ),
        make_candle("TCS", 9, 20, 2500.0, 2505.0, 2495.0, 2500.0, 500),
    )
    assert entry_fill is not None
    manager.apply_fill(entry_fill)

    # Next candle gaps down sharply below stop: open = 2400.00 (below stop 2450.00!)
    gap_bar = make_candle("TCS", 9, 25, 2400.0, 2410.0, 2390.0, 2405.0, 800)

    pos = manager.positions[102]
    exit_fill, exit_reason = simulator.evaluate_position_exit(pos, gap_bar)

    assert exit_fill is not None
    assert exit_reason == "GAP_STOP"
    assert exit_fill.is_gap_fill is True
    # CRITICAL: Fills at actual gap open (2400.00), NOT theoretical stop (2450.00)
    assert exit_fill.fill_price == Decimal("2400.00")


# --- FIXTURE 3: Target/Stop Collision & Ambiguity Sensitivity ---
def test_fixture_3_same_bar_stop_target_collision_and_sensitivity() -> None:
    entry_ts = datetime(2026, 11, 2, 9, 20, tzinfo=IST)
    col_bar = make_candle("INFY", 9, 25, 1500.0, 1620.0, 1430.0, 1550.0, 1000)

    # 1. Conservative Stop-First Simulation
    sim_cons = ExecutionSimulator(
        ambiguity_treatment=AmbiguityTreatment.CONSERVATIVE_STOP_FIRST
    )
    mgr_cons = PortfolioManager()
    prop_cons = TradeProposal(
        proposal_id="p_c1",
        instrument_id=103,
        symbol="INFY",
        decision_timestamp=datetime(2026, 11, 2, 9, 15, tzinfo=IST),
        earliest_entry_timestamp=entry_ts,
        entry_price=Decimal("1500.00"),
        stop_loss=Decimal("1450.00"),
        target_price=Decimal("1600.00"),
        quantity=10,
    )
    order_cons = mgr_cons.submit_proposal(prop_cons)
    assert order_cons is not None
    entry_bar = make_candle("INFY", 9, 20, 1500.0, 1505.0, 1495.0, 1500.0, 500)
    fill_cons_entry = sim_cons.evaluate_order(order_cons, entry_bar)
    assert fill_cons_entry is not None
    mgr_cons.apply_fill(fill_cons_entry)

    pos_cons = mgr_cons.positions[103]
    exit_cons, reason_cons = sim_cons.evaluate_position_exit(pos_cons, col_bar)
    assert exit_cons is not None
    assert exit_cons.is_ambiguous_exit is True
    assert reason_cons == "STOP_LOSS"
    assert exit_cons.fill_price == Decimal("1450.00")
    mgr_cons.apply_fill(exit_cons)

    # 2. Optimistic Target-First Simulation (Sensitivity Check)
    sim_opt = ExecutionSimulator(
        ambiguity_treatment=AmbiguityTreatment.OPTIMISTIC_TARGET_FIRST
    )
    mgr_opt = PortfolioManager()
    prop_opt = TradeProposal(
        proposal_id="p_o1",
        instrument_id=103,
        symbol="INFY",
        decision_timestamp=datetime(2026, 11, 2, 9, 15, tzinfo=IST),
        earliest_entry_timestamp=entry_ts,
        entry_price=Decimal("1500.00"),
        stop_loss=Decimal("1450.00"),
        target_price=Decimal("1600.00"),
        quantity=10,
    )
    order_opt = mgr_opt.submit_proposal(prop_opt)
    assert order_opt is not None
    fill_opt_entry = sim_opt.evaluate_order(order_opt, entry_bar)
    assert fill_opt_entry is not None
    mgr_opt.apply_fill(fill_opt_entry)

    pos_opt = mgr_opt.positions[103]
    exit_opt, reason_opt = sim_opt.evaluate_position_exit(pos_opt, col_bar)
    assert exit_opt is not None
    assert exit_opt.is_ambiguous_exit is True
    assert reason_opt == "TARGET"
    assert exit_opt.fill_price == Decimal("1600.00")
    mgr_opt.apply_fill(exit_opt)

    # Compare Realized P&L outcomes between Conservative vs Optimistic
    assert mgr_cons.realized_pnl < Decimal("0")  # Loss booked under conservative stop-first
    assert mgr_opt.realized_pnl > Decimal("0")  # Profit booked under optimistic target-first


# --- FIXTURE 4: Partial Fill on Volume Participation Cap ---
def test_fixture_4_partial_fill_on_volume_participation_cap() -> None:
    # 10% max participation cap
    simulator = ExecutionSimulator(max_participation_rate=Decimal("0.10"))
    order = ExecutionOrder(
        id="ord_part_1",
        proposal_id="prop_part_1",
        portfolio_id=1,
        instrument_id=104,
        symbol="SBIN",
        order_type=OrderType.MARKET,
        side=OrderSide.BUY,
        quantity=500,  # Wants 500 shares
        signal_timestamp=datetime(2026, 11, 2, 9, 15, tzinfo=IST),
        earliest_entry_timestamp=datetime(2026, 11, 2, 9, 20, tzinfo=IST),
        expiry_timestamp=datetime(2026, 11, 2, 9, 30, tzinfo=IST),
        created_at=datetime(2026, 11, 2, 9, 15, tzinfo=IST),
    )

    # Bar volume is 2000 shares -> 10% cap = 200 shares
    bar = make_candle("SBIN", 9, 20, 800.0, 805.0, 795.0, 802.0, 2000)

    fill = simulator.evaluate_order(order, bar)
    assert fill is not None
    assert fill.is_partial is True
    assert fill.fill_quantity == 200  # Capped at 200


# --- FIXTURE 5: Limit Touch Without Fill ---
def test_fixture_5_limit_touch_without_fill() -> None:
    simulator = ExecutionSimulator()
    limit_price = Decimal("1000.00")
    order = ExecutionOrder(
        id="ord_lim_1",
        proposal_id="prop_lim_1",
        portfolio_id=1,
        instrument_id=105,
        symbol="WIPRO",
        order_type=OrderType.LIMIT,
        side=OrderSide.BUY,
        quantity=20,
        price=limit_price,
        signal_timestamp=datetime(2026, 11, 2, 9, 15, tzinfo=IST),
        earliest_entry_timestamp=datetime(2026, 11, 2, 9, 20, tzinfo=IST),
        expiry_timestamp=datetime(2026, 11, 2, 9, 35, tzinfo=IST),
        created_at=datetime(2026, 11, 2, 9, 15, tzinfo=IST),
    )

    # 1. Bar low touches 1000.00 exactly (Touch without penetration)
    touch_bar = make_candle("WIPRO", 9, 20, 1005.0, 1010.0, 1000.0, 1004.0, 1000)
    fill_touch = simulator.evaluate_order(order, touch_bar)
    # Conservative rule: Touch does NOT fill!
    assert fill_touch is None

    # 2. Subsequent bar penetrates below limit (low = 998.00)
    penetrate_bar = make_candle("WIPRO", 9, 25, 1002.0, 1005.0, 998.0, 1001.0, 1000)
    fill_penetrate = simulator.evaluate_order(order, penetrate_bar)
    assert fill_penetrate is not None
    assert fill_penetrate.fill_price == limit_price


# --- FIXTURE 6: No Liquidity Zero Volume Bar ---
def test_fixture_6_no_liquidity_zero_volume_bar() -> None:
    simulator = ExecutionSimulator()
    order = ExecutionOrder(
        id="ord_zero_1",
        proposal_id="prop_zero_1",
        portfolio_id=1,
        instrument_id=106,
        symbol="HCLTECH",
        order_type=OrderType.MARKET,
        side=OrderSide.BUY,
        quantity=10,
        signal_timestamp=datetime(2026, 11, 2, 9, 15, tzinfo=IST),
        earliest_entry_timestamp=datetime(2026, 11, 2, 9, 20, tzinfo=IST),
        expiry_timestamp=datetime(2026, 11, 2, 9, 25, tzinfo=IST),
        created_at=datetime(2026, 11, 2, 9, 15, tzinfo=IST),
    )

    zero_vol_bar = make_candle("HCLTECH", 9, 20, 1500.0, 1500.0, 1500.0, 1500.0, 0)
    assert simulator.evaluate_order(order, zero_vol_bar) is None


# --- FIXTURE 7: Duplicate Event Rejection ---
def test_fixture_7_duplicate_event_rejection() -> None:
    manager = PortfolioManager(initial_capital=Decimal("30000.00"))
    prop = TradeProposal(
        proposal_id="prop_dup_1",
        instrument_id=107,
        symbol="AXISBANK",
        decision_timestamp=datetime(2026, 11, 2, 9, 15, tzinfo=IST),
        earliest_entry_timestamp=datetime(2026, 11, 2, 9, 20, tzinfo=IST),
        entry_price=Decimal("1000.00"),
        stop_loss=Decimal("980.00"),
        target_price=Decimal("1040.00"),
        quantity=5,
    )

    ord1 = manager.submit_proposal(prop)
    assert ord1 is not None

    # Resubmitting identical proposal ID
    ord2 = manager.submit_proposal(prop)
    assert ord2 is None
    assert (prop, OrderRejectionReason.DUPLICATE_ORDER_ID) in manager.rejected_proposals


# --- FIXTURE 8: Causal Timing / Out-of-Order Bar ---
def test_fixture_8_causal_timing_and_out_of_order_bar() -> None:
    simulator = ExecutionSimulator()
    decision_ts = datetime(2026, 11, 2, 9, 20, tzinfo=IST)
    earliest_entry = datetime(2026, 11, 2, 9, 25, tzinfo=IST)

    order = ExecutionOrder(
        id="ord_causal_1",
        proposal_id="p_causal_1",
        portfolio_id=1,
        instrument_id=108,
        symbol="BAJFINANCE",
        order_type=OrderType.MARKET,
        side=OrderSide.BUY,
        quantity=2,
        signal_timestamp=decision_ts,
        earliest_entry_timestamp=earliest_entry,
        expiry_timestamp=earliest_entry + timedelta(minutes=5),
        created_at=decision_ts,
    )

    # Bar timestamp is 09:20 (same as decision bar close) -> cannot fill retroactively!
    same_bar = make_candle("BAJFINANCE", 9, 20, 7000.0, 7050.0, 6980.0, 7020.0, 500)
    assert simulator.evaluate_order(order, same_bar) is None


# --- FIXTURE 9: Two Candidates Competing for Cash ---
def test_fixture_9_two_candidates_competing_for_cash() -> None:
    manager = PortfolioManager(initial_capital=Decimal("30000.00"))
    # Candidate A requires ~₹20,000
    prop_a = TradeProposal(
        proposal_id="prop_a",
        instrument_id=109,
        symbol="CANDIDATE_A",
        decision_timestamp=datetime(2026, 11, 2, 9, 15, tzinfo=IST),
        earliest_entry_timestamp=datetime(2026, 11, 2, 9, 20, tzinfo=IST),
        entry_price=Decimal("2000.00"),
        stop_loss=Decimal("1950.00"),
        target_price=Decimal("2100.00"),
        quantity=10,  # 10 * 2000 = 20,000 + fees
    )

    # Candidate B also requires ~₹20,000
    prop_b = TradeProposal(
        proposal_id="prop_b",
        instrument_id=110,
        symbol="CANDIDATE_B",
        decision_timestamp=datetime(2026, 11, 2, 9, 15, tzinfo=IST),
        earliest_entry_timestamp=datetime(2026, 11, 2, 9, 20, tzinfo=IST),
        entry_price=Decimal("2000.00"),
        stop_loss=Decimal("1950.00"),
        target_price=Decimal("2100.00"),
        quantity=10,  # 10 * 2000 = 20,000 + fees
    )

    # Candidate A has higher score (0.9 vs 0.7)
    scores = {"prop_a": 0.9, "prop_b": 0.7}
    accepted = manager.submit_proposals_batch([prop_b, prop_a], scores=scores)

    # Only Candidate A accepted, Candidate B rejected for insufficient cash
    assert len(accepted) == 1
    assert accepted[0].proposal_id == "prop_a"
    assert len(manager.rejected_proposals) == 1
    assert manager.rejected_proposals[0][1] == OrderRejectionReason.INSUFFICIENT_CASH


# --- FIXTURE 10: Market Close with Unresolved Position ---
def test_fixture_10_market_close_with_unresolved_position() -> None:
    manager = PortfolioManager(initial_capital=Decimal("30000.00"))
    entry_fill = FillEvent(
        fill_id="f_open",
        order_id="ord_open",
        instrument_id=111,
        symbol="HAL",
        timestamp=datetime(2026, 11, 2, 10, 0, tzinfo=IST),
        fill_price=Decimal("4000.00"),
        fill_quantity=2,
        side=OrderSide.BUY,
        cost_breakdown=NSEEquityIntradayFeeSchedule().calculate_costs(
            OrderSide.BUY, Decimal("4000.00"), 2
        ),
    )
    manager.apply_fill(entry_fill)

    # Feed halts or data gap at 14:00
    last_known_bar = make_candle("HAL", 14, 0, 4100.0, 4120.0, 4080.0, 4095.0, 200)
    manager.mark_position_unresolved(111, last_known_bar)

    assert manager.positions[111].status == "UNRESOLVED"
    assert manager.positions[111].current_mark_price == Decimal("4095.00")
    # Verify ledger recorded UNRESOLVED event
    assert any(e.event_type == "POSITION_UNRESOLVED" for e in manager.ledger_events)


# --- FIXTURE 11: Fee Rounding & Full Accounting Reconciliation ---
def test_fixture_11_fee_rounding_and_full_accounting_reconciliation() -> None:
    initial_cap = Decimal("30000.00")
    manager = PortfolioManager(initial_capital=initial_cap)
    simulator = ExecutionSimulator()

    # 1. Round trip trade 1: Profit
    prop1 = TradeProposal(
        proposal_id="p_rec_1",
        instrument_id=112,
        symbol="ITC",
        decision_timestamp=datetime(2026, 11, 2, 9, 15, tzinfo=IST),
        earliest_entry_timestamp=datetime(2026, 11, 2, 9, 20, tzinfo=IST),
        entry_price=Decimal("450.00"),
        stop_loss=Decimal("440.00"),
        target_price=Decimal("470.00"),
        quantity=20,  # 20 * 450 = 9000
    )
    ord1 = manager.submit_proposal(prop1)
    assert ord1 is not None

    b1_entry = make_candle("ITC", 9, 20, 450.0, 452.0, 448.0, 451.0, 1000)
    fill1_entry = simulator.evaluate_order(ord1, b1_entry)
    assert fill1_entry is not None
    manager.apply_fill(fill1_entry)

    # Target hit on next bar
    b1_exit = make_candle("ITC", 9, 25, 460.0, 475.0, 458.0, 472.0, 1000)
    fill1_exit, _ = simulator.evaluate_position_exit(manager.positions[112], b1_exit)
    assert fill1_exit is not None
    manager.apply_fill(fill1_exit)

    # 2. Round trip trade 2: Stop Loss hit
    prop2 = TradeProposal(
        proposal_id="p_rec_2",
        instrument_id=113,
        symbol="BEL",
        decision_timestamp=datetime(2026, 11, 2, 9, 30, tzinfo=IST),
        earliest_entry_timestamp=datetime(2026, 11, 2, 9, 35, tzinfo=IST),
        entry_price=Decimal("300.00"),
        stop_loss=Decimal("290.00"),
        target_price=Decimal("320.00"),
        quantity=30,  # 30 * 300 = 9000
    )
    ord2 = manager.submit_proposal(prop2)
    assert ord2 is not None

    b2_entry = make_candle("BEL", 9, 35, 300.0, 302.0, 298.0, 301.0, 1000)
    fill2_entry = simulator.evaluate_order(ord2, b2_entry)
    assert fill2_entry is not None
    manager.apply_fill(fill2_entry)

    # Stop loss hit on next bar
    b2_exit = make_candle("BEL", 9, 40, 295.0, 296.0, 288.0, 289.0, 1000)
    fill2_exit, _ = simulator.evaluate_position_exit(manager.positions[113], b2_exit)
    assert fill2_exit is not None
    manager.apply_fill(fill2_exit)

    # 3. Verify exact paisa accounting reconciliation
    assert manager.reconcile_accounting() is True

    # Mathematical identity assertion:
    # Ending Cash == Initial Capital + Realized P&L
    expected_ending_cash = round_paisa(initial_cap + manager.realized_pnl)
    assert round_paisa(manager.available_cash) == expected_ending_cash
    assert manager.reserved_cash == Decimal("0.00")
    assert all(pos.status == "CLOSED" for pos in manager.positions.values())
