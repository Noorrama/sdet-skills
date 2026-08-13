---
name: backend-automation-plan-generator
description: Generate the automation plan from an approved sdet_plan.json. Outputs automation_plan.json as a flat list of automation_scenarios — one object per test scenario — with test class, package, method name, fixture IDs, required state, and curl references with fixture-scoped placeholders. response_fields_used[] and test_data_output are left null/empty for TDG to fill. Structural contract consumed by both test-data-generator and test-code-generator. Requires human review before code generation begins.
---

# Backend Automation Plan Generator

Bridge between *what to test* (SDET plan) and *how to implement it* (test code + test data). Locks in all structural decisions before code generation starts — errors here cascade into every generated test method.

## Reads

| File | Purpose |
|---|---|
| `sdet_plan.json` (approved) | Human-reviewed output from sdet-plan-generator. Source of scenario_id, source_ref, is_legacy_regression, description, preconditions, test_layer, tags, priority. |
| `tasks_context.json` | Package/class naming conventions, component boundaries, api_contract, service_name, target_framework. |
| `code_change_context.json` | `curl_reference` construction from actual endpoint signatures. |
| `regression_context.json` | Existing class naming patterns for consistency. |

## Model
Fast tier — Haiku

## Per scenario (where `is_dedup = false`), generate one object in `automation_scenarios[]`

| Field | Details |
|---|---|
| `scenario_id` | From sdet_plan.json |
| `requirement_ref` | From sdet_plan.json `source_ref`, e.g. `RFC-78:step-9 / REQ-001 / AC-001` |
| `description` | From sdet_plan.json `name` |
| `is_legacy_regression` | From sdet_plan.json |
| `is_dedup` | `false` — dedup scenarios are skipped entirely |
| `target_framework` | From tasks_context.json, e.g. `GBT` |
| `service_name` | From tasks_context.json component field |
| `module` | From tasks_context.json component field |
| `package` | Fully qualified Java package based on `test_layer` + component grouping from tasks_context + existing regression naming patterns |
| `test_class` | Class name based on `test_layer` + feature/component grouping. Group related scenarios — not one class per scenario. e.g. `SaveCardComponentTest`, `SaveCardIntegrationTest`, `CardRepositoryIntegrationTest` |
| `test_layer` | From sdet_plan.json: `component` \| `integration` \| `e2e` |
| `method_name` | `should[ExpectedOutcome]When[Condition]` — Java-valid camelCase. Append suffix if collision within class. |
| `assertion_class` | Derived from test_class, e.g. `SaveCardAssertions`, `CardRepositoryAssertions` |
| `endpoint` | HTTP method + path from tasks_context api_contract, e.g. `POST /payment/v1/cards`. Empty string for DB/infra-only tests (no HTTP call). |
| `curl_reference` | Minimal valid curl from code_change_context or tasks_context api_contract. Use fixture-scoped placeholders: `{{FIX-xxx.fieldName}}` — e.g. `{{FIX-CARDPAY-001.bearerToken}}`, `{{FIX-CARDPAY-002.savedCardNumber}}`. Placeholder field names are **candidates** — TDG confirms and corrects them against the catalog response schema. Empty string for DB/infra-only tests. |
| `test_data[]` | One entry per independently provisioned entity needed by this scenario. See fixture guidance below. |
| `tags` | From sdet_plan.json tags + priority, e.g. `["negative", "P0"]` |
| `environments` | From tasks_context.json environments or default `["dev-cluster", "staging-cluster"]` |
| `execution_hints` | Default `{"retry_count": 2, "timeout_ms": 15000}`. Use `30000` for DB/infra tests, `60000` for performance tests. |
| `jira_ids` | Empty array `[]` unless tasks_context has JIRA references |

## test_data[] — per fixture entry in each scenario

Each scenario's `test_data[]` contains one entry per independently provisioned entity.

| Field | Details |
|---|---|
| `fixture_id` | Format: `FIX-{FEATURE}-{sequence}`. One ID per distinct system state. Scenarios requiring the same precondition state use the same fixture_id (same ID repeated across scenarios). |
| `description` | Human-readable: what entity, what state — e.g. "Verified customer CX-001 with valid Bearer token; card not previously saved" |
| `required_state.entity` | Domain the test data service owns: `CUSTOMER` \| `DRIVER` \| `BOOKING` \| `MERCHANT` \| `PAYMENT_INSTRUMENT` \| `DB_INFRA`. Maps to `testDataEntity` in the service request. Use `DB_INFRA` for Testcontainers / migration fixtures. |
| `required_state.category` | Exact category name from the test data service catalog (e.g. `CUSTOMER_WITH_WALLET`, `CUSTOMER_WITH_SAVED_CARD`). Maps to `testDataCategory.testDataCategoryName`. For `DB_INFRA`: the infra type (e.g. `TESTCONTAINERS_POSTGRESQL`). |
| `required_state.count` | Number of entities to provision. Maps to `testDataCategory.count`. Default `1`. Omit for `DB_INFRA`. |
| `required_state.config` | Additional parameters for this category (e.g. `wallet_status`, `saved_card_type`). Merged into the `testDataCategory` request body. |
| `response_fields_used` | Set to `[]`. **Do not populate here.** TDG looks up the TDP catalog response schema and fills confirmed field names. |
| `test_data_output` | Set to `null`. TDG writes enrichment here: `test_data_status`, `test_data_details.test_data_operations[]`, `test_buddy_prompt`. |

### How to identify fixtures from scenario preconditions

Read each scenario's `preconditions` from sdet_plan.json. Ask: *"What entity must exist, in what state, before this test can run?"*

- Same entity + same required state → use the same `fixture_id` across those scenarios
- Different state (e.g. customer with no card vs customer with card already saved) → different `fixture_id`
- DB/infra setup (Testcontainers, migration) → `entity: DB_INFRA`

Assign `FIX-{FEATURE_PREFIX}-{sequence}` IDs ordered by first appearance across all scenarios.

### Single-call boundary rule

One `fixture_id` = one call to the test data service at test runtime.
- If a scenario needs a customer AND a driver independently → two entries in `test_data[]` → two calls.
- If the test data service has a composite entity → one entry → one call → response includes all sub-entity fields.
- Mock stubs (WireMock) are never in `test_data[]` — they are infra setup, not test data service calls.

## Output → automation_plan.json

Schema root structure:
- `epic_id` — from tasks_context epics[0].id
- `automation_scenarios[]` — flat list, one object per non-dedup scenario, with all fields above

## Guardrails
- Skip scenarios where `is_dedup: true` — do not generate an automation_scenario entry for them.
- `test_class` groups related scenarios — not one class per scenario. Group by `(test_layer + feature_component)`.
- If endpoint not in code_change_context, use tasks_context api_contract. If neither has it, flag it.
- `required_state` must use the structured `{entity, category, count, config}` shape — no prose strings.
- `response_fields_used` must be `[]` for every fixture — TDG populates after catalog lookup. Pre-filling is a generation error.
- `test_data_output` must be `null` for every fixture — TDG writes to it. Pre-filling is a generation error.
- `curl_reference` placeholder field names (e.g. `{{FIX-CARDPAY-001.bearerToken}}`) are candidates derived from context — TDG validates and corrects them.
- `curl_reference` must use fixture-scoped `{{FIX-xxx.field}}` placeholders — never unscoped `{token}`.
- `endpoint` and `curl_reference` must be empty string `""` for DB/infra-only tests (no HTTP call).

## Validate
`jsonschema.validate(output, schemas/automation_plan.schema.json)`

## Log
N scenarios generated, N skipped (dedup), N unique fixture_ids across all scenarios.
