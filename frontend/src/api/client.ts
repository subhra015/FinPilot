/**
 * Secure HTTP API Client for FinPilot Frontend (SEC-02, SEC-06, SEC-15, SEC-16).
 *
 * Governed by:
 * - SECURITY_CHECKLIST.md SEC-02: No secrets in client bundle or localStorage.
 * - SECURITY_CHECKLIST.md SEC-15: Opaque server-side sessions via HttpOnly cookies.
 * - SECURITY_CHECKLIST.md SEC-16: CSRF token header for mutating requests.
 * - SECURITY_CHECKLIST.md SEC-06: Server-side validation authoritative.
 */

import { frontendConfig } from "../config/env";

export class ApiError extends Error {
  public status: number;
  public code?: string;
  public details?: unknown[];

  constructor(message: string, status: number, code?: string, details?: unknown[]) {
    super(sanitizeMessage(message));
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

/**
 * Sanitize error messages to eliminate accidental leakage of internal paths or credentials.
 */
function sanitizeMessage(msg: string): string {
  if (!msg || typeof msg !== "string") {
    return "An unexpected request error occurred.";
  }
  return msg
    .replace(/[A-Za-z]:\\[^:\s\n"']+/g, "[PATH_REDACTED]")
    .replace(/\/(?:[a-zA-Z0-9._-]+\/)+[a-zA-Z0-9._-]+/g, "[PATH_REDACTED]")
    .replace(/(Bearer\s+[A-Za-z0-9\-._~+/]+=*)/gi, "[REDACTED_TOKEN]");
}

/**
 * Extract anti-CSRF token from client-readable cookie.
 */
export function getCsrfTokenFromCookie(): string | null {
  if (typeof document === "undefined") {
    return null;
  }
  const match = document.cookie.match(/(?:^|;\s*)finpilot_csrf=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

type UnauthorizedHandler = () => void;
let onUnauthorizedCallback: UnauthorizedHandler | null = null;

export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  onUnauthorizedCallback = handler;
}

interface RequestOptions extends RequestInit {
  params?: Record<string, string | number | boolean | undefined>;
}

export async function apiRequest<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  const { params, headers = {}, ...rest } = options;
  const baseUrl = frontendConfig.apiBaseUrl.replace(/\/$/, "");

  let url = `${baseUrl}${endpoint.startsWith("/") ? "" : "/"}${endpoint}`;
  if (params) {
    const query = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined) {
        query.set(k, String(v));
      }
    }
    const qs = query.toString();
    if (qs) {
      url += `?${qs}`;
    }
  }

  const reqHeaders: Record<string, string> = {
    Accept: "application/json",
    ...((headers as Record<string, string>) || {}),
  };

  const method = (rest.method || "GET").toUpperCase();
  const isMutating = ["POST", "PUT", "PATCH", "DELETE"].includes(method);

  if (isMutating) {
    if (!reqHeaders["Content-Type"] && !(rest.body instanceof FormData)) {
      reqHeaders["Content-Type"] = "application/json";
    }
    const csrfToken = getCsrfTokenFromCookie();
    if (csrfToken) {
      reqHeaders["X-CSRF-Token"] = csrfToken;
    }
  }

  const response = await fetch(url, {
    credentials: "include", // Transmit HttpOnly session cookie automatically
    headers: reqHeaders,
    method,
    ...rest,
  });

  if (response.status === 401) {
    if (onUnauthorizedCallback) {
      onUnauthorizedCallback();
    }
    const errBody = await response.json().catch(() => ({}));
    throw new ApiError(
      errBody.error || "Authentication required or session expired.",
      401,
      errBody.code
    );
  }

  if (!response.ok) {
    const errBody = await response.json().catch(() => ({}));
    throw new ApiError(
      errBody.error || `Request failed with status ${response.status}`,
      response.status,
      errBody.code,
      errBody.details
    );
  }

  if (response.status === 204) {
    return {} as T;
  }

  return response.json() as Promise<T>;
}

export const api = {
  get: <T>(endpoint: string, params?: Record<string, string | number | boolean | undefined>) =>
    apiRequest<T>(endpoint, { method: "GET", params }),
  post: <T>(endpoint: string, body?: unknown) =>
    apiRequest<T>(endpoint, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  put: <T>(endpoint: string, body?: unknown) =>
    apiRequest<T>(endpoint, { method: "PUT", body: body ? JSON.stringify(body) : undefined }),
  patch: <T>(endpoint: string, body?: unknown) =>
    apiRequest<T>(endpoint, { method: "PATCH", body: body ? JSON.stringify(body) : undefined }),
  delete: <T>(endpoint: string) => apiRequest<T>(endpoint, { method: "DELETE" }),
};
