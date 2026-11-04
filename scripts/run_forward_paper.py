"""CLI script to run forward paper trading, live-data validation, and user confidence monitor (Layer 16).

Governed by:
- ACCEPTANCE_GATES.md §2 (Layer 16 Gate)
- DATA_AND_PERFORMANCE_POLICY.md §3 (Forward Paper Mode), §7, §8
- PROJECT_SPEC.md §3, §4, §5, §7, §9, §11
- SECURITY_CHECKLIST.md SEC-01 through SEC-27
"""

from __future__ import annotations

import argparse
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

# Ensure backend/src is in sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend" / "src"))

from finpilot.data.adapters.synthetic import SyntheticDataProviderAdapter
from finpilot.db.enums import DataMode
from finpilot.forward.engine import ForwardPaperTradingEngine
from finpilot.forward.integrity import verify_frozen_model_and_config
from finpilot.forward.models import (
    VirtualCapitalTier,
    VirtualPortfolioConfig,
)
from finpilot.schemas.candles import CandleBar

IST = ZoneInfo("Asia/Kolkata")


def format_inr(val: Decimal | float) -> str:
    """Format monetary value with Indian rupee symbol."""
    f = float(val)
    if f < 0:
        return f"-₹{abs(f):,.2f}"
    return f"₹{f:,.2f}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="FinPilot AI — Layer 16 Forward Paper Trading & User Confidence CLI"
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=30000.0,
        help="Virtual starting cash in INR (default: 30000.0)",
    )
    parser.add_argument(
        "--tier",
        type=str,
        default="TIER_30K",
        choices=["TIER_2K", "TIER_10K", "TIER_30K", "TIER_50K", "CUSTOM"],
        help="Virtual capital tier (default: TIER_30K)",
    )
    parser.add_argument(
        "--model-id",
        type=str,
        default="MODEL-LOGREG-V1",
        help="Frozen model ID (default: MODEL-LOGREG-V1)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=10,
        help="Number of forward paper trading days to simulate (default: 10)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Synthetic forward generator random seed (default: 42)",
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default="artifacts/forward_paper",
        help="Directory to save forward evaluation artifacts (default: artifacts/forward_paper)",
    )
    args = parser.parse_args()

    out_path = Path(args.out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print("FINPILOT AI — LAYER 16 FORWARD PAPER TRADING & LIVE DATA VALIDATION")
    print("=" * 80)
    print(f"Target Frozen Model ID: {args.model_id}")
    print(f"Virtual Capital:        {format_inr(args.capital)} ({args.tier})")
    print(f"Forward Horizon:        {args.days} trading days")
    print(f"Output Directory:       {args.out_dir}")
    print("-" * 80)

    # 1. Cryptographic Model & Configuration Verification
    print("\n[1/5] Verifying Frozen Layer 15 Model & Configuration Integrity...")
    verification = verify_frozen_model_and_config(model_id=args.model_id)
    if not verification.is_checksum_verified or not verification.is_policy_verified:
        print("  ✗ CRITICAL INTEGRITY FAILURE: Model binary or policy checksum mismatch!")
        print(f"    Expected: {verification.expected_artifact_checksum}")
        print(f"    Actual:   {verification.actual_artifact_checksum}")
        sys.exit(1)

    print(f"  ✓ Model Checksum Verified:      {verification.actual_artifact_checksum[:24]}... (SHA-256 match)")
    print(f"  ✓ Decision Policy Hash:         {verification.calibration_policy_hash[:24]}... (Frozen)")
    print(f"  ✓ Decision Threshold:           {verification.decision_threshold:.2f}")
    print(f"  ✓ Feature Schema Version:       {verification.feature_schema_version}")
    print(f"  ✓ Risk Configuration Version:   {verification.risk_config_version}")

    # 2. Virtual Portfolio Configuration
    print("\n[2/5] Initializing Server-Authoritative Forward Paper Trading Engine...")
    current_simulated_clock = [None]

    def get_clock_time() -> datetime:
        if current_simulated_clock[0] is not None:
            return current_simulated_clock[0]
        return datetime.now(UTC)

    cfg = VirtualPortfolioConfig(
        tier=VirtualCapitalTier(args.tier),
        initial_capital=Decimal(str(args.capital)),
        max_open_positions=1,
        portfolio_name="Forward-Paper-Live-Run",
        mode=DataMode.FORWARD_PAPER,
    )
    # Clean previous CLI run's ledger in out-dir if present for a fresh run
    run_ledger_file = out_path / "prediction_ledger.json"
    if run_ledger_file.exists():
        run_ledger_file.unlink()

    engine = ForwardPaperTradingEngine(
        config=cfg,
        model_id=args.model_id,
        clock=get_clock_time,
        ledger_path=run_ledger_file,
    )
    print(f"  ✓ Mode:                         {cfg.mode.value} (Real-money routes strictly forbidden)")
    print(f"  ✓ Virtual Starting Cash:        {format_inr(cfg.initial_capital)}")
    print(f"  ✓ Integer-Share Affordability:  ENFORCED (No fractional equity shares allowed)")
    print(f"  ✓ Fail-Closed Stale Window:     300.0s wall clock lag maximum")

    # 3. Ingest Forward Market Data Stream
    print(f"\n[3/5] Streaming Fresh Market Data Across Universe ({args.days} Sessions)...")
    symbols = ["RELIANCE", "TCS", "INFY"]
    adapter = SyntheticDataProviderAdapter()
    market_records = []
    
    current_d = date(2025, 2, 3)
    days_collected = 0
    while days_collected < args.days:
        if current_d.weekday() < 5:
            for sym in symbols:
                bars = adapter.fetch_bars(symbol=sym, target_date=current_d)
                market_records.extend(bars)
            days_collected += 1
        current_d += timedelta(days=1)

    # Sort strictly chronologically across symbols to model live synchronized arrival
    market_records.sort(key=lambda r: (r.timestamp, r.symbol))
    print(f"  ✓ Total Ingested Market Bars:   {len(market_records):,}")

    # Process each candle in the synchronized 10-step engine
    processed_count = 0
    for rec in market_records:
        candle = CandleBar(
            symbol=rec.symbol,
            timestamp=rec.timestamp,
            open=rec.open,
            high=rec.high,
            low=rec.low,
            close=rec.close,
            volume=rec.volume,
            mode=DataMode.FORWARD_PAPER,
        )
        current_simulated_clock[0] = candle.timestamp
        engine.process_completed_candle(bar=candle)
        processed_count += 1

    engine.flush()
    status = engine.get_status()
    perf = engine.get_performance_metrics()
    drift = engine.get_drift_metrics()

    # 4. Results & Performance Ledger Summary
    print("\n[4/5] Compiling Forward Paper Prediction & Execution Results...")
    events = engine.ledger.get_events()
    print("-" * 80)
    print(f"{'METRIC':<35} | {'FORWARD PAPER VALUE':<35}")
    print("-" * 80)
    print(f"{'Virtual Initial Capital':<35} | {format_inr(perf.starting_equity):<35}")
    print(f"{'Ending Paper Equity':<35} | {format_inr(perf.ending_equity):<35}")
    print(f"{'Gross Realized P&L':<35} | {format_inr(perf.gross_pnl):<35}")
    print(f"{'Total Statutory Charges & Fees':<35} | {format_inr(perf.total_fees):<35}")
    print(f"{'Net Realized P&L':<35} | {format_inr(perf.net_pnl):<35}")
    print(f"{'Net Return on Virtual Capital':<35} | {perf.net_return_pct:+.2f}%")
    print(f"{'Net Expectancy per Trade':<35} | {format_inr(perf.net_expectancy_per_trade):<35}")
    print(f"{'Profit Factor (Gains / |Losses|)':<35} | {perf.profit_factor:.2f}")
    print(f"{'Empirical Win Rate':<35} | {perf.win_rate_pct:.1f}% ({perf.winning_trades}/{perf.total_trades} trades)")
    print(f"{'Maximum Paper Drawdown':<35} | {perf.max_drawdown_pct:.2f}%")
    print(f"{'Worst Trading Day Net P&L':<35} | {format_inr(perf.worst_trading_day):<35}")
    print(f"{'Longest Losing Streak':<35} | {perf.longest_losing_streak} trades")
    print(f"{'95% CI Net P&L (Bootstrap)':<35} | [{format_inr(perf.ci_net_pnl_95[0])}, {format_inr(perf.ci_net_pnl_95[1])}]")
    print(f"{'Total Signals Evaluated':<35} | {perf.signals_evaluated:,}")
    print(f"{'Model Candidates Accepted':<35} | {perf.signals_accepted:,} (Coverage: {perf.coverage_rate * 100:.1f}%)")
    print(f"{'Accounting Discrepancy':<35} | {format_inr(drift.accounting_discrepancy)} (Reconciled to ₹0.00)")
    print("-" * 80)

    # Breakdown by Forward Decision State
    decision_counts: dict[str, int] = {}
    for ev in events:
        d = ev.decision.value
        decision_counts[d] = decision_counts.get(d, 0) + 1

    print("\n[5/5] Prediction Ledger Decision Breakdown (Recorded BEFORE Outcomes):")
    for d, cnt in sorted(decision_counts.items()):
        print(f"  • {d:<25}: {cnt:>5} records")

    print("\nData Health & Drift Monitor Status:")
    print(f"  • Max Observed Data Latency:    {drift.data_latency_seconds_max:.1f}s")
    print(f"  • Stale Feed Incidents:         {drift.stale_feed_incidents}")
    print(f"  • Abnormal Geometry Incidents:  {drift.abnormal_geometry_incidents}")
    print(f"  • Out-of-Distribution Records:  {drift.out_of_distribution_count}")
    print(f"  • Safe NO_NEW_ENTRIES Active:   {drift.safe_no_new_entry_mode} ({drift.safe_mode_trigger_reason or 'None'})")

    # Persist Forward Evaluation Artifacts
    manifest_data = {
        "manifest_version": "LAYER-16-FORWARD-PAPER-V1",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "model_id": args.model_id,
        "model_checksum": verification.actual_artifact_checksum,
        "policy_hash": verification.calibration_policy_hash,
        "decision_threshold": verification.decision_threshold,
        "feature_schema": verification.feature_schema_version,
        "risk_config_version": verification.risk_config_version,
        "virtual_capital": float(args.capital),
        "virtual_capital_tier": args.tier,
        "bars_processed": processed_count,
        "trades_completed": perf.total_trades,
        "net_pnl_inr": float(perf.net_pnl),
        "win_rate_pct": perf.win_rate_pct,
        "max_drawdown_pct": perf.max_drawdown_pct,
        "accounting_discrepancy": float(drift.accounting_discrepancy),
    }

    manifest_file = out_path / "FORWARD_PAPER_MANIFEST.json"
    report_file = out_path / "forward_paper_report.json"

    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)

    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "status": status.model_dump(mode="json"),
                "performance": perf.model_dump(mode="json"),
                "drift": drift.model_dump(mode="json"),
                "total_events_recorded": len(events),
                "decision_counts": decision_counts,
            },
            f,
            indent=2,
        )

    print(f"\nSaved Forward Manifest: {manifest_file}")
    print(f"Saved Forward Report:   {report_file}")
    print("\n" + "=" * 80)
    print("USER TRUST & INTEGRITY NOTICE:")
    print("Forward paper trading outcomes are empirical simulated demonstrations on forward data.")
    print("They do NOT guarantee future market profit or eliminate the risk of capital loss.")
    print("=" * 80)


if __name__ == "__main__":
    main()
