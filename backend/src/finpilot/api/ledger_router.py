"""FastAPI Router for append-only audit ledger and deterministic replay (SEC-01, SEC-06, Layer 12).

Governed by:
- ARCHITECTURE.md §5
- SECURITY_CHECKLIST.md SEC-01, SEC-06, SEC-19
- Layer 12 Gate: Append-only ledger events, idempotency, deterministic replay, hash validation.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from finpilot.db.enums import DataMode, UserRole
from finpilot.db.models import Account, LedgerEvent, Portfolio, User
from finpilot.ledger import AuditLedgerService, LedgerEventPayload, ReplayVerificationResult
from finpilot.schemas.errors import ResourceNotFoundError

from .dependencies import enforce_resource_ownership, get_current_user, get_db, require_csrf

router = APIRouter(prefix="/ledger", tags=["ledger"])
ledger_service = AuditLedgerService()


class LedgerEventResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sequence_number: int
    event_id: str
    event_type: str
    portfolio_id: int | None
    instrument_id: int | None
    mode: str
    integrity_hash: str
    prev_hash: str | None
    timestamp: datetime
    payload: dict[str, Any]


class ReplayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: DataMode = Field(default=DataMode.HISTORICAL_REPLAY)
    portfolio_id: int | None = Field(default=None)
    initial_cash: Decimal = Field(default=Decimal("30000.00"), gt=Decimal("0.00"))
    verify_hash_chain: bool = Field(default=True)


@router.get("/events", response_model=list[LedgerEventResponse])
def list_ledger_events(
    portfolio_id: int | None = Query(default=None),
    mode: DataMode = Query(default=DataMode.HISTORICAL_REPLAY),
    limit: int = Query(default=100, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> list[LedgerEventResponse]:
    """Retrieve append-only ledger events, enforcing object ownership."""
    stmt = select(LedgerEvent).where(LedgerEvent.mode == mode.value)

    if portfolio_id is not None:
        portfolio = db.execute(
            select(Portfolio).where(Portfolio.id == portfolio_id)
        ).scalar_one_or_none()
        if not portfolio:
            raise ResourceNotFoundError(f"Portfolio {portfolio_id} not found.")

        account = db.execute(
            select(Account).where(Account.id == portfolio.account_id)
        ).scalar_one_or_none()
        if not account:
            raise ResourceNotFoundError("Associated account not found.")

        enforce_resource_ownership(account.user_id, current_user, resource_name="Portfolio")
        stmt = stmt.where(LedgerEvent.portfolio_id == portfolio_id)
    elif current_user.role != UserRole.ADMIN.value:
        # Non-admins must supply a portfolio_id or be restricted to portfolios they own
        stmt = (
            stmt.join(Portfolio, LedgerEvent.portfolio_id == Portfolio.id)
            .join(Account, Portfolio.account_id == Account.id)
            .where(Account.user_id == current_user.id)
        )

    stmt = stmt.order_by(LedgerEvent.sequence_number.asc()).limit(limit)
    events = list(db.execute(stmt).scalars().all())

    return [
        LedgerEventResponse(
            sequence_number=ev.sequence_number,
            event_id=ev.event_id,
            event_type=ev.event_type,
            portfolio_id=ev.portfolio_id,
            instrument_id=ev.instrument_id,
            mode=ev.mode,
            integrity_hash=ev.integrity_hash,
            prev_hash=ev.prev_hash,
            timestamp=ev.timestamp,
            payload=json.loads(ev.payload),
        )
        for ev in events
    ]


@router.post(
    "/events",
    response_model=LedgerEventResponse,
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
def append_ledger_event(
    payload: LedgerEventPayload,
    portfolio_id: int | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> LedgerEventResponse:
    """Append a new decision/outcome event with idempotency and hash chaining."""
    account_id = None
    if portfolio_id is not None:
        portfolio = db.execute(
            select(Portfolio).where(Portfolio.id == portfolio_id)
        ).scalar_one_or_none()
        if not portfolio:
            raise ResourceNotFoundError(f"Portfolio {portfolio_id} not found.")

        account = db.execute(
            select(Account).where(Account.id == portfolio.account_id)
        ).scalar_one_or_none()
        if not account:
            raise ResourceNotFoundError("Associated account not found.")

        enforce_resource_ownership(account.user_id, current_user, resource_name="Portfolio")
        account_id = account.id

    event = ledger_service.record_event(
        db=db,
        payload=payload,
        account_id=account_id,
        portfolio_id=portfolio_id,
    )

    return LedgerEventResponse(
        sequence_number=event.sequence_number,
        event_id=event.event_id,
        event_type=event.event_type,
        portfolio_id=event.portfolio_id,
        instrument_id=event.instrument_id,
        mode=event.mode,
        integrity_hash=event.integrity_hash,
        prev_hash=event.prev_hash,
        timestamp=event.timestamp,
        payload=json.loads(event.payload),
    )


@router.post("/replay", response_model=ReplayVerificationResult)
def replay_ledger(
    request_data: ReplayRequest,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> ReplayVerificationResult:
    """Execute deterministic replay and cryptographic hash chain verification."""
    if request_data.portfolio_id is not None:
        portfolio = db.execute(
            select(Portfolio).where(Portfolio.id == request_data.portfolio_id)
        ).scalar_one_or_none()
        if not portfolio:
            raise ResourceNotFoundError(f"Portfolio {request_data.portfolio_id} not found.")

        account = db.execute(
            select(Account).where(Account.id == portfolio.account_id)
        ).scalar_one_or_none()
        if not account:
            raise ResourceNotFoundError("Associated account not found.")

        enforce_resource_ownership(account.user_id, current_user, resource_name="Portfolio")

    return ledger_service.replay_ledger(
        db=db,
        mode=request_data.mode,
        portfolio_id=request_data.portfolio_id,
        initial_cash=request_data.initial_cash,
        verify_hash_chain=request_data.verify_hash_chain,
    )
