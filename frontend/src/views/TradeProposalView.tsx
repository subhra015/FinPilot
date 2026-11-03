/**
 * Trade Proposal View (Layer 13).
 *
 * Implements proposal inspection and interactive simulation adhering to:
 * - Next-bar executable fill separation (no same-bar retroactive close fills).
 * - Integer share sizing (Q >= 1, zero fractional shares).
 * - Statutory Indian intraday fee schedule breakdown.
 * - Selective decision state and calibrated probability presentation.
 * - Client-side validation for UX with server authoritative boundary (SEC-06, SEC-19).
 */

import React, { useState } from "react";
import { calculateStatutoryFees, generateTradeProposal } from "../api/services";
import { TradeProposal } from "../api/types";
import { useDataMode } from "../context/ModeContext";

interface TradeProposalViewProps {
  initialSymbol?: string;
}

export const TradeProposalView: React.FC<TradeProposalViewProps> = ({ initialSymbol = "TCS" }) => {
  const { modeLabel } = useDataMode();
  const [symbol, setSymbol] = useState(initialSymbol);
  const [entryPrice, setEntryPrice] = useState(3892.4);
  const [stopLoss, setStopLoss] = useState(3861.2);
  const [profitTarget, setProfitTarget] = useState(3954.6);
  const [quantity, setQuantity] = useState<number | string>(7);
  const [proposal, setProposal] = useState<TradeProposal | null>(null);
  const [loading, setLoading] = useState(false);
  const [clientErrors, setClientErrors] = useState<string[]>([]);

  // Client-side validation function (SEC-06)
  const validateInputs = (): boolean => {
    const errors: string[] = [];
    const numQ = typeof quantity === "string" ? Number(quantity) : quantity;
    if (isNaN(numQ) || !Number.isInteger(numQ) || numQ < 1) {
      errors.push("Quantity must be a positive integer (Q >= 1). Fractional shares are forbidden.");
    }
    if (entryPrice <= 0) {
      errors.push("Entry price must be strictly positive.");
    }
    if (stopLoss >= entryPrice) {
      errors.push("For a long proposal, Stop Loss must be strictly below Entry Price.");
    }
    if (profitTarget <= entryPrice) {
      errors.push("For a long proposal, Profit Target must be strictly above Entry Price.");
    }
    const requiredCapital = entryPrice * (isNaN(numQ) ? 0 : numQ);
    if (requiredCapital > 30000.0) {
      errors.push(
        `Total trade capital (₹${requiredCapital.toFixed(2)}) exceeds the ₹30,000 scenario limit.`
      );
    }
    setClientErrors(errors);
    return errors.length === 0;
  };

  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validateInputs()) return;

    setLoading(true);
    const numQ = typeof quantity === "string" ? Number(quantity) : quantity;
    try {
      const prop = await generateTradeProposal(symbol);
      // Update with local validated form values
      const fees = calculateStatutoryFees("BUY", entryPrice, profitTarget, numQ);
      setProposal({
        ...prop,
        symbol,
        entry_price: entryPrice,
        stop_loss_price: stopLoss,
        profit_target_price: profitTarget,
        quantity: numQ,
        fees,
      });
    } finally {
      setLoading(false);
    }
  };

  const parsedQ = typeof quantity === "string" ? Number(quantity) : quantity;
  const safeQ = isNaN(parsedQ) || parsedQ < 1 ? 1 : parsedQ;
  // Immediate reactive calculation of fee estimate
  const currentFees = calculateStatutoryFees("BUY", entryPrice, profitTarget, safeQ);
  const capitalRequired = entryPrice * safeQ;
  const plannedRiskRupees = (entryPrice - stopLoss) * safeQ;
  const riskPctOfCapital = (plannedRiskRupees / 30000.0) * 100;

  return (
    <div className="view-container" role="region" aria-label="Trade Proposal View">
      <div className="view-header">
        <div>
          <h2>Trade Proposal & Execution Inspector</h2>
          <p className="subtitle">
            Signal vs next-bar execution timestamps, statutory fees, and selective probability thresholds.
          </p>
        </div>
        <div className="mode-tag-pill" data-testid="proposal-mode-tag">
          Mode: <strong>{modeLabel}</strong>
        </div>
      </div>

      {/* Causal Timing Invariant Notice */}
      <div className="alert-card alert-info">
        <h4>Causal Execution Invariant</h4>
        <p>
          A completed 5-minute candle may create a proposal only after its close is confirmed.
          <strong> It never fills retroactively at that same close.</strong> Executable fill timestamp
          is separated by at least 1 bar interval (e.g. signal at 10:15 IST &rarr; fill at 10:20 IST open).
        </p>
      </div>

      <div className="split-layout">
        {/* Left Column: Interactive Proposal Generator Form */}
        <div className="form-card card">
          <h4>Proposal Parameters (Client-Side UX Validation)</h4>
          <form onSubmit={handleGenerate} noValidate>
            <div className="form-group">
              <label htmlFor="symbol-select">Symbol</label>
              <select
                id="symbol-select"
                className="input-select"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
              >
                <option value="TCS">TCS (Tata Consultancy Services)</option>
                <option value="INFY">INFY (Infosys)</option>
                <option value="RELIANCE">RELIANCE (Reliance Industries)</option>
                <option value="HDFCBANK">HDFCBANK (HDFC Bank)</option>
                <option value="ICICIBANK">ICICIBANK (ICICI Bank)</option>
                <option value="LT">LT (Larsen & Toubro)</option>
              </select>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label htmlFor="entry-price">Entry Price (₹)</label>
                <input
                  id="entry-price"
                  type="number"
                  step="0.05"
                  className="input-text"
                  value={entryPrice}
                  onChange={(e) => setEntryPrice(parseFloat(e.target.value) || 0)}
                />
              </div>

              <div className="form-group">
                <label htmlFor="quantity-input">Quantity (Q &gt;= 1 Integer)</label>
                <input
                  id="quantity-input"
                  type="number"
                  step="any"
                  min="1"
                  className="input-text"
                  value={quantity}
                  onChange={(e) => setQuantity(e.target.value)}
                />
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label htmlFor="stop-loss">Stop Loss (₹)</label>
                <input
                  id="stop-loss"
                  type="number"
                  step="0.05"
                  className="input-text"
                  value={stopLoss}
                  onChange={(e) => setStopLoss(parseFloat(e.target.value) || 0)}
                />
              </div>

              <div className="form-group">
                <label htmlFor="profit-target">Profit Target (₹)</label>
                <input
                  id="profit-target"
                  type="number"
                  step="0.05"
                  className="input-text"
                  value={profitTarget}
                  onChange={(e) => setProfitTarget(parseFloat(e.target.value) || 0)}
                />
              </div>
            </div>

            {/* Validation Feedback */}
            {clientErrors.length > 0 && (
              <div className="validation-alert" role="alert">
                {clientErrors.map((err, i) => (
                  <div key={i}>&bull; {err}</div>
                ))}
              </div>
            )}

            <button
              type="submit"
              className="btn-primary"
              disabled={loading}
              data-testid="generate-proposal-btn"
            >
              {loading ? "Generating..." : "Generate Verified Proposal"}
            </button>
          </form>

          {/* Sizing & Affordability Summary */}
          <div className="mini-stats-grid">
            <div className="mini-stat">
              <span className="mini-stat-label">Capital Required</span>
              <span className="mini-stat-value">₹{capitalRequired.toFixed(2)}</span>
            </div>
            <div className="mini-stat">
              <span className="mini-stat-label">Planned Stop Risk</span>
              <span className="mini-stat-value">
                ₹{plannedRiskRupees.toFixed(2)} ({riskPctOfCapital.toFixed(2)}%)
              </span>
            </div>
            <div className="mini-stat">
              <span className="mini-stat-label">Max Risk Allowance</span>
              <span className="mini-stat-value">&le; 1.50% (₹450)</span>
            </div>
          </div>
        </div>

        {/* Right Column: Statutory Fee Schedule & Active Proposal Inspector */}
        <div className="proposal-card card">
          <h4>Statutory Transaction Cost Breakdown (Indian Equity Intraday)</h4>
          <p className="section-note">
            Full round-trip transaction costs computed upfront before selective ML evaluation.
          </p>

          <div className="fee-table">
            <div className="fee-row">
              <span>Brokerage (min ₹20 or 0.03% per leg)</span>
              <span>₹{currentFees.brokerage.toFixed(2)}</span>
            </div>
            <div className="fee-row">
              <span>Securities Transaction Tax (STT 0.025% on sell)</span>
              <span>₹{currentFees.stt.toFixed(2)}</span>
            </div>
            <div className="fee-row">
              <span>Exchange Turnover Charge (0.00325%)</span>
              <span>₹{currentFees.exchange_turnover.toFixed(2)}</span>
            </div>
            <div className="fee-row">
              <span>SEBI Turnover Charge (₹10 / crore)</span>
              <span>₹{currentFees.sebi_turnover.toFixed(2)}</span>
            </div>
            <div className="fee-row">
              <span>Stamp Duty (0.003% on buy)</span>
              <span>₹{currentFees.stamp_duty.toFixed(2)}</span>
            </div>
            <div className="fee-row">
              <span>GST (18% on Brokerage + Exchange + SEBI)</span>
              <span>₹{currentFees.gst.toFixed(2)}</span>
            </div>
            <div className="fee-row fee-total">
              <strong>Total Round-Trip Costs</strong>
              <strong>₹{currentFees.total_costs.toFixed(2)}</strong>
            </div>
          </div>

          {/* Proposal Decision State */}
          {proposal && (
            <div className="proposal-decision-box" data-testid="proposal-details">
              <h5>Proposal Decision & Execution Authorization</h5>
              <div className="proposal-meta-grid">
                <div><span>Proposal ID:</span> <code>{proposal.proposal_id}</code></div>
                <div><span>Signal Timestamp:</span> {proposal.signal_timestamp}</div>
                <div><span>Executable Fill Timestamp:</span> <strong>{proposal.execution_timestamp}</strong></div>
                <div>
                  <span>Decision State:</span>{" "}
                  <span className={`badge ${proposal.decision_state === "ACCEPTED" ? "badge-success" : "badge-danger"}`}>
                    {proposal.decision_state}
                  </span>
                </div>
                <div><span>Calibrated Prob:</span> {(proposal.calibrated_probability * 100).toFixed(1)}%</div>
                <div><span>Bin Support Freq:</span> {(proposal.calibration_bin_frequency * 100).toFixed(1)}%</div>
                <div><span>Est. Net Expectancy:</span> ₹{proposal.estimated_expectancy.toFixed(2)}</div>
                <div><span>Policy Version:</span> {proposal.policy_version}</div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
