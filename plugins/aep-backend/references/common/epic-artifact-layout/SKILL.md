---
name: epic-artifact-layout
description: >
  Canonical on-disk layout for one backend QA epic: plan lane (Phase A–B planning artifacts)
  vs codegen lane (GBT orchestrator runs). All skills resolve plan_dir and codegen_dir from
  epic_root. Downstream handoffs use version-less pointer files per artifact-versioning.
---

# Epic artifact layout (plan lane + codegen lane)

One epic owns a single tree under **`epic_root`**. Default:

```
qa-artifacts/<epic-slug>/          ← epic_root
  orchestrator_run_log.json        ← backend-test-plan-generator run log (epic_root)
  plan/                            ← plan_dir (default write target for Phase A–B)
    prd_context.json               ← pointer (+ prd_context_vN.json history)
    rfc_context.json
    tasks_context.json
    regression_context.json
    sdet_plan.json                 ← SDET approval gate (root status / approved_by / approved_at)
    qa_analysis.md
    sdet_testcases.csv
    automation_plan.json           ← APG output (+ automation_plan_vN.json)
    enriched_automation_plan.json  ← TDI output (+ enriched_automation_plan_vN.json)
    test_data_manifest.json
    run_log.json                   ← TDI action audit (not the codegen run)
  codegen/                         ← codegen_dir
    run.json                       ← automation-plan / codegen review gate (NOT SDET)
    pass1/
      artifacts/
        automation_plan.json       ← copy from plan lane before stage 0 (see below)
        automation_plan_enriched.json
        workspace.json
        …
      logs/
      rejects/
```

## Resolution (every orchestrator / skill entry)

Given `epic_id` or `epic_root`:

| Variable | Default path | Legacy fallback |
|---|---|---|
| `epic_root` | `qa-artifacts/<epic-slug>/` (or caller-supplied absolute path) | — |
| `plan_dir` | `{epic_root}/plan/` when that directory exists **or** when creating a new epic layout | `{epic_root}/` when `sdet_plan.json` lives at epic root (flat legacy) |
| `codegen_dir` | `{epic_root}/codegen/` | `{repo-root}/runs/<epic-slug>/` when present and `{epic_root}/codegen/` absent |

`run_dir` for pass *N* is always **`{codegen_dir}/pass<N>/`**.

Create `plan/` and `codegen/` on first write when the user has not opted into legacy flat layout.

## Pointer files (versioning)

Read **`{plan_dir}/sdet_plan.json`**, **`{plan_dir}/automation_plan.json`**, context pointers, etc.
Never infer the latest `*_vN.json` for skill-to-skill handoff unless the user explicitly passes an
override path for audit/replay. See `references/common/versioning/SKILL.md`.

## Dual human gates (do not merge)

| Gate | File | Approved when | Owns |
|---|---|---|---|
| **SDET** | `{plan_dir}/sdet_plan.json` | Root `status == "approved"` (and not stale: `updated_at` ≤ `approved_at`) | Test scenarios, BrowserStack upload, APG input |
| **Codegen** | `{codegen_dir}/run.json` | `review.status == "approved"` and `review.pass` matches the pass being run | Automation scenarios → GBT codegen / MR |

### `run.json` — `@TestInfo.owner` (test author)

`@TestInfo.owner` must be the **corporate email of whoever created / owns the generated tests**
(TestRail attribution), not a random email copied from an exemplar class.

Optional top-level field (write when approving codegen or before spawning the orchestrator):

```json
"test_author": {
  "email": "first.last@gojek.com",
  "source": "human_prompt | run_json | session"
}
```

- **`email`** — used verbatim on every new `@Test` method's `@TestInfo(owner = …)` for this pass
  (module-specific form: quoted string vs `GojekEngineer.*_EMAIL` vs `TestRailConfig.OWNER_*` —
  see `backend-automation/references/test-annotation-rules.md`).
- **`source`** — audit only; documents how the email was obtained.

**There is no automatic Cursor “user session → email” wire in the pipeline today.** The
orchestrator (or the human driving a one-off codegen spawn) must either put `test_author.email`
in `run.json`, pass `testinfo_owner: <email>` on the spawn prompt, or answer when the
orchestrator asks before stage 9 (`gbt-test-code-generator`).

`qa_analysis.md` feedback drives **review mode** on the test-plan generator; it is **not** a separate
`review/sdet_gate.json` file.

Failing the SDET gate blocks **automation-plan-generator** (and optional `gbt-automation-plan-generator`).
Failing the codegen gate blocks **code-gen-orchestrator stage 0+** — even when SDET is approved.

## Plan → codegen handoff (orchestrator)

Before **stage 0** (`gbt-workspace-prep`), the orchestrator copies the approved automation plan from
the plan lane into the pass artifacts (byte-identical copy, not a rewrite):

1. Source (first hit): `{plan_dir}/enriched_automation_plan.json` → else `{plan_dir}/automation_plan.json`
2. Destination: `{run_dir}/artifacts/automation_plan.json`

Stages that need RFC/tasks/regression/SDET context read them from **`plan_dir`** via absolute paths
in the spawn prompt (no requirement to copy those into `artifacts/` unless a stage spec says so).

## Spawn prompt minimum (GBT subagents)

```
epic_root: <absolute>
plan_dir: <absolute>
codegen_dir: <absolute>
run_dir: <absolute>   # {codegen_dir}/pass<N>/
epic_id: <slug>
pass: <N>
gbt_repo: <absolute worktree after stage 0; omit for APG-only>
run_json: <absolute> # {codegen_dir}/run.json
… plus absolute paths for every artifact this stage reads or writes
```
