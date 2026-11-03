/**
 * Navigation tabs component for FinPilot Views.
 */

import React from "react";
import { useAuth } from "../context/AuthContext";

export type ViewTab =
  | "research"
  | "scanner"
  | "proposal"
  | "risk"
  | "portfolio"
  | "ledger"
  | "evaluation"
  | "data-health";

interface NavigationProps {
  activeTab: ViewTab;
  onTabChange: (tab: ViewTab) => void;
}

interface TabItem {
  id: ViewTab;
  label: string;
  adminOnly?: boolean;
}

const TABS: TabItem[] = [
  { id: "research", label: "Research Status" },
  { id: "scanner", label: "Stock Scanner" },
  { id: "proposal", label: "Trade Proposal" },
  { id: "risk", label: "Risk Console" },
  { id: "portfolio", label: "Paper Portfolio" },
  { id: "ledger", label: "Prediction Ledger" },
  { id: "evaluation", label: "Evaluation Report" },
  { id: "data-health", label: "Data Health" },
];

export const Navigation: React.FC<NavigationProps> = ({ activeTab, onTabChange }) => {
  const { isAdmin } = useAuth();

  return (
    <nav className="app-nav" aria-label="Main Navigation">
      <ul className="nav-tabs" role="tablist">
        {TABS.map((tab) => {
          const isActive = activeTab === tab.id;
          return (
            <li key={tab.id} role="presentation">
              <button
                type="button"
                role="tab"
                aria-selected={isActive}
                id={`tab-${tab.id}`}
                aria-controls={`panel-${tab.id}`}
                className={`nav-tab ${isActive ? "active" : ""}`}
                onClick={() => onTabChange(tab.id)}
                data-testid={`tab-${tab.id}`}
              >
                {tab.label}
                {tab.id === "risk" && (
                  <span
                    className={`tab-pill ${isAdmin ? "pill-admin" : "pill-user"}`}
                    title={isAdmin ? "Full administrative authority" : "Read-only view"}
                  >
                    {isAdmin ? "Admin" : "Monitor"}
                  </span>
                )}
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
};
