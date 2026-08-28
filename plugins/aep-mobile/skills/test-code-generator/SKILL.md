---
name: mobile-test-code-generator
description: The Code-Generation-phase QA output. From the approved SDET_PLAN + post-build change_context, generates mobile automation — TapMind NLP steps (primary) and GMT (Appium+TestNG Java) coded tests (where needed) — for both Android & iOS, wired to test data, and emits test-code-generator.json (the traceable ledger with BrowserStack IDs, validation, and deferred scenarios). App-agnostic; grounds on the GMT coded repo. In Phase B this becomes the self-healing Frontend Test-Code-Gen agent.
---

# Mobile Test-Code Generator (all 5 GoTo apps)

**Stage output:** QA's output at the **Code Generation** phase — automation generated from the
SDET_PLAN once the build exists. Default output is **TapMind NLP** (per config); GMT coded is
produced where NLP can't express the case.

**Two things per scenario acted on:** (1) the runnable test file, and (2) an entry in
`test-code-generator.json` (the ledger of what was generated).

## Config
`config/<app>.json` → `default_output` (NLP), `repos.gmt`/`tapmind`/`shared_libs`, `locator_keys`,
`platforms`, `deeplink_scheme`.

## Reads
- **The SDET plan** — the approved scenarios (keep each scenario `scenario_id`). **Source of assertions and primary NLP sequence.** *Filename:* match **`*sdet_plan.json`** — emitted feature-suffixed as `<feature_key>_sdet_plan.json` (e.g. `split_bill_gopay_groups_sdet_plan.json`); resolve by suffix (or by `feature_metadata.feature_key`), never a hardcoded `sdet_plan.json`. Key fields consumed:
  - `scenario_list[].automation_steps[]` — **primary NLP source.** Pre-built interleaved action+verify sequence in TapMind dialect (emitted by sdet-plan-generator). Wrap each line with `runStep(...)`/`assertStep(...)` and bind real locators from `change_context` — do NOT re-derive the sequence from `steps[]`.
  - `scenario_list[].test_data[]` — structured fixtures (`fixture_id`, `entity`, `required_state`, `dynamic_conditions`, `provision`, `sensitive`). Pass to TDP for provisioning; never bind raw values inline.
  - `scenario_list[].browserstack_case_id` — present on SDET plan scenarios post-SYNC; use directly for `@TestInfo` instead of creating a new BS case when already set.
  - `coverage_categories.auto_selected[]` + `scenario_list[].source` — filter: generate for `source: input_derived` and `source: fe_baseline`; for `source: qa_added` generate only when `automatable: true`.
- `change_context.json` — **real per-platform locators** (android + ios), API shapes, routes, flags (post-build). **How to interact only.**
- `design_context.json` — screens/flows for navigation (when present).
- **Grounding = the GMT coded repo** (page objects, base classes, existing tests) via retrieval — where the real navigation & element knowledge lives; the TapMind repo alone is too thin to ground on.
- Test data via the **test-data-provisioner** (resolves each `test_data[]` fixture → handle):
  - `provision: "lease"` → request an existing entity from TDP's pool.
  - `provision: "construct"` → TDP builds the entity to spec.
  - `provision: "synthetic"` → always synthetic; mandatory when `sensitive: true` (KYC/PII/card state).
  - `provision: "override"` → inject a state override on top of a leased entity.
  - `dynamic_conditions[]` (TEMPORAL/RELATIONAL/SELECTION) → pass as selection constraints to TDP; these cannot be expressed as static `required_state` predicates.

## Model
Fast tier — **Composer 2.5** default; Sonnet for complex flows; escalate to Opus only on repeated failure.

## Select scenarios
Generate only where `automatable: true` **and** `is_legacy_regression: false` (new scenarios). Legacy
scenarios are **updated**, not regenerated (see Dedup). Route by `target_execution_framework`:
`TAPMIND_NLP` → invoke `aep-tapmind:nlp-codegen` (asks kb-only vs reuse-pioneer vs
one device pioneer, then writes `tapmind-mobile-tests`); `GMT_JAVA` → coded tests in this skill.

## Given strategy (the "Given" — Pillar 3 fallback hierarchy)
1. **Deep link** from the plan's `preconditions_metadata.target_entry_deeplink` — jump straight to the screen.
2. **API state injection** (via TDP) *then* deep link — if the screen needs state (items in cart, etc.).
3. **Reusable nav macro** — if no deep link; search the GMT/TapMind repo for a stable macro.
   Never generate raw home-screen tap-walks. No deep link **and** no macro → defer (see below).

## Process (per selected scenario)
**If routed `TAPMIND_NLP`:** invoke `aep-tapmind:nlp-codegen` and stop — do not wrap
`automation_steps` here. Remaining steps apply to `GMT_JAVA` only.

1. **Given:** resolve via the hierarchy above; record `given_strategy` + `deep_link`/`nav_macro_fallback`.
2. **Setup:** emit `mock_location` + `backdoor_login` (TDP user) via the house-style helpers.
3. **Elements:** bind element labels from `automation_steps[]` → real locators from `change_context` (android=resource-id, ios=accessibilityId, flutter=Key/Semantics). Never hard-code inline locators.
4. **NLP (primary):** read `scenario_list[].automation_steps[]` from the SDET plan — this is the pre-built interleaved sequence. Wrap each action line with `runStep(...)` and each verify line with `assertStep(...)`. Substitute TapMind helper calls verbatim (`openDeeplink(...)`, `loginToDriver(...)`, `setDriverToggle(...)`). When `automation_steps` is empty (`[]`), defer the scenario with reason `NO_NLP_STEPS`.
5. **GMT coded (where routed):** Appium+TestNG Java using the bound locators from step 3, real `Assert`, teardown.
6. **Assertions:** sourced **strictly from `automation_steps[]` verify lines and `sdet_plan.clickstream_events[]`** (`assertions_from: sdet_plan:<scenario_id>`) — never from the diff (Bias Guardrail). Turn `clickstream_events[]` into `analytics_assertions`.
7. **Test data:** pass each `test_data[]` fixture (by `fixture_id`) to TDP with `provision`/`dynamic_conditions`/`sensitive` signals; record each resolved handle as an entry in `data_bindings[]` (`fixture_id`, `status`, `provider`, `fixture_ref`, `provision_via`). Never raw values.
8. **Traceability:** stamp with `@TestInfo(suiteId, testCaseId)`. ID chain: `requirement_ref → browserstack_case_id` (from scenario) → `browserstack_suite_id`. **If `browserstack_case_id` already exists on the scenario (stamped during SDET plan SYNC), use it directly — do NOT create a new BS case.** Only create a new BS case when the field is absent.
9. **Waits/teardown:** dynamic waits only (static sleeps banned); teardown block mandatory.
10. **Dedup/update:** if a flow changed (from `change_context` + `regression_context`), **UPDATE** the existing test in place (`op: UPDATE`); only genuinely new scenarios `CREATE`; already-covered legacy → `SKIP`.

## Defer, don't guess
Do **not** emit a broken test. Add the scenario to `deferred[]` with a reason when:
- **PARTIAL_READINESS** — the scenario's screens/tasks aren't all Ready-for-QA yet.
- **UNMAPPED_DATA_NEED** — the provisioner returned `status: UNMAPPED`.
- **NO_LOCATOR** — a required element has no locator in `change_context`.
- **NO_NAV_ROUTE** — Pillar 4 hierarchy exhausted (no deep link, no macro).

## Produces
1. **The test file** — TapMind NLP (`.java` with `runStep`/`assertStep`) or GMT coded, at `artifact_ref`.
2. **`test-code-generator.json`** (→ `schemas/test-code-generator.schema.json`) — one entry per scenario
   acted on: `op`, `target`, `class_name`/`test_method`, `artifact_ref`, `traceability`, `setup`,
   `given_strategy`, `nl_steps`, `assertions_from`, `analytics_assertions`, `locators_used`,
   `data_bindings[]`, `flags_required`, `waits`, `teardown`, `validation` — plus `deferred[]` and a
   `summary` (created/updated/skipped_legacy/deferred/unmapped_data_need/validated_on_device/needs_review/no_nlp_steps).

## Validated by construction (when a device is available)
`TAPMIND_NLP` validation is owned by `nlp-codegen`: QA chooses kb-only (`generated`),
reuse-pioneer, or one device pioneer per similar-flow cluster (`cloned_from_pioneer` /
`validated_on_device`). Do not drive every NLP case on a device from this skill. GMT coded
stays `mode: "generated"` unless a device run is explicitly requested.

## Self-heal (Phase B)
Wrapped in the self-heal loop: generate → run on device farm → observe → fix (locators/waits) → retry.
Fixes only its own broken steps + known flakiness; a **genuine failure is reported as a bug, never
retried into green**; assertions are never weakened. A test that can't be safely healed →
`validation.result: NEEDS_REVIEW` (shipping blocked until a human reviews).

## Guardrails
- Never hard-code credentials/tokens/PII — resolve from vault/TestBuddy; mask in logs.
- Non-deterministic values (fare/ETA/surge) use matchers/tolerances, not exact equality.
- Output the manifest as valid JSON conforming to `schemas/test-code-generator.schema.json`.
