---
name: mobile-test-code-gen
description: Post-build mobile QA code-generation pipeline. Runs code-change extraction, impact shortlisting, backend test-data identification (when needed), TapMind NLP codegen, then GMT coded generation. Use only when explicitly invoked (e.g. /mobile-test-code-gen) after a build or MR — do not auto-start from casual chat.
disable-model-invocation: true
---

# Mobile Test Code Gen (orchestrator)

This skill is the post-build code-generation entry point. It does **not** pin a
model — it inherits the parent session. Stages are a **pipeline**, not parallel:
each step needs the prior step's outputs where noted. Call subagents **sequentially**.

`test-data-provisioner` is **not** a user-facing command. **`test-code-generator`**
spawns it when GMT scenarios need fixture handles — do not call it from this
orchestrator for identification or NLP.

## Prerequisites

**Plugins:** **`qa-mobile-toolkit`** (this pipeline). Step 3 requires **`qa-backend-toolkit`**
installed so the **`backend-test-data-identification`** skill is available (TDI team maintains it;
mobile does not fork identification).

**TestBuddy MCP:** required for step 3 when enrichment is missing.

**TapMind MCP + device:** only if step 4 runs in **device-pioneer** mode (QA choice inside nlp-codegen).

## Working-folder artifacts

Resolve the **plan** (first match unless the user names a file):

| Priority | File | Notes |
|---|---|---|
| 1 | `*enriched_automation_plan.json` | Skip step 3 |
| 2 | `*_automation_plan_generator.json` | Step 3 input if not enriched |
| 3 | `*sdet_plan.json` / `*_SDET_plan.json` | Step 3 input if not enriched |

Also required / expected:

| File | Step | Required? |
|---|---|---|
| `dev_manifest.json` and/or GitLab MR refs | 1 | One of manifest or MR for change surface |
| `change_context.json` | 2+ | **Required** after step 1 (hard stop if missing) |
| `compliance.json` | 2 | From step 1 |
| `regression_context.json` | 2 | Optional |
| `impact_shortlist.json` | 4–5 | Optional filter |
| `design_context.json` | 4–5 | Optional |

If no plan file is present, **stop** before step 1.

## Pipeline (sequential)

### 1. `code-change-extractor` — `agents/code-change-extractor.md`

Pass plan path, `dev_manifest.json` and/or MR refs, plugin root, working directory.

**Outputs:** `change_context.json`, `compliance.json`. If `change_context.json` is missing, **stop**.

### 2. `impact-shortlister` — `agents/impact-shortlister.md`

After step 1. Pass plan path, `change_context.json`, optional `regression_context.json`,
`compliance.json`, plugin root, working directory.

**Output:** `impact_shortlist.json` (sidecar). Empty/LIMITED shortlist is still success — continue.

### 3. `backend-test-data-identification` — **qa-backend-toolkit skill** (sub-agent)

**Skip** when `*enriched_automation_plan.json` already exists in the working folder.

Otherwise, after step 2:

- Spawn a sub-agent that loads and follows **`backend-test-data-identification`** from
  **qa-backend-toolkit** (`skills/backend-test-data-identification/SKILL.md`).
- Pass the resolved APG or SDET plan path and working folder as **`plan_dir`** (flat folder =
  legacy layout per epic-artifact-layout).
- **Do not** reimplement catalog calls in mobile agents.

**Outputs:** `enriched_automation_plan.json` (+ `test_data_manifest.json`) **next to the input plan**.
On abort (TestBuddy down, unparseable plan): **stop** — do not run nlp-codegen.

### 4. `nlp-codegen` — `agents/nlp-codegen.md`

After step 3 (or when enriched plan already present). Pass working directory, paths to
`change_context.json`, `impact_shortlist.json`, `design_context.json` when present, plugin root.

Runs **`skills/nlp-codegen/SKILL.md`** for all **`TAPMIND_NLP`** scenarios (kb-only / reuse-pioneer /
device-pioneer per skill §0). Writes Java into `tapmind-mobile-tests` and opens MR when auth allows.

Does **not** replace step 3 — it consumes **`enriched_automation_plan.json`**.

### 5. `test-code-generator` — `agents/test-code-generator.md`

After step 4 (or in parallel only when the plan has **no** `TAPMIND_NLP` scenarios). **GMT_JAVA only**
in this agent — do not hand TapMind NLP to step 5.

Pass SDET/APG plan, `change_context.json`, shortlist, design context, plugin root, working directory.

**Output:** `test-code-generator.json` + GMT artifacts; spawns **`test-data-provisioner`** per scenario.

## Report

| Step | Status | Output |
|---|---|---|
| code-change-extractor | created / failed | `change_context.json`, `compliance.json` |
| impact-shortlister | created / skipped / failed | `impact_shortlist.json` |
| backend-test-data-identification | created / skipped / failed | `enriched_automation_plan.json` |
| nlp-codegen | created / skipped / failed | tapmind-mobile-tests + MR; optional ledger |
| test-code-generator | created / skipped / failed | `test-code-generator.json` + GMT paths |

## Subagent map

| File | Notes |
|---|---|
| `agents/code-change-extractor.md` | step 1 |
| `agents/impact-shortlister.md` | step 2 |
| qa-backend **`backend-test-data-identification`** skill | step 3 (external plugin) |
| `agents/nlp-codegen.md` | step 4 |
| `agents/test-code-generator.md` | step 5 — GMT only |
| `agents/test-data-provisioner.md` | spawned by step 5 only |
