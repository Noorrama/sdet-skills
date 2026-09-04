---
name: impact-shortlister
description: Post-build test selection. Takes legacy regression rows (is_legacy_regression true + existing_case_ref) from the SDET plan or *_automation_plan_generator.json, enriched from regression_context when available, and narrows them to the cases the merged code actually impacts by matching the change surface (change_context.json / dev_manifest.json / GitLab MR bootstrap) against each candidate's title/steps. Deterministic tier is pure evidence matching — no scoring service. Remainder gets one agent judgment pass. Emits impact_shortlist.json as a sidecar — does not mutate the SDET plan. App-agnostic; selects, never generates.
model: sonnet
tools: Read, Write, Bash, Grep, Glob
---

# Mobile Impact Shortlister (post-build)

The pre-build plan marks **legacy regression candidates** (`is_legacy_regression: true` +
`existing_case_ref`). This skill answers the post-build question: **given the code that actually
merged, which of those legacy cases do we still need to run?**

```
pre-build                                     post-build (this skill)
sdet-plan-generator  ──► SDET_PLAN ──────────┐
                 and/or                      ├──► impact-shortlister ──► impact_shortlist.json
             *_automation_plan_generator.json│         (sidecar only — do not patch their plan)
regression-extractor ──► regression_context ─┤
  (enrichment only)                            │
code-change-extractor ─► change_context ─────┘
  OR GitLab MR bootstrap (testing / fallback)
```

**Candidate pool (strict):** unique `existing_case_ref` from plan rows where
`is_legacy_regression: true`. `regression_context.json` enriches title/steps/tapmind_steps by case
id — it does **not** expand the pool. Partial-overlap refs (`is_legacy_regression: false` but
`existing_case_ref` set) are out of scope here.

**It selects; it never generates.** No scoring service. No auto-MUST_RUN from plan linkage alone —
`plan_scenario_refs` is traceability only.

---

## Reads

| Input | Required | Source | What it contributes |
|---|---|---|---|
| `*sdet_plan.json` / `*SDET_plan.json` **or** `*_automation_plan_generator.json` | **one of them** | `sdet-plan-generator` | Legacy pool via `is_legacy_regression: true` + `existing_case_ref`; `new_scenarios_to_run` from non-legacy rows. APG uses `automation_scenarios[]` (automatable subset); the SDET plan uses `scenario_list[]` (full pool, including manual). Either is valid — join provenance lives on `impact_shortlist.json.inputs`. |
| `regression_context.json` | strongly | `regression-extractor` | Enriches legacy candidates (title, steps, tapmind_steps, source_module). |
| `change_context.json` | preferred | `code-change-extractor` | Change surface: files, screens, modules, flags, APIs, elements, CR risks. |
| `dev_manifest.json` | fallback | dev agent | Same surface when change_context isn't ready. |
| GitLab MR **changes** API | bootstrap | GitLab | Testing/fallback: union `changed_files` across EPIC MRs → bootstrap change surface. |
| `compliance.json` | optional | `code-change-extractor` | FAIL widens agent judgments (see guardrails). Accept leftover `id_compliance.json` as the same file. |

---

## Workflow

### 1. Build the change surface
From `change_context.json` (preferred). Union `elements[].provenance.file` + top-level
`changed_files` when present (MR bootstrap). Carry screens, modules, flags, APIs, CR risks.

**MR bootstrap (when code-change-extractor hasn't run):** fetch each EPIC MR's changed-file list
via GitLab API; set `bootstrap_from_mr: true`. Script infers `changed_modules` and screen ids from
paths (`ProfileContainerFragment` → `PROFILE_CONTAINER`, etc.).

### 2. Run the deterministic join
```
python3 scripts/shortlist_join.py draft \
  --plan <feature>_sdet_plan.json \
  # or --plan <feature>_automation_plan_generator.json \
  [--regression regression_context.json] \
  --change change_context.json \
  --out impact_shortlist.draft.json
```

Deterministic reason codes (any hit → `MUST_RUN`):
- `MODULE_TOUCHED` — candidate `source_module` in `changed_modules`
- `SCREEN_TOUCHED` — changed screen id in title/steps
- `LOCATOR_CHANGED` — modified/removed element token in title/steps
- `FLAG_TOUCHED` / `API_CONTRACT_CHANGED` / `CR_RISK`
- `FILE_PATH_TOUCHED` — loyalty/profile/catalogue/etc. path tokens match title/steps (MR bootstrap)

**Not a reason code:** plan scenario link — traceability only, never auto-MUST_RUN.

### 3. Judge the review_queue
For each remaining candidate, read title/steps vs. the change surface. Use plan `scope_summary`
when the SDET plan has it; APG does not — judge from scenario `description` /
`mapped_user_flow` instead:
- Plausibly exercises changed behavior → `SHOULD_RUN`, `AGENT_JUDGED_RELEVANT` + one-sentence explanation
- Tenuous → `OPTIONAL`
- No link → `deselected_tests`, `NO_IMPACT_SIGNAL` + explanation

### 4. Compose the sidecar — do not mutate their SDET plan
Merge draft `must_run` with judgments; validate against `schemas/impact_shortlist.schema.json`.

**One required artifact:** `impact_shortlist.json` — why each case was chosen (`reason_codes`,
`evidence`, `explanation`, `deselected_tests`) plus `inputs` pointing at the plan/APG file used.
Downstream runners and the demo read this.

Do **not** write `impact_shortlist` onto the other team's SDET plan (`additionalProperties: false`
on their schema would reject it). Join is the sidecar `inputs` pointer. `shortlist_join.py
patch-plan` stays in the script for copies we own; never run it on their plan.

---

## Guardrails

- **`MUST_RUN` is never demoted.** Evidence-backed only.
- **Legacy pool empty → `extraction_status: LIMITED`.** Zero `is_legacy_regression: true` rows is a
  plan gap, not "nothing impacted."
- **`id_compliance.status == FAIL` widens** — soft deselections become `OPTIONAL`.
- **Every deselection is auditable** in `deselected_tests`.
- **New (non-legacy) scenarios always run** — listed in `new_scenarios_to_run`.
- **No hallucinated evidence.**

See `examples/pam_feature/IMPACT_SHORTLISTER_REPORT.md` for a worked PAM validation. Join explainer: `agents-claude/impact-shortlister/SHORTLIST_JOIN_EXPLAINER.md`.
