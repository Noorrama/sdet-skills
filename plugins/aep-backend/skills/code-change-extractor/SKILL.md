---
name: backend-code-change-extractor
description: Extract structured signal from aggregated Epic MR diffs (GitLab unified diff + CR notes) into code_change_context.json. Feeds sdet-plan-generator Pass 2 and automation-plan-generator. Noise-filtered — skips logging, formatting, and unit test changes.
---

# Backend Code Change Extractor

At post-build, the code diff is ground truth. Extract only signals that affect testable behaviour — filtering out everything that does not.

**Downstream consumers:**
- `sdet-plan-generator Pass 2` — finds new/changed scenarios not in the pre-build plan
- `automation-plan-generator` — gets exact class names, packages, and structures for test code generation

## Reads

| Source | Content |
|---|---|
| GitLab unified diff | Aggregated diff of all MRs in the Epic (not individual commits) |
| CR notes | Code review comments clarifying intent or flagging behaviour changes |

## Model
Fast tier — Haiku

## What to extract

| Category | Details |
|---|---|
| New endpoints | Route, method, controller class, package, request/response model class names, `curl_reference` |
| Changed endpoints | What changed, previous contract, new contract |
| Validation rules | Field → constraint → error code → layer (`controller|service|repository`) |
| Error mappings | Exception class → HTTP status → error code → trigger condition |
| DB schema changes | New tables/columns/indexes/constraints from migration files |
| New enums / constants | New enum values, status codes, error code constants |
| Dependency changes | New downstream service calls, mock requirements, changed response shapes |
| Auth / header changes | New auth requirements, scopes, headers |
| Feature flags | New flag checks — each flag produces separate test scenario branches |
| Proto changes | New fields, changed types, new RPCs in `.proto` files |

**`curl_reference` format:** minimal valid curl with placeholder values (`{token}`, `{payment_id}`, `{amount}`).

## What NOT to extract (noise filter)
- Logging, metrics, tracing additions
- Code formatting / whitespace changes
- Private / internal method changes (no public API impact)
- Service's own unit test file changes (dev test scope)
- Javadoc / comment-only changes
- Build config changes unless they introduce feature flags

## Output → code_change_context.json

Schema root structure:
- `epic_id`, `mr_ids[]`, `extraction_date` (ISO8601)
- `new_endpoints[]` — `route`, `method`, `controller_class`, `package`, `request_model`, `response_model`, `curl_reference`
- `changed_endpoints[]` — `route`, `method`, `what_changed`, `previous_contract`, `new_contract`
- `validation_rules[]` — `field`, `constraint`, `error_code`, `layer`
- `error_mappings[]` — `exception`, `http_status`, `error_code`, `trigger_condition`
- `db_changes[]` — `migration_file`, `table`, `new_columns[]`, `new_constraints[]`, `new_indexes[]`
- `new_enums[]` — `class`, `package`, `new_values[]`
- `dependency_changes[]` — `service`, `method`, `needs_mock`, `mock_response_shape`
- `auth_changes[]` — `endpoint`, `required_scope`, `change: new|modified|removed`
- `feature_flags[]` — `flag`, `affects`, `on_behaviour`, `off_behaviour`
- `proto_changes[]` — `proto_file`, `new_fields[]`, `changed_fields[]`, `new_rpcs[]`

## Guardrails
- Process the aggregated Epic diff, not individual MR diffs — unit of extraction is the feature.
- Use CR notes to clarify ambiguous diffs.
- If a field appears in both a new endpoint and a validation rule, extract it in both places.
- Flag any validation rule whose error code is not in `rfc_context.json error_scenarios` — this is a coverage gap.

## Validate
`jsonschema.validate(output, schemas/code_change_context.schema.json)`

## Log
Counts per category. Flag validation rule error codes not found in rfc_context (coverage gap signal).
