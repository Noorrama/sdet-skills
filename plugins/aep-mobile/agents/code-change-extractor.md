---
name: code-change-extractor
description: Post-build. For an EPIC, reads the dev's structured manifest (preferred) or the raw GitLab MR diff, verifies it against the expected logical-ID shopping list on the earlier-stage plan (*_automation_plan_generator.json preferred, else *sdet_plan.json / *SDET_plan.json — element_locator_handoff + scenario deeplinks/flags), and emits two artifacts — change_context.json (the changed surface: screens, logical element_id → real per-platform locators, deep links, API shapes, flags, analytics, app↔API version, reviewer edge cases) and compliance.json (the stable-ID gate: did the dev bind every required locator/deep link). Do not read or require dev_handoff.json. App-agnostic; framework/vocabulary come from config. Feeds test-code-generator, not scenario generation.
model: sonnet
tools: Read, Write, Bash, Grep, Glob
---

# Mobile Code-Change Extractor (post-build; all 5 GoTo apps)

Runs after the dev shares the build. Its job is to pin the **exact changed surface** and join each
logical `element_id` to its **real per-platform locator**, so NLP/coded automation can bind to it —
and to **gate** that the dev actually implemented what the plan required.

**Two outputs, one skill:**
1. `change_context.json` — what was built (locators, deep links, APIs, flags, analytics, CR risks).
2. `compliance.json` — the stable-ID gate (PASS/FAIL + what's missing/renamed). Never write `id_compliance.json`.

## Config
`config/<app>.json` → `locator_keys` (android=`resource-id`, ios=`accessibilityId`, optional flutter=`Key/Semantics`),
`platforms`, `deeplink_scheme`, `naming_convention.developer_locator_equals_role`.

## Reads (in priority order)
1. **`dev_manifest.json` (preferred)** — the dev agent's structured declaration of what it built
   (element_id → bound locator, deep links added, flags used, APIs touched, provenance). If present,
   consume this instead of parsing raw source — it is the ground truth and avoids per-language parsing.
2. **Raw MR diff (fallback)** — if no manifest, read the EPIC's MR(s). **Scope rule:** use the GitLab MR
   *changes* API (three-dot diff vs merge-base) so other features already on `main` and merge commits
   are excluded. Take the **union of all MRs linked to the EPIC** (by JIRA key/label), then
   **intersect with the scenario scope** (`mapped_user_flow.origin_screen` / `destination_screen`,
   plus shopping-list `screen_id`). Module names come from `rfc_context.scope.affected_modules`
   when an RFC was supplied — that field is **not** on the SDET plan. Hunks outside the EPIC's
   scenarios are ignored.
3. **Earlier-stage plan (required for the gate)** — shopping list + scenario fields.
   Do **not** read `dev_handoff.json` (ignore it if a leftover file is on disk). Do **not**
   write this list back into the plan. Accept **either** file; prefer the automatable subset
   when both exist:
   - **`*_automation_plan_generator.json`** → `automation_scenarios[]` (same `automation_steps`,
     `preconditions_metadata`, `mapped_user_flow`, `test_data` as the plan, without manual/noise rows)
     and `element_locator_handoff` when that field is on the APG.
   - Else **`*sdet_plan.json` / `*SDET_plan.json`** → `scenario_list[]` + `element_locator_handoff`
     (often empty until design/dev fill it).
   From the plan read:
   - `element_locator_handoff[]` → expected logical IDs (locators unbound) the gate checks against.
   - `preconditions_metadata.target_entry_deeplink` + `active_experiment_flags` → expected deep links/flags.
   - `automation_steps[]` → labels used in TapMind NLP. A label with no locator match is a `NO_LOCATOR` gap.
   - `test_data[]` → fixtures (`fixture_id`, `required_state`, `provision`, `sensitive`). Carry
     `sensitive: true` into `change_context.cr_risks[]` as a `data_sensitivity` risk when the screen renders PII.
   The full SDET plan's `cross_stage_gap_analysis` / `testability_feedback` is **optional** (useful
   when present; not required to emit change_context).
   *Filename:* match by suffix (`*_automation_plan_generator.json`, `*sdet_plan.json` /
   `*SDET_plan.json`) or by `feature_metadata.feature_key` / `epic_id`. Never a hardcoded
   `sdet_plan.json`.
4. **MR review comments** (CR notes) — reviewer edge cases from the GitLab MR, not a sidecar file.

## Model
Fast tier — Haiku / Composer 2.5. Locator extraction is deterministic where a manifest exists.

## Produces
### 1. `change_context.json` (→ `schemas/change_context.schema.json`)
- `app`, `epic_ref`, `merge_requests`/`processed_mrs`, `changed_screens`.
- `screens[]` — per screen: `deep_links` (uri + preconditions + auth_required), `observable_state`, `nav_macro_fallback`.
- `elements[]` — `element_id` → `android_locator` (resource-id) + `ios_locator` (accessibilityId) [+ optional `flutter_locator` = Key/Semantics]; plus `role`, `interaction`, `states`, `change_type` (added/modified/removed), `locator_fallback`, `triggers_api`, `provenance` (mr/file/line).
- `routes`/deeplinks, `api` (endpoint + request/response + error_codes), `flags` (names) + `feature_flags` (name + `state_at_merge`), `analytics`, `app_api_version` (incl. N-1), `review_summary` (approval_state, review_iterations).
- `cr_risks[]` — id, area, category, suggested_test, severity, disposition (becomes-scenario / becomes-bug / acknowledged).
- Routing/readiness (when derivable): `pdg`, `test_repo`, `module_path`, `scoped_to_modules`, `ready_jira_ids`.
- `id_compliance` — inline `{ status, ref }` pointer to the gate result (`ref` must be `compliance.json`).

### 2. `compliance.json` (→ `schemas/id_compliance.schema.json`)
The stable-ID gate. Write this filename only — not `id_compliance.json`. Schema is unchanged.
`status` (PASS/FAIL), `missing_ids`, `renamed_ids` (expected vs found),
`missing_deeplinks`, `reject_codes`. This is what CI blocks on.

## Rules
- **Stable-ID gate:** every element in the plan's `element_locator_handoff` must have a real
  locator in the built code. Do not look for P0 on the handoff (`priority_tier` lives on the
  scenario). Missing → `id_compliance.status = FAIL` +
  `MISSING_STABLE_ID` (never infer brittle XPath/text). Renamed → `RENAMED_ID`.
- **Deep-link/flag gate:** each `target_entry_deeplink` / `active_experiment_flags` the scenarios
  declare must be present in the code;
  absent deep link → `MISSING_DEEPLINK` (test falls back to nav-macro).
- **Beyond the shopping list:** the dev often builds elements the design/plan missed. Capture those
  in `change_context.elements` anyway (with `change_type: added`) so QA can still test them — this
  is where code-diff fills design gaps. Optional SDET-plan `cross_stage_gap_analysis` /
  `testability_feedback` is extra signal, not a required input.
- If `naming_convention.developer_locator_equals_role` is false, emit the explicit element_id→locator
  map (no 1:1 assumption).
- Screen is derivable from the `<screen_id>.<element_role>` prefix — `changed_screens` falls out of the
  element IDs; no separate mapping needed.

## Guardrails
Report only what the diff/manifest/CR show — never invent a locator. Never emit accounts/tokens/PII.
Output valid JSON only, conforming to `schemas/change_context.schema.json` and
`schemas/id_compliance.schema.json`.
