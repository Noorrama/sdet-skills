---
name: backend-doc-delta-extractor
description: Extract what changed between two versions of a PRD, RFC, or Task Breakdown MD into doc_change_context.json. Used when an upstream document is updated mid-sprint. Produces a human-reviewable delta before sdet-plan-generator is re-triggered. This is the doc-change-context path for doc changes — distinct from the Post-Build Code-change-context mode which handles code diffs.
disable-model-invocation: true
---

# Backend Doc Delta Extractor

When a PRD, RFC, or Tasks document is updated mid-sprint, extract only what changed so that:
1. SDET + PM can review scope before anything regenerates
2. `sdet-plan-generator` re-runs with a focused delta, patching only affected scenarios

## Reads

| Input | Description |
|---|---|
| `doc_type` | `"PRD"`, `"RFC"`, or `"TASKS"` |
| `previous_version` | Previous version of the document (file path or content) |
| `updated_version` | Updated version of the document (file path or content) |
| `change_signal` | Optional: git commit message or manual note explaining the change |

## Model
Fast tier — Haiku

## What to extract

| Category | Details |
|---|---|
| Added content | New sections, acceptance criteria, validation steps, error scenarios, flows, edge cases |
| Modified content | Content present in both versions but changed; include old and new form; reordered validation steps count as modifications |
| Removed content | Content in previous version absent in updated; may require deprecating existing test scenarios |
| Impact assessment | Per delta item: adds new scenarios / changes existing / removes scope / which authority is affected (PRD→priority; RFC→validation sequence; Tasks→contracts) |

## Output → doc_change_context.json

Schema root structure:
- `doc_type: PRD|RFC|TASKS`, `change_date` (ISO8601), `change_signal` (string or null)
- `delta`
  - `added[]` — `section`, `content`, `impact: new_scenarios|update_existing|no_test_impact`, `affects_authority`
  - `modified[]` — `section`, `previous`, `updated`, `impact: new_scenarios|update_existing|deprecate_existing|no_test_impact`
  - `removed[]` — `section`, `content`, `impact: deprecate_existing|no_test_impact`
- `human_feedback_summary` (string — 2-3 sentences for SDET + PM review)
- `scenarios_to_add[]`, `scenarios_to_update[]`, `scenarios_to_deprecate[]`

## Guardrails
- Structural changes that preserve meaning (section rename, reorganisation) are NOT modifications — only semantic changes count.
- If `change_signal` contradicts what the diff shows, flag both to the human reviewer.
- `human_feedback_summary` must be factual and plain English: what changed and the test impact.
- `scenarios_to_deprecate` does not delete — it flags. SDET confirms deprecation at the human review gate.

## Doc-change-context path
Present `human_feedback_summary` to SDET + PM for confirmation **before** re-triggering `sdet-plan-generator`.

## Validate
`jsonschema.validate(output, schemas/doc_change_context.schema.json)`

## Log
Counts: added items, modified items, removed items, net new scenarios, scenarios to deprecate.
