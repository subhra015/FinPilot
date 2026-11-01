"""State transition validation tests for orders and ledger events (Layer 3)."""

from __future__ import annotations

import pytest

from finpilot.db.enums import OrderStatus
from finpilot.schemas import (
    InvalidStateTransitionError,
    validate_ledger_sequence,
    validate_order_transition,
)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (OrderStatus.PENDING, OrderStatus.APPROVED),
        (OrderStatus.PENDING, OrderStatus.REJECTED),
        (OrderStatus.PENDING, OrderStatus.CANCELLED),
        (OrderStatus.APPROVED, OrderStatus.FILLED),
        (OrderStatus.APPROVED, OrderStatus.PARTIALLY_FILLED),
        (OrderStatus.APPROVED, OrderStatus.CANCELLED),
        (OrderStatus.APPROVED, OrderStatus.EXPIRED),
        (OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED),
        (OrderStatus.PARTIALLY_FILLED, OrderStatus.CANCELLED),
        (OrderStatus.PARTIALLY_FILLED, OrderStatus.EXPIRED),
    ],
)
def test_valid_order_transitions_succeed(
    current: OrderStatus, target: OrderStatus
) -> None:
    result = validate_order_transition(current, target)
    assert result == target


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (OrderStatus.PENDING, OrderStatus.FILLED),  # Cannot jump approval
        (OrderStatus.PENDING, OrderStatus.PARTIALLY_FILLED),  # Cannot partially fill unapproved
        (OrderStatus.REJECTED, OrderStatus.APPROVED),  # Terminal state
        (OrderStatus.CANCELLED, OrderStatus.APPROVED),  # Terminal state
        (OrderStatus.FILLED, OrderStatus.PENDING),  # Cannot reopen filled order
        (OrderStatus.FILLED, OrderStatus.CANCELLED),  # Cannot cancel filled order
        (OrderStatus.EXPIRED, OrderStatus.FILLED),  # Terminal state
        (OrderStatus.EXPIRED, OrderStatus.APPROVED),  # Terminal state
    ],
)
def test_invalid_order_transitions_rejected(
    current: OrderStatus, target: OrderStatus
) -> None:
    with pytest.raises(InvalidStateTransitionError) as exc:
        validate_order_transition(current, target)
    assert f"Invalid Order state transition from '{current.value}' to '{target.value}'" in str(
        exc.value
    )


def test_valid_ledger_sequence_and_hash_chain() -> None:
    # Genesis event: seq 1, no prev_hash
    validate_ledger_sequence(
        prev_sequence=None,
        new_sequence=1,
        prev_hash=None,
        incoming_prev_hash=None,
    )

    # Chained event: seq 2, correct prev_hash
    dummy_prev_hash = "a" * 64
    validate_ledger_sequence(
        prev_sequence=1,
        new_sequence=2,
        prev_hash=dummy_prev_hash,
        incoming_prev_hash=dummy_prev_hash,
    )


def test_invalid_ledger_sequence_ordering_rejected() -> None:
    # Non-monotonic sequence (jump: 1 -> 3)
    with pytest.raises(InvalidStateTransitionError) as exc_jump:
        validate_ledger_sequence(
            prev_sequence=1,
            new_sequence=3,
            prev_hash="a" * 64,
            incoming_prev_hash="a" * 64,
        )
    assert "sequence=3" in str(exc_jump.value).lower()

    # Duplicate sequence (2 -> 2)
    with pytest.raises(InvalidStateTransitionError) as exc_dup:
        validate_ledger_sequence(
            prev_sequence=2,
            new_sequence=2,
            prev_hash="a" * 64,
            incoming_prev_hash="a" * 64,
        )
    assert "sequence=2" in str(exc_dup.value).lower()

    # Regressive sequence (3 -> 2)
    with pytest.raises(InvalidStateTransitionError) as exc_regress:
        validate_ledger_sequence(
            prev_sequence=3,
            new_sequence=2,
            prev_hash="a" * 64,
            incoming_prev_hash="a" * 64,
        )
    assert "sequence=2" in str(exc_regress.value).lower()


def test_ledger_hash_chain_mismatch_rejected() -> None:
    hash_a = "a" * 64
    hash_b = "b" * 64

    # Hash mismatch
    with pytest.raises(InvalidStateTransitionError) as exc_mismatch:
        validate_ledger_sequence(
            prev_sequence=1,
            new_sequence=2,
            prev_hash=hash_a,
            incoming_prev_hash=hash_b,
        )
    assert "hash=" in str(exc_mismatch.value).lower()

    # Missing incoming_prev_hash on non-genesis event
    with pytest.raises(InvalidStateTransitionError) as exc_missing:
        validate_ledger_sequence(
            prev_sequence=1,
            new_sequence=2,
            prev_hash=hash_a,
            incoming_prev_hash=None,
        )
    assert "hash=" in str(exc_missing.value).lower()

    # Non-empty incoming_prev_hash on genesis event
    with pytest.raises(InvalidStateTransitionError) as exc_gen_hash:
        validate_ledger_sequence(
            prev_sequence=None,
            new_sequence=1,
            prev_hash=None,
            incoming_prev_hash=hash_a,
        )
    assert "genesis" in str(exc_gen_hash.value).lower()
