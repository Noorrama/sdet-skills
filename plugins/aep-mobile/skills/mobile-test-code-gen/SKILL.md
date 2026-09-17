---
name: mobile-test-code-gen
description: Post-build mobile QA code-generation pipeline. Runs code-change extraction, then impact shortlisting, then test-code generation in sequence (each step needs the prior step's output). Use only when explicitly invoked (e.g. /mobile-test-code-gen) after a build or MR — do not auto-start from casual chat.
disable-model-invocation: true
---

# Mobile Test Code Gen (orchestrator)

This skill is the post-build code-generation entry point. It does **not** pin a
model — it inherits the parent session. The three stages are a **pipeline**, not
parallel: each step needs the prior step's output. Call the subagents
**sequentially**.

`test-data-provisioner` is **not** a user-facing command. `test-code-generator`
spawns it as a subagent when it needs fixture handles — do not call it from this
orchestrator, and do not reimplement provisioning here.

## Preconditions

In the working folder (or from the user), you need:

- An approved plan: `*_automation_plan_generator.json` (preferred) or
  `*sdet_plan.json` / `*SDET_plan.json`
- Something describing what landed: `dev_manifest.json` (preferred) or GitLab MR
  refs for the EPIC
- Optional but useful: `regression_context.json`, `design_context.json`

If no plan file is present, stop and say so — later stages cannot select or generate.

## Pipeline (sequential)

### 1. `code-change-extractor` — `agents/code-change-extractor.md` (sonnet)

Pass the plan path, `dev_manifest.json` and/or MR refs, plugin root, and working
directory. Wait until it finishes.

Expected outputs: `change_context.json`, `compliance.json`.

If it cannot produce `change_context.json`, **stop** — do not invent a change
surface for the next step. Report what failed.

### 2. `impact-shortlister` — `agents/impact-shortlister.md` (sonnet)

Only after step 1. Pass the plan path, `change_context.json` (or the extractor's
stated fallback), `regression_context.json` when present, `compliance.json`,
plugin root, and working directory.

Expected output: `impact_shortlist.json` (sidecar — do not patch the SDET plan).

A `LIMITED` shortlist (empty legacy pool) is still a completed step — continue
to test-code generation.

### 3. `test-code-generator` — `agents/test-code-generator.md` (sonnet)

Only after step 2. Pass the approved SDET plan, `change_context.json`,
`impact_shortlist.json`, `design_context.json` when present, plugin root, and
working directory.

The subagent generates TapMind NLP (via `aep-tapmind:nlp-codegen`) and/or GMT
coded tests. When scenarios need fixtures, **it** spawns `test-data-provisioner`
(`agents/test-data-provisioner.md`) — not this orchestrator.

Expected output: `test-code-generator.json` plus the test files it records.

## Report

After the pipeline (or after a hard stop), list:

| Step | Status | Output |
|---|---|---|
| code-change-extractor | created / failed | `change_context.json`, `compliance.json` |
| impact-shortlister | created / skipped / failed | `impact_shortlist.json` |
| test-code-generator | created / skipped / failed | `test-code-generator.json` + artefact paths |

## Subagent map

| File | Model | Notes |
|---|---|---|
| `agents/code-change-extractor.md` | sonnet | step 1 |
| `agents/impact-shortlister.md` | sonnet | step 2 |
| `agents/test-code-generator.md` | sonnet | step 3 |
| `agents/test-data-provisioner.md` | sonnet | spawned by test-code-generator, not by this skill |
