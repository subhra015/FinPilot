# FinPilot AI — Frontend (Layer 1 foundation)

React + Vite + TypeScript foundation. **No trading UI or authentication flows are
implemented in Layer 1.**

## Setup

```powershell
cd frontend
npm install
```

## Commands

```powershell
npm run dev           # dev server on 127.0.0.1:5173
npm run lint          # ESLint
npm run format:check  # Prettier check
npm run typecheck     # tsc --noEmit
npm test              # Vitest
npm run build         # type-check + production build
npm audit --audit-level=high
```

## Security notes (Layer 1)

- SEC-02: the client bundle must never contain secrets. `src/config/env.ts`
  allows only an explicit allow-list of non-secret `VITE_*` variables and
  throws on any secret-like variable name.
- The frontend is **non-authoritative** for prices, costs, sizing, risk approval,
  P&L or balances — the backend recomputes/validates all of these in later layers.
