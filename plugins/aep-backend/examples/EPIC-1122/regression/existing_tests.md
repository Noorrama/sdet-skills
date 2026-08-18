# Existing Test Catalog — wallet-service / payment module

> **Scope:** Tests covering `wallet-service` payment flows, scoped to
> `PaymentController`, `CardService`, `CardRepository`, and `CardValidationService`.
> Used as input to `regression-extractor` for EPIC-1122.

---

## Automated Tests (GBT Java)

### GBT-PAY-001
- **Framework:** GBT_JAVA
- **Class:** `PaymentControllerTest#saveCardHappyPath`
- **File:** `wallet-service/src/test/java/com/gojek/wallet/PaymentControllerTest.java`
- **API endpoint:** POST /payment/v1/cards
- **Requirement ref:** REQ-001
- **What it tests:** Valid card save returns HTTP 200 and a non-null token.
- **Is legacy regression:** Yes

### GBT-PAY-002
- **Framework:** GBT_JAVA
- **Class:** `CardValidationServiceTest#rejectExpiredCard`
- **File:** `wallet-service/src/test/java/com/gojek/wallet/service/CardValidationServiceTest.java`
- **API endpoint:** POST /payment/v1/cards
- **Requirement ref:** REQ-004
- **What it tests:** Card with `expiryYear < currentYear` is rejected with `INVALID_EXPIRY`.
- **Is legacy regression:** Yes

### GBT-PAY-003
- **Framework:** GBT_JAVA
- **Class:** `CardValidationServiceTest#rejectExpiredCardSameYear`
- **File:** `wallet-service/src/test/java/com/gojek/wallet/service/CardValidationServiceTest.java`
- **API endpoint:** POST /payment/v1/cards
- **Requirement ref:** REQ-004
- **What it tests:** Card with `expiryYear == currentYear` AND `expiryMonth < currentMonth` is rejected with `INVALID_EXPIRY`.
- **Is legacy regression:** Yes

### GBT-PAY-004
- **Framework:** GBT_JAVA
- **Class:** `CardRepositoryTest#uniqueConstraintBlocksDuplicate`
- **File:** `wallet-service/src/test/java/com/gojek/wallet/repository/CardRepositoryTest.java`
- **API endpoint:** POST /payment/v1/cards (DB layer)
- **Requirement ref:** REQ-003
- **What it tests:** Inserting the same `(customer_id, fingerprint)` twice raises `DataIntegrityViolationException`.
- **Is legacy regression:** Yes

---

## Manual Tests (BrowserStack)

### BS-PAY-011
- **Title:** Save card — duplicate card rejected (HTTP 409)
- **Module:** wallet-service
- **API endpoint:** POST /payment/v1/cards
- **Requirement ref:** REQ-003
- **Steps:**
  1. Save a valid Visa card for customer CX-001.
  2. Save the same Visa card again for CX-001.
  3. Assert HTTP 409 and error code `DUPLICATE_CARD`.
- **Is legacy regression:** Yes

### BS-PAY-012
- **Title:** Save card — missing cardNumber returns 400
- **Module:** wallet-service
- **API endpoint:** POST /payment/v1/cards
- **Requirement ref:** REQ-002
- **Steps:**
  1. POST /payment/v1/cards without `cardNumber` in body.
  2. Assert HTTP 400 and error `MISSING_FIELD` with `field: "cardNumber"`.
- **Is legacy regression:** Yes

---

## Coverage Summary

| Requirement | Covered by | Coverage type |
|---|---|---|
| REQ-001 (happy path save) | GBT-PAY-001 | Automated |
| REQ-002 (missing field) | BS-PAY-012 | Manual only |
| REQ-003 (duplicate card) | GBT-PAY-004, BS-PAY-011 | Automated + Manual |
| REQ-004 (expired card) | GBT-PAY-002, GBT-PAY-003 | Automated |
| REQ-005 (no card data in logs) | **NONE** | Not covered |
| NFR-001 (p95 ≤ 300 ms) | **NONE** | Not covered |
| NFR-003 (vault timeout → 503) | **NONE** | Not covered |

**Covered requirement refs:** REQ-001, REQ-002, REQ-003, REQ-004  
**Uncovered requirement refs:** REQ-005, NFR-001, NFR-003

---

## Modules Scoped

- `wallet-service/src/main/java/com/gojek/wallet/controller/PaymentController.java`
- `wallet-service/src/main/java/com/gojek/wallet/service/CardService.java`
- `wallet-service/src/main/java/com/gojek/wallet/service/CardValidationService.java`
- `wallet-service/src/main/java/com/gojek/wallet/repository/CardRepository.java`
