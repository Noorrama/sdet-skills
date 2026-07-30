---
name: backend-rfc-extractor
description: Extract design intent from a backend RFC into rfc_context.json. Maps the complete ordered validation sequence, API contracts, flows, error codes, edge cases, and cross-service dependencies for the backend QA pipeline.
---

# Backend RFC Extractor

Convert RFC text into a schema-compliant `rfc_context.json`. The RFC is the primary driver for scenario **completeness** — every validation step or error path must produce at least one test scenario.

**Authority boundary:** RFC captures API contracts at design level. `tasks_context.json` (tasks-extractor) is authoritative post-reconciliation. Flag conflicts — do not silently resolve them.

## Reads
RFC document (path passed as argument, or latest RFC MD in the feature folder)

## Model
Fast tier — Haiku

## What to extract

| Section | Details |
|---|---|
| Validation sequence | Full ordered steps — what is validated, why, failure error code and HTTP status. Must be complete and atomic. |
| API contracts | Per endpoint: route, method, request/response shape, auth. Mark `design_level: true`. |
| Flows | Happy path + all named deviation paths (retry, fallback, timeout). |
| Error scenarios | Technical: condition → error code → HTTP status → validation step ref. |
| Edge cases | Boundary values, race conditions, concurrent requests, timeout paths. |
| Cross-service dependencies | Downstream services, call order, failure behaviour. |
| Feature flags | Each flag state (on/off) requires separate scenarios. |
| SLA / timeouts | Timeout values, retry counts, circuit-breaker thresholds. |

## Output → rfc_context.json

Schema root structure:
- `feature_name` (string), `rfc_version` (string or null)
- `validation_sequence[]` — `step`, `name`, `what_is_validated`, `why`, `failure_error_code`, `failure_http_status`, `notes`
- `api_contracts[]` — `endpoint`, `method`, `design_level: true`, `auth`, `request_schema`, `response_schema`, `error_codes`
- `flows[]` — `name`, `steps[]` (+ `trigger` for non-happy-path flows)
- `error_scenarios[]` — `condition`, `error_code`, `http_status`, `validation_step_ref`
- `edge_cases[]` — `name`, `description`, `type: boundary|race_condition|timeout|concurrent`
- `cross_service_dependencies[]` — `service`, `call_order`, `failure_behaviour`
- `feature_flags[]` — `flag`, `on_behaviour`, `off_behaviour`
- `timeouts[]` — `context`, `value_ms`, `retry_count`

## Guardrails
- `validation_sequence` must be complete and ordered — this is the completeness guarantee.
- Do NOT merge or summarise validation steps — keep them atomic.
- Extract edge cases even when only implied (e.g., "max 3 retries" → extract "retry exhausted" edge case).
- Flag any underspecified API contract fields (e.g., missing error envelope shape).

## Validate
`jsonschema.validate(output, schemas/rfc_context.schema.json)`

## Log
Counts: validation steps, flows, error scenarios, edge cases extracted.
Flag any contracts that conflict with or are absent from tasks_context (if already available).
