---
name: backend-dedup-generator
description: Detect and flag duplicates in the SDET scenario plan or automation test methods. Two modes: scenario mode (after sdet-plan-generator, flags duplicate scenarios before human review) and method mode (after automation-plan-generator, flags duplicate test methods before code generation). Never deletes — only flags with is_dedup.
disable-model-invocation: true
---

# Backend Dedup Generator

Duplicate detection runs at two distinct pipeline points. Mode determines inputs, scope, and output.

## Model
Fast tier — Haiku

## Modes

| Mode | Runs after | Input | Scope | Flags |
|---|---|---|---|---|
| Scenario | `sdet-plan-generator` | `sdet_plan.json` | Duplicate test scenarios | `is_dedup` on scenario |
| Method | `automation-plan-generator` | `automation_plan.json` | Duplicate test methods | `is_dedup` on method |

## Mode 1: Scenario dedup

This mode compares scenarios **within one plan** against each other. It has no access to existing
coverage and must never claim any: "already covered by a test in the repo" is
`regression_action: "reuse"` plus `existing_case_ref`, written by `sdet-plan-generator` from
`regression_context.json`. Both fields make `automation-plan-generator` skip a scenario, but they
answer different questions. Setting `is_dedup` for an against-repo reason is wrong even when the
conclusion happens to be right, because nothing here can have checked.

### `scenario_group` siblings are never duplicates

**Read `scenario_group` first, before comparing anything.** The plan already records which scenarios
rest on the same Arrange — the same precondition state and the same triggering call, differing only
in the data row exercised. That is the *intended* output of the granularity rule, not an accident.

A group with several members is a matrix, not a duplicate set. In one real plan, `session-invite-attach`
held four scenarios (happy path, retry-after-timeout, concurrent race, timeout configuration) and
`members-invite-base` held four more — 27 of 77 scenarios sat in 8 such groups. Collapsing them
would destroy exactly what the SDET stage was tuned to produce, and the reviewer who approved that
grouping would not see it happen.

So: **two scenarios sharing a `scenario_group` are never flagged `is_dedup`.** They already declare a
shared input condition; what differs is the assertion, which is the point. If two members of one
group genuinely have the same outcome as well, that is an upstream granularity bug — report it in
`dedup_report.groups[]` with `near: true` for a human, do not flag it.

### How to compare — state the operationalization, do not improvise it

"Same input condition" and "same expected outcome" need a defined procedure, or two runs of this
skill disagree on the same plan.

| Half | Compare on | Record in |
|---|---|---|
| Input condition | `scenario_group` when both scenarios carry one; otherwise the tuple `(sorted fixture_ids, entry point from preconditions, feature-flag state from preconditions)` | `dedup_report.condition_key` |
| Expected outcome | the **set** of `step_descriptions[].expected_result`, compared case-insensitively as exact strings | `dedup_report.outcome_key` |

Exact-string comparison is deliberate. Semantic matching sounds better and is not reproducible — it
flags a different set every run, which makes a flag impossible to audit. Two scenarios that differ
only in wording are a *near* duplicate for a human, not an automatic flag.

**Duplicate:** same input condition **and** the same outcome set, even if named differently or drawn
from different context files.

**Not duplicate:**
- Same endpoint, different conditions (e.g., `amount = 0` vs `amount = -1` are boundary variants)
- Same flow at different test layers (component vs e2e)
- Same condition for different feature flag states
- **Same `scenario_group`** — siblings by construction, see above
- Same condition, overlapping-but-not-identical outcomes → `is_near_dedup`, never `is_dedup`

**Action:** Flag all but the canonical scenario with `is_dedup: true` and a `dedup_reason` naming the
canonical id. **Canonical = highest priority (P0 > P1 > P2); on a tie, the one with more
`step_descriptions`; on a further tie, the lowest `scenario_id`.** State the tie-break used in the
reason — "most specific" alone is not decidable by two readers.

**Output:** Updated `sdet_plan.json` with dedup flags + appended `dedup_report` block:
```json
{
  "dedup_report": {
    "mode": "scenario",
    "total_scenarios": 0,
    "flagged_as_dedup": 0,
    "groups": [
      { "canonical_scenario_id": "SCN-001", "duplicates": ["SCN-047"], "reason": "string" }
    ]
  }
}
```

## Mode 2: Method dedup

**Duplicate:** same setup + action + assertion logic, even across different classes; or different classes generated from the same `scenario_id`.

**Not duplicate:**
- Same method in different test layers (component vs integration)
- Same name, different assertion logic

**Action:** Flag duplicate method entries with `is_dedup: true` and `dedup_reason`. Canonical = method in the most appropriate class for the layer.

**Output:** Updated `automation_plan.json` with dedup flags + appended `dedup_report` block:
```json
{
  "dedup_report": {
    "mode": "method",
    "total_methods": 0,
    "flagged_as_dedup": 0,
    "groups": [
      { "canonical_method": "PaymentFlowTest#shouldReturnError", "duplicates": ["PaymentValidationTest#shouldReturnError"], "reason": "string" }
    ]
  }
}
```

## Guardrails (both modes)
- Never delete. Always flag. Human reviewer decides at the next gate.
- Flagged items are hidden in the review UI but remain in the file — reviewer can un-flag.
- Near-duplicates (not identical): use `is_near_dedup: true` with explanation. Do not auto-flag as full duplicates. `automation-plan-generator` does **not** skip on `is_near_dedup`, so a near duplicate still becomes a test method until a reviewer converts it — that asymmetry is deliberate.
- **Never set `is_dedup` for an against-repo reason.** This skill reads only the plan. If two scenarios both look already-covered, that is a `regression_action` question for `sdet-plan-generator`, which has `regression_context.json`; say so in `dedup_report` rather than flagging.
- **`is_legacy_regression` is read-only here.** It is set upstream and must not be changed. Where one scenario carries it and a plan-internal duplicate does not, the one *without* it is the canonical to keep flagged-off — the flagged copy should be the newer, less-traceable one.
- **Every `is_dedup: true` needs a `dedup_reason`.** A bare flag cannot be audited or reversed by a reviewer.

## Approval interaction

Flagging changes what a reviewer signed off: a scenario moving from "build this" to "duplicate, skip"
is a content change, not metadata. If the input plan's root `status` is `approved` and this run flags
**anything**, reset root `status` to `draft` with `approved_by` and `approved_at` null, and say so in
the log. A run that flags nothing leaves the approval untouched.

## Output location
Overwrite the input file in place with dedup flags added. Everything not named in this skill is left
byte-identical — dedup is additive except for the approval reset above.

## Validate
- Scenario mode: `jsonschema.validate(output, schemas/sdet_plan.schema.json)`
- Method mode: `jsonschema.validate(output, schemas/automation_plan.schema.json)`

## Log
N scenarios/methods checked; N flagged as dedup; N near-dedup flagged.
