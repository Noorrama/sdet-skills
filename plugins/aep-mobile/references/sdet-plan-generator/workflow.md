# SDET Plan Generator — Mandatory Workflow

Feature-agnostic procedure for **any** GoTo mobile feature. Details live in `SKILL.md`;
this file is the non-skippable spine every model must follow.

**Token rules:** Do not Read schema JSON or Python validators into context — run them via
Bash. Prefer PDF→text before extractors. GENERATE uses `agents/sdet-plan-runner.md`; SYNC
uses `agents/sdet-plan-sync.md`. Emit CSV via `scripts/plan_to_csv.py` and fill
`automation_steps` via `scripts/fill_automation_steps.py` — do not type those artefacts.

## Phase 0 — Preflight

1. Know required schemas exist under `schemas/` (do not Read them into context; validator enforces).
2. Require `prd_context.json` + `design_context.json` (record gaps if partial)
2a. Load `task_context.json` if present (the PRIMARY DRIVER from `task-extractor`; optional — formerly `plan_context.json`). It supplies the AC coverage floor (`epics[].user_stories[].acceptance_criteria[]`), test hooks (`epics[].test_hooks[]`, `type: deeplink|flag-override|state-injection`, URI in `invoke`), per-task `observable_state`, `flag_keys[]`, and `traceability[]`/`blocking_dependencies[]`. Carry its `blocking_issues[]` (e.g. a story with no ACs) and `testability_gaps[]` straight into the gap analysis.
3. Inherit all upstream `extraction_notes[]`
4. Invoke **regression-extractor** (BrowserStack MCP) — hard stop if MCP unavailable
5. Build checklist:
   ```bash
   python3 scripts/build_coverage_checklist.py \
     --prd prd_context.json \
     [--design design_context.json] \
     [--rfc rfc_context.json] \
     --out coverage_checklist.json
   ```

## Phase 1 — Category gate (Step 0)

- Emit coverage matrix → confirm AUTO + optional extras
- Headless: AUTO only

## Phase 2 — Core scenarios (do this BEFORE negatives)

Order is fixed:

1. Primary happy path **per acceptance criterion** (not one row per req_id)
2. **End-to-end** business flows (`End-to-end:` in title when multi-screen)
3. Alternate valid paths (personas, entry points, tiers)
4. Positive state persistence (nav away/back, refresh)
5. Boundaries, negatives, flags, interruptions

## Phase 3 — Regression dedup

- Match `regression_context` before finalizing titles
- `is_legacy_regression: true` **requires** `existing_case_ref`
- Indirect impacts → analysis.md table only

## Phase 4 — Self-audit (Step 4)

1. Map every checklist item → ≥1 scenario (`requirement_ref`)
2. Navigation audit (4c-nav): deeplink / ui_flow / regression / `[NAVIGATION NOT CONFIRMED]`
3. Balance audit (4c-mix): ≥50% positive OR `under_target — …` after retry
4. Write `<feature_key>_compliance_report.json` (see `schemas/compliance_report.schema.json`)

## Phase 5 — Compliance gate (BLOCKING)

**Do not write deliverable files until this passes:**

```bash
python3 scripts/validate_sdet_deliverables.py \
  --prd prd_context.json \
  --plan <feature_key>_SDET_plan.json \
  --csv <feature_key>_test_cases.csv \
  --analysis <feature_key>_analysis.md \
  [--design design_context.json] \
  [--rfc rfc_context.json] \
  [--task task_context.json] \
  --checklist coverage_checklist.json \
  --compliance <feature_key>_compliance_report.json
```

Fix every error → re-run until exit 0.

## Phase 6 — Write deliverables

Use templates:

- `templates/test_cases.csv` — TMS header (never invent columns)
- `templates/analysis_skeleton.md` — section structure

Outputs:

1. `<feature_key>_SDET_plan.json`
2. `<feature_key>_analysis.md`
3. `<feature_key>_test_cases.csv`
4. `<feature_key>_compliance_report.json` (audit proof; optional for import, required for gate)

## Phase 7 — Schema validate JSON

```bash
python3 -c "import json,jsonschema; jsonschema.validate(
  json.load(open('<feature_key>_SDET_plan.json')),
  json.load(open('schemas/sdet_plan.schema.json')))"
```

## Phase 8 — SYNC only (CSV feedback)

1. Merge CSV → `<feature_key>_SDET_plan.json` (preserve `is_legacy_regression`, `existing_case_ref`, `test_data`, `automation_steps`)
2. **BrowserStack upload:** all rows where `is_legacy_regression: false` (Manual + Automatable) — skip legacy only
3. **Automation plan:** only rows where `execution_mode: Automatable` — Manual excluded even if uploaded to BS
4. Stamp legacy ids from `existing_case_ref`; stamp new ids from upload response
5. Emit `<feature_key>_automation_plan_generator.json` with full scenario carry-over

---

See also: `anti_patterns.md`, `category_catalog.md`, full `agents/sdet-plan-runner.md`.
