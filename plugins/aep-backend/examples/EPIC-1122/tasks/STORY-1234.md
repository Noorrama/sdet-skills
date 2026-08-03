# STORY-1234 — Field Validation & Expiry Check for POST /payment/v1/cards

| Field          | Value |
|---|---|
| **Story ID**   | STORY-1234 |
| **Epic ID**    | EPIC-1122 |
| **Priority**   | P0 |
| **Type**       | NEW_HTTP_API |
| **Labels**     | backend, payments, wallet-service |
| **RFC ref**    | RFC-78 |
| **Dependencies** | STORY-1233 (DB schema must exist) |
| **Component**  | wallet-service |
| **Package**    | com.gojek.wallet.service |
| **Test layer** | component |

---

## Story Outcome

Add input validation to `POST /payment/v1/cards` covering required field presence and
card expiry before any DB write or vault call.

## Scope

Field validation (missing fields, Luhn check, expiry check) for `POST /payment/v1/cards`.
Does NOT cover deduplication or tokenisation (those are STORY-1235).

---

## API Contract

**Route:** `POST /payment/v1/cards`  
**Auth:** Bearer token (Authorization header, required)  
**Content-Type:** application/json

**Request fields:**

| Field       | Type   | Required | Validation rule |
|---|---|---|---|
| cardNumber  | string | Yes | 13–19 digits, passes Luhn algorithm |
| expiryMonth | int    | Yes | 1–12 |
| expiryYear  | int    | Yes | 4-digit calendar year |
| cvv         | string | Yes | 3–4 digits |
| holderName  | string | No  | max 50 chars |

**Response codes for this story:**

| Status | Error code | Trigger |
|---|---|---|
| 400 | `MISSING_FIELD` | Any required field absent; `field` names the first missing field |
| 400 | `INVALID_EXPIRY` | expiryYear < currentYear, OR expiryYear == currentYear AND expiryMonth < currentMonth |

---

## Functional Acceptance Criteria

1. **GIVEN** a request missing `cardNumber`  
   **WHEN** `POST /payment/v1/cards` is called  
   **THEN** response is HTTP 400 with body `{"error": "MISSING_FIELD", "field": "cardNumber"}`.

2. **GIVEN** a request missing `expiryMonth`  
   **WHEN** `POST /payment/v1/cards` is called  
   **THEN** response is HTTP 400 with body `{"error": "MISSING_FIELD", "field": "expiryMonth"}`.

3. **GIVEN** a request missing `cvv`  
   **WHEN** `POST /payment/v1/cards` is called  
   **THEN** response is HTTP 400 with body `{"error": "MISSING_FIELD", "field": "cvv"}`.

4. **GIVEN** a `CardDto` with `expiryYear < currentYear`  
   **WHEN** `POST /payment/v1/cards` is called  
   **THEN** response is HTTP 400 with body `{"error": "INVALID_EXPIRY"}`.

5. **GIVEN** a `CardDto` with `expiryYear == currentYear` AND `expiryMonth < currentMonth`  
   **WHEN** `POST /payment/v1/cards` is called  
   **THEN** response is HTTP 400 with body `{"error": "INVALID_EXPIRY"}`.

6. **GIVEN** a valid `CardDto` with all fields present and a future expiry date  
   **WHEN** `POST /payment/v1/cards` is called  
   **THEN** validation passes and the request proceeds to the deduplication check.

---

## Non-Functional Constraints

- No raw `cardNumber` or `cvv` value may be written to logs at any log level.

---

## Implementation Constraints

- Must reuse existing `CardValidationService` — do not introduce a new validator class.
- Validation must occur before any DB call or vault-service call.
- Use `@Valid` + `BindingResult` pattern consistent with existing wallet-service controllers.

---

## Error Codes

| Code | Status | Response body |
|---|---|---|
| `MISSING_FIELD`  | 400 | `{"error": "MISSING_FIELD", "field": "<fieldName>"}` |
| `INVALID_EXPIRY` | 400 | `{"error": "INVALID_EXPIRY"}` |

---

## Preconditions for Testing

- STORY-1233 merged (payment_cards table exists).
- `CardValidationService` bean is present in the Spring context.
- No vault-service mock needed for this story (validation is pre-vault).
