---
name: backend-automation-plan-generator
description: Generate the automation plan from an approved sdet_plan.json. Outputs automation_plan.json with test class names, package paths, fixture IDs, required state per scenario, curl references, and mock setup. Structural contract consumed by both test-data-generator and test-code-generator. Requires human review before code generation begins.
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
| `curl_reference` | Minimal valid curl from code_change_context or tasks_context api_contract. Placeholders: `{token}`, `{payment_id}`, `{amount}` |
| `fixture_id` | Format: `FIX-{feature}-{sequence}`. Group scenarios sharing the same system state under one fixture_id. |
| `required_state` | Specific pre-test system state for test-data-generator — avoid vague descriptions like "a valid user" |
| `mock_setup` | Downstream services needing mocking + response to return (from `dependency_changes` in code_change_context) |

## Output → automation_plan.json

Schema root structure:
- `feature_name`, `plan_version`
- `test_classes[]` — each with `class_name`, `package`, `test_layer`, `methods[]`
  - Each method: `method_name`, `scenario_id`, `is_dedup`, `curl_reference`, `fixture_id`, `required_state`, `mock_setup[]`, `tags[]`
- `fixtures_summary[]` — `fixture_id`, `description`, `used_by_scenarios[]`, `required_state`

## Guardrails
- Group scenarios into test classes by `(test_layer + feature_component)` — not one class per scenario.
- Skip methods where `is_dedup: true`.
- If endpoint not in code_change_context, use tasks_context api_contract. If neither has it, flag it.
- `required_state` must be specific enough for test-data-generator to produce a TDP payload without ambiguity.
- Share `fixture_id` across scenarios requiring identical system state — TDP provisions once and reuses.

## Validate
`jsonschema.validate(output, schemas/automation_plan.schema.json)`

## Log
N test classes, N methods, N fixtures, N scenarios skipped (dedup).
