/**
 * Research Status View (Layer 13).
 *
 * Displays research questions, V1 boundaries, globally chronological partitions,
 * 1-session embargo, active models, policy TP-V1, and the ₹300-₹1,500 evaluation band.
 */

import React, { useEffect, useState } from "react";
import { fetchResearchStatus, ResearchStatusData } from "../api/services";
import { useDataMode } from "../context/ModeContext";

export const ResearchStatusView: React.FC = () => {
  const { modeLabel } = useDataMode();
  const [data, setData] = useState<ResearchStatusData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    fetchResearchStatus()
      .then((res) => {
        if (mounted) {
          setData(res);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (mounted) {
          setError(err instanceof Error ? err.message : "Failed to load research status");
          setLoading(false);
        }
      });
    return () => {
      mounted = false;
    };
  }, []);

  if (loading) {
    return (
      <div className="view-container" role="region" aria-label="Research Status Loading">
        <div className="loading-spinner">Loading research status...</div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="view-container" role="alert">
        <div className="error-card">{error || "Failed to load research status."}</div>
      </div>
    );
  }

  return (
    <div className="view-container" role="region" aria-label="Research Status View">
      <div className="view-header">
        <div>
          <h2>Research Status & Specification</h2>
          <p className="subtitle">
            Causal validation design, partition geometry, and benchmark hurdles.
          </p>
        </div>
        <div className="mode-tag-pill" data-testid="research-mode-tag">
          Mode: <strong>{modeLabel}</strong>
        </div>
      </div>

      {/* Evaluation Band Alert */}
      <div className="alert-card alert-info">
        <h3>Evaluation Benchmark Hurdle</h3>
        <p>
          The evaluation band is strictly defined as <strong>₹{data.evaluationHurdleMin.toLocaleString()} to ₹{data.evaluationHurdleMax.toLocaleString()}</strong> net P&L on a standard <strong>₹{data.scenarioCapital.toLocaleString()}</strong> scenario capital base after deducting full statutory Indian equity intraday transaction costs.
        </p>
        <p className="disclaimer-text">
          <strong>Mandatory Disclaimer:</strong> This band is an empirical research acceptance hurdle. It is neither a profit promise, forecast, nor a trading recommendation. The baseline hurdle against which all selective models must validate is <em>{data.hurdleReference}</em>.
        </p>
      </div>

      {/* Primary Hypothesis & Specifications */}
      <div className="card-grid">
        <div className="card">
          <h4>Research Hypothesis</h4>
          <p>{data.primaryHypothesis}</p>
          <div className="meta-list">
            <div><span>Policy Version:</span> <strong>{data.policyVersion}</strong></div>
            <div><span>Feature Set:</span> <strong>{data.featureSetVersion}</strong></div>
            <div><span>Scenario Capital:</span> <strong>₹{data.scenarioCapital.toLocaleString()}</strong></div>
          </div>
        </div>

        <div className="card">
          <h4>Approved Models (V1 Baseline)</h4>
          <div className="model-list">
            {data.models.map((m) => (
              <div key={m.modelId} className="model-item">
                <div className="model-id">
                  <strong>{m.modelId}</strong>
                  <span className="badge badge-success">{m.status}</span>
                </div>
                <div className="model-meta">
                  <div>Algorithm: {m.algorithm}</div>
                  <div>Calibration: {m.calibrationMethod}</div>
                  <div>Threshold: &ge; {m.threshold.toFixed(4)}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Chronological Partitions */}
      <div className="card" style={{ marginTop: "1.5rem" }}>
        <h4>Globally Chronological Partitions (Strict Temporal Split)</h4>
        <p className="section-note">
          No future dates from any symbol may leak into training partitions. A 1-session embargo is strictly enforced at boundaries to eliminate multi-bar label overlap.
        </p>
        <div className="table-responsive">
          <table className="data-table">
            <thead>
              <tr>
                <th>Partition</th>
                <th>Start Date</th>
                <th>End Date</th>
                <th>Embargo</th>
                <th>Status</th>
                <th>Governing Purpose</th>
              </tr>
            </thead>
            <tbody>
              {data.partitions.map((p) => (
                <tr key={p.name}>
                  <td><strong>{p.name}</strong></td>
                  <td>{p.startDate}</td>
                  <td>{p.endDate}</td>
                  <td>{p.embargoDays} session</td>
                  <td>
                    <span className={`badge ${p.status === "LOCKED" ? "badge-danger" : "badge-neutral"}`}>
                      {p.status}
                    </span>
                  </td>
                  <td>{p.purpose}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
