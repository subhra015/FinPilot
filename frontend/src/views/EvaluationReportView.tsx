/**
 * Evaluation Report View (Layer 13).
 *
 * Implements:
 * - Multi-strategy baseline comparisons (REF-NOTRADE-V1, STRAT-SIMPLE-V1 vs ML candidates).
 * - Full economics breakdown: Gross P&L, Statutory Fees, Net P&L, Profit Factor, Expectancy.
 * - Murphy Brier score decomposition (Reliability, Resolution, Uncertainty).
 * - Prominent evaluation band hurdle disclaimer (₹300-₹1,500 on ₹30k capital).
 */

import React, { useEffect, useState } from "react";
import { fetchEvaluationReports } from "../api/services";
import { EvaluationMetrics } from "../api/types";
import { useDataMode } from "../context/ModeContext";

export const EvaluationReportView: React.FC = () => {
  const { modeLabel } = useDataMode();
  const [reports, setReports] = useState<EvaluationMetrics[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    fetchEvaluationReports()
      .then((res) => {
        if (mounted) {
          setReports(res);
          setLoading(false);
        }
      })
      .catch(() => {
        if (mounted) setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

  return (
    <div className="view-container" role="region" aria-label="Evaluation Report View">
      <div className="view-header">
        <div>
          <h2>Evaluation Benchmark & Model Diagnostics</h2>
          <p className="subtitle">
            Comparative performance against cash reference and rule-based baselines under statutory costs.
          </p>
        </div>
        <div className="mode-tag-pill" data-testid="evaluation-mode-tag">
          Mode: <strong>{modeLabel}</strong>
        </div>
      </div>

      {/* Mandatory Evaluation Band Disclaimer */}
      <div className="alert-card alert-warning">
        <h4>Evaluation Benchmark Hurdle Notice</h4>
        <p>
          The evaluation band of <strong>₹300 to ₹1,500</strong> net P&L on standard <strong>₹30,000 scenario capital</strong> is a rigorous quantitative acceptance benchmark hurdle designed to verify that the model generates positive net alpha after absorbing full statutory transaction costs.
        </p>
        <p className="disclaimer-text">
          <strong>Mandatory Risk Disclaimer:</strong> Past performance and historical replay backtests do not guarantee future performance. The no-trade cash reference (<code>REF-NOTRADE-V1</code>) serves as the primary hurdle that any model must surpass.
        </p>
      </div>

      {/* Comparative Strategies Table */}
      <div className="card">
        <h3>Comparative Performance Across All Baselines</h3>
        <p className="section-note">
          Evaluated through the identical Layer 6 event-driven simulator with statutory Indian equity intraday transaction fees.
        </p>

        {loading ? (
          <div className="loading-spinner">Loading evaluation reports...</div>
        ) : (
          <div className="table-responsive">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Strategy / Model ID</th>
                  <th>Description</th>
                  <th>Gross P&L</th>
                  <th>Statutory Fees</th>
                  <th>Net P&L (₹)</th>
                  <th>Win Rate %</th>
                  <th>Profit Factor</th>
                  <th>Max DD %</th>
                  <th>Expectancy / Trade</th>
                </tr>
              </thead>
              <tbody>
                {reports.map((r) => {
                  const isHurdleMet = r.net_pnl >= 300.0;
                  return (
                    <tr key={r.strategy_id} className={isHurdleMet ? "row-highlight" : ""}>
                      <td><strong>{r.strategy_id}</strong></td>
                      <td>{r.strategy_name}</td>
                      <td>₹{r.gross_pnl.toFixed(2)}</td>
                      <td className="text-negative">₹{r.total_fees.toFixed(2)}</td>
                      <td className={r.net_pnl > 0 ? "text-positive" : r.net_pnl < 0 ? "text-negative" : ""}>
                        <strong>₹{r.net_pnl.toFixed(2)}</strong>
                      </td>
                      <td>{r.win_rate_pct.toFixed(1)}%</td>
                      <td>{r.profit_factor.toFixed(2)}</td>
                      <td>{r.max_drawdown_pct.toFixed(2)}%</td>
                      <td className={r.expectancy_per_trade > 0 ? "text-positive" : r.expectancy_per_trade < 0 ? "text-negative" : ""}>
                        ₹{r.expectancy_per_trade.toFixed(2)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Murphy Brier Score Decomposition Card */}
      <div className="card" style={{ marginTop: "1.5rem" }}>
        <h3>Probability Calibration & Murphy Brier Decomposition</h3>
        <p className="section-note">
          <strong>Important Context:</strong> The Brier score is a composite metric combining calibration reliability, discrimination resolution, and dataset uncertainty; it is not a pure measure of calibration error alone.
        </p>

        <div className="card-grid">
          {reports
            .filter((r) => r.brier_score !== undefined)
            .map((r) => (
              <div key={r.strategy_id} className="brier-card">
                <h4>{r.strategy_name}</h4>
                <div className="brier-score-box">
                  <span className="brier-main-label">Total Brier Score</span>
                  <span className="brier-main-value">{r.brier_score?.toFixed(4)}</span>
                </div>
                <div className="brier-components-grid">
                  <div className="brier-comp">
                    <span className="brier-comp-title">Reliability (Calibration Error)</span>
                    <span className="brier-comp-val text-positive">{r.brier_reliability?.toFixed(4)}</span>
                    <span className="brier-comp-note">Closer to 0 is better</span>
                  </div>
                  <div className="brier-comp">
                    <span className="brier-comp-title">Resolution (Discrimination)</span>
                    <span className="brier-comp-val text-highlight">{r.brier_resolution?.toFixed(4)}</span>
                    <span className="brier-comp-note">Higher is better</span>
                  </div>
                  <div className="brier-comp">
                    <span className="brier-comp-title">Uncertainty (Base Rate Variance)</span>
                    <span className="brier-comp-val">{r.brier_uncertainty?.toFixed(4)}</span>
                    <span className="brier-comp-note">Inherent dataset property</span>
                  </div>
                </div>
              </div>
            ))}
        </div>
      </div>
    </div>
  );
};
