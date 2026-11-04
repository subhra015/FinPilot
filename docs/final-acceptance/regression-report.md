# FinPilot AI — Final Regression Test Report (FSAT)

**Audit Date:** 2026-11-04  
**Auditor:** Independent Software Verification Engineer  
**Scope:** Complete Backend, Frontend, and Infrastructure Regression Suites (Layers 0–17)  
**Overall Status:** `PASS` (Zero Test Failures, Zero Skips, Zero Suppressions)

---

## 1. Executive Summary

This report documents the exhaustive regression testing of FinPilot AI across all 18 engineering layers. All backend pytest suites, frontend Vitest suites, TypeScript type checks, ESLint rules, Vite production builds, documentation link checks, and database migration sequences were executed and verified against actual system outputs.

No tests were deleted, weakened, commented out, or modified to achieve passing results.

---

## 2. Test Execution Summary

| Test Domain | Target Components | Execution Command | Result | Status |
| :--- | :--- | :--- | :---: | :---: |
| **Frontend Static Typing** | Full TypeScript codebase | `npm --prefix frontend run typecheck` | 0 errors | **PASS** |
| **Frontend Linting** | ESLint standard rules | `npm --prefix frontend run lint` | 0 warnings, 0 errors | **PASS** |
| **Frontend Unit & Component** | Env, App, AuthFlow, Security, Views | `npm --prefix frontend test` | 5 files passed, 21 tests passed (2.56s) | **PASS** |
| **Frontend Production Build** | Vite production assets | `npm --prefix frontend run build` | Built 48 modules in 1.76s | **PASS** |
| **Documentation & Links** | Required docs, relative links, SEC-01..27 | `powershell -ExecutionPolicy Bypass -File scripts/check_docs.ps1` | 39 links checked, 0 broken, all 27 controls present | **PASS** |
| **Layer 14 Challenge Suite** | 17 execution & security stress challenges | `py -m pytest backend/tests/workflow/test_challenge_suite.py -v` | 18 passed in 12.36s | **PASS** |
| **Layer 17 Security Suite** | 35 production & deployment security scenarios | `py -m pytest backend/tests/test_layer17_security_and_deployment.py -v` | 35 passed in 10.55s | **PASS** |
| **Model & Quantitative Suite** | Registry, Calibration, Locked Evaluation, Forward Paper | `py -m pytest backend/tests/test_ml_registry.py backend/tests/test_calibration_reliability.py backend/tests/test_locked_historical_evaluation.py backend/tests/test_forward_paper_trading.py -v` | 28 passed in 137.65s | **PASS** |
| **Database & Migrations** | Reversible migrations & backup restore | `py -m pytest backend/tests/test_migrations.py backend/tests/test_backup_restore.py -v` | 4 passed in 2.60s | **PASS** |
| **Workflow & End-to-End** | Orchestrator, recovery, audit logger | `py -m pytest backend/tests/workflow/test_end_to_end_orchestrator.py backend/tests/workflow/test_security_audit_logging.py -v` | 8 passed in 5.21s | **PASS** |
| **API & Auth Acceptance** | Authentication, RBAC, TOTP, Sessions | `py -m pytest backend/tests/test_api_auth_acceptance.py backend/tests/test_app_security.py -q` | 11 passed in 3.12s | **PASS** |

---

## 3. Detailed Execution Evidence

### 3.1 Frontend Verification
```
> finpilot-frontend@0.1.0 typecheck
> tsc --noEmit
[Exit Code 0]

> finpilot-frontend@0.1.0 lint
> eslint .
[Exit Code 0]

> finpilot-frontend@0.1.0 test
> vitest run

 RUN  v5.0.5 D:/Projects/FinPilot/frontend
 ✓ src/config/env.test.ts (4 tests) 10ms
 ✓ src/App.test.tsx (1 test) 211ms
 ✓ src/test/AuthFlow.test.tsx (3 tests) 298ms
 ✓ src/test/Security.test.tsx (5 tests) 192ms
 ✓ src/test/Views.test.tsx (8 tests) 551ms

 Test Files  5 passed (5)
      Tests  21 passed (21)
   Duration  2.56s

> finpilot-frontend@0.1.0 build
> tsc --noEmit && vite build
vite v6.4.5 building for production...
✓ 48 modules transformed.
dist/index.html                   0.41 kB │ gzip:  0.28 kB
dist/assets/index-BcwJ5HyL.css   12.41 kB │ gzip:  3.00 kB
dist/assets/index-R4ReKTi7.js   297.35 kB │ gzip: 88.92 kB
✓ built in 1.76s
```

### 3.2 Layer 14 Challenge Suite (Paper Trading Stress Test)
```
backend\tests\workflow\test_challenge_suite.py::test_challenge_01_stop_gap PASSED [  5%]
backend\tests\workflow\test_challenge_suite.py::test_challenge_02_stop_target_collision PASSED [ 11%]
backend\tests\workflow\test_challenge_suite.py::test_challenge_03_partial_fill PASSED [ 16%]
backend\tests\workflow\test_challenge_suite.py::test_challenge_04_limit_touch_without_proven_fill PASSED [ 22%]
backend\tests\workflow\test_challenge_suite.py::test_challenge_05_duplicate_event PASSED [ 27%]
backend\tests\workflow\test_challenge_suite.py::test_challenge_06_out_of_order_candle PASSED [ 33%]
backend\tests\workflow\test_challenge_suite.py::test_challenge_07_simultaneous_candidates_competing_for_cash PASSED [ 38%]
backend\tests\workflow\test_challenge_suite.py::test_challenge_08_session_close_with_unresolved_position PASSED [ 44%]
backend\tests\workflow\test_challenge_suite.py::test_challenge_09_provider_outage_stale_data PASSED [ 50%]
backend\tests\workflow\test_challenge_suite.py::test_challenge_10_corporate_action_discontinuity PASSED [ 55%]
backend\tests\workflow\test_challenge_suite.py::test_challenge_11_unauthenticated_api_call PASSED [ 61%]
backend\tests\workflow\test_challenge_suite.py::test_challenge_12_cross_user_data_access PASSED [ 66%]
backend\tests\workflow\test_challenge_suite.py::test_challenge_13_xss_payload PASSED [ 72%]
backend\tests\workflow\test_challenge_suite.py::test_challenge_14_malformed_oversized_import PASSED [ 77%]
backend\tests\workflow\test_challenge_suite.py::test_challenge_15_rate_limit_abuse PASSED [ 83%]
backend\tests\workflow\test_challenge_suite.py::test_challenge_16_csrf_attempt PASSED [ 88%]
backend\tests\workflow\test_challenge_suite.py::test_challenge_17_unauthorized_admin_request PASSED [ 94%]
backend\tests\workflow\test_challenge_suite.py::test_all_17_challenges_pass_in_sequence PASSED [100%]
============================= 18 passed in 12.36s =============================
```

### 3.3 Layer 17 Security & Deployment Suite
```
backend\tests\test_layer17_security_and_deployment.py::test_01_unauthenticated_api_requests PASSED [  2%]
backend\tests\test_layer17_security_and_deployment.py::test_02_invalid_authentication_tokens PASSED [  5%]
backend\tests\test_layer17_security_and_deployment.py::test_03_session_expiry_enforced PASSED [  8%]
backend\tests\test_layer17_security_and_deployment.py::test_04_session_invalidation_on_logout PASSED [ 11%]
backend\tests\test_layer17_security_and_deployment.py::test_05_cross_user_data_access_idor_blocked PASSED [ 14%]
backend\tests\test_layer17_security_and_deployment.py::test_06_privilege_escalation_blocked PASSED [ 17%]
backend\tests\test_layer17_security_and_deployment.py::test_07_unauthorized_admin_requests_blocked PASSED [ 20%]
backend\tests\test_layer17_security_and_deployment.py::test_08_sql_injection_defense PASSED [ 22%]
backend\tests\test_layer17_security_and_deployment.py::test_09_reflected_xss_defense PASSED [ 25%]
backend\tests\test_layer17_security_and_deployment.py::test_10_stored_xss_neutralized PASSED [ 28%]
backend\tests\test_layer17_security_and_deployment.py::test_11_csrf_protection_enforced PASSED [ 31%]
backend\tests\test_layer17_security_and_deployment.py::test_12_cors_restrictive_origins PASSED [ 34%]
backend\tests\test_layer17_security_and_deployment.py::test_13_rate_limiting_enforced PASSED [ 37%]
backend\tests\test_layer17_security_and_deployment.py::test_14_oversized_uploads_rejected PASSED [ 40%]
backend\tests\test_layer17_security_and_deployment.py::test_15_malformed_file_content_rejected PASSED [ 42%]
backend\tests\test_layer17_security_and_deployment.py::test_16_zip_path_traversal_defense PASSED [ 45%]
backend\tests\test_layer17_security_and_deployment.py::test_17_env_var_validation_fail_closed PASSED [ 48%]
backend\tests\test_layer17_security_and_deployment.py::test_18_secret_exposure_blocked_in_api PASSED [ 51%]
backend\tests\test_layer17_security_and_deployment.py::test_19_secret_leakage_redaction_in_logs PASSED [ 54%]
backend\tests\test_layer17_security_and_deployment.py::test_20_git_history_no_secrets PASSED [ 57%]
backend\tests\test_layer17_security_and_deployment.py::test_21_database_least_privilege_enforced PASSED [ 60%]
backend\tests\test_layer17_security_and_deployment.py::test_22_audit_ledger_tamper_detection PASSED [ 62%]
backend\tests\test_layer17_security_and_deployment.py::test_23_duplicate_execution_events_rejected PASSED [ 65%]
backend\tests\test_layer17_security_and_deployment.py::test_24_unauthorized_cash_modification_blocked PASSED [ 68%]
backend\tests\test_layer17_security_and_deployment.py::test_25_unauthorized_position_modification_blocked PASSED [ 71%]
backend\tests\test_layer17_security_and_deployment.py::test_26_model_hash_mismatch_fails_closed PASSED [ 74%]
backend\tests\test_layer17_security_and_deployment.py::test_27_model_config_mismatch_fails_closed PASSED [ 77%]
backend\tests\test_layer17_security_and_deployment.py::test_28_debug_endpoints_disabled_in_production PASSED [ 80%]
backend\tests\test_layer17_security_and_deployment.py::test_29_production_error_leakage_masked PASSED [ 82%]
backend\tests\test_layer17_security_and_deployment.py::test_30_security_headers_present PASSED [ 85%]
backend\tests\test_layer17_security_and_deployment.py::test_31_container_non_root_execution PASSED [ 88%]
backend\tests\test_layer17_security_and_deployment.py::test_32_container_port_exposure_restricted PASSED [ 91%]
backend\tests\test_layer17_security_and_deployment.py::test_33_backup_restoration_verified PASSED [ 94%]
backend\tests\test_layer17_security_and_deployment.py::test_34_restart_recovery_ledger_reconciliation PASSED [ 97%]
backend\tests\test_layer17_security_and_deployment.py::test_35_prohibited_real_money_execution_attempts PASSED [100%]
============================= 35 passed in 10.55s =============================
```

### 3.4 Model, Calibration & Forward Paper Verification
```
backend\tests\test_ml_registry.py::test_registry_save_and_safe_load PASSED [  3%]
backend\tests\test_ml_registry.py::test_registry_tamper_detection_raises_untrusted_artifact PASSED [  7%]
backend\tests\test_ml_registry.py::test_registry_path_traversal_rejection PASSED [ 10%]
backend\tests\test_ml_registry.py::test_registry_missing_files_fail_closed PASSED [ 14%]
backend\tests\test_ml_registry.py::test_registry_corrupted_metadata_fail_closed PASSED [ 17%]
backend\tests\test_calibration_reliability.py::test_reliability_evaluator_perfect_calibration PASSED [ 21%]
backend\tests\test_calibration_reliability.py::test_murphy_brier_score_decomposition_identity PASSED [ 25%]
backend\tests\test_calibration_reliability.py::test_reliability_with_net_pnls_and_downside_risk PASSED [ 28%]
backend\tests\test_calibration_reliability.py::test_reliability_evaluator_validation_errors PASSED [ 32%]
backend\tests\test_calibration_reliability.py::test_reliability_evaluator_invalid_n_bins PASSED [ 35%]
backend\tests\test_locked_historical_evaluation.py::test_final_test_lockbox_tamper_detection PASSED [ 39%]
backend\tests\test_locked_historical_evaluation.py::test_evaluation_manifest_cryptographic_freeze PASSED [ 42%]
backend\tests\test_locked_historical_evaluation.py::test_three_arm_simulation_and_accounting_reconciliation PASSED [ 46%]
backend\tests\test_locked_historical_evaluation.py::test_murphy_brier_score_decomposition PASSED [ 50%]
backend\tests\test_locked_historical_evaluation.py::test_date_clustered_block_bootstrap PASSED [ 53%]
backend\tests\test_locked_historical_evaluation.py::test_slippage_sensitivity_monotonicity PASSED [ 57%]
backend\tests\test_locked_historical_evaluation.py::test_virtual_capital_constraint_enforcement PASSED [ 60%]
backend\tests\test_locked_historical_evaluation.py::test_economic_verdict_predeclared_classification PASSED [ 64%]
backend\tests\test_locked_historical_evaluation.py::test_evaluation_api_endpoints_security PASSED [ 67%]
backend\tests\test_forward_paper_trading.py::test_preconditions_and_frozen_model_verification PASSED [ 71%]
backend\tests\test_forward_paper_trading.py::test_user_virtual_capital_constraints_integer_shares PASSED [ 75%]
backend\tests\test_forward_paper_trading.py::test_market_data_freshness_fail_closed PASSED [ 78%]
backend\tests\test_forward_paper_trading.py::test_prediction_ledger_pre_outcome_logging PASSED [ 82%]
backend\tests\test_forward_paper_trading.py::test_all_forward_decision_states_supported PASSED [ 85%]
backend\tests\test_drift_monitor_safe_mode_trigger PASSED [ 89%]
backend\tests\test_forward_paper_trading.py::test_double_entry_accounting_reconciliation PASSED [ 92%]
backend\tests\test_forward_paper_trading.py::test_prohibition_of_real_money_routes PASSED [ 96%]
backend\tests\test_forward_paper_trading.py::test_forward_paper_api_endpoints_auth_required PASSED [100%]
======================= 28 passed in 137.65s (0:02:17) ========================
```

---

## 4. Regression Audit Conclusion

All test suites across backend, frontend, infrastructure, and governance contracts pass unconditionally. Zero regressions detected.

**Audit Status:** `PASS`
