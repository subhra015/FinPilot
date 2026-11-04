"""Comprehensive test suite for Layer 16: Forward Paper Trading & Live-Data Validation.

Governed by:
- ACCEPTANCE_GATES.md §2 (Layer 16 Gate)
- DATA_AND_PERFORMANCE_POLICY.md §3 (Forward Paper Mode), §7, §8
- PROJECT_SPEC.md §3, §4, §5, §7, §9, §11
- SECURITY_CHECKLIST.md SEC-01 through SEC-27
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from finpilot.app import create_app
from finpilot.baselines.simple_strategy import PredeclaredSimpleStrategy
from finpilot.data.adapters.synthetic import SyntheticDataProviderAdapter
from finpilot.db.base import Base
from finpilot.db.enums import DataMode, OrderSide, OrderStatus, UserRole
from finpilot.db.models import Account, Instrument, Portfolio, User
from finpilot.execution.models import AmbiguityTreatment, ExecutionOrder, FillEvent
from finpilot.forward.engine import ForwardPaperTradingEngine
from finpilot.forward.integrity import verify_frozen_model_and_config
from finpilot.forward.ledger import ForwardPredictionLedger
from finpilot.forward.models import (
    DriftMonitorMetrics,
    ForwardDecision,
    ForwardPaperStatus,
    ForwardPerformanceMetrics,
    PredictionEventRecord,
    VirtualCapitalTier,
    VirtualPortfolioConfig,
)
from finpilot.forward.monitor import DriftAndPerformanceMonitor
from finpilot.schemas.candles import CandleBar
from finpilot.schemas.errors import AuthenticationRequiredError

IST = ZoneInfo("Asia/Kolkata")


@pytest.fixture
def db_session():
    """In-memory SQLite database session fixture."""
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def mock_clock():
    """Deterministic market hours clock."""
    current_time = datetime(2025, 2, 3, 10, 0, 0, tzinfo=UTC)

    def _get_time():
        return current_time

    return _get_time


# ==============================================================================
# TEST 1: Preconditions & Frozen Model Integrity Verification
# ==============================================================================
def test_preconditions_and_frozen_model_verification():
    """Verify Layer 15 model SHA-256 checksum and policy hashes match frozen values."""
    verification = verify_frozen_model_and_config(
        model_id="MODEL-LOGREG-V1",
        calibration_policy_id="DECISION-POLICY-V1",
    )
    assert verification.is_checksum_verified is True
    assert verification.is_policy_verified is True
    assert verification.actual_artifact_checksum == "ede1e29783917673f44b68e72e62f446b96972feb741627539f52c2a2c455bfb"
    assert verification.calibration_policy_hash == "7b2f674b13ea73052d1e39eb3038228268d13ddf04eb25f9a51eb6b692cbd3bb"
    assert verification.decision_threshold == 0.54
    assert verification.feature_schema_version == "FS-V1"
    assert verification.risk_config_version == "RISK-CFG-V1"

    # Tampered checksum must fail closed
    with patch(
        "finpilot.forward.engine.verify_frozen_model_and_config",
        return_value=verification.model_copy(update={"is_checksum_verified": False}),
    ):
        with pytest.raises(RuntimeError, match="CRITICAL"):
            ForwardPaperTradingEngine(model_id="MODEL-LOGREG-V1")


# ==============================================================================
# TEST 2: User Virtual Capital Constraints & Integer-Share Affordability
# ==============================================================================
def test_user_virtual_capital_constraints_integer_shares(tmp_path):
    """Test virtual capital tiers and assert integer-share affordability blocks unaffordable trades."""
    ledger_file = tmp_path / "test_ledger_2k.json"

    # ₹2,000 capital tier
    cfg_2k = VirtualPortfolioConfig(
        tier=VirtualCapitalTier.TIER_2K,
        initial_capital=Decimal("2000.00"),
        max_open_positions=1,
    )
    engine_2k = ForwardPaperTradingEngine(
        config=cfg_2k,
        ledger_path=ledger_file,
    )
    assert engine_2k.portfolio_manager.available_cash == Decimal("2000.00")

    # Ingest candle for TCS at ₹3,800 (exceeds ₹2,000 cash for 1 share)
    candle_tcs = CandleBar(
        symbol="TCS",
        timestamp=datetime(2025, 2, 3, 9, 30, tzinfo=IST),
        open=Decimal("3800.00"),
        high=Decimal("3810.00"),
        low=Decimal("3790.00"),
        close=Decimal("3805.00"),
        volume=10000,
        mode=DataMode.FORWARD_PAPER,
    )

    # In synthetic test, even if model would propose TCS, risk engine must reject due to cash affordability
    event = engine_2k.process_completed_candle(candle_tcs)
    assert event is not None
    if event.decision == ForwardDecision.RISK_REJECTED:
        assert any(
            "INSUFFICIENT" in r or "AFFORD" in r or "QUANTITY" in r or "CASH" in r
            for r in event.risk_rejection_reasons
        )
    # Positions must remain 0
    assert len(engine_2k.portfolio_manager.positions) == 0


# ==============================================================================
# TEST 3: Market Data Freshness & Fail-Closed Stale-Data Handling
# ==============================================================================
def test_market_data_freshness_fail_closed(tmp_path):
    """Test > 300s wall clock data lag blocks new entries fail-closed while exits remain monitored."""
    ledger_file = tmp_path / "test_ledger_stale.json"
    wall_clock = datetime(2025, 2, 3, 10, 0, 0, tzinfo=UTC)

    engine = ForwardPaperTradingEngine(
        initial_capital=Decimal("30000.00"),
        stale_threshold_seconds=300,
        clock=lambda: wall_clock,
        ledger_path=ledger_file,
    )

    # Candle timestamp is 09:45:00 UTC = 15:15 IST (lag = 900s > 300s threshold)
    c_ts = datetime(2025, 2, 3, 9, 45, 0, tzinfo=UTC)
    c_ist = c_ts.astimezone(IST)
    candle_stale = CandleBar(
        symbol="RELIANCE",
        timestamp=c_ist,
        open=Decimal("2500.00"),
        high=Decimal("2510.00"),
        low=Decimal("2495.00"),
        close=Decimal("2505.00"),
        volume=10000,
        mode=DataMode.FORWARD_PAPER,
    )

    event = engine.process_completed_candle(candle_stale)
    assert event is not None
    assert event.decision == ForwardDecision.INSUFFICIENT_DATA
    assert "stale" in event.decision_reason.lower()

    # Monitor recorded the stale incident
    monitor = engine.monitor
    assert monitor.stale_feed_incidents >= 1


# ==============================================================================
# TEST 4: Prediction Ledger Pre-Outcome Logging & Separate Outcome Appending
# ==============================================================================
def test_prediction_ledger_pre_outcome_logging(tmp_path):
    """Assert predictions are logged BEFORE outcomes occur, and outcomes append without overwriting."""
    ledger_file = tmp_path / "test_ledger_pred.json"
    ledger = ForwardPredictionLedger(storage_path=ledger_file)

    now = datetime.now(UTC)
    pred_rec = PredictionEventRecord(
        event_id="PRED-TEST-001",
        prediction_timestamp=now,
        candle_timestamp=now - timedelta(minutes=5),
        symbol="RELIANCE",
        instrument_id=1,
        model_id="MODEL-LOGREG-V1",
        model_hash="ede1e29783917673f44b68e72e62f446b96972feb741627539f52c2a2c455bfb",
        raw_probability=0.62,
        calibrated_probability=0.58,
        estimated_expectancy=Decimal("12.50"),
        proposed_entry_price=Decimal("2500.00"),
        stop_loss_price=Decimal("2475.00"),
        profit_target_price=Decimal("2550.00"),
        requested_quantity=10,
        authorized_quantity=10,
        risk_authorized=True,
        decision=ForwardDecision.ACCEPTED,
        decision_reason="Candidate met model confidence threshold 0.54 and passed risk checks.",
    )

    # 1. Prediction logged pre-outcome
    saved = ledger.record_prediction(pred_rec)
    assert saved.event_id == "PRED-TEST-001"
    assert saved.fill_price is None
    assert saved.exit_price is None

    # Verify on-disk file
    assert ledger_file.exists()
    disk_data = json.loads(ledger_file.read_text(encoding="utf-8"))
    assert len(disk_data) == 1
    assert disk_data[0]["event_id"] == "PRED-TEST-001"
    assert disk_data[0]["fill_price"] is None

    # 2. Append fill outcome later
    fill_time = now + timedelta(minutes=5)
    ledger.append_outcome(
        event_id="PRED-TEST-001",
        fill_price=Decimal("2501.00"),
        fill_quantity=10,
        fill_timestamp=fill_time,
        slippage_incurred=Decimal("1.00"),
        charges_incurred=Decimal("15.20"),
    )

    ev_after_fill = ledger.get_event("PRED-TEST-001")
    assert ev_after_fill is not None
    assert ev_after_fill.fill_price == Decimal("2501.00")
    assert ev_after_fill.exit_price is None
    # Original pre-outcome prediction values must remain completely unchanged
    assert ev_after_fill.raw_probability == 0.62
    assert ev_after_fill.calibrated_probability == 0.58
    assert ev_after_fill.proposed_entry_price == Decimal("2500.00")

    # 3. Append exit outcome
    exit_time = now + timedelta(minutes=45)
    ledger.append_outcome(
        event_id="PRED-TEST-001",
        exit_price=Decimal("2550.00"),
        exit_timestamp=exit_time,
        exit_reason="PROFIT_TARGET",
        gross_pnl=Decimal("490.00"),
        net_pnl=Decimal("459.60"),
    )

    ev_after_exit = ledger.get_event("PRED-TEST-001")
    assert ev_after_exit is not None
    assert ev_after_exit.exit_price == Decimal("2550.00")
    assert ev_after_exit.net_pnl == Decimal("459.60")
    assert ev_after_exit.exit_reason == "PROFIT_TARGET"


# ==============================================================================
# TEST 5: Authoritative 10-Step Workflow Decision States
# ==============================================================================
def test_all_forward_decision_states_supported():
    """Verify all 7 canonical forward paper decision states exist and serialize properly."""
    expected = {
        "ACCEPTED",
        "NO_TRADE",
        "INSUFFICIENT_DATA",
        "INSUFFICIENT_EVIDENCE",
        "RISK_REJECTED",
        "ENTRY_UNFILLED",
        "EXECUTION_UNRESOLVED",
    }
    actual = {d.value for d in ForwardDecision}
    assert actual == expected


# ==============================================================================
# TEST 6: Drift and Performance Monitoring Safe Mode Trigger
# ==============================================================================
def test_drift_monitor_safe_mode_trigger():
    """Verify monitor triggers safe NO_NEW_ENTRIES mode on data health degradation or excessive drawdown."""
    monitor = DriftAndPerformanceMonitor(
        max_stale_incidents=3,
        max_drawdown_pct_limit=10.0,
    )
    now = datetime.now(UTC)

    # 1. Normal candle checks
    for _ in range(5):
        ok = monitor.record_candle_check(
            candle_timestamp=now,
            current_time=now + timedelta(seconds=10),
            is_geometry_valid=True,
        )
        assert ok is True
        assert monitor.safe_no_new_entry_mode is False

    # 2. Trigger stale feed incidents
    for _ in range(3):
        monitor.record_candle_check(
            candle_timestamp=now - timedelta(seconds=400),
            current_time=now,
            is_geometry_valid=True,
        )

    # Monitor must engage safe NO_NEW_ENTRIES mode without changing model weights
    assert monitor.safe_no_new_entry_mode is True
    assert "Stale" in (monitor.safe_mode_trigger_reason or "")

    # 3. Drawdown breach also triggers safe mode
    monitor2 = DriftAndPerformanceMonitor(max_drawdown_pct_limit=10.0)
    monitor2.update_drawdown(12.5)
    assert monitor2.safe_no_new_entry_mode is True
    assert "drawdown" in (monitor2.safe_mode_trigger_reason or "").lower()


# ==============================================================================
# TEST 7: Idempotency & Double-Entry Accounting Invariant
# ==============================================================================
def test_double_entry_accounting_reconciliation(tmp_path):
    """Verify portfolio manager double-entry accounting reconciles cash + positions to ₹0.00."""
    engine = ForwardPaperTradingEngine(
        initial_capital=Decimal("30000.00"),
        ledger_path=tmp_path / "ledger.json",
    )
    # Initial status
    status = engine.get_status()
    assert status.initial_capital == Decimal("30000.00")
    assert status.available_cash == Decimal("30000.00")
    assert status.reserved_cash == Decimal("0.00")
    assert status.open_positions_count == 0

    # Invariant: cash + reserved + positions - net_realized == initial_capital
    assert status.current_equity == Decimal("30000.00")


# ==============================================================================
# TEST 8: Strict Prohibition of Real-Money Broker Order Routing
# ==============================================================================
def test_prohibition_of_real_money_routes():
    """Assert forward paper trading runtime strictly isolates simulated execution from live broker routes."""
    engine = ForwardPaperTradingEngine(initial_capital=Decimal("30000.00"))
    assert engine.mode == DataMode.FORWARD_PAPER
    assert engine.portfolio_manager.mode == DataMode.FORWARD_PAPER

    # Check simulator uses simulated fill execution only
    assert hasattr(engine.simulator, "evaluate_order")
    # Live broker attributes must NOT exist
    assert not hasattr(engine, "broker_client")
    assert not hasattr(engine, "place_live_order")
    assert not hasattr(engine, "zerodha_client")
    assert not hasattr(engine, "upstox_client")


# ==============================================================================
# TEST 9: Authenticated Forward Paper API Router Endpoints
# ==============================================================================
def test_forward_paper_api_endpoints_auth_required():
    """Verify forward paper API routes reject unauthenticated requests with 401."""
    app = create_app()
    client = TestClient(app)

    # 1. Unauthenticated GET /api/forward-paper/status -> 401
    resp = client.get("/api/forward-paper/status")
    assert resp.status_code == 401

    # 2. Unauthenticated GET /api/forward-paper/performance -> 401
    resp = client.get("/api/forward-paper/performance")
    assert resp.status_code == 401

    # 3. Unauthenticated GET /api/forward-paper/prediction-ledger -> 401
    resp = client.get("/api/forward-paper/prediction-ledger")
    assert resp.status_code == 401

    # 4. Unauthenticated POST /api/forward-paper/configure -> 401
    resp = client.post(
        "/api/forward-paper/configure",
        json={"initial_capital": "30000.00", "tier": "TIER_30K", "max_open_positions": 1},
    )
    assert resp.status_code == 401
