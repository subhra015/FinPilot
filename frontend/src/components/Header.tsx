/**
 * Main application header with distinct Mode Badge, Role Badge, and Auth controls.
 *
 * Governed by:
 * - DATA_AND_PERFORMANCE_POLICY.md §3 (Mode isolation)
 * - SECURITY_CHECKLIST.md SEC-09 (RBAC indicators for UX)
 */

import React from "react";
import { useAuth } from "../context/AuthContext";
import { useDataMode } from "../context/ModeContext";
import type { DataMode } from "../api/types";

interface HeaderProps {
  onOpenLogin: () => void;
}

export const Header: React.FC<HeaderProps> = ({ onOpenLogin }) => {
  const { user, isAuthenticated, isAdmin, logout } = useAuth();
  const { mode, modeInfo, setMode } = useDataMode();

  return (
    <header className="app-header" role="banner">
      <div className="header-left">
        <div className="brand">
          <span className="brand-logo" aria-hidden="true">⚡</span>
          <span className="brand-title">FinPilot AI</span>
          <span className="brand-version" aria-label="Version 0.1.0">v0.1</span>
        </div>

        {/* Distinct Mode Selector */}
        <div className="mode-selector-container">
          <label htmlFor="mode-select" className="sr-only">
            Select Execution Mode
          </label>
          <select
            id="mode-select"
            value={mode}
            onChange={(e) => setMode(e.target.value as DataMode)}
            className={`mode-select ${modeInfo.badgeClass}`}
            data-testid="mode-select"
            aria-label="Execution mode selection"
          >
            <option value="HISTORICAL_REPLAY">HISTORICAL REPLAY</option>
            <option value="FORWARD_PAPER">FORWARD PAPER</option>
            <option value="SYNTHETIC_DEMO">SYNTHETIC DEMO</option>
          </select>
          <span
            className={`mode-badge ${modeInfo.badgeClass}`}
            data-testid="current-mode-badge"
          >
            {modeInfo.label}
          </span>
        </div>
      </div>

      <div className="header-right">
        {isAuthenticated && user ? (
          <div className="user-profile-badge" data-testid="user-profile">
            <span className="user-email" title={user.email} data-testid="user-email">
              {user.email}
            </span>
            <span
              className={`role-badge ${isAdmin ? "role-admin" : "role-user"}`}
              data-testid="user-role-badge"
            >
              {user.role}
            </span>
            <button
              type="button"
              onClick={() => void logout()}
              className="btn btn-secondary btn-sm"
              data-testid="logout-button"
            >
              Sign Out
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={onOpenLogin}
            className="btn btn-primary btn-sm"
            data-testid="login-button"
          >
            Sign In / Register
          </button>
        )}
      </div>
    </header>
  );
};
