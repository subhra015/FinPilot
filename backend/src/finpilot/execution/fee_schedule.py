"""Versioned fee schedule and statutory cost calculator for NSE cash equities (Layer 6).

Governed by:
- docs/trade-policy-contract-v1.md §1 (Fee Schedule Versioning)
- ARCHITECTURE.md §1 (Server Authoritative Costs)
- Layer 6 Gate: Broker-/date-/order-specific versioned fee schedule with paisa rounding.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import ROUND_HALF_UP, Decimal
from typing import Final

from finpilot.db.enums import OrderSide
from finpilot.schemas.errors import DomainValidationError, ErrorCode
from finpilot.schemas.execution_cost import CostBreakdown

FEE_SCHEDULE_V1: Final[str] = "NSE_EQUITY_INTRADAY_V1"
PAISA: Final[Decimal] = Decimal("0.01")


def round_paisa(amount: Decimal) -> Decimal:
    """Round a monetary amount to the nearest paisa (2 decimal places) using ROUND_HALF_UP."""
    return amount.quantize(PAISA, rounding=ROUND_HALF_UP)


class BaseFeeSchedule(ABC):
    """Abstract base class for versioned transaction cost schedules."""

    @property
    @abstractmethod
    def version(self) -> str:
        """Unique version identifier for the fee schedule."""

    @abstractmethod
    def calculate_costs(
        self,
        side: OrderSide,
        price: Decimal,
        quantity: int,
        modelled_slippage_bps: Decimal = Decimal("2.0"),
    ) -> CostBreakdown:
        """Calculate complete statutory and broker transaction costs for an order."""


class NSEEquityIntradayFeeSchedule(BaseFeeSchedule):
    """Statutory and discount broker fee schedule for Indian NSE Cash Equity Intraday.

    Components:
    1. Brokerage: min(0.03% of turnover, ₹20.00) per order.
    2. STT (Securities Transaction Tax): 0.025% on SELL turnover only (Equity Intraday).
    3. Exchange Turnover Charges: 0.00297% on turnover (BUY and SELL).
    4. SEBI Turnover Fee: 0.0001% (₹10 per crore) on turnover (BUY and SELL).
    5. Stamp Duty: 0.003% on BUY turnover only.
    6. GST: 18% on (Brokerage + Exchange Charges + SEBI Turnover Fee).
    7. Modelled Slippage: Default 2 bps (0.02%) on turnover.
    All components rounded to nearest paisa (₹0.01).
    """

    def __init__(self, schedule_version: str = FEE_SCHEDULE_V1) -> None:
        if schedule_version != FEE_SCHEDULE_V1:
            raise DomainValidationError(
                f"Unsupported fee schedule version: {schedule_version!r}. "
                f"Must be {FEE_SCHEDULE_V1}.",
                field="schedule_version",
                code=ErrorCode.VALIDATION_ERROR,
            )
        self._version = schedule_version

    @property
    def version(self) -> str:
        return self._version

    def calculate_costs(
        self,
        side: OrderSide,
        price: Decimal,
        quantity: int,
        modelled_slippage_bps: Decimal = Decimal("2.0"),
    ) -> CostBreakdown:
        """Calculate exact cost breakdown with paisa rounding."""
        if quantity <= 0:
            raise DomainValidationError(
                f"Quantity must be positive integer for cost calculation: {quantity}",
                field="quantity",
                code=ErrorCode.VALIDATION_ERROR,
            )
        if price <= Decimal("0"):
            raise DomainValidationError(
                f"Price must be positive for cost calculation: {price}",
                field="price",
                code=ErrorCode.VALIDATION_ERROR,
            )

        turnover = price * Decimal(quantity)

        # 1. Brokerage: min(0.03% of turnover, ₹20)
        raw_brokerage = turnover * Decimal("0.0003")
        brokerage = min(raw_brokerage, Decimal("20.00"))
        brokerage = round_paisa(brokerage)

        # 2. STT: 0.025% on SELL only for intraday equity
        if side == OrderSide.SELL:
            stt = round_paisa(turnover * Decimal("0.00025"))
        else:
            stt = Decimal("0.00")

        # 3. Exchange charges: 0.00297% on both BUY and SELL
        exchange_charges = round_paisa(turnover * Decimal("0.0000297"))

        # 4. SEBI turnover fee: ₹10 per crore (0.0001%)
        sebi_turnover_fee = round_paisa(turnover * Decimal("0.000001"))

        # 5. Stamp duty: 0.003% on BUY only
        if side == OrderSide.BUY:
            stamp_duty = round_paisa(turnover * Decimal("0.00003"))
        else:
            stamp_duty = Decimal("0.00")

        # 6. GST: 18% on (Brokerage + Exchange Charges + SEBI Charges)
        taxable_services = brokerage + exchange_charges + sebi_turnover_fee
        gst = round_paisa(taxable_services * Decimal("0.18"))

        # 7. Modelled slippage: turnover * (slippage_bps / 10000)
        slippage_rate = modelled_slippage_bps / Decimal("10000.0")
        modelled_slippage = round_paisa(turnover * slippage_rate)

        # Total costs
        total_costs = (
            brokerage
            + stt
            + exchange_charges
            + sebi_turnover_fee
            + stamp_duty
            + gst
            + modelled_slippage
        )

        return CostBreakdown(
            brokerage=brokerage,
            stt=stt,
            exchange_charges=exchange_charges,
            sebi_turnover_fee=sebi_turnover_fee,
            stamp_duty=stamp_duty,
            gst=gst,
            modelled_slippage=modelled_slippage,
            total_costs=total_costs,
        )
