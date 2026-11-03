"""Append-only audit ledger service with SHA-256 hash chaining and deterministic replay (Layer 12).

Governed by:
- ARCHITECTURE.md §5
- PROJECT_SPEC.md §3, §10, §11
- SECURITY_CHECKLIST.md SEC-06, SEC-19
- Layer 12 Gate: Tamper-evident hash chaining, corrections as new records,
  separation of hypothetical outcomes, and deterministic replay.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from finpilot.db.enums import DataMode, LedgerEventType
from finpilot.db.models import LedgerEvent
from finpilot.schemas.errors import DomainValidationError, ErrorCode

from .models import LedgerEventPayload, ReplayVerificationResult

GENESIS_PREV_HASH = "0" * 64


class AuditLedgerService:
    """Production append-only ledger service with cryptographic integrity verification."""

    @staticmethod
    def canonical_json(data: dict) -> str:
        """Produce deterministic canonical JSON string (sorted keys, compact separators)."""
        return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)

    @classmethod
    def compute_integrity_hash(
        cls,
        prev_hash: str | None,
        sequence_number: int,
        event_type: str,
        timestamp_iso: str,
        canonical_payload: str,
    ) -> str:
        """Compute the deterministic SHA-256 integrity hash for an append-only ledger event."""
        p_hash = prev_hash or GENESIS_PREV_HASH
        raw = f"{p_hash}|{sequence_number}|{event_type}|{timestamp_iso}|{canonical_payload}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def record_event(
        self,
        db: DBSession,
        payload: LedgerEventPayload,
        account_id: int | None = None,
        portfolio_id: int | None = None,
    ) -> LedgerEvent:
        """Append an event to the ledger with idempotency checks and SHA-256 hash chaining.

        Idempotency:
        - If an event with the same ``event_id`` already exists with identical payload,
          returns the existing event record.
        - If an event with the same ``event_id`` exists with differing content,
          raises DomainValidationError(CONFLICT).
        """
        canonical_dict = payload.model_dump(mode="json")
        canonical_str = self.canonical_json(canonical_dict)
        ts_iso = str(canonical_dict.get("timestamp") or payload.timestamp.isoformat())

        # 1. Idempotency Check
        existing = db.execute(
            select(LedgerEvent).where(LedgerEvent.event_id == payload.event_id)
        ).scalar_one_or_none()
        if existing:
            if existing.payload == canonical_str:
                return existing
            raise DomainValidationError(
                f"Conflicting payload for existing event_id: '{payload.event_id}'",
                field="event_id",
                code=ErrorCode.CONFLICT,
            )

        # 2. Get previous event in this execution mode to maintain sequential hash chain
        last_event = (
            db.execute(
                select(LedgerEvent)
                .where(LedgerEvent.mode == payload.mode.value)
                .order_by(LedgerEvent.sequence_number.desc())
            )
            .scalars()
            .first()
        )

        next_seq = (last_event.sequence_number + 1) if last_event else 1
        prev_hash = last_event.integrity_hash if last_event else GENESIS_PREV_HASH

        # 3. Compute SHA-256 integrity hash
        integrity_hash = self.compute_integrity_hash(
            prev_hash=prev_hash,
            sequence_number=next_seq,
            event_type=payload.event_type.value,
            timestamp_iso=ts_iso,
            canonical_payload=canonical_str,
        )

        event = LedgerEvent(
            sequence_number=next_seq,
            event_id=payload.event_id,
            event_type=payload.event_type.value,
            account_id=account_id,
            portfolio_id=portfolio_id,
            instrument_id=payload.instrument_id,
            mode=payload.mode.value,
            payload=canonical_str,
            integrity_hash=integrity_hash,
            prev_hash=prev_hash,
            timestamp=payload.timestamp,
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        return event

    def record_correction(
        self,
        db: DBSession,
        prior_event_id: str,
        correction_payload: LedgerEventPayload,
        correction_reason: str = "",
        reason: str | None = None,
        account_id: int | None = None,
        portfolio_id: int | None = None,
    ) -> LedgerEvent:
        """Record an explicit CORRECTION event.

        Strict Governance Rule: Prior events are NEVER mutated in place.
        Corrections are appended as new, forward-looking audit records with explicit provenance.
        """
        effective_reason = reason or correction_reason or "Correction recorded"
        prior = db.execute(
            select(LedgerEvent).where(LedgerEvent.event_id == prior_event_id)
        ).scalar_one_or_none()
        if not prior:
            raise DomainValidationError(
                f"Cannot correct nonexistent prior event: '{prior_event_id}'",
                field="prior_event_id",
                code=ErrorCode.RESOURCE_NOT_FOUND,
            )

        # Ensure correction fields are attached
        updated_payload = correction_payload.model_copy(
            update={
                "event_type": LedgerEventType.CORRECTION,
                "prior_event_id": prior_event_id,
                "correction_reason": effective_reason,
            }
        )
        return self.record_event(
            db=db,
            payload=updated_payload,
            account_id=account_id,
            portfolio_id=portfolio_id,
        )

    def replay_ledger(
        self,
        db: DBSession,
        mode: DataMode = DataMode.HISTORICAL_REPLAY,
        portfolio_id: int | None = None,
        initial_cash: Decimal = Decimal("30000.00"),
        verify_hash_chain: bool = True,
    ) -> ReplayVerificationResult:
        r"""Deterministic replay of recorded inputs and verification of hash-chain integrity.

        Validates:
        1. Sequential hash-chain integrity ($H_n = \text{SHA256}(H_{n-1} \parallel \dots)$).
        2. Detection of any tampered payloads or broken links.
        3. Separation of hypothetical policy outcomes from actual paper portfolio ledger.
        4. Cumulative cash, positions, and net realized P&L reconstruction.
        """
        stmt = select(LedgerEvent).where(LedgerEvent.mode == mode.value)
        if portfolio_id is not None:
            stmt = stmt.where(LedgerEvent.portfolio_id == portfolio_id)
        stmt = stmt.order_by(LedgerEvent.sequence_number.asc())

        events = list(db.execute(stmt).scalars().all())

        tamper_detected = False
        tamper_details: list[str] = []
        corrections_count = 0

        current_cash = initial_cash
        positions: dict[str, int] = {}
        realized_pnl = Decimal("0.00")
        hypothetical_pnl = Decimal("0.00")

        expected_prev_hash = GENESIS_PREV_HASH

        for ev in events:
            # 1. Cryptographic Hash Chain Verification
            payload_data = json.loads(ev.payload)
            ts_iso = str(payload_data.get("timestamp") or ev.timestamp.isoformat())

            if verify_hash_chain:
                # Verify link to previous event
                if ev.prev_hash != expected_prev_hash:
                    tamper_detected = True
                    tamper_details.append(
                        f"Seq {ev.sequence_number}: prev_hash mismatch. "
                        f"Expected {expected_prev_hash[:16]}..., got {str(ev.prev_hash)[:16]}..."
                    )

                # Verify event's own integrity hash over its stored payload
                recalculated_hash = self.compute_integrity_hash(
                    prev_hash=ev.prev_hash,
                    sequence_number=ev.sequence_number,
                    event_type=ev.event_type,
                    timestamp_iso=ts_iso,
                    canonical_payload=ev.payload,
                )
                if ev.integrity_hash != recalculated_hash:
                    tamper_detected = True
                    tamper_details.append(
                        f"Seq {ev.sequence_number}: payload integrity compromised! "
                        f"Stored {ev.integrity_hash[:16]}..., computed {recalculated_hash[:16]}..."
                    )

                expected_prev_hash = ev.integrity_hash

            # 2. Replay Portfolio Accounting
            is_hypothetical = payload_data.get("is_hypothetical", False)
            symbol = payload_data.get("symbol", "")

            # Hypothetical counterfactual outcomes are separated from actual paper accounts
            if not is_hypothetical:
                if ev.event_type == LedgerEventType.FILL.value:
                    fill = payload_data.get("fill_details", {})
                    qty = int(fill.get("fill_quantity", 0))
                    price = Decimal(str(fill.get("fill_price", 0)))
                    cost = Decimal(
                        str(payload_data.get("cost_breakdown", {}).get("total_costs", 0))
                    )

                    notional = price * Decimal(qty)
                    current_cash -= notional + cost
                    positions[symbol] = positions.get(symbol, 0) + qty

                elif ev.event_type == LedgerEventType.EXIT.value:
                    exit_d = payload_data.get("exit_details", {})
                    qty = int(exit_d.get("exit_quantity", 0))
                    price = Decimal(str(exit_d.get("exit_price", 0)))
                    cost = Decimal(
                        str(payload_data.get("cost_breakdown", {}).get("total_costs", 0))
                    )
                    net_p = Decimal(str(payload_data.get("net_pnl", 0)))

                    notional = price * Decimal(qty)
                    current_cash += notional - cost
                    positions[symbol] = max(0, positions.get(symbol, 0) - qty)
                    realized_pnl += net_p

                elif ev.event_type == LedgerEventType.CORRECTION.value:
                    corrections_count += 1
                    # Apply correction balance adjustments if present
                    adj = payload_data.get("net_pnl")
                    if adj is not None:
                        realized_pnl += Decimal(str(adj))

            else:
                # Accumulate hypothetical counterfactual outcomes separately
                hypo_net = payload_data.get("net_pnl")
                if hypo_net is not None:
                    hypothetical_pnl += Decimal(str(hypo_net))

        return ReplayVerificationResult(
            is_valid=not tamper_detected,
            events_replayed=len(events),
            corrections_applied=corrections_count,
            chain_verified=verify_hash_chain,
            reconstructed_cash=current_cash,
            reconstructed_positions=positions,
            reconstructed_realized_pnl=realized_pnl,
            hypothetical_realized_pnl=hypothetical_pnl,
            tamper_detected=tamper_detected,
            tamper_details=tamper_details,
        )
