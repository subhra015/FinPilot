/**
 * Session Expiration Alert Modal (SEC-15).
 *
 * Triggered automatically when an API request returns 401 Unauthorized.
 */

import React from "react";

interface SessionExpiredModalProps {
  isOpen: boolean;
  onDismiss: () => void;
  onReLogin: () => void;
}

export const SessionExpiredModal: React.FC<SessionExpiredModalProps> = ({
  isOpen,
  onDismiss,
  onReLogin,
}) => {
  if (!isOpen) {
    return null;
  }

  return (
    <div
      className="modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="session-expired-title"
      data-testid="session-expired-modal"
    >
      <div className="modal-content">
        <h2 id="session-expired-title" className="modal-title">
          Session Expired
        </h2>
        <p className="modal-body">
          Your secure authentication session has expired due to inactivity (30m) or absolute lifetime (12h).
          Please sign in again to continue.
        </p>
        <div className="modal-actions">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={onDismiss}
            data-testid="session-dismiss-btn"
          >
            Dismiss
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => {
              onDismiss();
              onReLogin();
            }}
            data-testid="session-relogin-btn"
          >
            Sign In Again
          </button>
        </div>
      </div>
    </div>
  );
};
