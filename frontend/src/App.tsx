/**
 * FinPilot AI Quantitative Dashboard Main Application (Layer 13).
 *
 * Coordinates:
 * - ModeProvider (HISTORICAL REPLAY, FORWARD PAPER, SYNTHETIC DEMO)
 * - AuthProvider (NIST SP 800-63B-4 auth, session cookies, CSRF, RBAC)
 * - Navigation across 8 required quantitative and risk views
 * - Client-side security: zero unsafe HTML rendering, safe text, no localStorage secrets
 */

import React, { useState } from "react";
import { Header } from "./components/Header";
import { LoginModal } from "./components/LoginModal";
import { ModeBanner } from "./components/ModeBanner";
import { Navigation, ViewTab } from "./components/Navigation";
import { SessionExpiredModal } from "./components/SessionExpiredModal";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { ModeProvider } from "./context/ModeContext";
import "./styles/app.css";
import { DataHealthView } from "./views/DataHealthView";
import { EvaluationReportView } from "./views/EvaluationReportView";
import { PaperPortfolioView } from "./views/PaperPortfolioView";
import { PredictionLedgerView } from "./views/PredictionLedgerView";
import { ResearchStatusView } from "./views/ResearchStatusView";
import { RiskConsoleView } from "./views/RiskConsoleView";
import { StockScannerView } from "./views/StockScannerView";
import { TradeProposalView } from "./views/TradeProposalView";

export const AppContent: React.FC = () => {
  const { sessionExpired, dismissSessionExpired } = useAuth();
  const [activeTab, setActiveTab] = useState<ViewTab>("research");
  const [selectedProposalSymbol, setSelectedProposalSymbol] = useState("TCS");
  const [isLoginModalOpen, setIsLoginModalOpen] = useState(false);

  const handleSelectSymbol = (symbol: string) => {
    setSelectedProposalSymbol(symbol);
    setActiveTab("proposal");
  };

  return (
    <div className="app-layout">
      {/* Top Header */}
      <Header onOpenLogin={() => setIsLoginModalOpen(true)} />

      {/* Prominent Mode Banner */}
      <ModeBanner />

      {/* Primary Navigation Tabs */}
      <Navigation activeTab={activeTab} onTabChange={setActiveTab} />

      {/* Main Content Area */}
      <main className="main-content" id={`panel-${activeTab}`} role="tabpanel">
        {activeTab === "research" && <ResearchStatusView />}
        {activeTab === "scanner" && <StockScannerView onSelectSymbol={handleSelectSymbol} />}
        {activeTab === "proposal" && <TradeProposalView initialSymbol={selectedProposalSymbol} />}
        {activeTab === "risk" && <RiskConsoleView />}
        {activeTab === "portfolio" && <PaperPortfolioView />}
        {activeTab === "ledger" && <PredictionLedgerView />}
        {activeTab === "evaluation" && <EvaluationReportView />}
        {activeTab === "data-health" && <DataHealthView />}
      </main>

      {/* Accessible Footer with Compliance Note */}
      <footer className="app-footer" style={{ textAlign: "center", padding: "1.5rem", color: "var(--text-muted)", fontSize: "0.8rem", borderTop: "1px solid var(--border-color)" }}>
        <p>FinPilot AI Intraday Quantitative System &mdash; Point-in-time research & paper simulation engine.</p>
        <p>No live broker trading features are implemented yet. Benchmark hurdle: ₹300&ndash;₹1,500 on ₹30,000 base capital.</p>
      </footer>

      {/* Modals */}
      <LoginModal isOpen={isLoginModalOpen} onClose={() => setIsLoginModalOpen(false)} />
      <SessionExpiredModal
        isOpen={sessionExpired}
        onDismiss={dismissSessionExpired}
        onReLogin={() => {
          dismissSessionExpired();
          setIsLoginModalOpen(true);
        }}
      />
    </div>
  );
};

export function App() {
  return (
    <ModeProvider>
      <AuthProvider>
        <AppContent />
      </AuthProvider>
    </ModeProvider>
  );
}
