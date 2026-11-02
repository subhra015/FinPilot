"""Unit tests for the versioned Indian equity intraday fee schedule (Layer 6)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from finpilot.db.enums import OrderSide
from finpilot.execution.fee_schedule import (
    FEE_SCHEDULE_V1,
    NSEEquityIntradayFeeSchedule,
    round_paisa,
)
from finpilot.schemas.errors import DomainValidationError


def test_fee_schedule_version_and_rejection() -> None:
    schedule = NSEEquityIntradayFeeSchedule()
    assert schedule.version == FEE_SCHEDULE_V1

    with pytest.raises(DomainValidationError) as exc:
        NSEEquityIntradayFeeSchedule(schedule_version="INVALID_VERSION")
    assert "Unsupported fee schedule version" in str(exc.value)


def test_round_paisa_half_up() -> None:
    assert round_paisa(Decimal("10.004")) == Decimal("10.00")
    assert round_paisa(Decimal("10.005")) == Decimal("10.01")
    assert round_paisa(Decimal("10.006")) == Decimal("10.01")


def test_fee_breakdown_for_buy_order() -> None:
    schedule = NSEEquityIntradayFeeSchedule()
    # BUY: 100 shares @ ₹2500 = ₹250,000 turnover
    price = Decimal("2500.00")
    qty = 100

    costs = schedule.calculate_costs(
        side=OrderSide.BUY,
        price=price,
        quantity=qty,
        modelled_slippage_bps=Decimal("2.0"),
    )

    # 1. Brokerage: min(0.03% of 250k = ₹75, ₹20) = ₹20.00
    assert costs.brokerage == Decimal("20.00")

    # 2. STT: 0 on BUY for intraday equity
    assert costs.stt == Decimal("0.00")

    # 3. Exchange charges: 0.00297% of 250k = ₹7.425 -> ₹7.43
    assert costs.exchange_charges == Decimal("7.43")

    # 4. SEBI turnover fee: 0.0001% of 250k = ₹0.25
    assert costs.sebi_turnover_fee == Decimal("0.25")

    # 5. Stamp duty: 0.003% of 250k = ₹7.50 on BUY
    assert costs.stamp_duty == Decimal("7.50")

    # 6. GST: 18% of (20.00 + 7.43 + 0.25 = 27.68) = 4.9824 -> ₹4.98
    assert costs.gst == Decimal("4.98")

    # 7. Modelled slippage: 250,000 * 0.0002 = ₹50.00
    assert costs.modelled_slippage == Decimal("50.00")

    # Total costs: 20 + 0 + 7.43 + 0.25 + 7.50 + 4.98 + 50 = ₹90.16
    expected_total = (
        costs.brokerage
        + costs.stt
        + costs.exchange_charges
        + costs.sebi_turnover_fee
        + costs.stamp_duty
        + costs.gst
        + costs.modelled_slippage
    )
    assert costs.total_costs == expected_total
    assert costs.total_costs == Decimal("90.16")


def test_fee_breakdown_for_sell_order() -> None:
    schedule = NSEEquityIntradayFeeSchedule()
    # SELL: 100 shares @ ₹2550 = ₹255,000 turnover
    price = Decimal("2550.00")
    qty = 100

    costs = schedule.calculate_costs(
        side=OrderSide.SELL,
        price=price,
        quantity=qty,
        modelled_slippage_bps=Decimal("2.0"),
    )

    # 1. Brokerage: min(76.50, 20) = ₹20.00
    assert costs.brokerage == Decimal("20.00")

    # 2. STT: 0.025% on SELL turnover = 255,000 * 0.00025 = ₹63.75
    assert costs.stt == Decimal("63.75")

    # 3. Exchange charges: 255,000 * 0.0000297 = 7.5735 -> ₹7.57
    assert costs.exchange_charges == Decimal("7.57")

    # 4. SEBI turnover fee: 255,000 * 0.000001 = 0.255 -> ₹0.26
    assert costs.sebi_turnover_fee == Decimal("0.26")

    # 5. Stamp duty: 0 on SELL
    assert costs.stamp_duty == Decimal("0.00")

    # 6. GST: 18% of (20.00 + 7.57 + 0.26 = 27.83) = 5.0094 -> ₹5.01
    assert costs.gst == Decimal("5.01")

    # 7. Slippage: 255,000 * 0.0002 = ₹51.00
    assert costs.modelled_slippage == Decimal("51.00")

    # Total costs: 20 + 63.75 + 7.57 + 0.26 + 0 + 5.01 + 51 = ₹147.59
    assert costs.total_costs == Decimal("147.59")
