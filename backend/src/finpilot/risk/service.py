"""High-level Risk Authorization Service coordinating configuration and evaluation (Layer 11).

Governed by:
- PROJECT_SPEC.md §4, §5, §7
- SECURITY_CHECKLIST.md SEC-01, SEC-06, SEC-09, SEC-19
- Layer 11 Gate: Complete independent risk service, replayable decision store,
  audit tracking, and simulator integration.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from finpilot.data.models import MarketDataRecord
from finpilot.execution.fee_schedule import BaseFeeSchedule
from finpilot.schemas.candles import CandleBar
from finpilot.schemas.scoping import UserScope
from finpilot.schemas.trade_policy import TradeProposal

from .config_service import RiskConfigService
from .evaluator import RiskEvaluator
from .models import (
    PositionCloseIntent,
    RiskConfig,
    RiskConfigAuditEvent,
    RiskEvaluationResult,
)


class RiskService:
    """Independent Risk Authority managing configuration and authorizing trade proposals.

    Invariants:
    1. Independent Decision Ledger: Records every risk evaluation result for deterministic replay.
    2. RBAC Enforcement: Exposes administrative risk controls strictly through UserScope checks.
    3. Simulator Bridge: Issues tamper-evident RiskAuthorization tokens verified
       by PortfolioManager.
    """

    def __init__(
        self,
        config_service: RiskConfigService | None = None,
        fee_schedule: BaseFeeSchedule | None = None,
    ) -> None:
        self.config_service = config_service or RiskConfigService()
        self.fee_schedule = fee_schedule
        self._decisions: list[RiskEvaluationResult] = []
        self._decisions_by_id: dict[str, RiskEvaluationResult] = {}

    @property
    def config(self) -> RiskConfig:
        return self.config_service.config

    def evaluate_entry_proposal(
        self,
        proposal: TradeProposal,
        candle: CandleBar | MarketDataRecord | None,
        available_cash: Decimal,
        total_equity: Decimal,
        current_positions: list[dict[str, Any]] | None = None,
        active_order_proposal_ids: set[str] | None = None,
        daily_realized_loss: Decimal = Decimal("0.00"),
        current_drawdown_pct: float = 0.0,
        model_id: str = "MODEL-LOGREG-V1",
        current_timestamp: datetime | None = None,
    ) -> RiskEvaluationResult:
        """Evaluate an entry proposal against the current active risk policy."""
        evaluator = RiskEvaluator(
            config=self.config_service.config,
            fee_schedule=self.fee_schedule,
        )
        res = evaluator.evaluate_entry_proposal(
            proposal=proposal,
            candle=candle,
            available_cash=available_cash,
            total_equity=total_equity,
            current_positions=current_positions,
            active_order_proposal_ids=active_order_proposal_ids,
            daily_realized_loss=daily_realized_loss,
            current_drawdown_pct=current_drawdown_pct,
            model_id=model_id,
            current_timestamp=current_timestamp or datetime.now(UTC),
        )
        self._decisions.append(res)
        self._decisions_by_id[res.decision_id] = res
        return res

    def evaluate_close_intent(
        self,
        close_intent: PositionCloseIntent,
        candle: CandleBar | MarketDataRecord | None,
        current_timestamp: datetime | None = None,
    ) -> RiskEvaluationResult:
        """Evaluate intent to close an open position (Exit)."""
        evaluator = RiskEvaluator(
            config=self.config_service.config,
            fee_schedule=self.fee_schedule,
        )
        res = evaluator.evaluate_close_intent(
            close_intent=close_intent,
            candle=candle,
            current_timestamp=current_timestamp or datetime.now(UTC),
        )
        self._decisions.append(res)
        self._decisions_by_id[res.decision_id] = res
        return res

    def get_decision(self, decision_id: str) -> RiskEvaluationResult | None:
        """Lookup an evaluation result by ID."""
        return self._decisions_by_id.get(decision_id)

    def get_all_decisions(self) -> list[RiskEvaluationResult]:
        """Return full decision history for audit and replay verification."""
        return list(self._decisions)

    # ------------------------------------------------------------------
    # Administrative Controls (Delegated to RiskConfigService with RBAC)
    # ------------------------------------------------------------------
    def update_config(self, updates: dict[str, Any], user_scope: UserScope) -> RiskConfig:
        """Update risk limits (admin only)."""
        return self.config_service.update_config(updates, user_scope)

    def set_kill_switch(
        self, active: bool, user_scope: UserScope, reason: str = ""
    ) -> RiskConfig:
        """Toggle emergency kill switch (admin only)."""
        return self.config_service.set_kill_switch(active, user_scope, reason)

    def set_manual_pause(
        self, paused: bool, user_scope: UserScope, reason: str = ""
    ) -> RiskConfig:
        """Toggle manual trading pause (admin only)."""
        return self.config_service.set_manual_pause(paused, user_scope, reason)

    def get_audit_log(self) -> list[RiskConfigAuditEvent]:
        """Return administrative configuration audit events."""
        return self.config_service.get_audit_log()
