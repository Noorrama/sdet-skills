---
name: mobile-impl-plan-extractor
description: Normalize the Implementation PLAN.md/Jira for a mobile change into plan_context.json — the PRIMARY DRIVER of the SDET_PLAN. Captures screens/view-models touched, new components, flag keys, and (critically) the test hooks (deeplink / flag-override / state-injection) that let the NLP steps reach a screen without a full UI walk. App-agnostic.
---

# Mobile Impl. Planning Extractor — PRIMARY DRIVER (all 5 GoTo apps)

The primary driver for the SDET_PLAN. It also supplies the **test hooks** the navigation layer
relies on (deeplinks / state-injection), so the automation can jump to the target screen instead
of walking the whole UI — the biggest reliability/token win for mobile.

## Config
`${CLAUDE_PLUGIN_ROOT}/config/<app>.json` → `deeplink_scheme`; set `plan_context.app = app_id`.

## Preflight — resolve, or record and continue
**Never stop, never guess.** Work through these before extracting. Anything that cannot be
resolved becomes an `extraction_gaps` entry and the run continues — a partial, honestly
labelled output is always better than no output. What is forbidden is inventing a value to
fill the hole.

1. **App id.** One of `gojek-consumer`, `gojek-driver`, `gofood-merchant`, `gopay-consumer`,
   `gopay-merchant`. Not resolvable → leave `app` absent, add a `BLOCKING` gap on `app`.
2. **Config** — `${CLAUDE_PLUGIN_ROOT}/config/<app>.json`. Unreadable → add a `DEGRADED` gap on
   `ENVIRONMENT` with reason *"cannot read ${CLAUDE_PLUGIN_ROOT}/config/<app>.json — plugin install
   may be incomplete"* and action *"run `claude plugin update aep-mobile@aep`, restart Claude,
   re-run"*. Set `extraction_status: DEGRADED`. Continue. `deeplink_scheme` comes from this file only — if unreadable, leave hook `invoke` values absent with a `DEGRADED` gap rather than assuming a scheme from the app name.
3. **Schema** — `${CLAUDE_PLUGIN_ROOT}/schemas/plan_context.schema.json`. Unreadable → `DEGRADED` gap on `ENVIRONMENT`, same install action.
   Fall back to the field list in this document **only** in that case, and say so in the gap.
4. **Input.** PLAN.md / Jira content present and readable. Absent → emit with `INCOMPLETE` and a `BLOCKING` gap.

## Reporting gaps — required on every run
Every output carries both fields (see the schema):

- `extraction_status` — `OK` only when `extraction_gaps` is empty. `INCOMPLETE` when a field
  could not be resolved from the source. `DEGRADED` when config/schema/tooling was unavailable.
- `extraction_gaps[]` — `{ field, reason, action, severity }`, severity one of `BLOCKING`
  (schema-required field absent), `DEGRADED` (resolved without normal grounding), `INFO`
  (optional content genuinely absent from the source doc).

Rules:
- A field you cannot resolve is **left absent** and recorded. Never filled with a placeholder,
  a plausible default, or a value carried over from another feature.
- `reason` cites the section actually checked (*"PRD §4.2 states the rule but names no
  module"*), not a generic *"not found"*.
- Silence is the failure mode being designed out here — an empty `extraction_gaps` on a
  half-specified source document is a worse bug than a malformed field.

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
Be precise. **Never invent a hook, deeplink, module or flag key** — a fabricated deeplink is
worse than a missing one, because downstream scenarios build on it and fail at run time with a
misleading error. A P0 flow with no hook goes to `testability_gaps`; that is the single most
valuable thing this skill produces.

Output valid JSON only, conforming to `${CLAUDE_PLUGIN_ROOT}/schemas/plan_context.schema.json`.

## Validate — report, never block
```
python3 -c "import json,jsonschema; jsonschema.validate(
  json.load(open('plan_context.json')),
  json.load(open('${CLAUDE_PLUGIN_ROOT}/schemas/plan_context.schema.json')))"
```
- Passes → `extraction_status: OK` (when `extraction_gaps` is empty).
- Fails → **still write the file.** Convert every validator error into an `extraction_gaps`
  entry (`field` = the validator's JSON path, `severity: BLOCKING`) and set
  `extraction_status: INCOMPLETE`. Never patch a value in just to make validation pass.
- Validator unavailable (`jsonschema` not installed) → write the file, add a `DEGRADED` gap on
  `ENVIRONMENT`, **and say so in your reply to the user** — not only in the JSON, which they may
  not open. Give them the command for their platform:
  - macOS / Linux with a system Python: `pip3 install --break-system-packages jsonschema`
    (plain `pip3 install` fails with an *externally-managed-environment* error under PEP 668)
  - inside a virtualenv, or with `uv`: `pip install jsonschema` / `uv pip install jsonschema`
  Never report an unvalidated output as valid — well-formed JSON is not schema conformance.
  Do not attempt the install yourself; it is the user's environment to change.
