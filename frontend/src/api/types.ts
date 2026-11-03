/**
 * TypeScript domain and API interfaces matching backend models (Layer 12 & Layer 13).
 *
 * Governed by:
 * - PROJECT_SPEC.md (₹30,000 scenario, evaluation band ₹300-₹1,500)
 * - docs/api-auth-specification.md
 * - SECURITY_CHECKLIST.md SEC-06, SEC-09, SEC-15, SEC-16, SEC-19
 */

export type UserRole = "USER" | "ADMIN" | "SERVICE";

export type DataMode = "HISTORICAL_REPLAY" | "FORWARD_PAPER" | "SYNTHETIC_DEMO";

export type DecisionState =
  | "ACCEPTED"
  | "NO_TRADE"
  | "INSUFFICIENT_DATA"
  | "RISK_REJECTED"
  | "ENTRY_UNFILLED"
  | "EXECUTION_UNRESOLVED";

export type LedgerEventType =
  | "ACCEPTED"
  | "DECISION"
  | "NO_TRADE"
  | "INSUFFICIENT_DATA"
  | "RISK_APPROVED"
  | "RISK_REJECTED"
  | "ORDER_CREATED"
  | "FILL"
  | "PARTIAL_FILL"
  | "ENTRY_UNFILLED"
  | "EXECUTION_UNRESOLVED"
  | "EXIT"
  | "EXPIRY"
  | "FEE_APPLIED"
  | "BALANCE_UPDATE"
  | "CORRECTION"
  | "OPPORTUNITY_OMITTED"
  | "PORTFOLIO_OUTCOME"
  | "HYPOTHETICAL_OUTCOME";

export interface UserProfile {
  user_id: string;
  email: string;
  role: UserRole;
  mfa_enabled: boolean;
  created_at?: string;
}

export interface AuthResponse {
  user?: UserProfile;
  mfa_required: boolean;
  user_id?: string;
  csrf_token?: string | null;
}

export interface FeeBreakdown {
  brokerage: number;
  stt: number;
  exchange_turnover: number;
  sebi_turnover: number;
  stamp_duty: number;
  gst: number;
  total_costs: number;
}

export interface TradeProposal {
  proposal_id: string;
  symbol: string;
  signal_timestamp: string;
  execution_timestamp: string;
  side: "BUY" | "SELL";
  entry_price: number;
  stop_loss_price: number;
  profit_target_price: number;
  quantity: number;
  fees: FeeBreakdown;
  decision_state: DecisionState;
  predicted_probability: number;
  calibrated_probability: number;
  calibration_bin_frequency: number;
  estimated_expectancy: number;
  policy_version: string;
  feature_set_version: string;
}

export interface RiskRuleStatus {
  rule_id: number;
  name: string;
  limit_description: string;
  is_passing: boolean;
  current_value: string;
}

export interface RiskConfigState {
  max_daily_loss: number;
  max_drawdown_pct: number;
  max_stop_risk_pct: number;
  max_concurrent_positions: number;
  kill_switch_active: boolean;
  manual_trading_paused: boolean;
  session_entry_cutoff: string;
  forced_square_off_cutoff: string;
  rules: RiskRuleStatus[];
}

export interface PortfolioPosition {
  symbol: string;
  quantity: number;
  entry_price: number;
  current_price: number;
  stop_loss: number;
  target: number;
  unrealized_pnl: number;
  entry_timestamp: string;
}

export interface PortfolioSummary {
  account_id: string;
  portfolio_id: string;
  initial_scenario_capital: number;
  current_cash: number;
  reserved_cash: number;
  realized_pnl: number;
  unrealized_pnl: number;
  total_equity: number;
  positions: PortfolioPosition[];
}

export interface LedgerEventRecord {
  sequence_number: number;
  event_id: string;
  event_type: LedgerEventType;
  symbol?: string;
  timestamp: string;
  prev_hash: string;
  integrity_hash: string;
  is_hypothetical: boolean;
  prior_event_id?: string | null;
  correction_reason?: string | null;
  payload: Record<string, unknown>;
}

export interface ReplayVerificationResponse {
  is_valid: boolean;
  events_replayed: number;
  corrections_applied: number;
  chain_verified: boolean;
  reconstructed_cash: string;
  reconstructed_positions: Record<string, number>;
  reconstructed_realized_pnl: string;
  hypothetical_realized_pnl: string;
  tamper_detected: boolean;
  tamper_details: string[];
}

export interface DataAuditCheck {
  check_name: string;
  description: string;
  status: "PASS" | "WARN" | "FAIL";
  details: string;
}

export interface DataHealthSummary {
  dataset_name: string;
  publisher: string;
  license_status: "VERIFIED" | "BLOCKED" | "RESTRICTED";
  allowed_purposes: string[];
  total_bars: number;
  quarantine_count: number;
  checks: DataAuditCheck[];
}

export interface EvaluationMetrics {
  strategy_id: string;
  strategy_name: string;
  gross_pnl: number;
  total_fees: number;
  net_pnl: number;
  win_rate_pct: number;
  profit_factor: number;
  max_drawdown_pct: number;
  expectancy_per_trade: number;
  brier_score?: number;
  brier_reliability?: number;
  brier_resolution?: number;
  brier_uncertainty?: number;
}
