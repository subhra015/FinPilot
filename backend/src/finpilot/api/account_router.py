"""FastAPI Router for operational accounts with ownership enforcement (SEC-01, SEC-06, Layer 12).

Governed by:
- ARCHITECTURE.md §5
- SECURITY_CHECKLIST.md SEC-01, SEC-06
- Layer 12 Gate: Authenticate private account routes; enforce object ownership to prevent IDOR.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from finpilot.db.enums import CurrencyCode, DataMode, UserRole
from finpilot.db.models import Account, User
from finpilot.schemas.errors import ResourceNotFoundError

from .dependencies import enforce_resource_ownership, get_current_user, get_db, require_csrf

router = APIRouter(prefix="/accounts", tags=["accounts"])


class AccountCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., min_length=1, max_length=100)
    initial_capital: Decimal = Field(default=Decimal("30000.00"), gt=Decimal("0.00"))
    currency: CurrencyCode = Field(default=CurrencyCode.INR)
    mode: DataMode = Field(default=DataMode.HISTORICAL_REPLAY)


class AccountResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int
    account_number: str
    name: str
    currency: str
    initial_scenario_capital: Decimal
    current_cash: Decimal
    mode: str
    is_active: bool
    user_id: int | None
    created_at: datetime


@router.get("", response_model=list[AccountResponse])
def list_accounts(
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> list[AccountResponse]:
    """List operational accounts. Users see only their own; Admins see all accounts."""
    stmt = select(Account)
    if current_user.role != UserRole.ADMIN.value:
        stmt = stmt.where(Account.user_id == current_user.id)

    accounts = list(db.execute(stmt.order_by(Account.id.asc())).scalars().all())
    return [
        AccountResponse(
            id=a.id,
            account_number=a.account_number,
            name=a.name,
            currency=a.currency,
            initial_scenario_capital=a.initial_scenario_capital,
            current_cash=a.current_cash,
            mode=a.mode,
            is_active=a.is_active,
            user_id=a.user_id,
            created_at=a.created_at,
        )
        for a in accounts
    ]


@router.post(
    "", response_model=AccountResponse, status_code=201, dependencies=[Depends(require_csrf)]
)
def create_account(
    payload: AccountCreateRequest,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> AccountResponse:
    """Create a new operational account bound to the authenticated user."""
    acc_number = f"ACC-{uuid.uuid4().hex[:8].upper()}"
    account = Account(
        user_id=current_user.id,
        account_number=acc_number,
        name=payload.name,
        currency=payload.currency.value,
        initial_scenario_capital=payload.initial_capital,
        current_cash=payload.initial_capital,
        mode=payload.mode.value,
        is_active=True,
    )
    db.add(account)
    db.commit()
    db.refresh(account)

    return AccountResponse(
        id=account.id,
        account_number=account.account_number,
        name=account.name,
        currency=account.currency,
        initial_scenario_capital=account.initial_scenario_capital,
        current_cash=account.current_cash,
        mode=account.mode,
        is_active=account.is_active,
        user_id=account.user_id,
        created_at=account.created_at,
    )


@router.get("/{account_id}", response_model=AccountResponse)
def get_account(
    account_id: int,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> AccountResponse:
    """Retrieve account details, enforcing owner check to prevent IDOR (SEC-06)."""
    account = db.execute(select(Account).where(Account.id == account_id)).scalar_one_or_none()
    if not account:
        raise ResourceNotFoundError(f"Account with ID {account_id} not found.")

    enforce_resource_ownership(account.user_id, current_user, resource_name="Account")

    return AccountResponse(
        id=account.id,
        account_number=account.account_number,
        name=account.name,
        currency=account.currency,
        initial_scenario_capital=account.initial_scenario_capital,
        current_cash=account.current_cash,
        mode=account.mode,
        is_active=account.is_active,
        user_id=account.user_id,
        created_at=account.created_at,
    )
