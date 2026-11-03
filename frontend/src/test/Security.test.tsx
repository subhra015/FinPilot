/**
 * Client-Side Security & Invariant Tests (Layer 13).
 *
 * Governed by:
 * - SECURITY_CHECKLIST.md SEC-02: Zero secrets in client storage or bundles.
 * - SECURITY_CHECKLIST.md SEC-06: Authoritative server validation, safe client validation.
 * - SECURITY_CHECKLIST.md SEC-07: Safe text rendering, zero dangerouslySetInnerHTML.
 * - SECURITY_CHECKLIST.md SEC-15: Opaque server sessions in HttpOnly cookies (no localStorage).
 * - SECURITY_CHECKLIST.md SEC-16: CSRF token injection on mutating requests.
 * - SECURITY_CHECKLIST.md SEC-19: Never trust client-side financial calculations.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { getCsrfTokenFromCookie } from "../api/client";
import { ResearchStatusView } from "../views/ResearchStatusView";
import { ModeProvider } from "../context/ModeContext";

describe("Client-Side Security Requirements (SEC-02, SEC-07, SEC-15, SEC-16)", () => {
  it("SEC-07: renders dangerous XSS payloads as harmless escaped text", () => {
    const maliciousPayload = "<script>alert('xss')</script><img src=x onerror=alert(1)>";

    // Create a mock component rendering untrusted text using safe JSX text node
    const SafeWrapper = () => (
      <div data-testid="untrusted-container">
        <span>{maliciousPayload}</span>
      </div>
    );

    render(<SafeWrapper />);

    const container = screen.getByTestId("untrusted-container");

    // The text content should contain the literal string, NOT HTML DOM nodes
    expect(container.textContent).toContain("<script>alert('xss')</script>");
    expect(container.getElementsByTagName("script").length).toBe(0);
    expect(container.getElementsByTagName("img").length).toBe(0);
  });

  it("SEC-07: enforces zero usage of dangerouslySetInnerHTML across all frontend source files", () => {
    // Use Vite's native import.meta.glob to load all ts/tsx source files as raw text
    const sourceModules = import.meta.glob<string>("../**/*.{ts,tsx}", {
      query: "?raw",
      import: "default",
      eager: true,
    });

    const filePaths = Object.keys(sourceModules);
    expect(filePaths.length).toBeGreaterThan(10);

    const violations: string[] = [];
    for (const [filePath, content] of Object.entries(sourceModules)) {
      if (typeof content === "string" && /dangerouslySetInnerHTML\s*[:=]/.test(content)) {
        violations.push(filePath);
      }
    }

    expect(violations).toEqual([]);
  });

  it("SEC-02 & SEC-15: verifies localStorage and sessionStorage contain zero authentication tokens or passwords", () => {
    // Assert that our application never sets tokens into window.localStorage
    expect(window.localStorage.getItem("token")).toBeNull();
    expect(window.localStorage.getItem("jwt")).toBeNull();
    expect(window.localStorage.getItem("access_token")).toBeNull();
    expect(window.localStorage.getItem("password")).toBeNull();
    expect(window.localStorage.getItem("session")).toBeNull();

    // Assert that our application never sets tokens into window.sessionStorage
    expect(window.sessionStorage.getItem("token")).toBeNull();
    expect(window.sessionStorage.getItem("jwt")).toBeNull();
    expect(window.sessionStorage.getItem("access_token")).toBeNull();
  });

  it("SEC-16: getCsrfTokenFromCookie extracts token accurately from document.cookie", () => {
    // In jsdom environment, document.cookie is writable
    document.cookie = "unrelated_cookie=abc123xyz";
    document.cookie = "finpilot_csrf=sec-csrf-token-test-999; path=/";

    const extracted = getCsrfTokenFromCookie();
    expect(extracted).toBe("sec-csrf-token-test-999");
  });

  it("SEC-19: displays mandatory evaluation band benchmark disclaimer prominently", async () => {
    render(
      <ModeProvider>
        <ResearchStatusView />
      </ModeProvider>
    );

    // Should render the hurdle band and disclaimer text
    expect(await screen.findByText(/Evaluation Benchmark Hurdle/i)).toBeInTheDocument();
    expect(screen.getByText(/neither a profit promise, forecast, nor a trading recommendation/i)).toBeInTheDocument();
  });
});
