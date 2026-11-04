"""CLI script to execute locked historical evaluation and user trust audit (Layer 15).

Governed by:
- ACCEPTANCE_GATES.md §2 (Layer 15 Gate)
- DATA_AND_PERFORMANCE_POLICY.md §2, §5, §7, §8
- PROJECT_SPEC.md §4, §5, §7, §9, §11
- SECURITY_CHECKLIST.md SEC-01 through SEC-27
"""

from __future__ import annotations

import argparse
from decimal import Decimal
from pathlib import Path
import sys

# Ensure backend/src is in sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend" / "src"))

from finpilot.evaluation.runner import LockedHistoricalEvaluationRunner


def format_inr(val: Decimal | float) -> str:
    """Format monetary value with Indian rupee symbol."""
    f = float(val)
    if f < 0:
        return f"-₹{abs(f):,.2f}"
    return f"₹{f:,.2f}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="FinPilot AI — Layer 15 Locked Historical Evaluation & User Trust CLI"
    )
    parser.add_argument(
        "--model-id",
        type=str,
        default="MODEL-LOGREG-V1",
        help="Model artifact ID to evaluate (default: MODEL-LOGREG-V1)",
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=30000.0,
        help="Initial capital in INR (default: 30000.0)",
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default="artifacts/evaluation",
        help="Output directory for manifests and evaluation reports",
    )
    args = parser.parse_args()

    print("=" * 80)
    print("FINPILOT AI — LAYER 15 LOCKED HISTORICAL EVALUATION & USER TRUST")
    print("=" * 80)
    print(f"Target Model ID: {args.model_id}")
    print(f"Virtual Capital: ₹{args.capital:,.2f}")
    print(f"Output Directory: {args.out_dir}")
    print("-" * 80)

    runner = LockedHistoricalEvaluationRunner(
        initial_capital=Decimal(str(args.capital)),
        output_dir=args.out_dir,
    )

    print("\n[1/5] Unsealing Final-Test Lockbox and Verifying Integrity...")
    report = runner.run_locked_evaluation(model_id=args.model_id)

    print(f"  ✓ Lockbox Sample Hash: {report.manifest.locked_final_test_hash}")
    print(f"  ✓ Evaluation Manifest SHA-256: {report.manifest.manifest_sha256}")
    print(f"  ✓ Total Validation Opportunities Recorded: {report.total_validation_records}")

    # 1. Three-Arm Performance Table
    print("\n" + "=" * 80)
    print("THREE-ARM HISTORICAL REPLAY PERFORMANCE COMPARISON")
    print("=" * 80)
    header = f"{'Metric':<28} | {'Arm A (No Trade)':<16} | {'Arm B (Simple)':<16} | {'Arm C (Simple+ML)':<16}"
    print(header)
    print("-" * len(header))

    def row(label: str, a_val: str, b_val: str, c_val: str) -> None:
        print(f"{label:<28} | {a_val:<16} | {b_val:<16} | {c_val:<16}")

    a = report.arm_a_no_trade
    b = report.arm_b_simple_baseline
    c = report.arm_c_ml_selected

    row("Starting Equity", format_inr(a.initial_capital), format_inr(b.initial_capital), format_inr(c.initial_capital))
    row("Ending Equity", format_inr(a.ending_equity), format_inr(b.ending_equity), format_inr(c.ending_equity))
    row("Gross Realized P&L", format_inr(a.gross_pnl), format_inr(b.gross_pnl), format_inr(c.gross_pnl))
    row("Statutory Fees & Slip", format_inr(a.total_fees), format_inr(b.total_fees), format_inr(c.total_fees))
    row("Net Realized P&L", format_inr(a.net_pnl), format_inr(b.net_pnl), format_inr(c.net_pnl))
    row("Net Return (%)", f"{a.net_return_pct:.2f}%", f"{b.net_return_pct:.2f}%", f"{c.net_return_pct:.2f}%")
    row("Net Expectancy / Trade", format_inr(a.net_expectancy_per_trade), format_inr(b.net_expectancy_per_trade), format_inr(c.net_expectancy_per_trade))
    row("Profit Factor", f"{a.profit_factor:.2f}", f"{b.profit_factor:.2f}", f"{c.profit_factor:.2f}")
    row("Win Rate (%)", f"{a.win_rate_pct:.1f}%", f"{b.win_rate_pct:.1f}%", f"{c.win_rate_pct:.1f}%")
    row("Trades (Total/Win/Loss)", f"{a.total_trades}/{a.winning_trades}/{a.losing_trades}", f"{b.total_trades}/{b.winning_trades}/{b.losing_trades}", f"{c.total_trades}/{c.winning_trades}/{c.losing_trades}")
    row("Max Drawdown (%)", f"{a.max_drawdown_pct:.2f}%", f"{b.max_drawdown_pct:.2f}%", f"{c.max_drawdown_pct:.2f}%")
    row("Worst Session Day", format_inr(a.worst_trading_day), format_inr(b.worst_trading_day), format_inr(c.worst_trading_day))
    row("Max Losing Streak", str(a.losing_streak), str(b.losing_streak), str(c.losing_streak))
    row("Signal Coverage (%)", f"{a.coverage_rate:.1f}%", f"{b.coverage_rate:.1f}%", f"{c.coverage_rate:.1f}%")
    row("95% CI Net P&L", "N/A", f"[{b.bootstrap_ci_net_pnl.ci_lower_95:,.1f}, {b.bootstrap_ci_net_pnl.ci_upper_95:,.1f}]", f"[{c.bootstrap_ci_net_pnl.ci_lower_95:,.1f}, {c.bootstrap_ci_net_pnl.ci_upper_95:,.1f}]")

    # 2. Incremental Contribution
    inc = report.incremental_contribution
    print("\n" + "-" * 80)
    print("INCREMENTAL ML SELECTION VALUE (Arm C vs. Arm B):")
    print(f"  • Incremental Net P&L:       {format_inr(float(inc['delta_net_pnl_inr']))}")
    print(f"  • Statutory Fee Savings:     {format_inr(float(inc['fee_savings_inr']))}")
    print(f"  • Harmful Trades Avoided:    {inc['trades_filtered_or_avoided']}")
    print(f"  • Drawdown Reduction:        {inc['max_drawdown_reduction_pct']:.2f}%")

    # 3. Murphy Brier Score Decomposition
    if c.brier_decomposition:
        bd = c.brier_decomposition
        print("\n" + "=" * 80)
        print("MURPHY (1973) BRIER SCORE DECOMPOSITION (Unsealed Test Partition)")
        print("=" * 80)
        print(f"  Overall Brier Score: {bd.brier_score:.6f}")
        print(f"  - Reliability (Calibration Error, lower is better): {bd.reliability:.6f}")
        print(f"  - Resolution (Discrimination Ability, higher is better): {bd.resolution:.6f}")
        print(f"  - Uncertainty (Base Rate Variance o_bar*(1-o_bar)):   {bd.uncertainty:.6f}")
        print(f"  Log Loss:            {bd.log_loss:.6f}")
        print(f"  Identity Holds:      {bd.identity_holds}")
        print(f"  Note: {bd.explanation}")

    # 4. Slippage Sensitivity Grid
    if c.slippage_sensitivity:
        print("\n" + "=" * 80)
        print("EXECUTION SLIPPAGE SENSITIVITY GRID (Arm C)")
        print("=" * 80)
        slip_hdr = f"{'Slippage':<12} | {'Gross P&L':<14} | {'Fees & Slip':<14} | {'Net P&L':<14} | {'Expectancy':<14} | {'Profit Factor':<14}"
        print(slip_hdr)
        print("-" * len(slip_hdr))
        for s in c.slippage_sensitivity:
            print(
                f"{s.slippage_bps:<12.1f} | {format_inr(s.gross_pnl):<14} | {format_inr(s.fees):<14} | "
                f"{format_inr(s.net_pnl):<14} | {format_inr(s.expectancy):<14} | {s.profit_factor:<14.2f}"
            )

    # 5. Virtual Capital Tiers Table
    print("\n" + "=" * 80)
    print("VIRTUAL CAPITAL SCENARIOS & INTEGER SHARE AFFORDABILITY")
    print("=" * 80)
    cap_hdr = f"{'Capital Tier':<14} | {'Affordable':<12} | {'Rejected':<10} | {'Net P&L':<12} | {'Return (%)':<12} | {'Notes':<25}"
    print(cap_hdr)
    print("-" * len(cap_hdr))
    for cs in report.capital_scenarios:
        print(
            f"{format_inr(cs.capital):<14} | {cs.affordable_trades:<12} | {cs.capital_rejected_trades:<10} | "
            f"{format_inr(cs.net_pnl):<12} | {cs.net_return_pct:<12.2f}% | {cs.notes[:35]}..."
        )

    # 6. Sample Trade Validation Log
    print("\n" + "=" * 80)
    print("TRANSPARENT TRADE VALIDATION LOG (Sample Opportunities)")
    print("=" * 80)
    val_hdr = f"{'Opportunity ID':<26} | {'Sym':<8} | {'Prob':<6} | {'Exp':<8} | {'Decision':<14} | {'Risk':<6} | {'Net PnL':<10}"
    print(val_hdr)
    print("-" * len(val_hdr))
    for rec in report.user_validation_sample[:5]:
        prob_str = f"{rec.calibrated_probability:.2f}" if rec.calibrated_probability is not None else "N/A"
        exp_str = format_inr(rec.estimated_expectancy) if rec.estimated_expectancy is not None else "N/A"
        risk_str = "AUTH" if rec.risk_authorized else "DENY"
        print(
            f"{rec.opportunity_id:<26} | {rec.symbol:<8} | {prob_str:<6} | {exp_str:<8} | "
            f"{rec.decision_state:<14} | {risk_str:<6} | {format_inr(rec.net_pnl):<10}"
        )

    # 7. Final Economic Verdict
    verd = report.economic_verdict
    print("\n" + "=" * 80)
    print("FINAL ECONOMIC VERDICT")
    print("=" * 80)
    print(f"VERDICT: {verd.verdict.value}")
    print(f"Research Integrity Passed:   {verd.research_integrity_passed}")
    print(f"Economic Edge Demonstrated:  {verd.economic_edge_demonstrated}")
    print(f"Incremental Net P&L:         {format_inr(verd.incremental_net_pnl_vs_simple)}")
    print(f"Statistical Confidence:      {verd.p_value_or_confidence}")
    print(f"\nJustification:\n{verd.justification}")
    print("=" * 80)
    print(f"\nLocked evaluation report persisted to:\n  {Path(args.out_dir) / 'locked_historical_evaluation_report.json'}")
    print(f"Evaluation manifest persisted to:\n  {Path(args.out_dir) / 'EVALUATION_MANIFEST_LOCKED_TEST.json'}\n")


if __name__ == "__main__":
    main()
