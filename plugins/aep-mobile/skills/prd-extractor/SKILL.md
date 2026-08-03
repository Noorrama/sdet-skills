---
name: mobile-prd-extractor
description: Extract structured PRD context for mobile QA into prd_context.json. Maps PRD requirements, module namespaces, business requirements, boundary conditions, rollout guidance, and feature flags to the schema used by the mobile QA pipeline.
---

# Mobile PRD Extractor (all 5 GoTo apps)

Convert PRD text into a schema-compliant `prd_context.json` for mobile QA. The extractor normalises explicit requirements and surfaces any missing or ambiguous information.

## Preflight — resolve, or record and continue
**Never stop, never guess.** Work through these before extracting. Anything that cannot be
resolved becomes an `extraction_gaps` entry and the run continues — a partial, honestly
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
   - **None resolvable** → emit a single file with `app` absent and a `BLOCKING` gap on `app`.
   Report the decision in your reply before extracting: *"2 apps detected — gopay-consumer
   (§4.1), gojek-consumer (§4.2). Writing 2 context files."*
2. **Config, per app in the set** — `${CLAUDE_PLUGIN_ROOT}/config/<app>.json`. Each output file's
   `app` comes from its own config's `app_id`; never copy one app's config onto another's file.
   Unreadable → add a `DEGRADED` gap on `ENVIRONMENT` with reason *"cannot read
   ${CLAUDE_PLUGIN_ROOT}/config/<app>.json — plugin install may be incomplete"* and action *"run
   `claude plugin update aep-mobile@aep`, restart Claude, re-run"*. Set
   `extraction_status: DEGRADED`. Continue; without it `app` stays absent with a `BLOCKING` gap.
3. **Schema** — `${CLAUDE_PLUGIN_ROOT}/schemas/prd_context.schema.json`. Unreadable → `DEGRADED` gap on `ENVIRONMENT`, same install action.
   Fall back to the field list in this document **only** in that case, and say so in the gap.
4. **Input.** PRD attached and readable. Empty or unparsed → emit the file with `extraction_status: INCOMPLETE` and one `BLOCKING` gap saying the source could not be read. Do not emit an extraction with zero requirements as though the PRD had none.

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
PRD text (Lark/Confluence)

## Model
Fast tier — Haiku / Composer 2.5. Escalate to a higher reasoning model only if the PRD is long or ambiguous.

## Output schema (→ prd_context.schema.json)
The output must conform to `${CLAUDE_PLUGIN_ROOT}/schemas/prd_context.schema.json`. The list below
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
  a `BLOCKING` gap naming it and the PRD section you checked. Emit the file anyway.
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
  json.load(open('${CLAUDE_PLUGIN_ROOT}/schemas/prd_context.schema.json')))"
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
