---
name: code-gen-orchestrator
description: Master orchestrator for the agentic backend-test codegen path — sequences gbt-context-builder (class-level decision maker), the module profile, automation-plan-generator, test-data-generator, gbt-method-decision-maker (method-level decision maker), gbt-test-code-generator, and test-code-validator's fix-and-revalidate loop into one epic run. Use after the SDET plan's human review gate is approved, when you want the whole automation-plan-through-validated-code path run in order instead of invoking each stage skill by hand. Does not re-implement any stage's logic — it sequences the existing skills and enforces the same gates and reject conventions they already have.
version: 1
disable-model-invocation: true
---

# Code Gen Skill (Master Orchestrator)

You are sequencing seven existing, independently-correct skills into one run for one epic. You
own **ordering, handoff, and the validate-fix loop** — you do not re-decide anything a stage
skill already decided. If you find yourself second-guessing a `gbt-context-builder` verdict,
re-picking a test class, or re-judging which method a scenario belongs to, stop: those
decisions belong to `gbt-context-builder` and `gbt-method-decision-maker` respectively, not to
you.

Your output is the same set of artifacts the stages would produce if run by hand, plus one
additional field: `automation_plan.json` carries a merged `test_data_payloads`, which is what
lets `gbt-test-code-generator` read a single input for both routing and fixture data. The
class-level reuse decision (`gbt-context-builder`) and the method-level reuse decision
(`gbt-method-decision-maker`) stay as two separate artifacts, each owned by the skill that
produced it — `gbt-test-code-generator` reads both.

## Absolute rules (violating any is a critical failure)

1. **Never skip the human review gate.** Stop after `sdet-plan-generator` and wait for
   `runs/<epic_id>/run.json` `review.status == "approved"` before running
   `automation-plan-generator`. This is the same gate those skills already enforce
   individually — you must not route around it by, say, calling `gbt-test-code-generator`
   directly with a hand-built plan.
2. **Run stages in this exact order, and stop on the first reject.** Do not run a later stage
   against a partial or rejected earlier artifact — that is how a "graph was down" reject
   becomes indistinguishable from "nothing to cover" several stages downstream.
3. **Do not re-derive a decision a stage skill already made.** `gbt-context-builder`'s
   layer verdicts, `automation-plan-generator`'s routing fields, and
   `gbt-test-code-generator`'s file placement are each that skill's responsibility. Your job
   ends at handing its output to the next stage unmodified, except for the one explicit merge
   in step 4.
4. **The `test_data_payloads` merge is the only artifact transformation you perform.** After
   `test-data-generator` writes `test_data.json`, copy its array verbatim into
   `automation_plan.json` under a new top-level key `test_data_payloads`, then re-write
   `automation_plan.json`. Do not alter any existing field while doing this, and do not drop
   `test_data.json` from disk — it stays as the record of what that stage produced.
5. **The validate-fix loop has a bounded budget, never an open one.** Re-run
   `gbt-test-code-generator`'s fix path only within the existing budgets
   (`GBT_MAX_FIX_RETRIES` for compile/CI-class failures, `GBT_MAX_PROFILE_FIX_RETRIES` for
   profile/rule violations from `test-code-validator`) — these are the same budgets
   `agent/automation_agent.py` / `agent/automation_job.py` already use, not new numbers you
   invent for the orchestrated path.
6. **Reject, don't degrade, at the orchestrator level too.** If any stage rejects, write
   `runs/<epic_id>/pass<N>/rejects/code-gen-skill.json` naming which stage failed and copy
   that stage's own reject payload in verbatim — do not paraphrase or summarize a reject.
7. **Output exactly one JSON run summary at the end.** No prose, no markdown fences outside
   the final summary object.

## Stage order

| # | Stage skill | Reads | Writes | Gate before running |
|---|---|---|---|---|
| 1 | `gbt-context-builder` | `rfc_context.json`, `tasks_context.json`, `regression_context.json`, code graph | `gbt_context.json` | code graph reachable for target module |
| 2 | module profile lookup | `gbt_context.module_profile_skill` | (nothing written — loaded into context) | `gbt_context.json` present |
| 3 | `automation-plan-generator` | `sdet_plan.json`, `gbt_context.json`, `dedup_report.json`, `tasks_context.json` | `automation_plan.json` | **human review gate approved** (`run.json`) |
| 4 | `test-data-generator` | `automation_plan.json`, `rfc_context.json`, `sdet_plan.json` | `test_data.json` | `automation_plan.json` present, non-empty `to_generate` |
| 5 | **merge step (this skill)** | `test_data.json` | `automation_plan.json` (adds `test_data_payloads`) | step 4 succeeded |
| 6 | `gbt-method-decision-maker` | `gbt_context.json`, `automation_plan.json`, `.gbt_repo` candidate test classes | `method_decisions.json` | `automation_plan.json` merged (step 5) |
| 7 | `gbt-test-code-generator` | `automation_plan.json` (merged), `gbt_context.json`, `method_decisions.json`, `run.json` | `.java` files, `codegen_manifest.json` | review gate still approved |
| 8 | `test-code-validator` | generated Java, `rules.json`, `automation_plan.json` | `validation_report.json` | at least one file generated |
| 9 | validate-fix loop | `validation_report.json` errors | re-invokes step 7 on `implicated_files`, then re-runs step 8 | `validation_report.blocked == true` and retry budget remains |

`sdet-plan-generator` (and the extractors before it) are **not** run by this skill — it starts
from an already-approved `sdet_plan.json`. Wire it in only if the epic has no plan yet.

## The validate-fix loop, precisely

1. Run `test-code-validator`. If `passed: true`, stop — done.
2. If `blocked: true` and the profile-fix budget is not exhausted, send
   `validation_report.implicated_files` (already capped and ordered by the validator) back to
   `gbt-test-code-generator`'s fix path with the specific violations, decrement the budget,
   and re-run only those files. Do not re-run `gbt-method-decision-maker` for a fix pass — its
   verdict was about placement, not about the rule violations this loop is fixing.
3. Re-run `test-code-validator` on the updated files. Go to 1.
4. If the budget is exhausted and errors remain, **stop the loop** (do not loop indefinitely),
   write the remaining `validation_report` findings into `codegen_manifest.todos[]` as
   reviewer TODOs, and record `fix_budget_exhausted: true` in the final run summary. This is a
   legitimate stopping condition, not a reject — partially-fixed generated code with clear
   TODOs is still useful to a reviewer.

## Definition of Ready (DoR)

- `runs/<epic_id>/pass1/sdet_plan.json` exists and its pass has an approved `run.json` gate,
  or the caller explicitly asks this skill to run `sdet-plan-generator` first.
- The code graph is reachable for the target module (checked again at step 1 — do not trust a
  prior run's liveness).
- `.gbt_repo` exists and resolves the target module.

## Reject if

Any individual stage's own reject conditions fire — see that stage's `SKILL.md`. This skill
adds exactly one orchestration-level reject:

| Reason | Detail |
|---|---|
| `stage_order_violated` | A later stage was about to run without its declared upstream artifact present — refuse rather than run against a stale or missing file |
| `review_gate_not_approved` | Attempted to run stage 3 or later before `run.json.review.status == "approved"` |
| `fix_loop_would_be_unbounded` | The validate-fix loop was about to run without a tracked remaining budget |

On reject, write `runs/<epic_id>/pass<N>/rejects/code-gen-skill.json`:

```json
{"stage": "code-gen-skill", "failed_at": "<stage-name>",
 "upstream_reject": {"...": "verbatim contents of that stage's own reject file"},
 "remediation": "<the exact command or stage to re-run>"}
```

## OUTPUT — return ONLY a single valid JSON object

Written to `runs/<epic_id>/pass1/artifacts/code_gen_run.json` (or `pass2/` on Pass 2), as the
one summary of the whole orchestrated run — every artifact it references was written by the
stage skill responsible for it, not by this skill.

```json
{
  "epic_id": "EPIC-1122",
  "pass": 1,
  "started_at": "<ISO-8601>",
  "finished_at": "<ISO-8601>",
  "stages": [
    {"stage": "gbt-context-builder", "status": "completed", "artifact": "runs/EPIC-1122/pass1/gbt_context.json"},
    {"stage": "module_profile_lookup", "status": "completed", "skill": "gbt-module-driver-platform"},
    {"stage": "automation-plan-generator", "status": "completed", "artifact": "runs/EPIC-1122/pass1/artifacts/automation_plan.json"},
    {"stage": "test-data-generator", "status": "completed", "artifact": "runs/EPIC-1122/pass1/artifacts/test_data.json"},
    {"stage": "merge_test_data_into_plan", "status": "completed", "detail": "automation_plan.test_data_payloads set from test_data.json, 5 entries"},
    {"stage": "gbt-method-decision-maker", "status": "completed", "artifact": "runs/EPIC-1122/pass1/artifacts/method_decisions.json", "detail": "1 exact_match, 1 closest_match_modify, 1 data_provider_new_row, 2 no_match"},
    {"stage": "gbt-test-code-generator", "status": "completed", "artifact": "runs/EPIC-1122/pass1/artifacts/codegen_manifest.json"},
    {"stage": "test-code-validator", "status": "completed_after_fix", "attempts": 2, "artifact": "runs/EPIC-1122/pass1/artifacts/validation_report.json"}
  ],
  "fix_loop": {"attempts_used": 1, "budget": 2, "fix_budget_exhausted": false},
  "final_validation": {"passed": true, "counts": {"error": 0, "warning": 1}},
  "files_written": {"created": 2, "updated": 3},
  "blocked": false,
  "reviewer_todos": [],
  "notes": "<one-paragraph summary of what ran, what was reused vs created, and anything a reviewer should check first>"
}
```

Use `""` for a missing string, `[]` for a missing list. Never use `null`.

## What this skill does not do

- **It does not decide test placement, class names, or reuse-vs-create.** That is
  `gbt-context-builder` end to end — see its `reference.md` for the ranking rule this skill
  relies on but never overrides.
- **It does not decide which method a scenario belongs to.** That is
  `gbt-method-decision-maker` end to end — this skill only sequences it between the plan
  merge and codegen, and never re-evaluates an `exact_match`/`closest_match_modify`/`no_match`
  verdict.
- **It does not write test scenarios.** `sdet-plan-generator` (and the human review gate) own
  that; this skill starts from an already-approved plan.
- **It does not add a new fix-retry mechanism.** It reuses the existing budgets and calls the
  existing `gbt-build-fix` / profile-fix paths — it only sequences when they run.
- **It does not create an MR or run tests.** Same boundary as `gbt-test-code-generator`.
