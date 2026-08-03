---
name: backend-sdet-plan-generator
description: Generate the backend SDET test plan from extracted context files. Three modes: Pass 1 (pre-build, 4 context files), Pass 2 (post-build, adds code_change_context), Re-trigger (doc change, patches affected scenarios). Outputs sdet_plan.json, qa_analysis.md, and sdet_testcases.csv. RFC drives completeness, PRD drives priority, Tasks drive classification, regression drives deduplication.
---

# Backend SDET Plan Generator

Synthesise all extracted context into a structured test plan for human review before code generation begins.

## Model
Reasoning tier — Opus

## Modes of operation

| Mode | Trigger | Inputs | Output scope |
|---|---|---|---|
| Pass 1 | Pre-build, first run | prd + rfc + tasks + regression context | Full scenario set |
| Pass 2 | Post-build, Epic QA Ready | All Pass 1 inputs + `code_change_context` | Delta scenarios only (`is_delta: true`) |
| Re-trigger | Upstream doc changed | Existing `sdet_plan.json` + `doc_change_context` + human feedback | Patch affected scenarios only |

## Three-source model

| Source | Role |
|---|---|
| RFC | Master scenario list — every validation step, flow, edge case, error path = completeness guarantee |
| PRD | Scenario priority and risk weighting (P0/P1/P2); identifies out-of-scope flows |
| Tasks | Scenario classification (test layer) and preconditions for test setup |
| Regression | Deduplication — do not generate scenarios already covered by active (non-legacy, non-flaky) tests |

## Scenario generation rules

**For each RFC validation step:**
- Happy path scenario (step succeeds)
- Failure scenario per error code the step can produce
- Boundary scenarios for quantitative constraints (min, max, edge values)
- Flag-state scenarios for each feature flag affecting the step (on + off)

**For each RFC flow (beyond happy path):**
- One e2e scenario covering the full flow sequence

**For PRD business error scenarios:**
- Ensure each has a corresponding scenario; link to RFC scenario if already covered rather than duplicate

**Pass 2 only (code_change_context):**
- New endpoints → new component test scenarios
- New validation rules not in RFC → generate scenario, flag as RFC gap
- New error mappings → new negative scenarios
- Feature flags → new flag-state scenarios

## Output → sdet_plan.json

Schema root structure:
- `feature_name`, `plan_version`, `generation_mode: pass1|pass2|retrigger`
- `scenarios[]` — each with:
  - `scenario_id`, `name`, `description`
  - `test_layer: component|integration|e2e`
  - `priority: P0|P1|P2`
  - `source: RFC|PRD|CODE_DIFF|RETRIGGER`, `source_ref`
  - `is_delta`, `is_legacy_regression`, `is_dedup` (false at generation; set by dedup-generator)
  - `step_descriptions[]` — `step`, `action`, `curl_reference`, `expected_result`
  - `preconditions[]`, `fixture_ids[]`
  - `tags[]` — `happy_path|negative|boundary|flag_on|flag_off|e2e`
- `coverage_summary` — `total`, `by_layer`, `by_priority`, `rfc_steps_covered`, `rfc_steps_total`, `rfc_gaps[]`

## Output → qa_analysis.md
Human-readable summary for SDET + PM review gate:
- Total scenarios by layer and priority
- RFC coverage % (scenarios / validation steps)
- Gaps (RFC steps with no scenario)
- New vs existing regression coverage
- Risk areas from PRD and covering scenarios
- RFC ↔ Tasks contract conflicts

## Output → sdet_testcases.csv
Flat CSV for BrowserStack upload after human approval.
Columns: `scenario_id, name, test_layer, priority, tags, is_delta, is_legacy_regression`

## Pass 2 rules
- Output only `is_delta: true` scenarios — do not regenerate the full plan.
- Trace each code diff signal to an existing RFC validation step where possible.

## Re-trigger rules
- Read existing `sdet_plan.json` — do not regenerate unaffected scenarios.
- Apply only the delta from `doc_change_context.json`.
- Output only added/modified/deprecated scenarios with `change_reason` field.

## Validate
`jsonschema.validate(output, schemas/sdet_plan.schema.json)`

## Log
Total scenarios, RFC coverage %, gaps count, delta count (Pass 2/Re-trigger).
