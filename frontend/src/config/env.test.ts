import { describe, expect, it } from "vitest";

import { loadFrontendConfig } from "./env";

describe("loadFrontendConfig", () => {
  it("accepts allow-listed non-secret VITE_ variables", () => {
    expect(loadFrontendConfig({ VITE_API_BASE_URL: "http://127.0.0.1:8000" })).toEqual({
      apiBaseUrl: "http://127.0.0.1:8000",
    });
  });

  it("rejects secret-like VITE_ variable names", () => {
    expect(() => loadFrontendConfig({ VITE_API_KEY: "abc" })).toThrow(/secret-like/i);
    expect(() => loadFrontendConfig({ VITE_AUTH_TOKEN: "abc" })).toThrow(/secret-like/i);
    expect(() => loadFrontendConfig({ VITE_CLIENT_SECRET: "abc" })).toThrow(/secret-like/i);
  });

  it("rejects VITE_ variables outside the allow-list", () => {
    expect(() => loadFrontendConfig({ VITE_SOMETHING_ELSE: "x" })).toThrow(/allow-list/i);
  });

  it("ignores non-VITE variables and falls back to localhost", () => {
    expect(loadFrontendConfig({ MODE: "test", DEV: true })).toEqual({
      apiBaseUrl: "http://127.0.0.1:8000",
    });
  });
});
