# RFC-78 — Save Payment-Method API (wallet-service)

| Field                    | Value |
|---|---|
| **RFC ID**               | RFC-78 |
| **Status**               | Approved |
| **PRD ref**              | PRD-321 |
| **Jira Epic**            | EPIC-1122 |
| **Author**               | Piyush |
| **Approver**             | Subrat |
| **Service**              | wallet-service |
| **Milestone**            | M1 |
| **Is approach finalised**| Yes |

---

## Overview

Add a `POST /payment/v1/cards` endpoint to wallet-service that accepts a card payload,
stores a fingerprint, tokenises via the vault-service, and returns a reusable token.
Duplicate cards and past-expiry cards are rejected at the API layer before any DB write.

---

## Scope

**In scope:**
- `POST /payment/v1/cards` endpoint
- Fingerprint computation (SHA-256 of `{customerId}:{cardNumber}`)
- Deduplication via DB unique constraint
- Vault tokenisation via `POST /vault/v1/tokenise`
- Error responses for duplicate, expired, and missing-field cases

**Out of scope:**
- Card retrieval, deletion, or listing
- Token refresh
- PCI raw storage (vault-service responsibility)

**Milestones:**

| Milestone | Scope |
|---|---|
| M1 | POST /payment/v1/cards — save, dedup, expiry validation, tokenisation |
| M2 | Token refresh and card deletion (separate RFC) |

---

## API Contract

### POST /payment/v1/cards

**Headers**

| Header        | Required | Value |
|---|---|---|
| Authorization | Yes      | Bearer {token} |
| Content-Type  | Yes      | application/json |
| Client-ID     | Yes      | Service client identifier |

**Request body (CardDto)**

| Field       | Type   | Required | Validation |
|---|---|---|---|
| cardNumber  | string | Yes | 13–19 digits, Luhn-valid |
| expiryMonth | int    | Yes | 1–12 |
| expiryYear  | int    | Yes | 4-digit year |
| cvv         | string | Yes | 3–4 digits |
| holderName  | string | No  | Max 50 chars |

**Responses**

| Status | Condition | Response body |
|---|---|---|
| 200 | Valid card saved successfully | `{"token": "<string>"}` |
| 400 | Missing required field | `{"error": "MISSING_FIELD", "field": "<fieldName>"}` |
| 400 | Card expiry is in the past | `{"error": "INVALID_EXPIRY"}` |
| 409 | Card fingerprint already exists for this customer | `{"error": "DUPLICATE_CARD"}` |
| 503 | Vault service unavailable | `{"error": "SERVICE_UNAVAILABLE"}` |

**SLA:** p95 latency ≤ 300 ms under normal load on staging.

**Feature flag:** `payment.card_save.enabled` — gates the entire endpoint.
- Disabled → 404 Not Found
- Enabled by default in staging; OFF in production until M1 sign-off.

---

## Business Logic (Ordered Validation Rules)

1. Check feature flag `payment.card_save.enabled`; if disabled, return 404.
2. Validate all required fields present (`cardNumber`, `expiryMonth`, `expiryYear`, `cvv`)
   → 400 `MISSING_FIELD` with `field` indicating the first missing field if any absent.
3. Validate `cardNumber` format: 13–19 digits, passes Luhn check
   → 400 `MISSING_FIELD` (reuse same error envelope) if format invalid.
4. Validate expiry: reject if `expiryYear < currentYear`
   OR (`expiryYear == currentYear` AND `expiryMonth < currentMonth`)
   → 400 `INVALID_EXPIRY`.
5. Compute SHA-256 fingerprint of `{customerId}:{cardNumber}`.
6. Check DB unique constraint on `(customer_id, fingerprint)` → 409 `DUPLICATE_CARD` if exists.
7. Call vault-service `POST /vault/v1/tokenise` with `{cardNumber}` → receive `{token}`.
   → If vault call fails or times out: return 503 `SERVICE_UNAVAILABLE`; do NOT persist to DB.
8. Persist `(customer_id, fingerprint, token, created_at)` to `payment_cards` table.
9. Return `{"token": token}` with HTTP 200.
10. Raw `cardNumber` and `cvv` must never be written to application logs at any level.

---

## DB Schema

**New table: `payment_cards`**

| Column      | Type         | Constraints |
|---|---|---|
| id          | UUID         | PK, auto-generated |
| customer_id | VARCHAR(64)  | NOT NULL, indexed |
| fingerprint | VARCHAR(64)  | NOT NULL |
| token       | VARCHAR(128) | NOT NULL |
| created_at  | TIMESTAMP    | NOT NULL, default NOW() |

**Unique constraint:** `UNIQUE (customer_id, fingerprint)` — enforces deduplication at DB level.

**Migration:** `V001__create_payment_cards.sql` — additive migration (new table only).
Rollback: drop the table.

---

## Sequence Diagram

```
Client          → wallet-service  : POST /payment/v1/cards {CardDto}
wallet-service  → wallet-service  : Check feature flag payment.card_save.enabled
wallet-service  → wallet-service  : Validate required fields + card format
wallet-service  → wallet-service  : Validate expiry date
wallet-service  → DB              : SELECT fingerprint WHERE customer_id + fingerprint
DB              → wallet-service  : Exists? → 409 DUPLICATE_CARD
wallet-service  → vault-service   : POST /vault/v1/tokenise {cardNumber}
vault-service   → wallet-service  : {token} or timeout
wallet-service  → DB              : INSERT payment_cards
wallet-service  → Client          : 200 {token}
```

---

## Service-Level Changes

| Service        | Change | Classes / Methods Introduced |
|---|---|---|
| wallet-service | New endpoint | `PaymentController#saveCard` |
| wallet-service | New service  | `CardService#saveCard` |
| wallet-service | New repo     | `CardRepository#existsByFingerprint`, `CardRepository#save` |
| wallet-service | New DB table | `payment_cards` (migration V001) |
| vault-service  | Consumed (existing) | `POST /vault/v1/tokenise` — no changes |

---

## Cross-Service Dependencies

| Service       | Call Order | Failure Behaviour |
|---|---|---|
| vault-service | After dedup check (step 7) | 503 SERVICE_UNAVAILABLE; no DB write |
| DB (PostgreSQL)| Dedup check (step 6) then persist (step 8) | 409 on unique constraint; 503 if DB down |

---

## Feature Flags

| Flag | Environment | Default | Behaviour when disabled |
|---|---|---|---|
| `payment.card_save.enabled` | staging | ON | 404 Not Found |
| `payment.card_save.enabled` | production | OFF | 404 Not Found |

---

## SLA & Timeouts

| Context | Value | Retry count |
|---|---|---|
| vault-service call timeout | 5000 ms | 1 retry, then 503 |
| Overall API p95 latency target | 300 ms | — |

---

## Risk Areas

| Risk | Severity | Mitigation |
|---|---|---|
| Concurrent duplicate saves bypass DB check | High | DB unique constraint is the final guard; tested with concurrent integration test |
| Vault service timeout causes partial state | High | No DB write before vault responds; 503 returned on timeout |
| Raw card data logged accidentally | High | Log scrubbing rule enforced in CI (REQ-005) |
| DB migration failure on deploy | Medium | Additive migration only; rollback drops the table |

---

## Edge Cases

| Edge Case | Description |
|---|---|
| Boundary card number (13 digits) | Minimum-length Luhn-valid card number must be accepted |
| Boundary card number (19 digits) | Maximum-length card number must be accepted |
| expiryMonth = current month, expiryYear = current year | Card expiring this month is valid (not in the past) |
| Concurrent duplicate save (race condition) | Two identical requests in-flight simultaneously — DB constraint must catch the second |
| Vault timeout after 5000 ms | No DB write; 503 returned |
| Feature flag OFF | 404 returned; no validation of payload |
