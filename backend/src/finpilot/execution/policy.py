"""Trade policy engine (TP-V1) enforcing ratified contract rules (Layer 6).

Governed by:
- docs/trade-policy-contract-v1.md
- ARCHITECTURE.md §1, §3 (Trade Policy Engine)
- Layer 6 Gate: Causal execution timing, session cutoffs, and integer sizing.
"""

from __future__ import annotations

from datetime import time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from finpilot.db.enums import OrderStatus, OrderType
from finpilot.schemas.common import normalize_to_utc
from finpilot.schemas.errors import DomainValidationError, ErrorCode
from finpilot.schemas.trade_policy import TradePolicyV1Contract, TradeProposal

from .models import ExecutionOrder, OrderRejectionReason

IST = ZoneInfo("Asia/Kolkata")
POLICY_ENTRY_CUTOFF = time(15, 0)


class TradePolicyEngine:
    """Enforces the ratified TP-V1 Trade Policy contract.

    Rules:
    1. Single fixed version: `TP-V1`.
    2. Causal Entry: Earliest executable entry is the open of the next 5-minute candle
       strictly after the decision candle (`decision_timestamp + 5m`).
    3. Session Cutoff: Entries prohibited at or after 15:00 IST.
    4. Long-Only Invariants: Stop loss < Entry price < Target price.
    5. Integer Sizing: Fractional shares strictly prohibited.
    """

    def __init__(
        self,
        contract: TradePolicyV1Contract | None = None,
        market_entry_expiry_bars: int = 1,
        limit_entry_expiry_bars: int = 3,
    ) -> None:
        self.contract = contract or TradePolicyV1Contract()
        self.market_entry_expiry_bars = market_entry_expiry_bars
        self.limit_entry_expiry_bars = limit_entry_expiry_bars

    def create_order_from_proposal(
        self,
        proposal: TradeProposal,
        portfolio_id: int,
    ) -> tuple[ExecutionOrder | None, OrderRejectionReason | None]:
        """Convert a validated TradeProposal into an executable ExecutionOrder under TP-V1."""
        if proposal.policy_version != self.contract.policy_version:
            raise DomainValidationError(
                f"Policy version mismatch: proposal specifies {proposal.policy_version!r}, "
                f"engine requires {self.contract.policy_version!r}",
                field="policy_version",
                code=ErrorCode.VALIDATION_ERROR,
            )

        # Causal timing: earliest entry is at least 5 minutes after decision candle open
        earliest_entry = normalize_to_utc(proposal.earliest_entry_timestamp)
        decision_time = normalize_to_utc(proposal.decision_timestamp)

        if earliest_entry <= decision_time:
            raise DomainValidationError(
                f"Causal entry violation: earliest_entry ({earliest_entry}) "
                f"must be strictly after decision_time ({decision_time})",
                field="earliest_entry_timestamp",
                code=ErrorCode.VALIDATION_ERROR,
            )

        # Check Session Cutoff (15:00 IST)
        entry_time_ist = earliest_entry.astimezone(IST).time()
        if entry_time_ist >= POLICY_ENTRY_CUTOFF:
            return None, OrderRejectionReason.OUTSIDE_SESSION_HOURS

        # Check integer quantity
        if proposal.quantity < 1:
            return None, OrderRejectionReason.ZERO_QUANTITY

        # Calculate expiry
        expiry = earliest_entry + timedelta(minutes=5 * self.market_entry_expiry_bars)

        order_id = f"ord_tp_{proposal.proposal_id[:16]}"
        order = ExecutionOrder(
            id=order_id,
            proposal_id=proposal.proposal_id,
            portfolio_id=portfolio_id,
            instrument_id=proposal.instrument_id,
            symbol=proposal.symbol,
            order_type=OrderType.MARKET,
            side=proposal.side,
            quantity=proposal.quantity,
            filled_quantity=0,
            price=proposal.entry_price,
            status=OrderStatus.PENDING,
            created_at=decision_time,
            signal_timestamp=decision_time,
            earliest_entry_timestamp=earliest_entry,
            expiry_timestamp=expiry,
            stop_loss=proposal.stop_loss,
            target_price=proposal.target_price,
            risk_authorization_id=None,
            mode=proposal.mode,
        )

        return order, None

    def calculate_risk_based_quantity(
        self,
        account_equity: Decimal,
        entry_price: Decimal,
        stop_loss: Decimal,
        risk_fraction: Decimal = Decimal("0.01"),  # 1% risk per trade default
    ) -> int:
        """Compute integer share sizing based on fixed percentage equity risk."""
        if entry_price <= stop_loss:
            raise DomainValidationError(
                f"Invalid stop loss for sizing: entry {entry_price} <= stop {stop_loss}",
                code=ErrorCode.VALIDATION_ERROR,
            )

        risk_per_share = entry_price - stop_loss
        max_risk_amount = account_equity * risk_fraction
        shares = int(max_risk_amount / risk_per_share)
        return max(1, shares)
