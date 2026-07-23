---
name: mobile-prd-extractor
description: Extract structured PRD context for mobile QA into prd_context.json. Maps PRD requirements, module namespaces, business requirements, boundary conditions, rollout guidance, and feature flags to the schema used by the mobile QA pipeline.
---

# Mobile PRD Extractor (all 5 GoTo apps)

Convert PRD text into a schema-compliant `prd_context.json` for mobile QA. The extractor normalises explicit requirements and surfaces any missing or ambiguous information.

## Config
Read `config/<app>.json` for `app_id`. Set `prd_context.app = app_id`. The skill is otherwise app-agnostic.

## Reads
PRD text (Lark/Confluence)

## Model
Fast tier — Haiku / Composer 2.5. Escalate to a higher reasoning model only if the PRD is long or ambiguous.

## Output schema (→ prd_context.schema.json)
The output must conform to `schemas/prd_context.schema.json` with the following root structure:

- `app` (string, from config)
- `feature_key` (string)
- `module_namespace` (array of strings)
- `business_requirements` (array)

### `business_requirements`
Each item must include:
- `req_id` (string)
- `target_module` (string)
- `user_story` (string)

Optional fields for each business requirement:
- `milestone` (string)
- `context_screen` (string)
- `expected_ui_copy` (array of objects with `screen` and `ui_copy`)
- `target_personas` (array of objects with `type` and optional `prerequisites`)

### Optional root fields
- `boundary_conditions` (array of objects with `req_id`, `edge_case_description`, `proposed_default`)
- `applicable_countries` (array of strings)
- `applicable_platforms` (array of strings)
- `applicable_service_types` (array of strings)
- `out_of_scope_module` (array of strings)
- `rollout_plan` (object with `user_segment` and `timeline`)
- `feature_flags` (array of strings)

## Guardrails
- Do not invent values. If something is unspecified, leave it out or note it in the PRD extraction process.
- Output valid JSON only.
- Do not add fields that are not allowed by `prd_context.schema.json`.

## Validate
`jsonschema.validate(output, schemas/prd_context.schema.json)`
