/**
 * Prediction Ledger & Audit View (Layer 13).
 *
 * Implements:
 * - Append-only event stream inspection.
 * - Visual SHA-256 cryptographic hash-chaining verification.
 * - Explicit correction event policy (never mutate prior events in place).
 * - Interactive deterministic replay verification trigger.
 */

import React, { useEffect, useState } from "react";
import { fetchLedgerEvents, triggerReplayVerification } from "../api/services";
import { LedgerEventRecord, ReplayVerificationResponse } from "../api/types";
import { useDataMode } from "../context/ModeContext";

export const PredictionLedgerView: React.FC = () => {
  const { modeLabel } = useDataMode();
  const [events, setEvents] = useState<LedgerEventRecord[]>([]);
  const [replayResult, setReplayResult] = useState<ReplayVerificationResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [replaying, setReplaying] = useState(false);

  useEffect(() => {
    let mounted = true;
    fetchLedgerEvents()
      .then((res) => {
        if (mounted) {
          setEvents(res);
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

  const handleVerifyReplay = async () => {
    setReplaying(true);
    try {
      const res = await triggerReplayVerification();
      setReplayResult(res);
    } finally {
      setReplaying(false);
    }
  };

  return (
    <div className="view-container" role="region" aria-label="Prediction Ledger View">
      <div className="view-header">
        <div>
          <h2>Prediction Ledger & Audit Trail</h2>
          <p className="subtitle">
            Append-only, SHA-256 hash-chained event store with deterministic replay verification.
          </p>
        </div>
        <div className="mode-tag-pill" data-testid="ledger-mode-tag">
          Mode: <strong>{modeLabel}</strong>
        </div>
      </div>

      {/* Append-Only & Hash-Chaining Explanation Banner */}
      <div className="alert-card alert-info">
        <h4>Cryptographic Hash-Chained Invariant</h4>
        <p>
          Each ledger event calculates an immutable SHA-256 hash:{" "}
          <code>H_n = SHA256(H_&#123;n-1&#125; || EventPayload)</code>. Historical records cannot be
          modified or deleted. Corrections are recorded as explicit <code>CORRECTION</code> events
          referencing the prior event ID with documented justification.
        </p>
      </div>

      {/* Replay Verification Trigger Card */}
      <div className="card">
        <div className="section-header-row">
          <div>
            <h3>Deterministic Replay Verification</h3>
            <p className="section-note">
              Reconstruct cash, position balances, and realized P&L from the genesis block forward.
            </p>
          </div>
          <button
            type="button"
            className="btn-primary"
            onClick={handleVerifyReplay}
            disabled={replaying}
            data-testid="verify-replay-btn"
          >
            {replaying ? "Replaying Ledger..." : "Run Replay Verification"}
          </button>
        </div>

        {replayResult && (
          <div className="replay-results-card" data-testid="replay-results">
            <div className="replay-status-header">
              <span className={`badge ${replayResult.is_valid && !replayResult.tamper_detected ? "badge-success" : "badge-danger"}`}>
                {replayResult.is_valid && !replayResult.tamper_detected ? "REPLAY VALIDATED: ZERO TAMPERING" : "TAMPER DETECTED"}
              </span>
              <span>Events Replayed: <strong>{replayResult.events_replayed}</strong></span>
              <span>Hash Chain: <strong>{replayResult.chain_verified ? "Continuous & Intact" : "Broken"}</strong></span>
            </div>
            <div className="replay-stats-row">
              <div>Reconstructed Cash: <strong>₹{replayResult.reconstructed_cash}</strong></div>
              <div>Realized P&L: <strong>₹{replayResult.reconstructed_realized_pnl}</strong></div>
              <div>Corrections Applied: <strong>{replayResult.corrections_applied}</strong></div>
            </div>
          </div>
        )}
      </div>

      {/* Append-Only Event Log Table */}
      <div className="card" style={{ marginTop: "1.5rem" }}>
        <h3>Append-Only Audit Stream</h3>
        {loading ? (
          <div className="loading-spinner">Loading ledger events...</div>
        ) : (
          <div className="table-responsive">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Seq #</th>
                  <th>Event ID</th>
                  <th>Type</th>
                  <th>Symbol</th>
                  <th>Timestamp</th>
                  <th>Previous Hash (H_n-1)</th>
                  <th>Integrity Hash (H_n)</th>
                  <th>Payload Preview</th>
                </tr>
              </thead>
              <tbody>
                {events.map((evt) => (
                  <tr key={evt.event_id}>
                    <td><strong>{evt.sequence_number}</strong></td>
                    <td><code>{evt.event_id}</code></td>
                    <td>
                      <span className={`badge ${
                        evt.event_type === "CORRECTION"
                          ? "badge-warning"
                          : evt.event_type === "FILL"
                          ? "badge-success"
                          : "badge-neutral"
                      }`}>
                        {evt.event_type}
                      </span>
                    </td>
                    <td>{evt.symbol || "—"}</td>
                    <td>{evt.timestamp}</td>
                    <td>
                      <code className="text-muted" title={evt.prev_hash}>
                        {evt.prev_hash.slice(0, 10)}...{evt.prev_hash.slice(-6)}
                      </code>
                    </td>
                    <td>
                      <code className="text-highlight" title={evt.integrity_hash}>
                        {evt.integrity_hash.slice(0, 10)}...{evt.integrity_hash.slice(-6)}
                      </code>
                    </td>
                    <td>
                      <code className="payload-preview">
                        {JSON.stringify(evt.payload).slice(0, 50)}...
                      </code>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
