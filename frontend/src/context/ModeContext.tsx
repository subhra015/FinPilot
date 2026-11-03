/**
 * Data Mode Context & State Management (Layer 0, Layer 13).
 *
 * Governed by:
 * - DATA_AND_PERFORMANCE_POLICY.md §3: Three distinct execution modes;
 *   cross-mode mixing in any evidence output is strictly prohibited.
 */

import React, { createContext, useContext, useState, useMemo } from "react";
import type { DataMode } from "../api/types";

export interface ModeInfo {
  mode: DataMode;
  label: string;
  badgeClass: string;
  description: string;
  warningText: string;
}

// eslint-disable-next-line react-refresh/only-export-components
export const MODE_METADATA: Record<DataMode, ModeInfo> = {
  HISTORICAL_REPLAY: {
    mode: "HISTORICAL_REPLAY",
    label: "HISTORICAL REPLAY",
    badgeClass: "badge-replay",
    description: "Point-in-time causal simulation using historical completed NSE 5-minute candles.",
    warningText: "Historical Replay Mode: Past performance is simulated and does not guarantee future results.",
  },
  FORWARD_PAPER: {
    mode: "FORWARD_PAPER",
    label: "FORWARD PAPER",
    badgeClass: "badge-paper",
    description: "Forward-looking paper execution with next-bar causal fills. Zero real money.",
    warningText: "Forward Paper Mode: Simulated executions under strict ₹30,000 scenario capital without real broker order routing.",
  },
  SYNTHETIC_DEMO: {
    mode: "SYNTHETIC_DEMO",
    label: "SYNTHETIC DEMO",
    badgeClass: "badge-synthetic",
    description: "Isolated synthetic data fixtures for testing and demonstration.",
    warningText: "Synthetic Demo Mode: Artificial fixtures ONLY. Cannot be used or reported as market evidence.",
  },
};

interface ModeContextType {
  mode: DataMode;
  modeInfo: ModeInfo;
  modeLabel: string;
  setMode: (mode: DataMode) => void;
}

const ModeContext = createContext<ModeContextType | undefined>(undefined);

export const ModeProvider: React.FC<{ children: React.ReactNode; initialMode?: DataMode }> = ({
  children,
  initialMode = "HISTORICAL_REPLAY",
}) => {
  const [mode, setMode] = useState<DataMode>(initialMode);

  const modeInfo = useMemo(() => MODE_METADATA[mode], [mode]);
  const modeLabel = modeInfo.label;

  return (
    <ModeContext.Provider value={{ mode, modeInfo, modeLabel, setMode }}>
      {children}
    </ModeContext.Provider>
  );
};

// eslint-disable-next-line react-refresh/only-export-components
export function useDataMode(): ModeContextType {
  const context = useContext(ModeContext);
  if (!context) {
    throw new Error("useDataMode must be used within a ModeProvider");
  }
  return context;
}
