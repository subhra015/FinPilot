# FinPilot AI — Risk Engine Policy & Authorization Contract

Status: **Ratified (Layer 11)**  
Owning Package: `backend/src/finpilot/risk/`  
Governed by: `PROJECT_SPEC.md` §4, §5, §7, `DATA_AND_PERFORMANCE_POLICY.md` §2, §7, `SECURITY_CHECKLIST.md` `SEC-01`, `SEC-06`, `SEC-09`, `SEC-19`  

---

## 1. Executive Summary & Governance Principles

The FinPilot **Independent Risk Engine** acts as an authoritative, fail-closed firewall situated between trade proposal generators (ML models, baseline heuristics) and the execution simulator / broker layer.

### Core Governance Rules:
1. **Independent Authority (`SEC-19`)**: The machine learning model can propose a trade candidate, but **cannot authorize it** or bypass any risk rule. Model confidence ($P = 0.999$) is strictly non-authoritative.
2. **Mandatory Authorization Token**: The portfolio manager / execution simulator rejects any proposal lacking an authentic, cryptographically sealed `RiskAuthorization` token matching the exact proposal ID, model ID, and policy version.
3. **Deny-by-Default Architecture**: Every trade proposal is denied unless all 11 risk controls pass concurrently.
4. **Static Conservative Caps Only**: No Kelly criterion sizing, no dynamic leverage, and no speculative margin. Position sizes are bounded by fixed capital limits and integer shares.
5. **Entry vs. Exit Asymmetry**: Closing an open position reduces risk and releases capital. Exits are permitted past the 15:00 IST entry cutoff and with zero available cash. However, an exit is **never assumed to fill** if market data is missing, halted, or zero-volume.
6. **Strict RBAC & Tamper-Evident Audit Logging (`SEC-01`, `SEC-08`, `SEC-09`)**: Risk settings are protected from normal users. Only authorized administrators (`is_admin=True`) can mutate limits or toggle the kill switch. Every modification emits an immutable, cryptographically signed `RiskConfigAuditEvent` with SHA-256 hash chaining.

---

## 2. Cryptographic Authorization Contract (`RiskAuthorization`)

Before any order can enter the order book, the Risk Engine issues an immutable Pydantic V2 model:

```python
class RiskAuthorization(BaseModel):
    authorization_id: str
    proposal_id: str
    model_id: str
    policy_version: str            # Fixed to "TP-V1"
    symbol: str                    # NSE symbol (e.g., "RELIANCE")
    instrument_id: int             # Stable database identity
    side: OrderSide                # BUY or SELL
    authorized_quantity: int       # Strictly integer shares (Q >= 1)
    allocated_capital: Decimal     # Capital reserved (including fees & slippage)
    max_adverse_entry_price: Decimal  # Worst allowable fill price (10 bps buffer)
    stop_loss_limit: Decimal       # Maximum allowable stop-loss price
    target_price_limit: Decimal    # Expected profit target price
    authorized_at: datetime        # Normalized UTC timestamp
    expires_at: datetime           # Expiry timestamp (next bar open)
    auth_signature: str            # Deterministic SHA-256 seal
```

### Seal Computation & Tamper Detection:
The authorization seal is calculated across all core fields:
$$\text{Seal} = \text{SHA256}(\text{AuthID} \parallel \text{PropID} \parallel \text{ModelID} \parallel \text{Policy} \parallel \text{Symbol} \parallel \text{Qty} \parallel \text{AllocatedCap} \parallel \text{AdversePrice} \parallel \text{StopLimit} \parallel \dots)$$

Any tampering with quantity, limits, or timestamps invalidates `verify_signature()` and triggers an immediate `OrderRejectionReason.UNAUTHORIZED` rejection by the execution simulator.

---

## 3. The 11 Deny-by-Default Risk Controls

| # | Control | Threshold / Constraint | Machine-Readable Rejection Reason |
|---|---|---|---|
| **1** | **Emergency Kill Switch** | Globally halts all new entries immediately | `KILL_SWITCH_ACTIVE` |
| **2** | **Manual Trading Pause** | Admin-mandated operational pause | `MANUAL_TRADING_PAUSED` |
| **3** | **Governance Allowlist** | Symbol must be in approved universe (`RELIANCE`, `TCS`, `INFY`) | `UNSUPPORTED_INSTRUMENT` |
| **4** | **Version Governance** | Policy must match `TP-V1`; Model must match approved registry | `POLICY_VERSION_MISMATCH` / `MODEL_VERSION_MISMATCH` |
| **5** | **Market Data Freshness** | Candle bar must exist and staleness $\le 300\text{s}$ | `DATA_STALE_OR_MISSING` |
| **6** | **Market Bar Integrity** | Valid OHLC geometry: $H \ge \max(O,C,L)$, $L \le \min(O,C,H)$, $P > 0$, $V > 0$ | `MARKET_DATA_INVALID` |
| **7** | **Session & Cutoff Timing** | Within 09:15–15:30 IST; New entries prohibited after **15:00 IST** | `OUT_OF_SESSION` / `SESSION_ENTRY_CUTOFF` |
| **8** | **Position / Order Hygiene** | No duplicate active order IDs; no existing position in same symbol | `DUPLICATE_SIGNAL_OR_ORDER` / `UNRESOLVED_POSITION_STATE` |
| **9** | **Concurrent Positions Cap** | Maximum 1 open position at any time (baseline specification) | `MAX_CONCURRENT_POSITIONS_EXCEEDED` |
| **10** | **Circuit Breakers** | Daily realized loss $\ge ₹1,500$ or Current drawdown $\ge 10.0\%$ | `DAILY_LOSS_LIMIT_EXCEEDED` / `DRAWDOWN_SUSPENSION_TRIGGERED` |
| **11** | **Cash Affordability** | $\text{Required Capital} = (P_{\text{adverse}} \times Q) + \text{Fees} \le \text{Available Cash}$ | `INSUFFICIENT_AVAILABLE_CASH` |
| **12** | **Planned Stop Risk Cap** | Planned stop loss $\le 2.0\%$ of total equity ($₹600$ cap on $₹30,000$) | `EXCESSIVE_STOP_RISK` |
| **13** | **Exposure Limits** | Per-instrument exposure $\le 50.0\%$ ($₹15,000$); Total exposure $\le 100.0\%$ | `POSITION_EXPOSURE_CAP_EXCEEDED` / `TOTAL_EXPOSURE_CAP_EXCEEDED` |

---

## 4. Entry vs. Exit Asymmetry (Square-Off Governance)

The Risk Engine rigorously distinguishes between opening a new position and closing an existing one:

```
                            Trade Request Received
                                       │
                    ┌──────────────────┴──────────────────┐
                    ▼                                     ▼
             Entry Proposal                          Exit Intent
         (Opening New Exposure)                (Closing Existing Position)
                    │                                     │
     ┌──────────────┴──────────────┐               ┌──────┴──────┐
     ▼                             ▼               ▼             ▼
Cutoff >= 15:00 IST?         Available Cash?   Market Data   Zero Volume /
   -> REJECT                     -> REJECT      Missing?        Halted?
Max Positions = 1?           Stop Risk > 2%?   -> REJECT     -> REJECT
   -> REJECT                     -> REJECT         │             │
                    │                              └──────┬──────┘
                    ▼                                     ▼
        Issue RiskAuthorization                Issue RiskAuthorization
          for BUY Fill (TP-V1)                   for SELL Fill (Square-Off)
```

### Invariants:
1. **Forced EOD Exits**: Between 15:15 IST and 15:30 IST, entries are blocked by `SESSION_ENTRY_CUTOFF`, but exits are authorized to allow clean end-of-day square-off.
2. **Capital Release**: Closing an existing position releases margin. An exit intent is never blocked by low cash or concurrent position caps.
3. **No Phantom Fills**: An exit proposal is **denied** if the market candle is missing or volume is zero. The system never assumes an order can fill during a market halt.

---

## 5. Administrative RBAC & Cryptographic Audit Trail

### Access Control Model (`SEC-01`, `SEC-09`):
- All configuration changes are handled by `RiskConfigService`.
- Every mutating method (`update_config`, `set_kill_switch`, `set_manual_pause`) inspects `UserScope.is_admin`.
- Non-admin users, client frontends, or automated strategies attempting mutation raise `PermissionDeniedError`.

### Immutable Audit Events (`SEC-08`):
Every administrative change logs a `RiskConfigAuditEvent`:
```python
class RiskConfigAuditEvent(BaseModel):
    audit_id: str
    timestamp: datetime
    user_id: str
    user_role: str
    action: str
    previous_config_hash: str
    new_config_hash: str
    changed_fields: dict[str, Any]
    audit_signature: str
```

The SHA-256 hash chain links `previous_config_hash` to `new_config_hash`, ensuring an unforgeable, tamper-evident record of all risk parameter adjustments.
