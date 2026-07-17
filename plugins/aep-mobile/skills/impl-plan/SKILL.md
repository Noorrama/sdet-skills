---
name: mobile-impl-plan-extractor
description: Normalize the Implementation PLAN.md/Jira for a mobile change into plan_context.json — the PRIMARY DRIVER of the SDET_PLAN. Captures screens/view-models touched, new components, flag keys, and (critically) the test hooks (deeplink / flag-override / state-injection) that let the NLP steps reach a screen without a full UI walk. App-agnostic.
---

# Mobile Impl. Planning Extractor — PRIMARY DRIVER (all 5 GoTo apps)

The primary driver for the SDET_PLAN. It also supplies the **test hooks** the navigation layer
relies on (deeplinks / state-injection), so the automation can jump to the target screen instead
of walking the whole UI — the biggest reliability/token win for mobile.

## Config
`config/<app>.json` → `deeplink_scheme`; set `plan_context.app = app_id`.

## Reads
PLAN.md (repo/MR) or the Jira ticket for the change.

## Model
Fast tier — Composer 2.5. Escalate to reasoning if the plan is complex; scenario quality depends on this.

## Extract (→ plan_context.schema.json)
1. **change_summary**; **screens_touched** (screen_ids); **view_models**; **new_components**.
2. **flag_keys** (+ defaults).
3. **test_hooks** — each with `type` (deeplink / flag-override / state-injection), `target`
   (screen_id/element_id) and `invoke` (the deeplink URI / how to set the flag / how to inject state).
4. **observable_states** — success/failure signal per P0 flow.
5. **testability_gaps** — any P0 behaviour with no hook/observable state (highest-value feedback).
6. **sequencing**.

## Definition of Ready — reject/flag if
A P0 flow has no observable state, no hook/deeplink, or unlisted flags → add to `testability_gaps`.

## Guardrails
Be precise; don't invent hooks/modules. Output valid JSON only, conforming to `schemas/plan_context.schema.json`.
