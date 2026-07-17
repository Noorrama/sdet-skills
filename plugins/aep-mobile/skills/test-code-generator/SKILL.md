---
name: mobile-test-code-generator
description: The Code-Generation-phase QA output. From the approved SDET_PLAN + post-build change_context, generates mobile automation — TapMind NLP steps (primary) and GMT (Appium+TestNG Java) coded tests (where needed) — for both Android & iOS, wired to test data. App-agnostic; grounds on the GMT coded repo. In Phase B this becomes the self-healing Frontend Test-Code-Gen agent.
---

# Mobile Test-Code Generator (all 5 GoTo apps)

**Stage output:** QA's output at the **Code Generation** phase — automation generated from the
SDET_PLAN once the build exists. Default output is **TapMind NLP** (per config); GMT coded is
produced where NLP can't express the case.

## Config
`config/<app>.json` → `default_output` (NLP), `repos.gmt`/`tapmind`/`shared_libs`, `locator_keys`,
`platforms`, `deeplink_scheme`.

## Reads
- `sdet_plan.json` — the approved scenarios (keep each scenario `id`).
- `change_context.json` — **real per-platform locators** (android + ios), API shapes, routes (post-build).
- `design_context.json` — screens/flows for navigation.
- **Grounding = the GMT coded repo** (page objects, base classes, existing tests) via retrieval — used for BOTH NLP and coded output (it is where the real navigation & element knowledge lives; the TapMind repo alone is too thin to ground on).
- Test data via the **test-data-provisioner** (resolves each `data_needs` → handle).

## Model
Fast tier — **Composer 2.5** default; Sonnet for complex flows; escalate to Opus only on repeated failure.

## Process
For each `automatable` scenario:
1. **Navigation:** use the scenario's `navigation` — `deeplink` (from the PLAN hook) to reach `screen_id`, else walk the `flow` path. Reuse existing navigation macros / page-object nav rather than re-deriving.
2. **Elements:** resolve each `element_id` → real locator from `change_context` (`android_locator` = resource-id, `ios_locator` = accessibilityId). Never hard-code inline locators.
3. **NLP (primary):** emit TapMind steps for the scenario (label/element_role-based; steps in the app's `tapmind` repo). *(Align the step grammar to your actual TapMind syntax — see the sample in examples/.)*
4. **GMT coded (where target_framework=GMT or NLP can't express it):** emit an Appium+TestNG Java test into the GMT project, reusing existing page objects/base classes; tag with scenario `id`/`requirement_ref`/`priority`.
5. **Both platforms:** parameterise the locator by platform from `change_context`; run on `config.device_matrix`.
6. **Test data:** bind each `data_needs` to the provisioner's handle (never raw values).
7. **Dedup/update:** if a flow changed (from `change_context` + dedup), UPDATE the existing test/step in place; only genuinely new scenarios create new tests.

## Self-heal (Phase B)
Wrapped in the self-heal loop: generate → run on device farm → observe → fix (locators/waits) → retry.
Self-heal fixes only its own broken steps + known flakiness; a **genuine failure is reported as a bug, never retried into green**; assertions are never weakened. (Precondition for reliable NLP self-heal: TapMind must expose step-level diagnostics + grounding.)

## Guardrails
- Never hard-code credentials/tokens/PII — resolve from vault/TestBuddy; mask in logs.
- Non-deterministic values (fare/ETA/surge) use matchers/tolerances, not exact equality.
