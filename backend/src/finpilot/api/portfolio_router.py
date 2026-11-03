"""FastAPI Router for portfolios and positions with ownership checks (SEC-01, SEC-06, Layer 12).

Governed by:
- ARCHITECTURE.md §5
- SECURITY_CHECKLIST.md SEC-01, SEC-06
- Layer 12 Gate: Authenticate private portfolio routes; enforce object ownership to prevent IDOR.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from finpilot.db.enums import DataMode, UserRole
from finpilot.db.models import Account, Portfolio, Position, User
from finpilot.schemas.errors import ResourceNotFoundError

from .dependencies import enforce_resource_ownership, get_current_user, get_db, require_csrf

router = APIRouter(prefix="/portfolios", tags=["portfolios"])


class PortfolioCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: int = Field(..., ge=1)
    name: str = Field(..., min_length=1, max_length=100)
    mode: DataMode = Field(default=DataMode.HISTORICAL_REPLAY)


class PositionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int
    instrument_id: int
    quantity: int
    average_entry_price: Decimal
    current_price: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal


class PortfolioResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int
    account_id: int
    name: str
    mode: str
    created_at: datetime
    positions: list[PositionResponse] = Field(default_factory=list)


@router.get("", response_model=list[PortfolioResponse])
def list_portfolios(
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> list[PortfolioResponse]:
    """List portfolios belonging to accounts owned by the user (or all if admin)."""
    stmt = select(Portfolio).join(Account, Portfolio.account_id == Account.id)
    if current_user.role != UserRole.ADMIN.value:
        stmt = stmt.where(Account.user_id == current_user.id)

    portfolios = list(db.execute(stmt.order_by(Portfolio.id.asc())).scalars().all())
    return [
        PortfolioResponse(
            id=p.id,
            account_id=p.account_id,
            name=p.name,
            mode=p.mode,
            created_at=p.created_at,
            positions=[
                PositionResponse(
                    id=pos.id,
                    instrument_id=pos.instrument_id,
                    quantity=pos.quantity,
                    average_entry_price=pos.average_entry_price,
                    current_price=pos.current_price,
                    realized_pnl=pos.realized_pnl,
                    unrealized_pnl=pos.unrealized_pnl,
                )
                for pos in p.positions
            ],
        )
        for p in portfolios
    ]


@router.post(
    "", response_model=PortfolioResponse, status_code=201, dependencies=[Depends(require_csrf)]
)
def create_portfolio(
    payload: PortfolioCreateRequest,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> PortfolioResponse:
    """Create a portfolio for an account owned by current user."""
    account = db.execute(
        select(Account).where(Account.id == payload.account_id)
    ).scalar_one_or_none()
    if not account:
        raise ResourceNotFoundError(f"Account {payload.account_id} not found.")

    enforce_resource_ownership(account.user_id, current_user, resource_name="Account")

    portfolio = Portfolio(
        account_id=payload.account_id,
        name=payload.name,
        mode=payload.mode.value,
    )
    db.add(portfolio)
    db.commit()
    db.refresh(portfolio)

    return PortfolioResponse(
        id=portfolio.id,
        account_id=portfolio.account_id,
        name=portfolio.name,
        mode=portfolio.mode,
        created_at=portfolio.created_at,
        positions=[],
    )


@router.get("/{portfolio_id}", response_model=PortfolioResponse)
def get_portfolio(
    portfolio_id: int,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> PortfolioResponse:
    """Retrieve portfolio and its current positions, enforcing owner check to prevent IDOR."""
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

    positions = list(
        db.execute(select(Position).where(Position.portfolio_id == portfolio_id)).scalars().all()
    )

    return PortfolioResponse(
        id=portfolio.id,
        account_id=portfolio.account_id,
        name=portfolio.name,
        mode=portfolio.mode,
        created_at=portfolio.created_at,
        positions=[
            PositionResponse(
                id=pos.id,
                instrument_id=pos.instrument_id,
                quantity=pos.quantity,
                average_entry_price=pos.average_entry_price,
                current_price=pos.current_price,
                realized_pnl=pos.realized_pnl,
                unrealized_pnl=pos.unrealized_pnl,
            )
            for pos in positions
        ],
    )
