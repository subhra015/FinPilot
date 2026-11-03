/**
 * Risk Console View (Layer 13).
 *
 * Implements:
 * - 11 Deny-by-default controls verification table.
 * - Emergency Kill Switch and Manual Trading Pause toggles.
 * - Role-based authorization display (SEC-09: admin actions enabled for ADMIN, disabled with clear notice for USER).
 * - Cryptographically signed administrative audit log stream.
 */

import React, { useEffect, useState } from "react";
import {
  fetchRiskAuditLog,
  fetchRiskConfig,
  setKillSwitch,
  setManualTradingPaused,
} from "../api/services";
import { RiskConfigState } from "../api/types";
import { useAuth } from "../context/AuthContext";
import { useDataMode } from "../context/ModeContext";

export const RiskConsoleView: React.FC = () => {
  const { modeLabel } = useDataMode();
  const { isAdmin, user } = useAuth();
  const [config, setConfig] = useState<RiskConfigState | null>(null);
  const [auditLogs, setAuditLogs] = useState<{ event_id: string; timestamp: string; action: string; user_id: string; checksum: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const loadData = async () => {
    try {
      const [cfg, logs] = await Promise.all([fetchRiskConfig(), fetchRiskAuditLog()]);
      setConfig(cfg);
      setAuditLogs(logs);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to load risk state");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleToggleKillSwitch = async () => {
    if (!isAdmin) return;
    setActionMessage(null);
    setActionError(null);
    try {
      const nextState = !config?.kill_switch_active;
      await setKillSwitch(nextState);
      setActionMessage(
        nextState
          ? "CRITICAL: Emergency Kill Switch ENGAGED. All trading halted."
          : "Emergency Kill Switch DISENGAGED. Normal risk checks active."
      );
      await loadData();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Kill switch request failed");
    }
  };

  const handleToggleManualPause = async () => {
    if (!isAdmin) return;
    setActionMessage(null);
    setActionError(null);
    try {
      const nextState = !config?.manual_trading_paused;
      await setManualTradingPaused(nextState);
      setActionMessage(
        nextState
          ? "Manual Trading PAUSED. New entries blocked."
          : "Manual Trading RESUMED."
      );
      await loadData();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Trading pause request failed");
    }
  };

  return (
    <div className="view-container" role="region" aria-label="Risk Console View">
      <div className="view-header">
        <div>
          <h2>Risk Console & Autonomous Safety Engine</h2>
          <p className="subtitle">
            Independent risk engine with 11 deny-by-default rules and fail-closed architecture.
          </p>
        </div>
        <div className="mode-tag-pill" data-testid="risk-mode-tag">
          Mode: <strong>{modeLabel}</strong>
        </div>
      </div>

      {/* Role Notice Banner (SEC-09) */}
      <div className={`alert-card ${isAdmin ? "alert-warning" : "alert-info"}`}>
        <h4>Authority Level: {isAdmin ? "ADMINISTRATOR (Full Authority)" : "MONITOR (Read-Only)"}</h4>
        <p>
          {isAdmin ? (
            <>You are logged in as <strong>{user?.email}</strong> with <code>ADMIN</code> role. You have full authority to operate emergency switches, modify risk limits, and trigger forced halts. All administrative mutations generate signed audit events.</>
          ) : (
            <>You are currently in <strong>Read-Only Monitoring Mode</strong>. Modifying risk parameters or toggling emergency switches requires administrative authority (SEC-09). The server authoritatively rejects non-admin attempts.</>
          )}
        </p>
      </div>

      {actionMessage && (
        <div className="alert-card alert-success" role="status">
          {actionMessage}
        </div>
      )}
      {actionError && (
        <div className="alert-card alert-danger" role="alert">
          {actionError}
        </div>
      )}

      {/* Emergency Control Panel */}
      <div className="emergency-panel card">
        <div className="emergency-header">
          <div>
            <h3>Emergency Operational Controls</h3>
            <p className="section-note">
              Immediate system-wide intervention. Kill switch halts all order routing instantly.
            </p>
          </div>
          <div className="emergency-actions">
            <button
              type="button"
              className={`btn ${config?.kill_switch_active ? "btn-success" : "btn-danger"}`}
              onClick={handleToggleKillSwitch}
              disabled={!isAdmin || loading}
              title={isAdmin ? "Toggle Emergency Kill Switch" : "Admin authority required"}
              data-testid="kill-switch-btn"
            >
              {config?.kill_switch_active ? "Disengage Kill Switch" : "ACTIVATE KILL SWITCH"}
            </button>

            <button
              type="button"
              className={`btn ${config?.manual_trading_paused ? "btn-secondary" : "btn-warning"}`}
              onClick={handleToggleManualPause}
              disabled={!isAdmin || loading}
              title={isAdmin ? "Toggle Manual Trading Pause" : "Admin authority required"}
              data-testid="pause-trading-btn"
            >
              {config?.manual_trading_paused ? "Resume Trading" : "Pause Trading"}
            </button>
          </div>
        </div>

        {/* Current Risk Limit Parameters */}
        <div className="risk-params-grid">
          <div className="param-card">
            <span className="param-title">Max Daily Loss</span>
            <span className="param-value text-negative">₹{config?.max_daily_loss.toFixed(2)}</span>
            <span className="param-note">3.0% of scenario capital</span>
          </div>
          <div className="param-card">
            <span className="param-title">Max Drawdown Limit</span>
            <span className="param-value text-warning">{config?.max_drawdown_pct.toFixed(2)}%</span>
            <span className="param-note">Triggers trading suspension</span>
          </div>
          <div className="param-card">
            <span className="param-title">Per-Trade Stop Risk</span>
            <span className="param-value">{config?.max_stop_risk_pct.toFixed(2)}%</span>
            <span className="param-note">&le; ₹450 per order</span>
          </div>
          <div className="param-card">
            <span className="param-title">Max Concurrent Positions</span>
            <span className="param-value">{config?.max_concurrent_positions}</span>
            <span className="param-note">Baseline single-position</span>
          </div>
        </div>
      </div>

      {/* 11 Deny-by-Default Checks Table */}
      <div className="card" style={{ marginTop: "1.5rem" }}>
        <h3>11 Deny-by-Default Gate Controls</h3>
        <p className="section-note">
          Independent risk engine authorization contract. Any rule failure causes immediate proposal rejection.
        </p>
        <div className="table-responsive">
          <table className="data-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Safety Gate</th>
                <th>Limit & Policy Requirement</th>
                <th>Observed State</th>
                <th>Gate Status</th>
              </tr>
            </thead>
            <tbody>
              {config?.rules.map((rule) => (
                <tr key={rule.rule_id}>
                  <td><strong>{rule.rule_id}</strong></td>
                  <td>{rule.name}</td>
                  <td>{rule.limit_description}</td>
                  <td><code>{rule.current_value}</code></td>
                  <td>
                    <span className={`badge ${rule.is_passing ? "badge-success" : "badge-danger"}`}>
                      {rule.is_passing ? "PASSING" : "BLOCKED"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Signed Administrative Audit Trail */}
      <div className="card" style={{ marginTop: "1.5rem" }}>
        <h3>Signed Administrative Audit Trail</h3>
        <p className="section-note">
          Cryptographically hashed risk configuration changes and operator interventions.
        </p>
        <div className="table-responsive">
          <table className="data-table">
            <thead>
              <tr>
                <th>Audit ID</th>
                <th>Timestamp</th>
                <th>Operator</th>
                <th>Action & Parameters</th>
                <th>Integrity Checksum</th>
              </tr>
            </thead>
            <tbody>
              {auditLogs.map((log) => (
                <tr key={log.event_id}>
                  <td><code>{log.event_id}</code></td>
                  <td>{log.timestamp}</td>
                  <td>{log.user_id}</td>
                  <td><code>{log.action}</code></td>
                  <td><code className="text-muted">{log.checksum}</code></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
