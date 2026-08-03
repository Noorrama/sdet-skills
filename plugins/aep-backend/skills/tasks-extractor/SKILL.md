---
name: backend-tasks-extractor
description: Extract implementation details from Task Breakdown MDs (TASKS.md, STORIES.md, FEATURE_SPECIFICATION.md, SYSTEM_ARCHITECTURE.md, [Service]_CONTEXT.md) into tasks_context.json. Authoritative source for API contracts after codebase reconciliation.
---

# Backend Tasks Extractor

Convert Task Breakdown documents into a schema-compliant `tasks_context.json`. `tasks_context.json` is the **authoritative source for API contracts** — it reflects actual codebase state after Local Codebase Scanner reconciliation. RFC captures design intent; Tasks win on contract details when they conflict.

## Reads (all that are present)

| File | Content |
|---|---|
| `TASKS.md` | Typed task templates |
| `STORIES.md` | Epic → Story hierarchy |
| `FEATURE_SPECIFICATION.md` | High-level feature spec |
| `SYSTEM_ARCHITECTURE.md` | Architecture decisions, component map |
| `[Service]_CONTEXT.md` | Service-specific context from codebase scan |

## Model
Fast tier — Haiku

## Typed task templates to recognise

| Task type | Key fields |
|---|---|
| `NEW_HTTP_API` | Route, method, headers, query params, request/response contract, HTTP error codes |
| `NEW_GRPC_API` | Service, RPC, request/response messages, gRPC error codes, proto compatibility |
| `EXISTING_API_CHANGE` | Current contract, proposed contract, compatibility, deprecation, migration |
| `DB_SCHEMA` | Tables, columns, indexes, constraints, relationships, migration, backfill |
| `PROTO_UPDATE` | Field numbers, enum changes, oneof changes, reserved fields, build version |

## What to extract

| Section | Details |
|---|---|
| Ground-truth API contracts | Exact route, method, field names/types, required vs optional, error codes |
| Per-component validation constraints | Which class validates what; impl constraints (e.g., "reuse PaymentValidator", "DB constraint at insert") |
| Component boundaries | Which validations live at controller / service / repository / DB layer → maps to test layer |
| Story → Task hierarchy | Link each task to parent story and epic for traceability |
| Implementation constraints | DB state, upstream service state, config values required before a test can run |

## Output → tasks_context.json

Schema root structure:
- `feature_name` (string)
- `epics[]` — each with `id`, `title`, `stories[]`
  - Each story: `id`, `title`, `tasks[]`
  - Each task: `id`, `type`, `component`, `package`, `api_contract`, `validation_constraints[]`, `test_layer`, `preconditions[]`
- `rfc_conflicts[]` — `field`, `rfc_value`, `tasks_value`, `resolution: tasks_wins|needs_review`

**test_layer classification:**
- Validation entirely within one service → `component`
- Crosses one external dependency → `integration`
- Spans multiple services → `e2e`

## Guardrails
- Every task must have a recognised `type`; use `"OTHER"` and note it if unlisted.
- `rfc_conflicts` is required even if empty — never silently reconcile, always flag.
- `preconditions` must be specific: what DB rows, config flags, upstream responses must exist.

## Validate
`jsonschema.validate(output, schemas/tasks_context.schema.json)`

## Log
Counts per task type extracted; RFC conflicts found.
