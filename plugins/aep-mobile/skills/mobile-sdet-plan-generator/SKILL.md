---
name: mobile-sdet-plan-generator
description: Pre-build mobile QA entry point. Extracts PRD/RFC/design/task contexts in parallel, then generates SDET plan deliverables. Regression runs inside the GENERATE runner after PRD/RFC exist. Use during implementation planning. MUST run scripts/validate_sdet_deliverables.py (exit 0) before shipping. Keeps the human review loop here; delegates GENERATE to sdet-plan-runner and SYNC to sdet-plan-sync.
---

# Mobile SDET Plan Generator (orchestrator)

This skill is the pre-build entry point. It does **not** pin a model — it inherits
the parent session. It (1) calls context-extractor subagents in parallel, then
(2) keeps the human-gate loop here and delegates plan computation to
`agents/sdet-plan-runner.md` (**GENERATE**, opus) and `agents/sdet-plan-sync.md`
(**SYNC**, opus) — **one spawn per mode**.

SessionStart already ran `hooks/check-deps.sh` (python3/jsonschema/npx). Do **not**
spawn `aep-mobile-setup` on every run. Only if the user explicitly asks for setup /
missing dependencies: run a short inline check (jsonschema import + note about
BrowserStack MCP) and **stop** — do not pull MCP tool schemas.

**PDFs / screenshots:** Before spawning prd/rfc extractors, if the input is a PDF or
page images, convert to text first (e.g. `pdftotext`, macOS `textutil`, or paste
exported text). Pass the text path to the extractor. Never feed multi-page PDF
screenshots to the model as images when text is available.

**Regression is not parallel.** `regression-extractor` needs `app_id` /
`feature_key` / `module_namespace` from PRD (and RFC `affected_modules` when
present). It stays inside `sdet-plan-runner` Preflight step 9.

Supporting files (read when needed, not at load):

- `references/sdet-plan-generator/workflow.md`
- `references/sdet-plan-generator/anti_patterns.md`
- `references/sdet-plan-generator/category_catalog.md`
- `references/sdet-plan-generator/templates/test_cases.csv`
- `references/sdet-plan-generator/templates/analysis_skeleton.md`

---

## Phase A — Independent context extraction

Skip this entire phase on **SYNC**. On **GENERATE**, run it unless every needed
`*_context.json` is already on disk **and** the user did not ask to re-extract.

### 1. Detect which of the 4 independent inputs are present

Scan the working folder (and attachments). Fire only extractors whose input is
present; skip the rest. If `*_context.json` exists and user did not ask to
re-extract, skip that extractor.

**Do not** spawn `regression-extractor` here.

| Subagent | Input to look for | Skip when |
|---|---|---|
| `prd-extractor` (`agents/prd-extractor.md`) | PRD text/file (prefer text; convert PDF→text first) | No PRD |
| `rfc-extractor` (`agents/rfc-extractor.md`) | RFC text/file (prefer text; convert PDF→text first) | No RFC |
| `design-extractor` (`agents/design-extractor.md`) | Figma "Export Design Raw JSON" | No design export |
| `task-extractor` (`agents/task-extractor.md`) | Dev task tree JSON or JIRA export | No task input |

Report the detection decision before spawning.

### 2. Fire matching extractors in PARALLEL

Launch selected subagents in a **single** turn. Pass plugin root, input path(s),
working directory.

### 3. Report what was created

| Extractor | Status | Output file(s) |
|---|---|---|
| prd-extractor | created / skipped / failed | `prd_context.json` or per-app |
| rfc-extractor | created / skipped / failed | `rfc_context.json` or per-app |
| design-extractor | created / skipped / failed | `design_context.json` |
| task-extractor | created / skipped / failed | `task_context.json` |
| regression-extractor | *(runner only)* | `regression_context.json` in Phase B |

If the user **only** asked to extract context: stop after this table.

---

## Phase B — Human-facing plan loop

### 1. Resolve scope in this conversation

Inspect extractor outputs. Apply preflight rules 5–7 here (per-app / team /
milestone). Do **not** invent missing `prd_context` / `design_context`.

### 2. Category confirmation (this conversation)

Read `references/sdet-plan-generator/category_catalog.md`. Emit Coverage Matrix,
confirm OPTIONAL EXTRAS via `AskUserQuestion`. `functional` / `positive` is never
removable.

### 3. GENERATE — one call

Spawn `sdet-plan-runner` (`agents/sdet-plan-runner.md`) **once** with:

- resolved `app`, `team_name`, `milestone`
- `coverage_categories` = auto ∪ optional extras
- plugin root + working directory

The runner invokes **`regression-extractor`**, then writes plan JSON, analysis.md,
CSV (via `plan_to_csv.py`), and compliance_report. If it hard-stops on BrowserStack,
quote the message and stop.

### 4. Show the plan — wait on the QA

1. Summarise `<feature_key>_analysis.md` (Inputs & Open Points first).
2. Point at `<feature_key>_test_cases.csv` as the editable artefact.
3. Do **not** upload to BrowserStack yet — that is SYNC.

### 5. SYNC — one call per edited CSV

Spawn `sdet-plan-sync` (`agents/sdet-plan-sync.md`) **once** with edited CSV +
existing plan paths. After return, show upload / automation-plan summary. Repeat
per CSV edit. Do **not** re-run Phase A on SYNC.

## What you must not do

- Do not extract contexts yourself — use extractor subagents.
- Do not spawn `regression-extractor` in Phase A.
- Do not generate plan JSON / analysis / CSV yourself.
- Do not put `model:` on this file.
- Do not call `test-data-provisioner` from this skill.
- Do not skip analysis.md review before SYNC.
- Do not spawn setup on every GENERATE.

## Subagent map

| File | Model | When |
|---|---|---|
| `agents/prd-extractor.md` | sonnet | Phase A, parallel |
| `agents/rfc-extractor.md` | sonnet | Phase A, parallel |
| `agents/design-extractor.md` | sonnet | Phase A, parallel |
| `agents/task-extractor.md` | sonnet | Phase A, parallel |
| `agents/sdet-plan-runner.md` | opus | Phase B GENERATE |
| `agents/sdet-plan-sync.md` | opus | Phase B SYNC |
| `agents/regression-extractor.md` | sonnet | Inside GENERATE runner |
| `agents/setup.md` | sonnet | Only if user asks setup-only |
