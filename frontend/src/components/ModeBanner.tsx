/**
 * Persistent high-visibility mode banner preventing mode confusion (SEC-06, SEC-19).
 */

import React from "react";
import { useDataMode } from "../context/ModeContext";

export const ModeBanner: React.FC = () => {
  const { modeInfo } = useDataMode();

  return (
    <div
      className={`mode-banner ${modeInfo.badgeClass}`}
      role="alert"
      data-testid="mode-banner"
    >
      <div className="banner-content">
        <span className="banner-icon" aria-hidden="true">
          ℹ️
        </span>
        <span className="banner-text">
          <strong>{modeInfo.label}:</strong> {modeInfo.warningText}
        </span>
      </div>
    </div>
  );
};
