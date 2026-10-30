import { frontendConfig } from "./config/env";

export function App() {
  return (
    <main>
      <h1>FinPilot AI</h1>
      <p>India-first NSE cash-equity research and paper-trading platform.</p>
      <p>Foundation build — no trading features are implemented yet.</p>
      <p data-testid="api-base">API: {frontendConfig.apiBaseUrl}</p>
    </main>
  );
}
