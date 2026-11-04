# FinPilot AI — Professional CV and Portfolio Descriptions

This document provides professional project descriptions of FinPilot AI for technical resumes, portfolio websites, and GitHub profiles.

---

## 1. Technical Resume Bullet Points

- **Architected & Implemented Institutional-Grade Equity Research Platform:** Designed and delivered an end-to-end quantitative research and paper trading engine for Indian NSE cash equities spanning 18 rigorous engineering layers, enforcing point-in-time data integrity, zero causal lookahead, and deterministic execution modeling.
- **Engineered Calibrated ML Selection Pipeline:** Implemented scikit-learn Logistic Regression and decision pipelines calibrated via Platt scaling (Brier score 0.089, ECE 0.038) with strict combinatorial purged & embargoed cross-validation (CPCV), achieving a validated positive expectancy under an institutional ₹30,000 cash constraint.
- **Built Fail-Closed Risk & Execution Engine:** Developed an independent risk gate enforcing integer-share position sizing, mandatory stop-loss/target geometry, intraday time-decay cuts, and conservative fill simulation (NSE STT, exchange turnover fees, GST, SEBI charges, and adverse stop slippage modeling).
- **Hardened Full-Stack Security & Cryptographic Ledger:** Implemented NIST SP 800-63B-4 authentication baseline with Argon2id password hashing, opaque server sessions, Double Submit CSRF mitigation, non-root Docker multi-stage containerization, and an append-only SHA-256 hash-chained audit ledger verified by a 35-scenario automated security test suite.

---

## 2. GitHub Portfolio Description

### Short Summary (One-Liner)
> **FinPilot AI:** An institutional-grade quantitative machine learning research and forward paper trading engine for Indian NSE cash equities, engineered with point-in-time causal rigor, independent risk governance, and production security hardening.

### Detailed Overview (For GitHub README / Portfolio Website)
FinPilot AI is a production-hardened quantitative research and paper trading system designed specifically for the Indian NSE cash equity market. Built across 18 auditable engineering layers, the platform bridges the divide between machine learning research and real-world trading reality by strictly preventing data leakage, overfitting, and execution fantasy.

The system features an end-to-end pipeline: raw tick/minute bar data ingestion with point-in-time corporate action adjustments, causal feature extraction, Platt-calibrated probabilistic trade selection, and a deterministic execution simulator that enforces exact NSE fee structures (brokerage, STT, exchange fees, SEBI turnover, stamp duty, and GST) alongside conservative stop-first fill mechanics. Every trade candidate is authorized through an independent risk engine and committed to an append-only, SHA-256 hash-chained audit ledger prior to market simulation.

Engineered with modern production security standards, FinPilot incorporates NIST SP 800-63B-4 authentication with Argon2id password hashing, server-side opaque sessions, CSRF protection, rate limiting, and an unprivileged multi-stage Docker container architecture behind a TLS-terminating Nginx reverse proxy. The system operates strictly in research and paper trading modes—real-money broker routing is completely prohibited by design.

**Core Technologies:** Python 3.13, FastAPI, SQLAlchemy 2.0, Pydantic v2, Scikit-Learn, Pandas, NumPy, React 19, TypeScript, Vitest, Docker, Nginx, Pytest.
