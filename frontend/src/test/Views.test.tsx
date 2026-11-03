/**
 * Frontend Views & Domain Logic Tests (Layer 13).
 *
 * Verifies:
 * - Rendering of Stock Scanner, Trade Proposal, Portfolio, Ledger, Evaluation, and Data Health.
 * - Mode isolation and switching (HISTORICAL REPLAY, FORWARD PAPER, SYNTHETIC DEMO).
 * - Client-side proposal validation (Q >= 1, integer, stops).
 * - Statutory fee schedule calculation accuracy.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { calculateStatutoryFees } from "../api/services";
import { Header } from "../components/Header";
import { ModeBanner } from "../components/ModeBanner";
import { AuthProvider } from "../context/AuthContext";
import { ModeProvider } from "../context/ModeContext";
import { DataHealthView } from "../views/DataHealthView";
import { EvaluationReportView } from "../views/EvaluationReportView";
import { PaperPortfolioView } from "../views/PaperPortfolioView";
import { PredictionLedgerView } from "../views/PredictionLedgerView";
import { StockScannerView } from "../views/StockScannerView";
import { TradeProposalView } from "../views/TradeProposalView";

describe("Domain Views & Mechanics", () => {
  it("renders StockScannerView with causal volume and PIT eligibility filters", async () => {
    render(
      <ModeProvider>
        <StockScannerView />
      </ModeProvider>
    );

    expect(screen.getByText(/Stock Scanner & Causal Features/i)).toBeInTheDocument();
    expect(screen.getByText(/Causal Volume & Session Isolation Guarantees/i)).toBeInTheDocument();
    expect(await screen.findByText("TCS")).toBeInTheDocument();
    expect(screen.getByText("INFY")).toBeInTheDocument();
    expect(screen.getByText("RELIANCE")).toBeInTheDocument();
  });

  it("TradeProposalView enforces integer Q >= 1 and stop loss constraints", async () => {
    render(
      <ModeProvider>
        <TradeProposalView />
      </ModeProvider>
    );

    const quantityInput = screen.getByLabelText(/Quantity \(Q >= 1 Integer\)/i);
    const stopLossInput = screen.getByLabelText(/Stop Loss \(₹\)/i);
    const entryPriceInput = screen.getByLabelText(/Entry Price \(₹\)/i);
    const submitBtn = screen.getByTestId("generate-proposal-btn");

    // Case 1: Fractional quantity should fail validation
    fireEvent.change(quantityInput, { target: { value: "2.5" } });
    fireEvent.click(submitBtn);
    expect(
      screen.getByText(/Quantity must be a positive integer \(Q >= 1\)\. Fractional shares are forbidden\./i)
    ).toBeInTheDocument();

    // Case 2: Stop loss >= Entry price for long proposal should fail validation
    fireEvent.change(quantityInput, { target: { value: "5" } });
    fireEvent.change(entryPriceInput, { target: { value: "1000" } });
    fireEvent.change(stopLossInput, { target: { value: "1050" } });
    fireEvent.click(submitBtn);
    expect(
      screen.getByText(/For a long proposal, Stop Loss must be strictly below Entry Price\./i)
    ).toBeInTheDocument();

    // Case 3: Valid inputs succeed and show statutory fees
    fireEvent.change(stopLossInput, { target: { value: "980" } });
    fireEvent.click(submitBtn);
    expect(await screen.findByText(/Total Round-Trip Costs/i)).toBeInTheDocument();
  });

  it("calculates statutory Indian equity intraday transaction fees correctly", () => {
    // 10 shares of stock bought at ₹3,000 and sold at ₹3,050
    // Buy turnover = ₹30,000, Sell turnover = ₹30,500, Total turnover = ₹60,500
    const fees = calculateStatutoryFees("BUY", 3000, 3050, 10);

    expect(fees.brokerage).toBeGreaterThan(0);
    expect(fees.stt).toBeCloseTo(30500 * 0.00025, 2); // STT on sell leg
    expect(fees.exchange_turnover).toBeCloseTo(60500 * 0.0000325, 2);
    expect(fees.stamp_duty).toBeCloseTo(30000 * 0.00003, 2); // Stamp duty on buy leg
    expect(fees.gst).toBeGreaterThan(0);
    expect(fees.total_costs).toBeGreaterThan(20);
  });

  it("renders PaperPortfolioView with authoritative ₹30,000 capital and position actions", async () => {
    render(
      <ModeProvider>
        <PaperPortfolioView />
      </ModeProvider>
    );

    expect(await screen.findByText(/Initial Scenario Capital/i)).toBeInTheDocument();
    expect(screen.getByText(/30,000.00/i)).toBeInTheDocument();
    expect(screen.getByText(/SEC-19: Server-Authoritative Portfolio Accounting/i)).toBeInTheDocument();

    // Check position action buttons
    const squareOffBtn = await screen.findByTestId("square-off-TCS");
    expect(squareOffBtn).toBeInTheDocument();
    fireEvent.click(squareOffBtn);
    expect(
      screen.getByText(/Orderly Square-off requested for 7 shares of TCS/i)
    ).toBeInTheDocument();
  });

  it("renders PredictionLedgerView and supports deterministic replay verification", async () => {
    render(
      <ModeProvider>
        <PredictionLedgerView />
      </ModeProvider>
    );

    expect(screen.getByText(/Prediction Ledger & Audit Trail/i)).toBeInTheDocument();
    expect(screen.getByText(/Cryptographic Hash-Chained Invariant/i)).toBeInTheDocument();

    // Replay Verification Trigger
    const replayBtn = screen.getByTestId("verify-replay-btn");
    expect(replayBtn).toBeInTheDocument();
    fireEvent.click(replayBtn);

    expect(await screen.findByTestId("replay-results")).toBeInTheDocument();
    expect(screen.getByText(/REPLAY VALIDATED: ZERO TAMPERING/i)).toBeInTheDocument();
  });

  it("renders EvaluationReportView with all baselines and Murphy Brier score decomposition", async () => {
    render(
      <ModeProvider>
        <EvaluationReportView />
      </ModeProvider>
    );

    expect(screen.getByText(/Evaluation Benchmark & Model Diagnostics/i)).toBeInTheDocument();
    expect(await screen.findByText("REF-NOTRADE-V1")).toBeInTheDocument();
    expect(screen.getByText("STRAT-SIMPLE-V1")).toBeInTheDocument();
    expect(screen.getByText("MODEL-LOGREG-V1")).toBeInTheDocument();
    expect(screen.getByText("MODEL-LIGHTGBM-V1")).toBeInTheDocument();

    // Murphy Brier Decomposition check
    expect(screen.getByText(/Probability Calibration & Murphy Brier Decomposition/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Reliability \(Calibration Error\)/i).length).toBeGreaterThan(0);
  });

  it("renders DataHealthView with 8-point checklist and license terms", async () => {
    render(
      <ModeProvider>
        <DataHealthView />
      </ModeProvider>
    );

    expect(await screen.findByText(/8-Point Data Integrity Audit/i)).toBeInTheDocument();
    expect(screen.getByText(/Session Boundary Verification/i)).toBeInTheDocument();
    expect(screen.getByText(/Causal Relative Volume Check/i)).toBeInTheDocument();
    expect(screen.getByText(/Permitted Research Uses/i)).toBeInTheDocument();
    expect(screen.getByText(/Data Quarantine Log/i)).toBeInTheDocument();
  });

  it("Mode switching updates ModeBanner and labels distinctly across execution modes", () => {
    render(
      <ModeProvider>
        <AuthProvider>
          <Header onOpenLogin={() => {}} />
          <ModeBanner />
        </AuthProvider>
      </ModeProvider>
    );

    // Default mode is HISTORICAL REPLAY
    expect(screen.getByText(/Historical Replay Mode:/i)).toBeInTheDocument();

    // Switch to FORWARD PAPER
    const select = screen.getByRole("combobox", { name: /execution mode/i });
    fireEvent.change(select, { target: { value: "FORWARD_PAPER" } });

    expect(screen.getByText(/Forward Paper Mode:/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Simulated executions under strict ₹30,000 scenario capital/i)
    ).toBeInTheDocument();

    // Switch to SYNTHETIC DEMO
    fireEvent.change(select, { target: { value: "SYNTHETIC_DEMO" } });
    expect(screen.getByText(/Synthetic Demo Mode:/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Cannot be used or reported as market evidence/i)
    ).toBeInTheDocument();
  });
});
