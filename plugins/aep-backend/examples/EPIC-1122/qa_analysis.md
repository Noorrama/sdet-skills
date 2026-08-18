# QA Analysis — EPIC-1122: Save Payment-Method API

> **Generation mode:** Pass 1 (pre-build)  
> **Plan version:** v1  
> **Date:** 2026-08-06  
> **SDET + PM review gate — approve before proceeding to automation-plan-generator**

---

## Summary

| Metric | Value |
|---|---|
| Total scenarios | 22 |
| RFC coverage | **100%** (9 / 9 validation steps) |
| RFC gaps | **0** |
| Legacy regression | 5 scenarios (all need gap-remediation — see below) |
| Net-new scenarios | 17 |
| Key uncovered gaps addressed | 3 (REQ-005, NFR-001, NFR-003) |

---

## Scenarios by Test Layer

| Layer | Count | Scenario IDs |
|---|---|---|
| component | 10 | 002, 003, 004, 005, 006, 007, 013, 014, 015, 021 |
| integration | 12 | 001, 008, 009, 010, 011, 012, 016, 017, 018, 019, 020, 022 |
| e2e | 0 | — |

---

## Scenarios by Priority

| Priority | Count | Rationale |
|---|---|---|
| P0 | 16 | Business-critical flows, all security/PCI requirements, availability (vault) |
| P1 | 6 | Boundary tests, performance test, repo-layer assertions |
| P2 | 0 | — |

---

## RFC Coverage (RFC-78)

| RFC Step | Description | Scenarios |
|---|---|---|
| Step 1 | Feature flag check | SC-EPIC1122-010 (flag_off) + SC-EPIC1122-001 (flag_on implicit) |
| Step 2 | Required field validation | SC-EPIC1122-002, -003, -004, -005 |
| Step 3 | cardNumber format + Luhn | SC-EPIC1122-013 (boundary min), -014 (boundary max), -021 (Luhn fail) |
| Step 4 | Expiry validation | SC-EPIC1122-006, -007 (past), -015 (boundary current month) |
| Step 5 | Fingerprint computation | Covered implicitly in SC-EPIC1122-001, -008 |
| Step 6 | DB dedup check | SC-EPIC1122-008, -011 (race condition) |
| Step 7 | Vault call + failure | SC-EPIC1122-009 (vault 503), -016 (vault timeout) |
| Step 8 | DB persist | SC-EPIC1122-001 (step-3 verifies row), -018 (repo-level) |
| Step 9 | Return 200 + token | SC-EPIC1122-001 |

**RFC coverage: 9/9 steps covered — 100%**  
**RFC gaps: NONE**

---

## Legacy Regression Status

All 6 existing tests are marked `is_legacy_regression: true`. None are disqualifying for scenario generation (all are either unit tests or manual-only). New automated scenarios are generated for all of them.

| Scenario | Coverage source | Gap |
|---|---|---|
| SC-EPIC1122-001 (happy path) | GBT-PAY-001 | Unit test only — no vault integration |
| SC-EPIC1122-002 (missing cardNumber) | BS-PAY-012 | Manual test only — needs automation |
| SC-EPIC1122-006 (expired past year) | GBT-PAY-002 | Service unit test — HTTP envelope not verified |
| SC-EPIC1122-007 (expired same year past month) | GBT-PAY-003 | Service unit test — HTTP envelope not verified |
| SC-EPIC1122-008 (duplicate card) | BS-PAY-011 + GBT-PAY-004 | BS-PAY-011 is manual; GBT-PAY-004 tests DB layer only |

---

## Net-New Scenarios Addressing Key Gaps

| Scenario | Requirement | Why not previously covered |
|---|---|---|
| SC-EPIC1122-012 | REQ-005 — No raw card data in logs | No test existed at any level |
| SC-EPIC1122-022 | NFR-001 — p95 latency ≤ 300ms | No performance test existed |
| SC-EPIC1122-009 + -016 | NFR-003 — Vault unavailability → 503, no DB write | Not tested at any level |
| SC-EPIC1122-010 | Feature flag OFF → 404 | Not tested |
| SC-EPIC1122-011 | Race condition concurrent duplicate | Not tested |
| SC-EPIC1122-003, -004, -005 | Missing expiryMonth / expiryYear / cvv | Only cardNumber tested manually |
| SC-EPIC1122-013, -014, -015, -021 | Boundary card numbers and expiry edge | Not tested |

---

## PRD Risk Areas Coverage

| PRD Risk Area | P0 Scenarios |
|---|---|
| Concurrent duplicate bypass DB check (High) | SC-EPIC1122-011 |
| Vault timeout → partial state (High) | SC-EPIC1122-009, -016 |
| Raw card data logged accidentally (High) | SC-EPIC1122-012 |
| DB migration failure on deploy (Medium) | SC-EPIC1122-017 |

---

## RFC ↔ Tasks Contract: No Conflicts Found

Both RFC-78 and the task stories agree on:
- Route: `POST /payment/v1/cards`
- Required fields and error codes
- Test layer assignments (component for validation, integration for dedup/vault)

---

## Out-of-Scope Items Excluded

Per PRD-321 `out_of_scope`:
- Card retrieval / deletion — no scenarios generated
- Multi-card UI — no scenarios generated
- Token refresh (M2) — no scenarios generated
- PCI raw storage (vault-service responsibility) — no scenarios generated

---

## ✅ Definition of Done Checklist

- [x] sdet_plan.json schema-valid
- [x] qa_analysis.md present with RFC coverage %
- [x] sdet_testcases.csv present
- [x] coverage_summary.rfc_gaps is empty (all 9 steps covered)
- [x] Log: 22 scenarios | RFC coverage 100% | 0 gaps | 5 legacy regression
