"""Append-only forward prediction ledger with separate outcome appending (Layer 16).

Governed by:
- ACCEPTANCE_GATES.md §2 (Layer 16 Gate)
- ARCHITECTURE.md §5
- PROJECT_SPEC.md §3, §10, §11
- SECURITY_CHECKLIST.md SEC-06, SEC-08, SEC-19
"""

from __future__ import annotations

import contextlib
import json
import logging
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session as DBSession

from finpilot.db.enums import DataMode, LedgerEventType
from finpilot.forward.models import ForwardDecision, PredictionEventRecord
from finpilot.ledger.models import LedgerEventPayload
from finpilot.ledger.service import AuditLedgerService
from finpilot.schemas.errors import DomainValidationError, ErrorCode, sanitize_error_message

logger = logging.getLogger(__name__)

DEFAULT_PREDICTION_LEDGER_PATH = Path("artifacts/forward/prediction_ledger.json")


class LedgerIntegrityError(DomainValidationError):
    """Raised when the prediction ledger cannot be loaded or its integrity is violated."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message=message,
            field="ledger_path",
            code=ErrorCode.VALIDATION_ERROR,
        )


class LedgerPersistenceError(DomainValidationError):
    """Raised when the prediction ledger fails to atomically persist to disk."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message=message,
            field="ledger_path",
            code=ErrorCode.INTERNAL_ERROR,
        )


class ForwardPredictionLedger:
    """Manages the append-only record of predictions and subsequent execution outcomes.

    Invariants:
    1. Pre-Outcome Recording: Every candidate is recorded *before* its outcome is known.
    2. No Overwrite: When an outcome (fill, exit, expiry) is finalized, it is appended as
       a separate event, preserving the original prediction record immutably.
    3. Idempotency: Duplicate events with the same event_id return the existing record.
    4. Crash Recovery: On startup, reconstructs pending and completed predictions from
       the persistent JSON store or database.
    """

    def __init__(
        self,
        ledger_path: Path | str = DEFAULT_PREDICTION_LEDGER_PATH,
        storage_path: Path | str | None = None,
        audit_service: AuditLedgerService | None = None,
        db: DBSession | None = None,
    ) -> None:
        self.ledger_path = Path(storage_path or ledger_path)
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self.audit_service = audit_service or AuditLedgerService()
        self.db = db
        self._records: dict[str, PredictionEventRecord] = {}
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        """Load records from disk on startup for recovery.

        Fails closed with LedgerIntegrityError if the file exists but cannot be parsed,
        ensuring corrupted or truncated persistence stores are never silently ignored.
        """
        if not self.ledger_path.exists():
            return

        try:
            with open(self.ledger_path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                raise DomainValidationError(
                    "Invalid ledger format: expected top-level JSON array of prediction records",
                    field="ledger_path",
                    code=ErrorCode.VALIDATION_ERROR,
                )
            for item in data:
                rec = PredictionEventRecord.model_validate(item)
                self._records[rec.event_id] = rec
        except Exception as exc:
            safe_err = sanitize_error_message(str(exc))
            logger.error(
                "Prediction ledger loading failed for %s: %s",
                self.ledger_path.name,
                safe_err,
            )
            raise LedgerIntegrityError(
                f"Ledger file integrity check failed at {self.ledger_path.name}: {safe_err}"
            ) from exc

    def _save_to_disk(self) -> None:
        """Persist current ledger records to disk atomically.

        Propagates LedgerPersistenceError on disk failure while safely cleaning up
        transient temporary files.
        """
        tmp_path = self.ledger_path.with_suffix(f".{uuid.uuid4().hex[:8]}.tmp")
        try:
            dumped = [rec.model_dump(mode="json") for rec in self._records.values()]
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(dumped, f, indent=2, sort_keys=True)
            tmp_path.replace(self.ledger_path)
        except Exception as exc:
            if tmp_path.exists():
                with contextlib.suppress(OSError):
                    tmp_path.unlink()
            safe_err = sanitize_error_message(str(exc))
            logger.error(
                "Prediction ledger persistence failed for %s: %s",
                self.ledger_path.name,
                safe_err,
            )
            raise LedgerPersistenceError(
                f"Failed to persist prediction ledger to {self.ledger_path.name}: {safe_err}"
            ) from exc

    def record_prediction(self, record: PredictionEventRecord) -> PredictionEventRecord:
        """Record candidate prediction event BEFORE outcome is known (Idempotent)."""
        if record.event_id in self._records:
            existing = self._records[record.event_id]
            if existing.model_dump(mode="json") == record.model_dump(mode="json"):
                return existing
            raise DomainValidationError(
                f"Conflicting payload for existing prediction event: {record.event_id}",
                field="event_id",
                code=ErrorCode.CONFLICT,
            )

        self._records[record.event_id] = record

        # Also log to append-only AuditLedgerService if DB session is available
        if self.db is not None and record.decision in (
            ForwardDecision.ACCEPTED,
            ForwardDecision.RISK_REJECTED,
            ForwardDecision.INSUFFICIENT_EVIDENCE,
        ):
            # Map decision to LedgerEventType
            ev_type = LedgerEventType.DECISION
            if record.decision == ForwardDecision.ACCEPTED:
                ev_type = LedgerEventType.ACCEPTED
            elif record.decision == ForwardDecision.INSUFFICIENT_EVIDENCE:
                ev_type = LedgerEventType.INSUFFICIENT_EVIDENCE
            elif record.decision == ForwardDecision.RISK_REJECTED:
                ev_type = LedgerEventType.RISK_REJECTED

            payload = LedgerEventPayload(
                event_id=record.event_id,
                event_type=ev_type,
                timestamp=record.prediction_timestamp,
                mode=DataMode.FORWARD_PAPER,
                opportunity_id=record.event_id,
                symbol=record.symbol,
                instrument_id=record.instrument_id,
                decision_state=record.decision.value,
                policy_version="TP-V1",
                model_id=record.model_id,
                feature_set_version=record.feature_version,
                features_snapshot=record.features_snapshot,
                predicted_probability=record.raw_probability,
                calibrated_probability=record.calibrated_probability,
                estimated_expectancy=float(record.estimated_expectancy)
                if record.estimated_expectancy
                else None,
                risk_decision={
                    "is_authorized": record.risk_authorized,
                    "authorization_id": record.risk_authorization_id,
                    "rejection_reasons": record.risk_rejection_reasons,
                },
                is_hypothetical=False,
            )
            self.audit_service.record_event(self.db, payload)

        if record.decision == ForwardDecision.ACCEPTED or len(self._records) % 25 == 0:
            self._save_to_disk()
        else:
            self._dirty = True
        return record

    def flush(self) -> None:
        """Persist all pending in-memory records to disk."""
        if getattr(self, "_dirty", False):
            self._save_to_disk()
            self._dirty = False

    def append_outcome(
        self,
        event_id: str,
        paper_order_id: str | None = None,
        fill_price: Any | None = None,
        fill_quantity: int | None = None,
        fill_timestamp: Any | None = None,
        slippage_incurred: Any | None = None,
        charges_incurred: Any | None = None,
        exit_price: Any | None = None,
        exit_timestamp: Any | None = None,
        exit_reason: str | None = None,
        gross_pnl: Any | None = None,
        net_pnl: Any | None = None,
    ) -> PredictionEventRecord:
        """Append outcome details without mutating prior prediction record fields."""
        if event_id not in self._records:
            raise DomainValidationError(
                f"Prediction event {event_id!r} not found in prediction ledger.",
                field="event_id",
                code=ErrorCode.NOT_FOUND,
            )

        prior = self._records[event_id]
        updated = prior.model_copy(
            update={
                "paper_order_id": paper_order_id
                if paper_order_id is not None
                else prior.paper_order_id,
                "fill_price": fill_price if fill_price is not None else prior.fill_price,
                "fill_quantity": fill_quantity
                if fill_quantity is not None
                else prior.fill_quantity,
                "fill_timestamp": fill_timestamp
                if fill_timestamp is not None
                else prior.fill_timestamp,
                "slippage_incurred": slippage_incurred
                if slippage_incurred is not None
                else prior.slippage_incurred,
                "charges_incurred": charges_incurred
                if charges_incurred is not None
                else prior.charges_incurred,
                "exit_price": exit_price if exit_price is not None else prior.exit_price,
                "exit_timestamp": exit_timestamp
                if exit_timestamp is not None
                else prior.exit_timestamp,
                "exit_reason": exit_reason if exit_reason is not None else prior.exit_reason,
                "gross_pnl": gross_pnl if gross_pnl is not None else prior.gross_pnl,
                "net_pnl": net_pnl if net_pnl is not None else prior.net_pnl,
            }
        )
        self._records[event_id] = updated

        # Append separate outcome event to persistent audit ledger
        if self.db is not None:
            if exit_price is not None:
                prefix = "EXIT"
                ev_type = LedgerEventType.EXIT
            elif fill_price is not None:
                prefix = "FILL"
                ev_type = LedgerEventType.FILL
            elif paper_order_id is not None:
                prefix = "ORDER"
                ev_type = LedgerEventType.ORDER_CREATED
            else:
                prefix = "OUTCOME"
                ev_type = LedgerEventType.DECISION

            outcome_payload = LedgerEventPayload(
                event_id=f"{prefix}-{event_id}",
                event_type=ev_type,
                timestamp=exit_timestamp or fill_timestamp or prior.prediction_timestamp,
                mode=DataMode.FORWARD_PAPER,
                opportunity_id=event_id,
                symbol=prior.symbol,
                instrument_id=prior.instrument_id,
                decision_state=prior.decision.value,
                policy_version="TP-V1",
                model_id=prior.model_id,
                fill_details={"fill_price": str(fill_price), "quantity": fill_quantity}
                if fill_price
                else None,
                exit_details={"exit_price": str(exit_price), "reason": exit_reason}
                if exit_price
                else None,
                cost_breakdown={"fees": str(charges_incurred), "slippage": str(slippage_incurred)},
                gross_pnl=gross_pnl,
                net_pnl=net_pnl,
                prior_event_id=event_id,
                is_hypothetical=False,
            )
            self.audit_service.record_event(self.db, outcome_payload)

        self._save_to_disk()
        return updated

    def get_all_records(self) -> list[PredictionEventRecord]:
        """Return all prediction records sorted chronologically."""
        return sorted(self._records.values(), key=lambda r: r.prediction_timestamp)

    def get_events(self, symbol: str | None = None) -> list[PredictionEventRecord]:
        """Retrieve all prediction records, optionally filtered by symbol."""
        all_recs = self.get_all_records()
        if symbol is not None:
            clean_sym = symbol.strip().upper()
            return [r for r in all_recs if r.symbol == clean_sym]
        return all_recs

    def get_record(self, event_id: str) -> PredictionEventRecord | None:
        """Retrieve single prediction record by event ID."""
        return self._records.get(event_id)

    def get_event(self, event_id: str) -> PredictionEventRecord | None:
        """Retrieve single prediction record by event ID (alias)."""
        return self.get_record(event_id)

    def __len__(self) -> int:
        return len(self._records)
