---
name: mobile-code-change-extractor
description: Post-build. For an EPIC, reads the dev's structured manifest (preferred) or the raw GitLab MR diff, verifies it against the SDET_PLAN's element_locator_handoff (the expected logical-ID shopping list), and emits two artifacts — change_context.json (the changed surface: screens, logical element_id → real per-platform locators, deep links, API shapes, flags, analytics, app↔API version, reviewer edge cases) and id_compliance.json (the stable-ID gate: did the dev bind every required locator/deep link). App-agnostic; framework/vocabulary come from config. Feeds test-code-generator, not scenario generation.
---

# Mobile Code-Change Extractor (post-build; all 5 GoTo apps)

Runs after the dev shares the build. Its job is to pin the **exact changed surface** and join each
logical `element_id` to its **real per-platform locator**, so NLP/coded automation can bind to it —
and to **gate** that the dev actually implemented what the plan required.

**Two outputs, one skill:**
1. `change_context.json` — what was built (locators, deep links, APIs, flags, analytics, CR risks).
2. `id_compliance.json` — the stable-ID gate (PASS/FAIL + what's missing/renamed).

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
   **intersect with the SDET_PLAN scope** (scenario screens / `affected_modules`) — hunks outside the
   EPIC's scenarios are ignored.
3. **The SDET plan → `element_locator_handoff`** — the **expected** logical-ID shopping list. This is
   the reference the gate checks the built code against. Also read `preconditions_metadata`
   (`target_entry_deeplink`, `active_experiment_flags`) as the **expected** deep links/flags to verify.
   *Filename:* match **`*sdet_plan.json`** — the plan is emitted feature-suffixed as
   `<feature_key>_sdet_plan.json` (e.g. `split_bill_gopay_groups_sdet_plan.json`), so resolve it by
   suffix (or by matching `feature_metadata.feature_key` to the EPIC), never a hardcoded `sdet_plan.json`.
4. **MR review comments** (CR notes) — reviewer edge cases.

## Model
Fast tier — Haiku / Composer 2.5. Locator extraction is deterministic where a manifest exists.

## Produces
### 1. `change_context.json` (→ schemas/change_context.schema.json)
- `app`, `epic_ref`, `merge_requests`/`processed_mrs`, `changed_screens`.
- `screens[]` — per screen: `deep_links` (uri + preconditions + auth_required), `observable_state`, `nav_macro_fallback`.
- `elements[]` — `element_id` → `android_locator` (resource-id) + `ios_locator` (accessibilityId) [+ optional `flutter_locator` = Key/Semantics]; plus `role`, `interaction`, `states`, `change_type` (added/modified/removed), `locator_fallback`, `triggers_api`, `provenance` (mr/file/line).
- `routes`/deeplinks, `api` (endpoint + request/response + error_codes), `flags` (names) + `feature_flags` (name + `state_at_merge`), `analytics`, `app_api_version` (incl. N-1), `review_summary` (approval_state, review_iterations).
- `cr_risks[]` — id, area, category, suggested_test, severity, disposition (becomes-scenario / becomes-bug / acknowledged).
- Routing/readiness (when derivable): `pdg`, `test_repo`, `module_path`, `scoped_to_modules`, `ready_jira_ids`.
- `id_compliance` — inline `{ status, ref }` pointer to the gate result.

### 2. `id_compliance.json` (→ schemas/id_compliance.schema.json)
The stable-ID gate. `status` (PASS/FAIL), `missing_ids`, `renamed_ids` (expected vs found),
`missing_deeplinks`, `reject_codes`. This is what CI blocks on.

## Rules
- **Stable-ID gate:** every element in the SDET_PLAN's `element_locator_handoff` (esp. P0) must have a
  real locator in the built code. Missing → `id_compliance.status = FAIL` + `MISSING_STABLE_ID`
  (never infer brittle XPath/text). Renamed → `RENAMED_ID`.
- **Deep-link/flag gate:** each `target_entry_deeplink` / `active_experiment_flags` the plan declares
  must be present in the code; absent deep link → `MISSING_DEEPLINK` (test falls back to nav-macro).
- **Beyond the shopping list:** the dev often builds elements the design/plan missed (see the plan's
  `cross_stage_gap_analysis` / `testability_feedback`). Capture those in `change_context.elements`
  anyway (with `change_type: added`) so QA can still test them — this is where code-diff fills design gaps.
- If `naming_convention.developer_locator_equals_role` is false, emit the explicit element_id→locator
  map (no 1:1 assumption).
- Screen is derivable from the `<screen_id>.<element_role>` prefix — `changed_screens` falls out of the
  element IDs; no separate mapping needed.

## Guardrails
Report only what the diff/manifest/CR show — never invent a locator. Never emit accounts/tokens/PII.
Output valid JSON only, conforming to `schemas/change_context.schema.json` and
`schemas/id_compliance.schema.json`.
