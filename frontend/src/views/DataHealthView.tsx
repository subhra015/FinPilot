/**
 * Data Health & Audit Screen (Layer 13).
 *
 * Implements:
 * - 8-point data pipeline audit status checks.
 * - Source dataset license terms and permitted use cases.
 * - Bar quarantine log and geometry inspection.
 */

import React, { useEffect, useState } from "react";
import { fetchDataHealthSummary } from "../api/services";
import { DataHealthSummary } from "../api/types";
import { useDataMode } from "../context/ModeContext";

export const DataHealthView: React.FC = () => {
  const { modeLabel } = useDataMode();
  const [summary, setSummary] = useState<DataHealthSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    fetchDataHealthSummary()
      .then((res) => {
        if (mounted) {
          setSummary(res);
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

  if (loading || !summary) {
    return (
      <div className="view-container" role="region" aria-label="Data Health Loading">
        <div className="loading-spinner">Auditing data feed health and license contracts...</div>
      </div>
    );
  }

  return (
    <div className="view-container" role="region" aria-label="Data Health View">
      <div className="view-header">
        <div>
          <h2>Data Feed Health & Pipeline Audit</h2>
          <p className="subtitle">
            8-point data validation audit, licensing compliance, and quarantine log inspection.
          </p>
        </div>
        <div className="mode-tag-pill" data-testid="data-health-mode-tag">
          Mode: <strong>{modeLabel}</strong>
        </div>
      </div>

      {/* Dataset & Licensing Governance Card */}
      <div className="card">
        <div className="section-header-row">
          <div>
            <h3>Dataset & License Governance</h3>
            <p className="section-note">
              Dataset: <strong>{summary.dataset_name}</strong> | Publisher: <strong>{summary.publisher}</strong>
            </p>
          </div>
          <span className="badge badge-success">License Status: {summary.license_status}</span>
        </div>

        <div className="license-info-grid">
          <div className="license-box">
            <h4>Permitted Research Uses</h4>
            <ul className="license-list">
              {summary.allowed_purposes.map((purpose, i) => (
                <li key={i}>&check; {purpose}</li>
              ))}
            </ul>
          </div>
          <div className="license-box">
            <h4>Mandatory Restrictions</h4>
            <ul className="license-list restriction-list">
              <li>&times; Strictly prohibited from commercial redistribution.</li>
              <li>&times; Prohibited from automated external broker routing without manual human gate.</li>
              <li>&times; Derived feature store must preserve point-in-time timestamp integrity.</li>
            </ul>
          </div>
        </div>
      </div>

      {/* 8-Point Data Audit Checklist */}
      <div className="card" style={{ marginTop: "1.5rem" }}>
        <div className="section-header-row">
          <h3>8-Point Data Integrity Audit</h3>
          <span className="stat-subtext">Total Processed Bars: <strong>{summary.total_bars.toLocaleString()}</strong></span>
        </div>

        <div className="table-responsive">
          <table className="data-table">
            <thead>
              <tr>
                <th>Check #</th>
                <th>Audit Standard</th>
                <th>Specification & Integrity Contract</th>
                <th>Details / Audit Output</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {summary.checks.map((chk, index) => (
                <tr key={chk.check_name}>
                  <td><strong>{index + 1}</strong></td>
                  <td><strong>{chk.check_name}</strong></td>
                  <td>{chk.description}</td>
                  <td>{chk.details}</td>
                  <td>
                    <span className={`badge ${chk.status === "PASS" ? "badge-success" : "badge-danger"}`}>
                      {chk.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Quarantine Log */}
      <div className="card" style={{ marginTop: "1.5rem" }}>
        <div className="section-header-row">
          <h3>Data Quarantine Log ({summary.quarantine_count} Flagged Bars)</h3>
          <span className="badge badge-neutral">Auto-Quarantine Filter Active</span>
        </div>
        <p className="section-note">
          Bars failing session boundaries, zero-volume checks, or geometric integrity are quarantined
          and excluded from causal feature generation.
        </p>

        <div className="table-responsive">
          <table className="data-table">
            <thead>
              <tr>
                <th>Quarantine ID</th>
                <th>Symbol</th>
                <th>Timestamp</th>
                <th>Detected Anomaly</th>
                <th>Resolution</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td><code>Q-001</code></td>
                <td>INFY</td>
                <td>2024-04-12 09:14:00 IST</td>
                <td>Pre-open bar received before session boundary 09:15 IST</td>
                <td><span className="badge badge-warning">QUARANTINED (Purged)</span></td>
              </tr>
              <tr>
                <td><code>Q-002</code></td>
                <td>RELIANCE</td>
                <td>2024-06-04 11:30:00 IST</td>
                <td>Duplicate timestamp bar with conflicting tick volume</td>
                <td><span className="badge badge-warning">QUARANTINED (First Retained)</span></td>
              </tr>
              <tr>
                <td><code>Q-003</code></td>
                <td>TCS</td>
                <td>2024-09-18 15:35:00 IST</td>
                <td>Post-market block trade bar timestamped after 15:30 IST</td>
                <td><span className="badge badge-warning">QUARANTINED (Purged)</span></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
