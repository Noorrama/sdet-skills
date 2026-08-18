# STORY-1235 — Deduplication, Vault Tokenisation & Happy-Path Response

| Field          | Value |
|---|---|
| **Story ID**   | STORY-1235 |
| **Epic ID**    | EPIC-1122 |
| **Priority**   | P0 |
| **Type**       | NEW_HTTP_API |
| **Labels**     | backend, payments, wallet-service |
| **RFC ref**    | RFC-78 |
| **Dependencies** | STORY-1233, STORY-1234 |
| **Component**  | wallet-service |
| **Package**    | com.gojek.wallet.service, com.gojek.wallet.controller |
| **Test layer** | integration |

---

## Story Outcome

Complete the `POST /payment/v1/cards` endpoint by adding fingerprint deduplication
and vault tokenisation so that a valid card produces a reusable token.

## Scope

Fingerprint computation → DB dedup check → vault call → DB persist → 200 token response.
Feature flag gating (`payment.card_save.enabled`).
503 on vault timeout (no DB write).

---

## API Contract

**Route:** `POST /payment/v1/cards`  
**Auth:** Bearer token (Authorization header, required)

**Response codes for this story:**

| Status | Error code | Trigger |
|---|---|---|
| 200 | — | Valid card; returns `{"token": "<string>"}` |
| 409 | `DUPLICATE_CARD` | SHA-256 fingerprint already exists for this customer |
| 503 | `SERVICE_UNAVAILABLE` | Vault call fails or times out (5000 ms) |
| 404 | — | Feature flag `payment.card_save.enabled` is OFF |

---

## Functional Acceptance Criteria

1. **GIVEN** a verified customer with a valid Bearer token and a new (not previously saved) Visa card  
   **WHEN** `POST /payment/v1/cards` is called with a complete valid `CardDto`  
   **THEN** response is HTTP 200 with body `{"token": "<non-null string>"}` and one row is persisted in `payment_cards`.

2. **GIVEN** a customer who has already saved the same card (same `{customerId}:{cardNumber}` fingerprint)  
   **WHEN** `POST /payment/v1/cards` is called with identical card details  
   **THEN** response is HTTP 409 with body `{"error": "DUPLICATE_CARD"}` and no new row is written.

3. **GIVEN** a valid `CardDto` but vault-service returns a 503 or times out after 5000 ms  
   **WHEN** `POST /payment/v1/cards` is called  
   **THEN** response is HTTP 503 with body `{"error": "SERVICE_UNAVAILABLE"}` and no row is persisted in `payment_cards`.

4. **GIVEN** the feature flag `payment.card_save.enabled` is OFF  
   **WHEN** `POST /payment/v1/cards` is called with any payload  
   **THEN** response is HTTP 404 and no validation or DB call is made.

5. **GIVEN** two concurrent requests for the same customer with the same card (race condition)  
   **WHEN** both requests reach the DB check simultaneously  
   **THEN** exactly one succeeds with HTTP 200 and the other receives HTTP 409 `DUPLICATE_CARD` (enforced by DB unique constraint).

---

## Non-Functional Constraints

- Vault-service call timeout: 5000 ms with 1 retry before returning 503.
- p95 latency for the full request (validation + dedup + vault + persist) ≤ 300 ms under normal staging load.
- No raw `cardNumber` or `cvv` logged at any level.

---

## Implementation Constraints

- SHA-256 fingerprint must use format `{customerId}:{cardNumber}` (UTF-8 bytes, hex output).
- Vault call must use `VaultClient#tokenise(cardNumber)` — do not inline HTTP calls.
- DB persist must happen only after a successful vault response.
- Must handle `DataIntegrityViolationException` from repository and translate to 409.

---

## Error Codes

| Code | Status | Response body |
|---|---|---|
| `DUPLICATE_CARD` | 409 | `{"error": "DUPLICATE_CARD"}` |
| `SERVICE_UNAVAILABLE` | 503 | `{"error": "SERVICE_UNAVAILABLE"}` |

---

## Preconditions for Testing

- STORY-1233 and STORY-1234 merged.
- vault-service stub/mock configured to return a fixed token for valid cards, and 503 for designated test card numbers.
- Feature flag `payment.card_save.enabled` set to ON in test environment.
- Test fixtures: a verified customer, a new valid Visa card, a card already persisted for that customer.
