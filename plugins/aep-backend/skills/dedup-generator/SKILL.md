---
name: backend-dedup-generator
description: Detect and flag duplicates in the SDET scenario plan or automation test methods. Two modes: scenario mode (after sdet-plan-generator, flags duplicate scenarios before human review) and method mode (after automation-plan-generator, flags duplicate test methods before code generation). Never deletes — only flags with is_dedup.
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

**Duplicate:** same input condition → same expected outcome, even if named differently or from different context files.

**Not duplicate:**
- Same endpoint, different conditions (e.g., `amount = 0` vs `amount = -1` are boundary variants)
- Same flow at different test layers (component vs e2e)
- Same condition for different feature flag states

**Action:** Flag all but the most specific / highest priority scenario with `is_dedup: true` and `dedup_reason`.

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
- Near-duplicates (not identical): use `is_near_dedup: true` with explanation. Do not auto-flag as full duplicates.
- If `is_legacy_regression: true` and a new scenario duplicates an active regression, flag the **new** one — not the active regression.

## Output location
Overwrite the input file in place with dedup flags added.

## Validate
- Scenario mode: `jsonschema.validate(output, schemas/sdet_plan.schema.json)`
- Method mode: `jsonschema.validate(output, schemas/automation_plan.schema.json)`

## Log
N scenarios/methods checked; N flagged as dedup; N near-dedup flagged.
