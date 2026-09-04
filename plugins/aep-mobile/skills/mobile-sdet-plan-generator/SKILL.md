---
name: mobile-sdet-plan-generator
description: Pre-build mobile QA entry point. Runs the aep-mobile dependency preflight, then extracts whichever of PRD / RFC / design / task / regression inputs are present (skipping missing ones) by delegating to extractor subagents, then generates master SDET Plan deliverables in JSON, MD, CSV, and compliance_report formats. Use during implementation planning, when extracting mobile PRD/RFC/design/task/regression context, running aep-mobile-setup, checking aep-mobile dependencies, or asking what is missing after install. MUST run scripts/validate_sdet_deliverables.py (exit 0) before shipping — see workflow.md. Keeps the human review loop in this conversation; delegates GENERATE/SYNC computation to the sdet-plan-runner subagent.
---

# Mobile SDET Plan Generator (orchestrator)

This skill is the pre-build entry point. It does **not** pin a model — it inherits
the parent session. It (1) runs setup, (2) calls the context-extractor subagents
in parallel, then (3) keeps the human-gate loop here and delegates plan
computation to `agents/sdet-plan-runner.md` (`model: opus`) **once per GENERATE**
and **once per SYNC**.

There is no separate `mobile-context-extraction` command. Extractors are
subagents this skill calls.

`aep-mobile-setup` is also not a standalone command. The same preflight runs as
step 0 of every invocation. A setup-only request
(*"Run aep-mobile-setup and tell me what is missing"*, *"check aep-mobile
dependencies"*) still works: run step 0, report the table, **stop**.

Supporting files (read when you need them, not at load):

- `agents/sdet-plan-generator/workflow.md`
- `agents/sdet-plan-generator/anti_patterns.md`
- `agents/sdet-plan-generator/category_catalog.md`
- `agents/sdet-plan-generator/templates/test_cases.csv`
- `agents/sdet-plan-generator/templates/analysis_skeleton.md`

---

## Phase A — Setup + context extraction

Skip this entire phase on **SYNC** (contexts already exist). On **GENERATE**,
run it unless every needed `*_context.json` is already on disk **and** the user
did not ask to re-extract.

### 0. Preflight (always on GENERATE / first run)

Spawn the `aep-mobile-setup` subagent (`agents/setup.md`, model: sonnet) and wait.

- Print its summary table in your reply.
- If the user only asked for setup / missing dependencies: **stop here**.
- python3 / jsonschema failures do **not** block extractors.
- BrowserStack MCP failure: still run prd / rfc / design / task; **skip**
  `regression-extractor` and say so.

### 1. Detect which of the 5 inputs are present

Scan the working folder (and any files the user attached). The five extractors
do not depend on each other's output. Fire only those whose input is present;
skip the rest. If the matching `*_context.json` is already present and the user
did not ask to re-extract, skip that extractor.

| Subagent | Input to look for | Skip when |
|---|---|---|
| `prd-extractor` (`agents/prd-extractor.md`) | PRD text/file — name or heading contains `prd` / `PRD`, or the user pasted a PRD | No PRD is attached or findable |
| `rfc-extractor` (`agents/rfc-extractor.md`) | RFC text/file — name or heading contains `rfc` / `RFC` | No RFC exists (documented as optional) |
| `design-extractor` (`agents/design-extractor.md`) | Figma "Export Design Raw JSON" file (`formatVersion`, large node tree) | No design export is present |
| `task-extractor` (`agents/task-extractor.md`) | Dev task tree JSON (`schemas/task_input.schema.json`) or a raw JIRA export of the milestone → epic → story → task tree | No task/JIRA input is present |
| `regression-extractor` (`agents/regression-extractor.md`) | Enough search metadata to query BrowserStack: `app_id` and/or `feature_key` / `module_namespace` from the user, a PRD/RFC, or an existing context file | Metadata cannot be resolved, **or** step 0 reported BrowserStack MCP down |

Report the detection decision before spawning, e.g.
*"PRD + design present; no RFC; task JSON present. Firing prd, design, task, regression; skipping rfc."*

### 2. Fire matching extractors in PARALLEL

Launch every selected subagent in a **single** turn so they run concurrently.
Pass each: plugin root, exact input path(s), working directory. Do not wait for
one extractor before starting another. Do not synthesise a missing input from
another extractor's output.

### 3. Report what was created

| Extractor | Status | Output file(s) |
|---|---|---|
| setup | ran / issues | (table from step 0) |
| prd-extractor | created / skipped / failed | `prd_context.json` or `prd_context.<app_id>.json` |
| rfc-extractor | created / skipped / failed | `rfc_context.json` or `rfc_context.<app_id>.json` |
| design-extractor | created / skipped / failed | `design_context.json` |
| task-extractor | created / skipped / failed | `task_context.json` |
| regression-extractor | created / skipped / failed | `regression_context.json` |

If the user **only** asked to extract context (not to generate a plan): stop
after this table. Otherwise continue to Phase B.

---

## Phase B — Human-facing plan loop

### 1. Resolve scope in this conversation

Inspect the working folder for extractor outputs (`prd_context.json` /
`prd_context.<app_id>.json`, same pattern for rfc/design, plus `task_context.json`).
Apply the runner's preflight rules 5–7 **here**, because they need the QA:

- **Per-app files** → ask which app if the QA did not say. One app per run.
- **Multiple `team_name` / `milestone` values** on PRD requirements → one
  `AskUserQuestion` per dimension that needs it.
- Headless / no user → pass nothing and let the runner's combined-plan fallback fire.

Do **not** invent a missing `prd_context` / `design_context`. If both are absent
after Phase A, say so and stop — the runner cannot generate a plan from nothing.

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
`<feature_key>_compliance_report.json`. It may invoke `regression-extractor`
internally only if `regression_context.json` is still missing after Phase A.

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
again, repeat this step (one SYNC call each time). Do **not** re-run Phase A on SYNC.

## What you must not do

- Do not extract contexts yourself — that is the extractor subagents.
- Do not generate the plan JSON / analysis / CSV yourself — that is the runner.
- Do not put `model:` on this file.
- Do not call `test-data-provisioner` from this skill — it is a postbuild agent
  spawned by `test-code-generator` only.
- Do not skip the analysis.md review before offering SYNC.

## Subagent map

| File | Model | When |
|---|---|---|
| `agents/setup.md` | sonnet | Phase A step 0 |
| `agents/prd-extractor.md` | sonnet | Phase A, in parallel |
| `agents/rfc-extractor.md` | sonnet | Phase A, in parallel |
| `agents/design-extractor.md` | sonnet | Phase A, in parallel |
| `agents/task-extractor.md` | sonnet | Phase A, in parallel |
| `agents/regression-extractor.md` | sonnet | Phase A, in parallel |
| `agents/sdet-plan-runner.md` | opus | Phase B GENERATE / SYNC |
