---
name: backend-test-data-generator
description: Generate test data requests from the approved automation_plan.json, translating fixture required_state definitions into TDP/TestBuddy provisioning payloads. Runs in parallel with test-code-generator. Fixtures are resolved at execution time in Phase B CI — not embedded in test code.
---

# Backend Test Data Generator

Translate `required_state` definitions from the automation plan into concrete TDP (Test Data Platform) / TestBuddy provisioning requests. Runs in the **Data Lane** in parallel with test-code-generator — neither lane depends on the other's output.

**Key design principle:** Fixtures are resolved at **execution time** (Phase B CI), not at code generation time. Test code references fixture IDs; TDP resolves them to actual entity IDs at runtime — making test data environment-independent.

## Reads

| File | Purpose |
|---|---|
| `automation_plan.json` (approved + dedup-flagged) | Source of `fixture_id` + `required_state` per method |
| `tasks_context.json` | DB schema constraints that test data must satisfy |
| `code_change_context.json` | DB changes (new columns, constraints) affecting fixture structure |

## Model
Fast tier — Haiku

## Per unique fixture_id, generate

| Element | Details |
|---|---|
| Entity creation requests | What entities TDP must create (users, accounts, transactions, etc.) |
| State setup | What state those entities must be in |
| Constraint satisfaction | All DB constraints from tasks_context satisfied; new NOT NULL columns must have values |
| Relationships | Entity relationships (user → account → transaction) |
| Cleanup strategy | `delete_all_created_entities` (default) or `rollback` if test verifies persistence |

## Output → test_data_requests.json

Schema root structure:
- `feature_name`, `tdp_version`
- `fixtures[]` — each with:
  - `fixture_id`, `description`, `used_by_methods[]`
  - `entities[]` — `entity_type`, `tdp_resource`, `fields{}`, `ref_id`, `belongs_to` (optional)
  - `state_assertions[]` — plain-text assertions TDP must verify
  - `cleanup: delete_all_created_entities|rollback`
  - `constraint_notes[]` — DB constraint context from migration files
- `tdp_payload_summary` — `total_fixtures`, `total_entities`, `entity_types[]`

## Guardrails
- Deduplicate by `fixture_id` — if multiple methods share a fixture, generate one request, not N.
- Translate `required_state` faithfully — do not add extra state.
- `ref_id` values are local references (e.g., `user_ref_1`) — TDP resolves them to real IDs at runtime.
- Never embed real entity IDs, real tokens, or real account numbers — use synthetic or TDP-generated values.
- Satisfy all DB constraints from tasks_context `db_changes`, including new NOT NULL columns.

## Validate
`jsonschema.validate(output, schemas/test_data_requests.schema.json)`

## Log
N fixtures generated, N entities, N fixtures deduplicated.
