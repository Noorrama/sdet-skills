---
name: backend-automation-plan-generator
description: Generate the automation plan from an approved sdet_plan.json. Outputs automation_plan.json with test class names, package paths, fixture IDs, required state per scenario, and curl references with fixture-scoped placeholders. response_fields_used[] is left empty — populated by test-data-generator after catalog lookup. Structural contract consumed by both test-data-generator and test-code-generator. Requires human review before code generation begins.
---

# Backend Automation Plan Generator

Bridge between *what to test* (SDET plan) and *how to implement it* (test code + test data). Locks in all structural decisions before code generation starts — errors here cascade into every generated test method.

## Reads

| File | Purpose |
|---|---|
| `sdet_plan.json` (approved) | Human-reviewed output from sdet-plan-generator |
| `tasks_context.json` | Package/class naming conventions and component boundaries |
| `code_change_context.json` | `curl_reference` construction from actual endpoint signatures |
| `regression_context.json` | Existing class naming patterns for consistency |

## Model
Fast tier — Haiku

## Per scenario (where `is_dedup = false`), generate

| Field | Details |
|---|---|
| Test class assignment | Based on `test_layer` + feature/component grouping from tasks_context + existing regression naming patterns |
| Package path | Fully qualified Java package (e.g., `com.gojek.payments.test.component`) |
| Method name | `should[ExpectedOutcome]When[Condition]` — Java-valid camelCase. Append suffix if collision within class. |
| `curl_reference` | Minimal valid curl from code_change_context or tasks_context api_contract. Use fixture-scoped placeholders: `{{FIX-xxx.fieldName}}` — e.g. `{{FIX-CARDPAY-001.bearerToken}}`, `{{FIX-CARDPAY-002.savedCardNumber}}`. Placeholder field names are **candidates** — TDG confirms and corrects them against the catalog response schema. |
| `fixture_ids[]` | Format: `FIX-{feature}-{sequence}`. One entry per independently provisioned entity. Group scenarios sharing the same system state under one fixture_id. A scenario needing customer + driver = two entries. |

## Fixtures summary — per unique fixture_id, generate

Each fixture_id that appears in any method's `fixture_ids[]` must have exactly one entry in `fixtures_summary[]`.

| Field | Details |
|---|---|
| `fixture_id` | Matches the ID used in methods |
| `description` | Human-readable: what entity, what state |
| `used_by_scenarios[]` | All scenario_ids that reference this fixture |
| `required_state.entity` | Domain the test data service owns: `CUSTOMER` \| `DRIVER` \| `BOOKING` \| `MERCHANT` \| `PAYMENT_INSTRUMENT` \| `DB_INFRA`. Maps to `testDataEntity` in the service request. Use `DB_INFRA` for Testcontainers / migration fixtures not provisioned by the test data service. |
| `required_state.category` | Exact category name from the test data service catalog (e.g. `CUSTOMER_WITH_GOPAY`, `DRIVER_4W_ONLINE`). Maps to `testDataCategory.testDataCategoryName`. For `DB_INFRA`: the infra type (e.g. `TESTCONTAINERS_POSTGRESQL`). |
| `required_state.count` | Number of entities to provision. Maps to `testDataCategory.count`. Default `1`. Omit for `DB_INFRA`. |
| `required_state.config` | Additional parameters for this category (e.g. `wallet_balance_idr`, `service_area_id`). Merged into the `testDataCategory` request body. |
| `response_fields_used[]` | Set to `[]`. **Do not populate here.** TDG looks up the TDP catalog response schema for this entity + category and fills in the confirmed field names. |
| `output` | Set to `null`. TDG writes enrichment here after catalog lookup: `test_data_status`, `test_data_operations[]`, `test_buddy_prompt`. Code generator reads `output.test_data_status` to select the provisioning strategy. |

### Single-call boundary rule

One `fixture_id` = one call to the test data service at test runtime.
- If a scenario needs a customer AND a driver independently → two fixture_ids → two calls.
- If the test data service has a composite entity (e.g. `BOOKING` that provisions customer + driver + booking state together) → one fixture_id → one call → response includes fields from all sub-entities.
- Mock stubs (`mock_setup`) are never fixture_ids — they are WireMock/infra setup, not test data service calls.

## Output → automation_plan.json

Schema root structure:
- `feature_name`, `plan_version`
- `test_classes[]` — each with `class_name`, `package`, `test_layer`, `methods[]`
  - Each method: `method_name`, `scenario_id`, `is_dedup`, `curl_reference`, `fixture_ids[]`, `tags[]`
- `fixtures_summary[]` — `fixture_id`, `description`, `used_by_scenarios[]`, `required_state{entity, category, count, config}`, `response_fields_used[]`, `output` (null — written by TDG)

## Guardrails
- Group scenarios into test classes by `(test_layer + feature_component)` — not one class per scenario.
- Skip methods where `is_dedup: true`.
- If endpoint not in code_change_context, use tasks_context api_contract. If neither has it, flag it.
- `required_state` must use the structured `{entity, category, count, config}` shape — no prose strings.
- `response_fields_used` must be `[]` for every fixture — TDG populates this after catalog lookup. Pre-filling it here is a generation error.
- `output` must be `null` for every fixture — TDG writes to it. Pre-filling it here is a generation error.
- `curl_reference` placeholder field names (e.g. `{{FIX-CARDPAY-001.bearerToken}}`) are candidates derived from context — TDG validates and corrects them.
- `curl_reference` must use fixture-scoped `{{FIX-xxx.field}}` placeholders — never unscoped `{token}` — so TDG and code-generator can resolve which fixture each field belongs to.
- Share a `fixture_id` across scenarios requiring identical system state — test data service provisions once and reuses.

## Validate
`jsonschema.validate(output, schemas/automation_plan.schema.json)`

## Log
N test classes, N methods, N fixtures, N scenarios skipped (dedup).
