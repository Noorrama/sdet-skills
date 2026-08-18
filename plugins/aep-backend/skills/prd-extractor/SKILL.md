---
name: backend-prd-extractor
description: Extract product intent from a backend PRD into prd_context.json. Maps user stories, acceptance criteria, risk areas, business error scenarios, and SLA expectations for the backend QA pipeline.
---

# Backend PRD Extractor

Convert PRD text into a schema-compliant `prd_context.json` for the backend SDET pipeline. Feeds `sdet-plan-generator` with scenario priority, risk weighting, and business error scenarios.

## Reads
PRD document (path passed as argument, or latest PRD MD/Confluence export in the feature folder)

## Model
Fast tier — Haiku

## What to extract

| Section | Details |
|---|---|
| User stories | *As a [persona], I want [goal], so that [benefit].* Include story ID if present. |
| Acceptance criteria | Per story — mark each as `functional` or `non_functional` |
| Risk areas | Flows flagged high-value/high-risk; infer from "critical", "must not", "guaranteed" |
| Business error scenarios | User-facing failure descriptions, not technical errors |
| SLA / NFR | Latency targets, throughput, uptime, retry limits, timeouts |
| Out of scope | Explicit exclusions — prevents unnecessary scenario generation |

## Output → prd_context.json

Schema root structure:
- `feature_name` (string)
- `prd_version` (string or null)
- `user_stories` — each with `id`, `persona`, `goal`, `benefit`, `acceptance_criteria[]`
  - Each criterion: `id`, `description`, `type: functional|non_functional`
- `risk_areas` — each with `flow`, `reason`, `priority: P0|P1|P2`
- `business_error_scenarios` — each with `trigger`, `user_facing_message`, `story_ref`
- `sla` — `p99_latency_ms`, `throughput_rps`, `uptime_percent`, `notes` (null if unspecified)
- `out_of_scope` (array of strings)

## Guardrails
- Extract only what is stated. Note ambiguities in a `notes` field — do not guess.
- Every acceptance criterion must trace to a user story.
- If SLA is not mentioned, set fields to `null` — do not invent numbers.
- `out_of_scope` is as important as in-scope — missing it causes unnecessary test generation.
- Output valid JSON only.

## Validate
`jsonschema.validate(output, schemas/prd_context.schema.json)`

## Log
One-line summary: stories extracted, criteria, risk areas, error scenarios.
