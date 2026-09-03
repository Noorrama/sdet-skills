---
name: mobile-sdet-plan-generator
description: Ingests pre-build contexts (plan, prd, design, rfc) to perform cross-stage gap analysis and generate master SDET Plan deliverables in JSON, MD, CSV, and compliance_report formats. Use during implementation planning. MUST run scripts/validate_sdet_deliverables.py (exit 0) before shipping — see workflow.md. Keeps the human review loop in this conversation; delegates GENERATE/SYNC computation to the sdet-plan-runner subagent.
---

# Mobile SDET Plan Generator (orchestrator)

This skill is the interactive entry point for the SDET plan. It does **not** pin a
model — it inherits the parent session. The human-gate loop (disambiguation, showing
`analysis.md`, taking CSV edits, re-sync) **must** run here, in the main conversation.
The actual plan-generation computation lives in `agents/sdet-plan-runner.md`
(`model: opus`) and is called **once per GENERATE** and **once per SYNC**.

Supporting files (read when you need them, not at load):

- `agents/sdet-plan-generator/workflow.md`
- `agents/sdet-plan-generator/anti_patterns.md`
- `agents/sdet-plan-generator/category_catalog.md`
- `agents/sdet-plan-generator/templates/test_cases.csv`
- `agents/sdet-plan-generator/templates/analysis_skeleton.md`

## Human-facing loop

### 1. Resolve scope in this conversation

Inspect the working folder for extractor outputs (`prd_context.json` /
`prd_context.<app_id>.json`, same pattern for rfc/design, plus `task_context.json`).
Apply the runner's preflight rules 5–7 **here**, because they need the QA:

- **Per-app files** → ask which app if the QA did not say. One app per run.
- **Multiple `team_name` / `milestone` values** on PRD requirements → one
  `AskUserQuestion` per dimension that needs it.
- Headless / no user → pass nothing and let the runner's combined-plan fallback fire.

Do **not** invent a missing `prd_context` / `design_context`. If both are absent, say
so and stop — the runner cannot generate a plan from nothing.

### 2. Category confirmation (this conversation)

Read `agents/sdet-plan-generator/category_catalog.md`. From the present contexts,
emit the Coverage Matrix (`Category | Tier | Why`) plus the projected-balance line,
then confirm OPTIONAL EXTRAS via `AskUserQuestion` (multiSelect) per the runner's
Step 0. Headless → AUTO set only.

`functional` / `positive` is never removable.

### 3. GENERATE — one call

Spawn `sdet-plan-runner` (`agents/sdet-plan-runner.md`) **once** with:

- `mode: GENERATE`
- resolved `app`, `team_name`, `milestone` (when chosen)
- `coverage_categories` = auto_selected ∪ optional_extras_selected
- plugin root + working directory

Wait for it. The runner writes `<feature_key>_SDET_plan.json`,
`<feature_key>_analysis.md`, `<feature_key>_test_cases.csv`,
`<feature_key>_compliance_report.json` (and invokes `regression-extractor` internally
if `regression_context.json` is not already on disk).

If the runner hard-stops on BrowserStack MCP, quote its message and stop — do not
invent regression coverage.

### 4. Show the plan — wait on the QA

This is the mandatory human gate. In this conversation:

1. Open / summarise `<feature_key>_analysis.md` (Inputs & Open Points first).
2. Point at `<feature_key>_test_cases.csv` as the editable artefact.
3. Tell the QA they can edit the CSV (add/remove/change rows) and hand it back.
4. **Do not** upload to BrowserStack or emit the automation plan yet — that is SYNC.

### 5. SYNC — one call per edited CSV

When the QA provides a modified `<feature_key>_test_cases.csv`, spawn
`sdet-plan-runner` **once** with:

- `mode: SYNC`
- the same resolved scope as GENERATE
- paths to the edited CSV and existing `<feature_key>_SDET_plan.json`

The runner merges edits, uploads new (non-legacy) cases to BrowserStack, stamps
ids, and emits `<feature_key>_automation_plan_generator.json`.

After it returns: show the upload / automation-plan summary. If they edit the CSV
again, repeat this step (one SYNC call each time).

## What you must not do

- Do not generate the plan JSON / analysis / CSV yourself — that is the runner.
- Do not put `model:` on this file.
- Do not fold `test-data-provisioner` into this skill.
- Do not skip the analysis.md review before offering SYNC.
