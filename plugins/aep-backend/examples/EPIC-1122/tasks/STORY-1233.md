# STORY-1233 — DB Schema & Repository Layer for payment_cards

| Field          | Value |
|---|---|
| **Story ID**   | STORY-1233 |
| **Epic ID**    | EPIC-1122 |
| **Priority**   | P0 |
| **Type**       | DB_SCHEMA |
| **Labels**     | backend, payments, wallet-service, db |
| **RFC ref**    | RFC-78 |
| **Dependencies** | — (no upstream story dependency) |
| **Component**  | wallet-service |
| **Package**    | com.gojek.wallet.repository |
| **Test layer** | integration |

---

## Story Outcome

As a **backend engineer**, I want the `payment_cards` table created with its unique
constraint and the repository layer in place so that the service layer can persist and
query card fingerprints.

## Scope

Creates the `payment_cards` DB table and the `CardRepository` JPA interface.
Does NOT implement any HTTP endpoint or service logic.

---

## Functional Acceptance Criteria

1. **GIVEN** the Flyway migration `V001__create_payment_cards.sql` is applied  
   **WHEN** the schema is inspected  
   **THEN** the `payment_cards` table exists with columns `id`, `customer_id`, `fingerprint`, `token`, `created_at` and a unique constraint on `(customer_id, fingerprint)`.

2. **GIVEN** two rows with the same `(customer_id, fingerprint)` are inserted  
   **WHEN** the second INSERT is executed  
   **THEN** a `DataIntegrityViolationException` is thrown (unique constraint violation).

3. **GIVEN** a valid `PaymentCard` entity  
   **WHEN** `CardRepository#save` is called  
   **THEN** the row is persisted and the auto-generated UUID `id` is returned.

4. **GIVEN** an existing `(customer_id, fingerprint)` pair  
   **WHEN** `CardRepository#existsByCustomerIdAndFingerprint` is called  
   **THEN** it returns `true`.

5. **GIVEN** a non-existent `(customer_id, fingerprint)` pair  
   **WHEN** `CardRepository#existsByCustomerIdAndFingerprint` is called  
   **THEN** it returns `false`.

---

## Non-Functional Constraints

- Migration must be additive (new table only); rolling back drops the table.
- Index on `customer_id` must be created to support fast fingerprint lookup.

---

## Implementation Constraints

- Use Flyway for migration — no manual schema changes.
- `CardRepository` must extend `JpaRepository<PaymentCard, UUID>`.
- Do not add any business logic to the repository layer.

---

## Error Codes

None — this story is DB/repo layer only; no HTTP responses.

---

## Preconditions for Testing

- Local PostgreSQL (or Testcontainers) with Flyway applied.
- No existing `payment_cards` table in the test schema.
