/**
 * Authentication & RBAC UX Tests (SEC-01, SEC-09, SEC-15).
 *
 * Tests NIST SP 800-63B-4 password policy, 401 session expiration, and RBAC views.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LoginModal } from "../components/LoginModal";
import { SessionExpiredModal } from "../components/SessionExpiredModal";
import { AuthProvider } from "../context/AuthContext";
import { ModeProvider } from "../context/ModeContext";
import { RiskConsoleView } from "../views/RiskConsoleView";

describe("Authentication & RBAC Flows", () => {
  it("enforces NIST SP 800-63B-4 guidance on registration form in LoginModal", () => {
    render(
      <AuthProvider>
        <LoginModal isOpen={true} onClose={() => {}} />
      </AuthProvider>
    );

    // Switch to Register form via the register link button
    const registerBtn = screen.getByTestId("switch-to-register-btn");
    fireEvent.click(registerBtn);

    // Check for NIST guidance notice
    expect(
      screen.getByText(/NIST SP 800-63B-4: 15\+ characters/i)
    ).toBeInTheDocument();

    const emailInput = screen.getByTestId("reg-email-input");
    const passwordInput = screen.getByTestId("reg-password-input");
    const submitBtn = screen.getByRole("button", { name: /create account/i });

    // Enter invalid short password (less than 15 characters for single-factor user)
    fireEvent.change(emailInput, { target: { value: "test@finpilot.io" } });
    fireEvent.change(passwordInput, { target: { value: "shortpass" } });
    fireEvent.click(submitBtn);

    // Validation alert must appear
    expect(
      screen.getByText(/Password must be at least 15 characters/i)
    ).toBeInTheDocument();
  });

  it("SessionExpiredModal renders dialog and handles re-login callback", () => {
    let reLoginTriggered = false;
    let dismissTriggered = false;

    render(
      <SessionExpiredModal
        isOpen={true}
        onDismiss={() => {
          dismissTriggered = true;
        }}
        onReLogin={() => {
          reLoginTriggered = true;
        }}
      />
    );

    expect(screen.getByText(/Session Expired/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Your secure authentication session has expired/i)
    ).toBeInTheDocument();

    // Click Sign In Again button
    const reLoginBtn = screen.getByRole("button", { name: /sign in again/i });
    fireEvent.click(reLoginBtn);
    expect(reLoginTriggered).toBe(true);

    // Click Dismiss button
    const dismissBtn = screen.getByRole("button", { name: /dismiss/i });
    fireEvent.click(dismissBtn);
    expect(dismissTriggered).toBe(true);
  });

  it("SEC-09: RiskConsoleView restricts emergency kill-switch when not logged in as Admin", async () => {
    render(
      <ModeProvider>
        <AuthProvider>
          <RiskConsoleView />
        </AuthProvider>
      </ModeProvider>
    );

    // In default unauthenticated state, user is in read-only monitor mode
    expect(await screen.findByText(/MONITOR \(Read-Only\)/i)).toBeInTheDocument();

    const killSwitchBtn = screen.getByTestId("kill-switch-btn");
    expect(killSwitchBtn).toBeDisabled();
    expect(killSwitchBtn).toHaveAttribute("title", "Admin authority required");

    const pauseBtn = screen.getByTestId("pause-trading-btn");
    expect(pauseBtn).toBeDisabled();
  });
});
