/**
 * Frontend configuration loader (SEC-02).
 *
 * The client bundle may only receive NON-SECRET values. This module enforces an
 * allow-list of `VITE_*` variables and refuses any secret-like variable name so
 * that a key accidentally placed in a `VITE_*` variable fails the build/tests
 * rather than leaking into a browser bundle.
 */

export interface FrontendConfig {
  apiBaseUrl: string;
}

export const ALLOWED_VITE_KEYS = ["VITE_API_BASE_URL"] as const;

const SECRET_LIKE = /(SECRET|TOKEN|PASSWORD|PASSWD|API_KEY|APIKEY|PRIVATE|CREDENTIAL|AUTH)/i;

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";

export function loadFrontendConfig(env: Record<string, unknown>): FrontendConfig {
  for (const key of Object.keys(env)) {
    if (!key.startsWith("VITE_")) {
      continue;
    }
    if (SECRET_LIKE.test(key)) {
      throw new Error(`Refusing secret-like Vite variable in client bundle: ${key}`);
    }
    if (!(ALLOWED_VITE_KEYS as readonly string[]).includes(key)) {
      throw new Error(`Unknown VITE_ variable not in allow-list: ${key}`);
    }
  }

  const raw = env.VITE_API_BASE_URL;
  const apiBaseUrl = typeof raw === "string" && raw.length > 0 ? raw : DEFAULT_API_BASE_URL;
  return { apiBaseUrl };
}

export const frontendConfig = loadFrontendConfig(import.meta.env as Record<string, unknown>);
