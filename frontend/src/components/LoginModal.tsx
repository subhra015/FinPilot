/**
 * Sign In / Registration Modal with NIST SP 800-63B-4 guidance and TOTP MFA step (SEC-01, SEC-05, SEC-15).
 */

import React, { useState } from "react";
import { useAuth } from "../context/AuthContext";
import type { UserRole } from "../api/types";

interface LoginModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const LoginModal: React.FC<LoginModalProps> = ({ isOpen, onClose }) => {
  const { login, verifyMfa, register } = useAuth();

  const [mode, setMode] = useState<"login" | "register" | "mfa">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<UserRole>("USER");
  const [totpCode, setTotpCode] = useState("");
  const [pendingUserId, setPendingUserId] = useState<string>("");

  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (!isOpen) {
    return null;
  }

  const resetState = () => {
    setEmail("");
    setPassword("");
    setTotpCode("");
    setPendingUserId("");
    setError(null);
    setSuccessMsg(null);
    setMode("login");
  };

  const handleClose = () => {
    resetState();
    onClose();
  };

  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      const res = await login(email, password);
      if (res.mfaRequired && res.userId) {
        setPendingUserId(res.userId);
        setMode("mfa");
      } else {
        handleClose();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleMfaSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);

    if (totpCode.trim().length !== 6 || !/^\d{6}$/.test(totpCode.trim())) {
      setError("Please enter a valid 6-digit numeric TOTP code.");
      setIsSubmitting(false);
      return;
    }

    try {
      await verifyMfa(pendingUserId, totpCode.trim());
      handleClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "MFA verification failed.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRegisterSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccessMsg(null);

    // Client-side validation enforcing NIST SP 800-63B-4 for user guidance
    const minLength = role === "ADMIN" ? 8 : 15;
    if (password.length < minLength) {
      setError(
        `NIST Policy: Password must be at least ${minLength} characters for ${
          role === "ADMIN" ? "MFA-enabled Admin" : "single-factor User"
        }.`
      );
      return;
    }

    setIsSubmitting(true);
    try {
      await register(email, password, role);
      setSuccessMsg("Registration successful! You can now sign in.");
      setMode("login");
      setPassword("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      className="modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="auth-modal-title"
      data-testid="auth-modal"
    >
      <div className="modal-content auth-modal-content">
        <div className="modal-header">
          <h2 id="auth-modal-title" className="modal-title">
            {mode === "login" && "Sign In to FinPilot AI"}
            {mode === "register" && "Create Researcher Account"}
            {mode === "mfa" && "Two-Factor Verification (TOTP)"}
          </h2>
          <button
            type="button"
            className="modal-close"
            onClick={handleClose}
            aria-label="Close authentication modal"
          >
            ×
          </button>
        </div>

        {error && (
          <div className="alert alert-error" role="alert" data-testid="auth-error-alert">
            {error}
          </div>
        )}

        {successMsg && (
          <div className="alert alert-success" role="status" data-testid="auth-success-alert">
            {successMsg}
          </div>
        )}

        {/* 1. Login Form */}
        {mode === "login" && (
          <form onSubmit={handleLoginSubmit} className="auth-form" data-testid="login-form">
            <div className="form-group">
              <label htmlFor="login-email">Email Address</label>
              <input
                id="login-email"
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="trader@finpilot.test"
                className="form-input"
                data-testid="login-email-input"
              />
            </div>

            <div className="form-group">
              <label htmlFor="login-password">Password / Passphrase</label>
              <input
                id="login-password"
                type="password"
                required
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter password..."
                className="form-input"
                data-testid="login-password-input"
              />
            </div>

            <div className="form-actions">
              <button
                type="submit"
                disabled={isSubmitting}
                className="btn btn-primary btn-block"
                data-testid="login-submit-btn"
              >
                {isSubmitting ? "Authenticating..." : "Sign In"}
              </button>
            </div>

            <div className="auth-switch">
              <span>Don't have an account? </span>
              <button
                type="button"
                className="btn-link"
                onClick={() => {
                  setError(null);
                  setMode("register");
                }}
                data-testid="switch-to-register-btn"
              >
                Register
              </button>
            </div>
          </form>
        )}

        {/* 2. Registration Form */}
        {mode === "register" && (
          <form onSubmit={handleRegisterSubmit} className="auth-form" data-testid="register-form">
            <div className="form-group">
              <label htmlFor="reg-email">Email Address</label>
              <input
                id="reg-email"
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="researcher@finpilot.test"
                className="form-input"
                data-testid="reg-email-input"
              />
            </div>

            <div className="form-group">
              <label htmlFor="reg-role">Account Role</label>
              <select
                id="reg-role"
                value={role}
                onChange={(e) => setRole(e.target.value as UserRole)}
                className="form-select"
                data-testid="reg-role-select"
              >
                <option value="USER">User (Standard Researcher)</option>
                <option value="ADMIN">Admin (Full Risk Authority & Kill Switch)</option>
              </select>
            </div>

            <div className="form-group">
              <label htmlFor="reg-password">
                Passphrase ({role === "ADMIN" ? "≥ 8 chars" : "≥ 15 chars"})
              </label>
              <input
                id="reg-password"
                type="password"
                required
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="e.g. correct horse battery staple"
                className="form-input"
                data-testid="reg-password-input"
              />
              <span className="form-hint">
                NIST SP 800-63B-4: {role === "ADMIN" ? "8+" : "15+"} characters. No arbitrary uppercase/symbol rules required.
              </span>
            </div>

            <div className="form-actions">
              <button
                type="submit"
                disabled={isSubmitting}
                className="btn btn-primary btn-block"
                data-testid="register-submit-btn"
              >
                {isSubmitting ? "Creating Account..." : "Create Account"}
              </button>
            </div>

            <div className="auth-switch">
              <span>Already registered? </span>
              <button
                type="button"
                className="btn-link"
                onClick={() => {
                  setError(null);
                  setMode("login");
                }}
                data-testid="switch-to-login-btn"
              >
                Sign In
              </button>
            </div>
          </form>
        )}

        {/* 3. TOTP MFA Form */}
        {mode === "mfa" && (
          <form onSubmit={handleMfaSubmit} className="auth-form" data-testid="mfa-form">
            <p className="mfa-instructions">
              Enter the 6-digit verification code from your authenticator application (RFC 6238 TOTP).
            </p>
            <div className="form-group">
              <label htmlFor="totp-code">Authentication Code</label>
              <input
                id="totp-code"
                type="text"
                inputMode="numeric"
                pattern="[0-9]*"
                maxLength={6}
                required
                autoFocus
                value={totpCode}
                onChange={(e) => setTotpCode(e.target.value)}
                placeholder="123456"
                className="form-input text-center text-lg"
                data-testid="totp-code-input"
              />
            </div>

            <div className="form-actions">
              <button
                type="submit"
                disabled={isSubmitting}
                className="btn btn-primary btn-block"
                data-testid="mfa-submit-btn"
              >
                {isSubmitting ? "Verifying Code..." : "Verify & Sign In"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};
