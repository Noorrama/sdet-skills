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
- **The SDET plan** — the approved scenarios (keep each scenario `scenario_id`). **Source of assertions.** *Filename:* match **`*sdet_plan.json`** — emitted feature-suffixed as `<feature_key>_sdet_plan.json` (e.g. `split_bill_gopay_groups_sdet_plan.json`); resolve by suffix (or by `feature_metadata.feature_key`), never a hardcoded `sdet_plan.json`.
- `change_context.json` — **real per-platform locators** (android + ios), API shapes, routes, flags (post-build). **How to interact only.**
- `design_context.json` — screens/flows for navigation (when present).
- **Grounding = the GMT coded repo** (page objects, base classes, existing tests) via retrieval — where the real navigation & element knowledge lives; the TapMind repo alone is too thin to ground on.
- Test data via the **test-data-provisioner** (resolves each `test_data_tags` → handle).

## Model
Fast tier — **Composer 2.5** default; Sonnet for complex flows; escalate to Opus only on repeated failure.

## Select scenarios
Generate only where `automatable: true` **and** `is_legacy_regression: false` (new scenarios). Legacy
scenarios are **updated**, not regenerated (see Dedup). Route by `target_execution_framework`
(`TAPMIND_NLP` → NLP; `GMT_JAVA` → coded).

## Given strategy (the "Given" — Pillar 4 fallback hierarchy)
1. **Deep link** from the plan's `target_entry_deeplink` — jump straight to the screen.
2. **API state injection** (via TDP) *then* deep link — if the screen needs state (items in cart, etc.).
3. **Reusable nav macro** — if no deep link; search the GMT/TapMind repo for a stable macro.
   Never generate raw home-screen tap-walks. No deep link **and** no macro → defer (see below).

## Process (per selected scenario)
1. **Given:** resolve via the hierarchy above; record `given_strategy` + `deep_link`/`nav_macro_fallback`.
2. **Setup:** emit `mock_location` + `backdoor_login` (TDP user) via the house-style helpers.
3. **Elements:** resolve each `element_id` → real locator from `change_context` (android=resource-id, ios=accessibilityId, flutter=Key/Semantics). Never hard-code inline locators.
4. **NLP (primary):** emit TapMind `runStep(...)` for interactions ending in `assertStep(...)`. Align grammar to the app's TapMind syntax (see `examples/`).
5. **GMT coded (where routed):** Appium+TestNG Java using the bound locators, real `Assert`, teardown.
6. **Assertions:** derive the "Then" **strictly from `sdet_plan`** (`assertions_from: sdet_plan:<scenario_id>`) — never from the diff (Bias Guardrail). Turn the plan's `clickstream_events` into `analytics_assertions`.
7. **Test data:** bind each need to the provisioner's handle (`data_binding`, never raw values).
8. **Traceability:** stamp the test with `@TestInfo(suiteId, testCaseId)` and record the ID chain
   (`requirement_id → story_id → jira_task_ids → browserstack_suite_id/testCaseId`). **Without the BS
   IDs the test runs but results never post back to BrowserStack.** For an `op: CREATE` with no BS
   case yet, create the BS case first and write the returned id into the annotation.
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
   `data_binding`, `flags_required`, `waits`, `teardown`, `validation` — plus `deferred[]` and a
   `summary` (created/updated/skipped_legacy/deferred/unmapped_data_need/validated_on_device/needs_review).

## Validated by construction (when a device is available)
Drive the emitted NLP on a real device (BrowserStack/emulator), keep only steps that PASS, and record
`validation: { mode: "validated_on_device", result, steps_validated, steps_repaired }`. Offline
generation sets `mode: "generated"` so consumers know it's unverified.

## Self-heal (Phase B)
Wrapped in the self-heal loop: generate → run on device farm → observe → fix (locators/waits) → retry.
Fixes only its own broken steps + known flakiness; a **genuine failure is reported as a bug, never
retried into green**; assertions are never weakened. A test that can't be safely healed →
`validation.result: NEEDS_REVIEW` (shipping blocked until a human reviews).

## Guardrails
- Never hard-code credentials/tokens/PII — resolve from vault/TestBuddy; mask in logs.
- Non-deterministic values (fare/ETA/surge) use matchers/tolerances, not exact equality.
- Output the manifest as valid JSON conforming to `schemas/test-code-generator.schema.json`.
