---
name: mobile-sdet-plan-generator
description: The Impl. Planning-phase QA output. Generates the SDET_PLAN — risk-based, requirement-traced mobile test scenarios with navigation and data_needs — from the four pre-build contexts (PLAN is the primary driver) + existing tests. App-agnostic; produces sdet_plan.json (scenario schema) + testability_feedback. Entry point of the pipeline; runs pre-build, in parallel with implementation.
---

# Mobile SDET_PLAN & Scenario Generator (all 5 GoTo apps)

**Stage output:** QA's output at the **Impl. Planning** phase — the SDET_PLAN with scenarios,
produced pre-build (parallel to implementation). Its scenarios drive the Code-Generation phase.

## Config
`config/<app>.json` → `default_output` (NLP), `deeplink_scheme`, `repos.gmt`/`shared_libs` (for dedup retrieval). Set `scenario.app = app_id`.

## Reads (contract)
- `plan_context.json` — **PRIMARY DRIVER** (change surface, test hooks, flags, observable states).
- `prd_context.json` — requirements + acceptance + `data_signals` to trace to.
- `design_context.json` — screens, element_ids, states, flows (navigation source).
- `rfc_context.json` — risk/flags/N-1 (optional).
- Existing GMT/NLP tests via retrieval from `repos.gmt` — for dedup & reuse.

## Model
Reasoning tier — **Opus / GPT 5.5**. Accuracy-critical, ~1 run/EPIC.

## Process (→ scenario.schema.json)
1. Take the change surface from `plan_context` (primary); generate scenarios reachable from it + PRD acceptance.
2. Expand across `happy / edge / negative / contract / nfr` + **mobile extras**: offline/poor-network, permission states, deep-link/navigation, feature-flag on/off, non-deterministic values (fare/ETA/surge).
3. **Navigation per scenario:** prefer a `plan_context` **test hook** (`method:deeplink`, `hook_id`) to reach `screen_id`; else `method:flow` with the `path` from `design_context.flows`. (Prefer deeplink/state-injection over a full UI walk.)
4. **data_needs per scenario:** derive from `prd_context.data_signals` + rule boundaries; each with `provision` (lease/construct/synthetic/override), `sensitive`, `testbuddy_hint`, `source_ref`. (See test-data-provisioner.)
5. Annotate: `requirement_ref`, `priority` (payments/wallet/auth = P0), `type`, `target_platforms` (default both), `target_framework` = **NLP** (default from config; GMT where NLP can't express it).
6. **Coverage gates:** every P0 requirement → ≥1 scenario; **every `data_signal` → ≥1 scenario** (else flag the gap). Dedup against existing tests.
7. Emit `testability_feedback` from `plan_context.testability_gaps` + `design_context.missing_ids`.

## Guardrails
- PLAN is the primary driver; don't test surface not in plan/PRD. Unknown surface → scenario with assumption noted, `automatable:false`.
- Output valid JSON only, conforming to `schemas/scenario.schema.json`.
