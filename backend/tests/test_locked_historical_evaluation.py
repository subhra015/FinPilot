"""Tests for Locked Historical Evaluation, Model Validation, and User Trust (Layer 15).

Governed by:
- ACCEPTANCE_GATES.md §2 (Layer 15 Gate)
- DATA_AND_PERFORMANCE_POLICY.md §2, §5, §7, §8
- PROJECT_SPEC.md §4, §5, §7, §9, §11
- SECURITY_CHECKLIST.md SEC-01 through SEC-27
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
import numpy as np
import pytest
from sqlalchemy.orm import Session as DBSession

from finpilot.app import create_app
from finpilot.config import Settings
from finpilot.db import create_engine_from_settings, create_session_factory
from finpilot.db.base import Base
from finpilot.db.enums import OrderSide
from finpilot.db.models import Instrument, User
from finpilot.evaluation.bootstrap import session_block_bootstrap
from finpilot.evaluation.metrics import (
    compute_brier_decomposition,
    compute_drawdown,
    compute_fee_breakdown,
    compute_losing_streak_and_worst_day,
    compute_profit_factor,
)
from finpilot.evaluation.models import (
    EconomicVerdictEnum,
    EvaluationManifest,
    LockedHistoricalEvaluationReport,
)
from finpilot.evaluation.runner import LockedHistoricalEvaluationRunner
from finpilot.execution.fee_schedule import NSEEquityIntradayFeeSchedule, round_paisa
from finpilot.labeling.generator import TradePolicyLabelGenerator
from finpilot.labeling.lockbox import FinalTestLockbox
from finpilot.labeling.models import LabelingApproach, PartitionType, SplitManifest, TradePolicyLabel
from finpilot.labeling.split_manager import FinalTestLockedError, TemporalSplitManager
from finpilot.schemas.errors import DomainValidationError


def _setup_api_client(
    make_settings: Callable[..., Any],
    tmp_path_factory: Any,
) -> tuple[TestClient, DBSession, Settings]:
    db_path = tmp_path_factory.mktemp("eval_api_db") / "test_eval.db"
    settings = make_settings(
        database_url=f"sqlite:///{db_path}",
        cors_allowed_origins="http://localhost:3000",
        secret_key="b" * 64,
        debug=False,
    )
    engine = create_engine_from_settings(settings)
    session_factory = create_session_factory(engine)
    Base.metadata.create_all(bind=engine)

    db = session_factory()
    inst = Instrument(
        id=1,
        isin="INE467B01029",
        symbol="TCS",
        name="Tata Consultancy Services Ltd",
        market="EQUITY",
        exchange="NSE",
        currency="INR",
        tick_size=Decimal("0.05"),
        lot_size=1,
        status="ACTIVE",
    )
    db.add(inst)
    db.commit()

    app = create_app(settings)
    app.state.db_factory = session_factory

    client = TestClient(app, base_url="http://localhost:3000", raise_server_exceptions=False)
    return client, db, settings


# ==============================================================================
# 1. Final-Test Lockbox and Anti-Snooping Controls
# ==============================================================================

def test_final_test_lockbox_tamper_detection() -> None:
    """Locked final test partition cannot be accessed without unseal token and fails on tampering."""
    runner = LockedHistoricalEvaluationRunner()
    lockbox, split_manifest = runner.load_or_reconstruct_lockbox()

    assert lockbox.is_locked is True

    # 1. Routine access without token fails closed
    with pytest.raises(FinalTestLockedError, match="Access to LOCKED_FINAL_TEST is blocked"):
        lockbox.get_final_test_samples()

    # 2. Access with invalid token fails closed
    with pytest.raises(FinalTestLockedError, match="Access to LOCKED_FINAL_TEST is blocked"):
        lockbox.get_final_test_samples(unlock_token="MALICIOUS_UNSEAL_ATTEMPT_12345")

    # 3. Access with valid token returns verified samples
    token = lockbox.generate_unlock_token()
    samples = lockbox.get_final_test_samples(unlock_token=token)
    assert len(samples) == 681
    assert lockbox.verify_integrity(samples) is True

    # 4. Tampering detection: modifying any sample ID immediately triggers error
    corrupted_samples = list(samples)
    tampered_label = corrupted_samples[0].model_copy(update={"sample_id": "TAMPERED-SAMPLE-ID-001"})
    corrupted_samples[0] = tampered_label
    with pytest.raises(DomainValidationError, match="Integrity check failed"):
        lockbox.verify_integrity(corrupted_samples)


# ==============================================================================
# 2. Evaluation Manifest Cryptographic Freeze
# ==============================================================================

def test_evaluation_manifest_cryptographic_freeze() -> None:
    """Pre-evaluation manifest is cryptographically sealed with checksums of models and data."""
    runner = LockedHistoricalEvaluationRunner()
    _, split_manifest = runner.load_or_reconstruct_lockbox()

    manifest = runner.build_evaluation_manifest(
        split_manifest=split_manifest,
        model_id="MODEL-LOGREG-V1",
    )

    assert isinstance(manifest, EvaluationManifest)
    assert manifest.manifest_id.startswith("EVAL-MANIFEST-LOCKED-MODEL-LOGREG-V1")
    assert manifest.locked_final_test_hash == "8c02ffda1a534713de5d3ae0d29d2bac5461768bbdff51723e3ef30702aafab1"
    assert manifest.model_freeze.model_id == "MODEL-LOGREG-V1"
    assert manifest.model_freeze.artifact_checksum == "ede1e29783917673f44b68e72e62f446b96972feb741627539f52c2a2c455bfb"
    assert manifest.model_freeze.decision_threshold == 0.54
    assert len(manifest.manifest_sha256) == 64  # Valid SHA-256 hex digest


# ==============================================================================
# 3. Three-Arm Baseline Simulation Parity & Accounting Reconciliation
# ==============================================================================

def test_three_arm_simulation_and_accounting_reconciliation() -> None:
    """All 3 arms execute under identical capital, fee schedule, and simulator rules."""
    runner = LockedHistoricalEvaluationRunner()
    report = runner.run_locked_evaluation(model_id="MODEL-LOGREG-V1")

    assert isinstance(report, LockedHistoricalEvaluationReport)

    # Arm A: Cash reference
    arm_a = report.arm_a_no_trade
    assert arm_a.initial_capital == Decimal("30000.00")
    assert arm_a.ending_equity == Decimal("30000.00")
    assert arm_a.gross_pnl == Decimal("0.00")
    assert arm_a.total_fees == Decimal("0.00")
    assert arm_a.net_pnl == Decimal("0.00")
    assert arm_a.total_trades == 0

    # Arm B: Simple non-ML baseline
    arm_b = report.arm_b_simple_baseline
    assert arm_b.initial_capital == Decimal("30000.00")
    assert arm_b.total_trades > 0
    assert arm_b.gross_pnl + arm_b.initial_capital - arm_b.total_fees == arm_b.ending_equity

    # Arm C: Simple strategy + Calibrated ML selection
    arm_c = report.arm_c_ml_selected
    assert arm_c.initial_capital == Decimal("30000.00")
    assert arm_c.gross_pnl + arm_c.initial_capital - arm_c.total_fees == arm_c.ending_equity

    # Incremental contribution consistency
    inc = report.incremental_contribution
    delta_pnl = Decimal(inc["delta_net_pnl_inr"])
    assert delta_pnl == arm_c.net_pnl - arm_b.net_pnl
    assert inc["trades_filtered_or_avoided"] == arm_b.total_trades - arm_c.total_trades


# ==============================================================================
# 4. Murphy (1973) Brier Score Decomposition
# ==============================================================================

def test_murphy_brier_score_decomposition() -> None:
    """Murphy Brier decomposition satisfies Brier = Reliability - Resolution + Uncertainty."""
    probabilities = [0.1, 0.2, 0.35, 0.6, 0.7, 0.85, 0.9] * 10
    outcomes = [0, 0, 0, 1, 1, 1, 1] * 10

    decomp = compute_brier_decomposition(probabilities, outcomes, n_bins=10)

    assert decomp.identity_holds is True
    reconstructed = decomp.reliability - decomp.resolution + decomp.uncertainty
    assert abs(decomp.brier_score - reconstructed) < 1e-3
    assert decomp.reliability >= 0.0
    assert decomp.resolution >= 0.0
    assert decomp.uncertainty > 0.0
    assert decomp.log_loss > 0.0
    assert "conflates calibration" in decomp.explanation


# ==============================================================================
# 5. Dependence-Aware Date-Clustered Block Bootstrap
# ==============================================================================

def test_date_clustered_block_bootstrap() -> None:
    """Session block bootstrap resamples entire sessions and computes 95% CIs."""
    trades_by_session: dict[str, list[dict[str, Any]]] = {
        "2026-01-27": [{"net_pnl": Decimal("50.00")}, {"net_pnl": Decimal("-20.00")}],
        "2026-01-28": [{"net_pnl": Decimal("-80.00")}],
        "2026-01-29": [{"net_pnl": Decimal("100.00")}, {"net_pnl": Decimal("30.00")}],
        "2026-01-30": [{"net_pnl": Decimal("-40.00")}],
    }
    capital = Decimal("30000.00")

    ci_dict = session_block_bootstrap(
        trades_by_session=trades_by_session,
        initial_capital=capital,
        b_replications=500,
        random_seed=42,
    )

    pnl_ci = ci_dict["net_pnl"]
    assert pnl_ci.point_estimate == 40.0
    assert pnl_ci.ci_lower_95 <= pnl_ci.ci_upper_95
    assert pnl_ci.std_err > 0.0
    assert pnl_ci.method == "date_clustered_block_bootstrap_b1000"


# ==============================================================================
# 6. Execution Slippage Sensitivity Monotonicity
# ==============================================================================

def test_slippage_sensitivity_monotonicity() -> None:
    """Higher modelled slippage monotonically reduces net P&L and increases total costs."""
    runner = LockedHistoricalEvaluationRunner()
    results = runner.run_slippage_sensitivity(
        model_id="MODEL-LOGREG-V1",
        slippage_grid=[0.0, 2.0, 5.0, 10.0],
    )

    assert len(results) == 4
    for i in range(len(results) - 1):
        assert results[i].fees <= results[i + 1].fees
        assert results[i].net_pnl >= results[i + 1].net_pnl


# ==============================================================================
# 7. Virtual Capital Scenarios & Integer Share Affordability
# ==============================================================================

def test_virtual_capital_constraint_enforcement() -> None:
    """Low capital scenarios enforce cash affordability rejecting high-priced shares."""
    runner = LockedHistoricalEvaluationRunner()
    scenarios = runner.run_capital_scenarios(
        model_id="MODEL-LOGREG-V1",
        tiers=[Decimal("2000.00"), Decimal("10000.00"), Decimal("30000.00")],
    )

    assert len(scenarios) == 3
    s_2k = scenarios[0]
    assert s_2k.capital == Decimal("2000.00")
    # At ₹2,000 capital, high-priced shares like TCS (~₹3,800) cannot afford 1 share
    assert s_2k.affordable_trades <= scenarios[1].affordable_trades
    assert "exceed total account cash" in s_2k.notes


# ==============================================================================
# 8. Predeclared Economic Verdict Classification
# ==============================================================================

def test_economic_verdict_predeclared_classification() -> None:
    """Economic verdict categorizes result into one of the 5 predeclared standards."""
    runner = LockedHistoricalEvaluationRunner()
    report = runner.run_locked_evaluation(model_id="MODEL-LOGREG-V1")
    verd = report.economic_verdict

    assert verd.verdict in list(EconomicVerdictEnum)
    assert verd.research_integrity_passed is True
    assert "Bootstrap CI" in verd.p_value_or_confidence
    assert len(verd.justification) > 10


# ==============================================================================
# 9. Evaluation API Endpoints Security and Data Contracts
# ==============================================================================

def test_evaluation_api_endpoints_security(
    make_settings: Callable[..., Any],
    tmp_path_factory: Any,
) -> None:
    """Evaluation API endpoints enforce authentication and return complete reports."""
    client, db, _ = _setup_api_client(make_settings, tmp_path_factory)

    # 1. Unauthenticated requests fail closed with 401
    resp_unauth = client.get("/api/evaluation/locked-test")
    assert resp_unauth.status_code == 401

    # 2. Register and authenticate test user
    client.post(
        "/api/auth/register",
        json={
            "email": "eval_tester@finpilot.test",
            "password": "valid-passphrase-2026-secure",
            "role": "USER",
        },
    )
    client.post(
        "/api/auth/login",
        json={
            "email": "eval_tester@finpilot.test",
            "password": "valid-passphrase-2026-secure",
        },
    )

    # 3. Authenticated GET /api/evaluation/locked-test
    resp = client.get("/api/evaluation/locked-test?model_id=MODEL-LOGREG-V1")
    assert resp.status_code == 200
    data = resp.json()
    assert "manifest" in data
    assert "arm_a_no_trade" in data
    assert "arm_b_simple_baseline" in data
    assert "arm_c_ml_selected" in data
    assert "economic_verdict" in data

    # 4. Authenticated GET /api/evaluation/manifest
    resp_man = client.get("/api/evaluation/manifest")
    assert resp_man.status_code == 200
    man_data = resp_man.json()
    assert man_data["manifest_id"].startswith("EVAL-MANIFEST-LOCKED")

    # 5. Authenticated GET /api/evaluation/capital-scenarios
    resp_cap = client.get("/api/evaluation/capital-scenarios")
    assert resp_cap.status_code == 200
    assert len(resp_cap.json()) >= 3

    # 6. Authenticated GET /api/evaluation/user-validation-log
    resp_val = client.get("/api/evaluation/user-validation-log?limit=10")
    assert resp_val.status_code == 200
    assert isinstance(resp_val.json(), list)
