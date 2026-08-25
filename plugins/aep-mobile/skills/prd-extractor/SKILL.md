---
name: mobile-prd-extractor
description: Extract structured PRD context for mobile QA into prd_context.json. Maps PRD requirements, module namespaces, business requirements, boundary conditions, rollout guidance, and feature flags to the schema used by the mobile QA pipeline.
---

# Mobile PRD Extractor (all 5 GoTo apps)

Convert PRD text into a schema-compliant `prd_context.json` for mobile QA. The extractor normalises explicit requirements and surfaces any missing or ambiguous information.

## Preflight — resolve, or record and continue
**Never stop, never guess.** Work through these before extracting. Anything that cannot be
resolved becomes an `extraction_notes` entry and the run continues — a partial, honestly
labelled output is always better than no output. What is forbidden is inventing a value to
fill the hole.

1. **App set — how many apps does this PRD cover?** Never assume one. Read the whole document
   first and collect every app in scope from: sibling sections named per app (`4.1 Gopay`,
   `4.2 Gojek`), the title, an explicit scope/platform table, or the user naming them. Map each
   to an app id: `gojek-consumer`, `gojek-driver`, `gofood-merchant`, `gopay-consumer`,
   `gopay-merchant`.
   - **One app** → one output file, as before.
   - **Two or more** → one output file per app (see *Output files*). This is common for shared
     SDK / platform-component PRDs.
   - **None resolvable** → emit a single file with `app` absent and a `NEEDS_ANSWER` note on `app`.
   Report the decision in your reply before extracting: *"2 apps detected — gopay-consumer
   (§4.1), gojek-consumer (§4.2). Writing 2 context files."*
2. **Config, per app in the set** — `config/<app>.json`. Each output file's
   `app` comes from its own config's `app_id`; never copy one app's config onto another's file.
   Unreadable → add a `WORTH_CHECKING` note on `ENVIRONMENT` with reason *"cannot read
   config/<app>.json — plugin install may be incomplete"* and action *"reinstall/update the
   aep-mobile plugin and restart your editor, then re-run"*. Set
   `extraction_status: LIMITED`. Continue; without it `app` stays absent with a `NEEDS_ANSWER` note.
3. **Schema** — `schemas/prd_context.schema.json`. Unreadable → `WORTH_CHECKING` note on `ENVIRONMENT`, same install action.
   Fall back to the field list in this document **only** in that case, and say so in the note.
4. **Input.** PRD attached and readable. Empty or unparsed → emit the file with `extraction_status: PARTIAL` and one `NEEDS_ANSWER` note saying the source could not be read. Do not emit an extraction with zero requirements as though the PRD had none.

## Output files — one per app in scope
| Apps in scope | Files written |
| :--- | :--- |
| 1 | `prd_context.json` |
| 2+ | `prd_context.<app_id>.json` for each — e.g. `prd_context.gopay-consumer.json`, `prd_context.gojek-consumer.json` |

Each file is a complete, independently valid `prd_context` with a **single** `app`. The schema is
unchanged; nothing downstream needs to know a split happened.

**What goes in each file:**
- Requirements from that app's own sections only. A Gojek-only surface never appears in the
  GoPay file.
- **Plus** the document-level sections that apply to every app — context, problem statement,
  success metrics, the shared SDK/component contract. Both files need these; a plan generated
  without them is missing the actual subject of the PRD.

**Marking shared requirements:** give a requirement that applies to every app the **same
`req_id` in every file** (e.g. `SDK-01`). App-specific requirements get an app-scoped id
(`GOPAY-04`, `GOJEK-04`). A `req_id` appearing in more than one file is therefore shared by
definition — which is all the QA needs to dedup when they review both plans, and it costs no
schema change.

**Per-app divergence is a requirement, not a footnote.** When the PRD says a rule differs by app
(*"disable state is only for gopay as we have limit there; in gojek we don't have limit"*), each
file records only its own app's behaviour. Never copy both variants into both files, and never
average them into one rule.

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
to search for. Look for the concept, whatever the doc calls it. A section headed `Requirements`,
`Business Requirements`, `User Stories` or `Scope` all feed `business_requirements`; `Edge Cases`
/ `Boundary Conditions` / `Validations` all feed `boundary_conditions`; `Owning Team`, `Squad` or
`Pod` all feed `team_name` on the requirement they scope.

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
PRD text (Lark/Confluence)

## Model
Fast tier — Haiku / Composer 2.5. Escalate to a higher reasoning model only if the PRD is long or ambiguous.

## Output schema (→ prd_context.schema.json)
The output must conform to `schemas/prd_context.schema.json`. The list below
is a reading aid, not the contract — validate against the file.

- `app` (string, from config)
- `feature_key` (string)
- `module_namespace` (array of strings)
- `business_requirements` (array)

### `business_requirements`
Each item must include:
- `req_id` (string)
- `target_module` (string)
- `user_story` (string)

Optional fields for each business requirement:
- `milestone` (string)
- `team_name` (string) — when the PRD scopes requirements by owning team (e.g. sections or a
  table naming the team responsible for each requirement or a
  per-team breakdown), record that team against each requirement it belongs to. Read for meaning,
  not by key name — "Owning team", "Squad", "Pod" all feed this field. If the PRD gives no
  team-wise scope, omit the key; do not invent a team from the app or module name.
- `context_screen` (string)
- `expected_ui_copy` (array of objects with `screen` and `ui_copy`)
- `target_personas` (array of objects with `type` and optional `prerequisites`)

### Optional root fields
- `boundary_conditions` (array of objects with `req_id`, `edge_case_description`, `proposed_default`)
- `applicable_countries` (array of strings)
- `applicable_platforms` (array of strings)
- `applicable_service_types` (array of strings)
- `out_of_scope_module` (array of strings)
- `rollout_plan` (object with `user_segment` and `timeline`)
- `feature_flags` (array of strings)

## Guardrails
- **Never invent a value.** Not for a field you expect to exist, not to make the output look
  complete, not as a "reasonable default".
- Absent **optional** content in the PRD → omit the key. That is a correct extraction, not a
  failure.
- Absent **required** content that cannot be read from the PRD → leave the field absent and add
  a `NEEDS_ANSWER` note naming it and the PRD section you checked. Emit the file anyway.
- Do not add fields the schema disallows.
- Output valid JSON only.
- **Never merge two apps into one file.** A `prd_context` carries exactly one `app`. If the PRD
  covers several, write several files — do not pick the app with the most sections and drop the
  rest, and do not concatenate their requirements under one `app`.

## Validate — report, never block
Run once **per output file** — every file in a multi-app split is validated separately.
```
python3 -c "import json,jsonschema; jsonschema.validate(
  json.load(open('<each prd_context file>')),
  json.load(open('schemas/prd_context.schema.json')))"
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
