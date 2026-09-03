---
name: mobile-context-extraction
description: Pre-build mobile QA context extraction. Runs the aep-mobile dependency preflight first, then extracts whichever of PRD / RFC / design / task / regression inputs are present in the working folder into their context JSON files (skips extractors whose input is missing). Use when extracting mobile PRD/RFC/design/task/regression context, running aep-mobile-setup, checking aep-mobile dependencies, or asking what is missing after install.
---

# Mobile Context Extraction (orchestrator)

This skill is the pre-build entry point. It does **not** extract anything itself and does
**not** pin a model — it inherits the parent session. Extraction work is delegated to
model-pinned subagents under `agents/`.

`aep-mobile-setup` is no longer a standalone command. The same preflight runs automatically
as step 0 of every invocation. A setup-only request
(*"Run aep-mobile-setup and tell me what is missing"*, *"check aep-mobile dependencies"*)
still works: run step 0, report the table, **stop** — do not fire extractors.

## Step 0 — Preflight (always)

Spawn the `aep-mobile-setup` subagent (`agents/setup.md`, model: sonnet) and wait for it.

- Print its summary table in your reply.
- If the user only asked for setup / missing dependencies: **stop here**.
- python3 / jsonschema failures do **not** block extractors (each extractor already
  records `WORTH_CHECKING` and continues).
- BrowserStack MCP failure: still run prd / rfc / design / task; **skip**
  `regression-extractor` and say so. Regression and SDET-plan upload hard-stop without it.

## Step 1 — Detect which of the 5 inputs are present

Scan the working folder (and any files the user attached). The five extractors do not
depend on each other's output — they read different inputs. Fire only those whose input
is present; skip the rest (same "skip if not present" rules each extractor already
documents).

| Subagent | Input to look for | Skip when |
|---|---|---|
| `prd-extractor` (`agents/prd-extractor.md`) | PRD text/file — name or heading contains `prd` / `PRD`, or the user pasted a PRD | No PRD is attached or findable |
| `rfc-extractor` (`agents/rfc-extractor.md`) | RFC text/file — name or heading contains `rfc` / `RFC` | No RFC exists (documented as optional) |
| `design-extractor` (`agents/design-extractor.md`) | Figma "Export Design Raw JSON" file (`formatVersion`, large node tree) | No design export is present |
| `task-extractor` (`agents/task-extractor.md`) | Dev task tree JSON (`schemas/task_input.schema.json`) or a raw JIRA export of the milestone → epic → story → task tree | No task/JIRA input is present |
| `regression-extractor` (`agents/regression-extractor.md`) | Enough search metadata to query BrowserStack: `app_id` and/or `feature_key` / `module_namespace` from the user, a PRD/RFC, or an existing context file | Metadata cannot be resolved, **or** step 0 reported BrowserStack MCP down |

Report the detection decision before spawning, e.g.
*"PRD + design present; no RFC; task JSON present; BrowserStack metadata from PRD app=gojek-consumer. Firing prd, design, task, regression; skipping rfc."*

## Step 2 — Fire matching extractors in PARALLEL

Launch every selected subagent in a **single** turn so they run concurrently. Each
subagent starts with a clean context — pass it:

- the plugin root (so `config/`, `schemas/`, `scripts/` resolve)
- the exact input path(s) you detected
- the working directory to write into

Do not wait for one extractor before starting another. Do not synthesise a missing
input from another extractor's output.

## Step 3 — Report what was created

After all spawned subagents finish, list each extractor:

| Extractor | Status | Output file(s) |
|---|---|---|
| setup | ran / issues | (table from step 0) |
| prd-extractor | created / skipped / failed | `prd_context.json` or `prd_context.<app_id>.json` |
| rfc-extractor | created / skipped / failed | `rfc_context.json` or `rfc_context.<app_id>.json` |
| design-extractor | created / skipped / failed | `design_context.json` |
| task-extractor | created / skipped / failed | `task_context.json` |
| regression-extractor | created / skipped / failed | `regression_context.json` |

Quote any hard-gate stop (BrowserStack) verbatim from the subagent. Then point the
user at `mobile-sdet-plan-generator` for the next pipeline stage.

## Subagent map

| File | Model | Was |
|---|---|---|
| `agents/setup.md` | sonnet | `skills/setup` (`aep-mobile-setup`) |
| `agents/prd-extractor.md` | sonnet | `skills/prd-extractor` |
| `agents/rfc-extractor.md` | sonnet | `skills/rfc-extractor` |
| `agents/design-extractor.md` | sonnet | `skills/design-extractor` |
| `agents/task-extractor.md` | sonnet | `skills/task-extractor` |
| `agents/regression-extractor.md` | sonnet | `skills/regression-extractor` |
