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
resolved becomes an `extraction_notes` entry and the run continues — a partial, honestly
labelled output is always better than no output. What is forbidden is inventing a value to
fill the hole.

1. **App id.** One of `gojek-consumer`, `gojek-driver`, `gofood-merchant`, `gopay-consumer`,
   `gopay-merchant`. Not resolvable → leave `app` absent, add a `NEEDS_ANSWER` note on `app`.
2. **Config** — `${CLAUDE_PLUGIN_ROOT}/config/<app>.json`. Unreadable → add a `WORTH_CHECKING` note on
   `ENVIRONMENT` with reason *"cannot read ${CLAUDE_PLUGIN_ROOT}/config/<app>.json — plugin install
   may be incomplete"* and action *"run `claude plugin update aep-mobile@aep`, restart Claude,
   re-run"*. Set `extraction_status: LIMITED`. Continue. `deeplink_scheme` comes from this file only — if unreadable, leave hook `invoke` values absent with a `WORTH_CHECKING` note rather than assuming a scheme from the app name.
3. **Schema** — `${CLAUDE_PLUGIN_ROOT}/schemas/plan_context.schema.json`. Unreadable → `WORTH_CHECKING` note on `ENVIRONMENT`, same install action.
   Fall back to the field list in this document **only** in that case, and say so in the note.
4. **Input.** PLAN.md / Jira content present and readable. Absent → emit with `PARTIAL` and a `NEEDS_ANSWER` note.

## Notes on what the document didn't say — required on every run
Every output carries two fields. They are a to-do list for the document's author, **not** a
verdict on your work — a doc still being written will always produce some, and that is the
normal, expected result.

- `extraction_status`
  - `COMPLETE` — everything the document specified was captured.
  - `PARTIAL` — the document didn't specify some things; they're listed below. Normal for a
    work-in-progress doc.
  - `LIMITED` — a config file, schema or the validator wasn't available, so part of the run had
    less grounding than usual.
- `extraction_notes[]` — `{ field, reason, action, follow_up }`, where `follow_up` is:
  - `NEEDS_ANSWER` — someone has to supply this before the tests can cover it.
  - `WORTH_CHECKING` — a value was produced, but without its usual reference source. Confirm it.
  - `FYI` — optional content the document simply doesn't have. No action needed.

Rules:
- A field you cannot resolve is **left empty** and noted. Never filled with a placeholder, a
  plausible default, or a value carried over from another feature.
- `reason` says what you checked and what was there (*"PRD section 4.2 states the rule but names
  no module"*), not a bare *"not found"*.
- `action` is the concrete next step (*"confirm the target module with the PM"*), so the note can
  be acted on without re-reading the doc.
- Staying silent is the failure being designed out here. An empty `extraction_notes` on a
  half-written document is a worse outcome than a field left empty and explained.
## Matching the source document — normalise, don't invent
Source docs are human-written. Labels and values vary; the schema does not. Reading a value that
**is** in the document and expressing it in the schema's vocabulary is normalisation, and it is
required. Supplying a value the document does not contain is invention, and it is forbidden.
Do not confuse the two — refusing to normalise is not caution, it is a false open-point report.

**Field labels — match by meaning, not by key name.** Schema keys are output names, never strings
to search for. Look for the concept, whatever the doc calls it. `Deeplink` / `Deep link` / `URI` /
`Route` all describe a `deeplink` test hook; `Feature flag` / `Litmus key` / `Experiment` all feed
`flag_keys`.

**Enum values — match case-insensitively, emit the canonical spelling.** Compare the document's
value to the schema's allowed values ignoring:
- letter case — `DRAFT`, `draft`, `Draft` all → `"Draft"`
- surrounding whitespace, and any trailing punctuation or checkbox glyph (`☑ DRAFT` → `"Draft"`)
- separator style — `state injection`, `state_injection`, `State-Injection` → `"state-injection"`

Emit the schema's exact spelling, never the document's. This applies to **every** enum in the
schema, not just the ones named here.

**Synonyms — allowed when unambiguous, recorded when used.** `In Progress` → `"In Review"` is a
fair mapping; make it, and add an `FYI` note noting the source value so the mapping is auditable.
A pure case or whitespace fix needs no note — it is not a judgement call.

**When nothing matches, say what you found.** If no allowed value fits even case-insensitively,
leave the field absent and make the note specific — quote the document's value and list the legal
ones: *"header reads `PRD WALKTHROUGH`; not a legal value (allowed: …)"*. Never report it as
*"not found"* — the field was found, its value could not be expressed, and those send the reader
to different places. Never pick the nearest-looking value to dodge the note.

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
- Passes → `extraction_status: COMPLETE` (when `extraction_notes` is empty).
- Fails → **still write the file.** Convert every validator error into an `extraction_notes`
  entry (`field` = the validator's JSON path, `follow_up: NEEDS_ANSWER`) and set
  `extraction_status: PARTIAL`. Never patch a value in just to make validation pass.
- Validator unavailable (`jsonschema` not installed) → write the file, add a `WORTH_CHECKING` note on
  `ENVIRONMENT`, **and say so in your reply to the user** — not only in the JSON, which they may
  not open. Give them the command for their platform:
  - macOS / Linux with a system Python: `pip3 install --break-system-packages jsonschema`
    (plain `pip3 install` fails with an *externally-managed-environment* error under PEP 668)
  - inside a virtualenv, or with `uv`: `pip install jsonschema` / `uv pip install jsonschema`
  Never report an unvalidated output as valid — well-formed JSON is not schema conformance.
  Do not attempt the install yourself; it is the user's environment to change.
