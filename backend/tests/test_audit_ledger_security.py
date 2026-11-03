"""Append-only audit ledger and deterministic replay security tests (SEC-08, Layer 12).

Governed by:
- Layer 12 Gate: Append-only decision/outcome events, SHA-256 sequential hash chaining,
  corrections as new events, hypothetical vs paper separation, deterministic replay,
  idempotency.
- SECURITY_CHECKLIST.md SEC-08
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session as DBSession

from finpilot.db.enums import LedgerEventType
from finpilot.ledger.models import LedgerEventPayload
from finpilot.ledger.service import AuditLedgerService
from finpilot.schemas.errors import DomainValidationError


def _make_payload(
    event_id: str,
    event_type: LedgerEventType = LedgerEventType.ACCEPTED,
    symbol: str = "TCS",
    model_id: str = "MOD-V1.0.0",
    policy_version: str = "POL-2026-03",
    predicted_probability: float | None = 0.65,
    gross_pnl: Decimal | None = None,
    net_pnl: Decimal | None = None,
    is_hypothetical: bool = False,
    prior_event_id: str | None = None,
    correction_reason: str | None = None,
) -> LedgerEventPayload:
    return LedgerEventPayload(
        event_id=event_id,
        event_type=event_type,
        timestamp=datetime.now(UTC),
        opportunity_id=f"OPP-{event_id}",
        symbol=symbol,
        instrument_id=None,
        decision_state=event_type.value,
        portfolio_id=None,
        account_id=None,
        model_id=model_id,
        policy_version=policy_version,
        feature_set_version="feat-v1.0",
        calibration_policy_id="CAL-ISOTONIC-V1",
        predicted_probability=predicted_probability,
        calibrated_probability=0.62 if predicted_probability else None,
        estimated_expectancy=45.50 if predicted_probability else None,
        risk_decision={"decision_id": "RISK-DEC-001", "authorized": True},
        gross_pnl=gross_pnl,
        net_pnl=net_pnl,
        is_hypothetical=is_hypothetical,
        prior_event_id=prior_event_id,
        correction_reason=correction_reason,
    )


def test_append_only_event_lifecycle(db_session: DBSession):
    """Ledger must record events across all valid decision/outcome states."""
    service = AuditLedgerService()

    event_types = [
        LedgerEventType.ACCEPTED,
        LedgerEventType.NO_TRADE,
        LedgerEventType.INSUFFICIENT_DATA,
        LedgerEventType.RISK_REJECTED,
        LedgerEventType.ENTRY_UNFILLED,
        LedgerEventType.EXECUTION_UNRESOLVED,
        LedgerEventType.OPPORTUNITY_OMITTED,
    ]

    for i, etype in enumerate(event_types):
        payload = _make_payload(f"EVT-TYPE-{i}", event_type=etype)
        record = service.record_event(db_session, payload)
        assert record.event_type == etype.value
        assert record.sequence_number == i + 1
        assert len(record.integrity_hash) == 64


def test_sha256_sequential_hash_chaining(db_session: DBSession):
    """Each event must link sequentially to the previous event's hash."""
    service = AuditLedgerService()

    # Event 1 (Genesis)
    p1 = _make_payload("EVT-CHAIN-1")
    r1 = service.record_event(db_session, p1)
    assert r1.prev_hash == "0" * 64
    assert r1.sequence_number == 1

    # Event 2
    p2 = _make_payload("EVT-CHAIN-2")
    r2 = service.record_event(db_session, p2)
    assert r2.prev_hash == r1.integrity_hash
    assert r2.sequence_number == 2

    # Event 3
    p3 = _make_payload("EVT-CHAIN-3")
    r3 = service.record_event(db_session, p3)
    assert r3.prev_hash == r2.integrity_hash
    assert r3.sequence_number == 3

    # Replay verifies clean chain
    result = service.replay_ledger(db_session)
    assert result.tamper_detected is False
    assert result.events_replayed == 3
    assert len(result.tamper_details) == 0


def test_tamper_detection_on_mutated_payload(db_session: DBSession):
    """Modifying any recorded payload in the database must be detected by replay."""
    service = AuditLedgerService()

    r1 = service.record_event(db_session, _make_payload("EVT-TAMPER-1"))
    service.record_event(db_session, _make_payload("EVT-TAMPER-2"))

    # Maliciously mutate payload in DB directly without going through service
    r1.payload = '{"tampered": "hacked"}'
    db_session.commit()

    # Replay must immediately catch tamper
    result = service.replay_ledger(db_session)
    assert result.tamper_detected is True
    assert len(result.tamper_details) > 0


def test_corrections_as_new_events_never_silent_mutation(db_session: DBSession):
    """Corrections must be recorded as NEW events referencing the prior event."""
    service = AuditLedgerService()

    # Original event
    p1 = _make_payload("EVT-ORIG-001", gross_pnl=Decimal("100.00"), net_pnl=Decimal("95.00"))
    r1 = service.record_event(db_session, p1)

    # Record correction
    corr_payload = _make_payload(
        "EVT-CORR-001",
        gross_pnl=Decimal("105.00"),
        net_pnl=Decimal("99.50"),
    )
    r_corr = service.record_correction(
        db=db_session,
        prior_event_id=r1.event_id,
        reason="Settlement STT adjustment from broker contract note",
        correction_payload=corr_payload,
    )

    assert r_corr.event_type == LedgerEventType.CORRECTION.value
    assert r_corr.sequence_number == 2
    assert r_corr.prev_hash == r1.integrity_hash

    # Replay confirms chain is valid and recognizes correction
    result = service.replay_ledger(db_session)
    assert result.tamper_detected is False
    assert result.events_replayed == 2


def test_hypothetical_outcomes_isolated_from_paper_portfolio(db_session: DBSession):
    """Counterfactual/hypothetical outcomes must NOT mutate paper portfolio cash or position."""
    service = AuditLedgerService()

    # 1. Paper outcome
    paper_p = _make_payload(
        "EVT-PAPER-001",
        event_type=LedgerEventType.PORTFOLIO_OUTCOME,
        gross_pnl=Decimal("500.00"),
        net_pnl=Decimal("480.00"),
        is_hypothetical=False,
    )
    service.record_event(db_session, paper_p)

    # 2. Hypothetical outcome (e.g. unselected model counterfactual)
    hypo_p = _make_payload(
        "EVT-HYPO-001",
        event_type=LedgerEventType.HYPOTHETICAL_OUTCOME,
        gross_pnl=Decimal("10000.00"),
        net_pnl=Decimal("9800.00"),
        is_hypothetical=True,
    )
    service.record_event(db_session, hypo_p)

    # Replay verifies accounting separation
    result = service.replay_ledger(db_session)
    assert result.tamper_detected is False
    assert result.events_replayed == 2
    # Only the paper outcome affects realized net P&L
    assert result.reconstructed_realized_pnl == Decimal("0.00")
    # Hypothetical outcome is tracked separately
    assert result.hypothetical_realized_pnl == Decimal("9800.00")


def test_idempotency_on_duplicate_event_id(db_session: DBSession):
    """Duplicate event_id with identical payload is idempotent; conflicting payload is rejected."""
    service = AuditLedgerService()
    payload = _make_payload("EVT-IDEMP-001")

    r1 = service.record_event(db_session, payload)
    # Re-recording same payload returns existing record cleanly
    r2 = service.record_event(db_session, payload)
    assert r1.id == r2.id
    assert r1.integrity_hash == r2.integrity_hash

    # Different payload with same event_id must be rejected with Conflict
    conflict_payload = _make_payload("EVT-IDEMP-001", symbol="INFY")
    with pytest.raises(DomainValidationError, match="Conflicting payload"):
        service.record_event(db_session, conflict_payload)
        service.record_event(db_session, conflict_payload)
