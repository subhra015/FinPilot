# FinPilot AI — Exception Register

Status: **Layer 0 initial (empty)**. Every approved security exception must be
recorded here (SEC-26). No exception exists as of Layer 0.

Related: `SECURITY.md`, `SECURITY_CHECKLIST.md`.

---

## Rule

An exception to a `SEC-*` control is allowed only if:

- it is recorded here with owner, justification, scope and **expiry date**;
- it does not violate a V1 hard boundary (no live orders, no payments,
  no unlicensed data exposure);
- it is reviewed at expiry and in the Layer 17 full review.

Un-recorded exceptions are policy violations.

## Register

| ID | SEC control | Scope | Justification | Owner | Approved (date/by) | Expiry | Status |
|---|---|---|---|---|---|---|---|
| _(none)_ | | | | | | | |

Status values: `ACTIVE` · `EXPIRED` · `CLOSED` · `REVOKED`.
