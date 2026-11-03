"""State machine validation for execution and ledger transitions (Layer 3).

Enforces:
- Explicit allowed transitions for OrderStatus.
- Rejection of illegal state transitions (e.g. REJECTED -> FILLED).
- Monotonic sequence numbers and hash chaining for LedgerEvent transitions.
"""

from __future__ import annotations

from typing import Final

from finpilot.db.enums import OrderStatus

from .errors import InvalidStateTransitionError

# Order state machine transition map
VALID_ORDER_TRANSITIONS: Final[dict[OrderStatus, frozenset[OrderStatus]]] = {
    OrderStatus.PENDING: frozenset(
        {
            OrderStatus.APPROVED,
            OrderStatus.REJECTED,
            OrderStatus.CANCELLED,
        }
    ),
    OrderStatus.APPROVED: frozenset(
        {
            OrderStatus.FILLED,
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.EXPIRED,
        }
    ),
    OrderStatus.PARTIALLY_FILLED: frozenset(
        {
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.EXPIRED,
        }
    ),
    # Terminal states (no outgoing transitions allowed)
    OrderStatus.FILLED: frozenset(),
    OrderStatus.REJECTED: frozenset(),
    OrderStatus.CANCELLED: frozenset(),
    OrderStatus.EXPIRED: frozenset(),
}


def validate_order_transition(
    current_status: OrderStatus | str,
    target_status: OrderStatus | str,
) -> OrderStatus:
    """Validate that transitioning from ``current_status`` to ``target_status`` is allowed.

    Raises InvalidStateTransitionError if the transition is illegal.
    """
    curr = (
        current_status
        if isinstance(current_status, OrderStatus)
        else OrderStatus(str(current_status))
    )
    target = (
        target_status if isinstance(target_status, OrderStatus) else OrderStatus(str(target_status))
    )

    if curr == target:
        return target

    allowed = VALID_ORDER_TRANSITIONS.get(curr, frozenset())
    if target not in allowed:
        raise InvalidStateTransitionError(
            current_state=curr.value,
            target_state=target.value,
            entity="Order",
        )

    return target


def validate_ledger_sequence(
    prev_sequence: int | None,
    new_sequence: int,
    prev_hash: str | None,
    incoming_prev_hash: str | None,
) -> None:
    """Validate that ledger sequence numbers increment by exactly 1 and hash chains match."""
    if prev_sequence is None:
        if new_sequence != 1:
            raise InvalidStateTransitionError(
                current_state="None (genesis)",
                target_state=f"sequence={new_sequence}",
                entity="LedgerEventSequence",
            )
        if incoming_prev_hash is not None:
            raise InvalidStateTransitionError(
                current_state="genesis",
                target_state=f"prev_hash={incoming_prev_hash}",
                entity="LedgerEventHashChain",
            )
    else:
        expected_seq = prev_sequence + 1
        if new_sequence != expected_seq:
            raise InvalidStateTransitionError(
                current_state=f"sequence={prev_sequence}",
                target_state=f"sequence={new_sequence} (expected {expected_seq})",
                entity="LedgerEventSequence",
            )
        if incoming_prev_hash != prev_hash:
            raise InvalidStateTransitionError(
                current_state=f"hash={prev_hash}",
                target_state=f"prev_hash={incoming_prev_hash}",
                entity="LedgerEventHashChain",
            )
